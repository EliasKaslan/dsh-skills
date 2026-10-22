<#
    sync-dsh-repos.ps1
    Deterministic sync of the DSH home config + the orchestrator preset bundle
    into the private GitHub / GitCode mirrors.

    ASCII ONLY (Windows PowerShell 5.1 decodes BOM-less .ps1 as GBK; a single
    non-ASCII byte can break parsing and make the whole script a no-op).
    No PS7 syntax: no ternary, no ??, no -AsByteStream, no utf8NoBOM.

    Secret handling (hard rule):
      * tokens are read from the token_file named in remotes.json;
      * a token value is NEVER printed, NEVER written to .git/config and
        NEVER written into any file inside the mirror repo;
      * every git output line goes through Get-RedactedText first;
      * the root cordis.patch.yml (plaintext PAT literal) is removed from the
        snapshot and replaced by a value-redacted copy, guarded by a re-scan;
      * every git call runs as "git -c credential.helper=" with
        GIT_TERMINAL_PROMPT=0 and a hard per-call timeout, so a scheduled run
        can never block on a credential prompt.

    Exit codes:
      0  success or nothing to do
      3  environment error (mirror repo, remotes.json, or git identity missing)
      4  upstream merge conflict
      5  snapshot failure (robocopy, commit, or the cordis redaction guard)
      6  push failure (including a git call that timed out)
      7  remote diverged (remote master not mergeable)
      8  unexpected exception
#>

param(
    [switch]$DryRun,
    [switch]$NoUpstream,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# NEVER let git open an interactive credential prompt. With credential.helper
# enabled (wincred) Git Credential Manager pops a GUI and hangs for minutes, so
# a scheduled run would hang instead of failing. GIT_ASKPASS is cleared to the
# empty string on purpose: setting it to a command fails with
#   error: cannot spawn cmd / c exit 1: No such file or directory
$env:GIT_TERMINAL_PROMPT = '0'
$env:GIT_ASKPASS = ''

# Every git invocation is run as:  git -c credential.helper= <args>
# (see Invoke-Git), so no credential helper is ever consulted.

# ------------------------------------------------------------------ constants

$DshHome     = 'C:\Users\admin\.dsh'
$Mirror      = 'D:\repos\deepseek-harness'
$Snap        = Join-Path $Mirror 'dsh-home'
$PresetSrc   = 'D:\workspace\agent\dsh_base\artifacts\presets\orchestrator-bundle'
$PresetDst   = Join-Path $Mirror 'dsh-presets\orchestrator-bundle'
# 2026-10-22: the legacy dsh_base tree was removed; the preset lane is now
# optional. When the source is absent the lane is skipped instead of failing
# the whole run with exit 5.
$PresetOn    = [bool](Test-Path -LiteralPath $PresetSrc)
$SyncDir     = Join-Path $Mirror 'sync'
$DryRoot     = Join-Path $env:TEMP 'dsh-repo-sync-dryrun'

$RemoteNames = @('github', 'gitcode')

$XdNames  = @('sessions', 'node_modules', '.git', '.pnpm-store', '.secrets', 'storages')
$XfNames  = @('*credentials*', '*.key', '*.pem', '*.token', '.credentials.yaml', '*.zstd')
$XdPreset = @('node_modules', '.git')
$XfPreset = @()

$GitignoreLines = @('sync/logs/', 'sync/state.json', 'sync/ALERT.md', 'sync/.lock')

$Script:Secrets    = @()
$Script:ExitCode   = 0
$Script:Reason     = ''
$Script:Results    = @{}
$Script:Changed    = $false
$Script:LocalHead  = ''
$Script:UpHead     = ''
$Script:SnapFiles  = 0
$Script:SnapBytes  = 0
$Script:PrsFiles   = 0
$Script:PrsBytes   = 0
$Script:ExcEntries = 0
$Script:ExcDirs    = 0
$Script:ExcFiles   = 0
$Script:ExcBytes   = 0
$Script:PrsExc     = 0
$Script:LogPath    = ''
$Script:StatePath  = ''
$Script:AlertPath  = ''
$Script:RunSyncDir = ''
$Script:IsDry      = $false
$Script:StartedUtc = [datetime]::UtcNow

foreach ($n in $RemoteNames) { $Script:Results[$n] = @{ ok = $false; pushed_sha = ''; error = '' } }

# ------------------------------------------------------------------- helpers

function Get-RedactedText {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $out = $Text
    foreach ($s in $Script:Secrets) {
        if ($s -and $s.Length -ge 6) { $out = $out.Replace($s, '<redacted>') }
    }
    $out = [regex]::Replace($out, '://[^/@\s]+@', '://<redacted>@')
    return $out
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        $null = New-Item -ItemType Directory -Path $dir -Force
    }
    $enc = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

function Write-LogLine {
    param([string]$Message)
    $line = Get-RedactedText $Message
    Write-Host $line
    if ($Script:LogPath) {
        $dir = Split-Path -Parent $Script:LogPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) {
            $null = New-Item -ItemType Directory -Path $dir -Force -ErrorAction SilentlyContinue
        }
        try {
            $enc = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
            [System.IO.File]::AppendAllText($Script:LogPath, $line + "`r`n", $enc)
        } catch {
            # logging must never mask the real result
        }
    }
}

function Get-PropValue {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Get-QuotedArg {
    param([string]$Value)
    if ($Value -match '[\s"]') {
        $esc = $Value.Replace('"', '\"')
        return '"' + $esc + '"'
    }
    return $Value
}

function Get-SumBytes {
    param($Items)
    $total = [int64]0
    if ($null -eq $Items) { return $total }
    foreach ($i in $Items) { $total += [int64]$i.Length }
    return $total
}

function Get-TreeStats {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return @{ Files = 0; Bytes = [int64]0 } }
    $fs = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue)
    return @{ Files = [int]$fs.Count; Bytes = (Get-SumBytes $fs) }
}

function Invoke-Git {
    param([string[]]$GitArgs, [int]$TimeoutSec = 120)
    # NOTE: do NOT use Start-Process here. Without -Wait, Start-Process never
    # populates ExitCode (measured: blank even after WaitForExit + Refresh),
    # which would silently turn every git failure into "rc=0". The raw
    # System.Diagnostics.Process path below returns the true exit code and
    # gives a hard timeout.
    $fullArgs = @('-c', 'credential.helper=') + $GitArgs
    $parts = @()
    foreach ($a in $fullArgs) { $parts += (Get-QuotedArg $a) }
    $line = ($parts -join ' ')
    $text = ''
    $code = 1
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'git'
    $psi.Arguments = $line
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        $null = $proc.Start()
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()
        $finished = $proc.WaitForExit($TimeoutSec * 1000)
        if (-not $finished) {
            $code = 124
            $text = 'TIMEOUT: git did not finish within ' + $TimeoutSec + 's; process tree killed'
            try { $null = & taskkill /F /T /PID $proc.Id 2>&1 } catch { }
            try { if (-not $proc.HasExited) { $proc.Kill() } } catch { }
            try { $null = $proc.WaitForExit(5000) } catch { }
        } else {
            $code = [int]$proc.ExitCode
            # Only await the readers on the normal path: after a kill a
            # surviving grandchild could hold the pipe open forever.
            $text = $text + $outTask.GetAwaiter().GetResult() + $errTask.GetAwaiter().GetResult()
        }
    } catch {
        $code = 1
        $text = $text + 'failed to run git: ' + $_.Exception.Message
    }
    try { $proc.Dispose() } catch { }
    return @{ Code = $code; Text = (Get-RedactedText $text) }
}

function Assert-SafeMirrorTarget {
    param([string]$Path, [string]$AllowedRoot)
    $full = [System.IO.Path]::GetFullPath($Path)
    $root = [System.IO.Path]::GetFullPath($AllowedRoot)
    if ($full.Length -le $root.Length) { throw ('unsafe robocopy target (is the root): ' + $full) }
    if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw ('unsafe robocopy target (outside allowed root): ' + $full)
    }
}

function Invoke-RobocopyMirror {
    param([string]$Source, [string]$Target, [string[]]$ExcludeDirs, [string[]]$ExcludeFiles)
    if (-not (Test-Path -LiteralPath $Source)) {
        return @{ Code = 16; Text = ('source missing: ' + $Source) }
    }
    $null = New-Item -ItemType Directory -Path $Target -Force -ErrorAction SilentlyContinue
    $rcArgs = @($Source, $Target, '/MIR', '/XJ', '/R:1', '/W:1', '/NFL', '/NDL', '/NP', '/NJH', '/NJS')
    if (@($ExcludeDirs).Count -gt 0) { $rcArgs += '/XD'; $rcArgs += @($ExcludeDirs) }
    if (@($ExcludeFiles).Count -gt 0) { $rcArgs += '/XF'; $rcArgs += @($ExcludeFiles) }
    $out = & robocopy @rcArgs 2>&1
    $code = [int]$LASTEXITCODE
    $txt = ($out | Out-String)
    return @{ Code = $code; Text = (Get-RedactedText $txt) }
}

# Exclusion census. Walks the tree exactly like robocopy: a directory whose
# name matches /XD prunes the whole subtree (first match wins, so nested
# node_modules are not counted twice); a file whose name matches /XF is
# reported individually. Paths and byte sizes only - never file contents.
function Get-ExclusionReport {
    param([string]$Root, [string[]]$Xd, [string[]]$Xf)
    $dirRows = New-Object System.Collections.ArrayList
    $fileRows = New-Object System.Collections.ArrayList
    $dirFiles = 0
    $dirBytes = [int64]0
    $fileBytes = [int64]0
    if (-not (Test-Path -LiteralPath $Root)) {
        return @{ DirRows = $dirRows; FileRows = $fileRows; DirFiles = 0; DirBytes = [int64]0; FileBytes = [int64]0 }
    }
    $stack = New-Object System.Collections.Stack
    $stack.Push('')
    while ($stack.Count -gt 0) {
        $rel = [string]$stack.Pop()
        if ($rel -eq '') { $abs = $Root } else { $abs = Join-Path $Root $rel }
        $kids = @(Get-ChildItem -LiteralPath $abs -Force -ErrorAction SilentlyContinue)
        foreach ($k in $kids) {
            if ($rel -eq '') { $krel = $k.Name } else { $krel = $rel + '\' + $k.Name }
            if ($k.PSIsContainer) {
                $hit = $false
                foreach ($n in $Xd) { if ($k.Name -eq $n) { $hit = $true } }
                if ($hit) {
                    $sub = @(Get-ChildItem -LiteralPath $k.FullName -Recurse -File -Force -ErrorAction SilentlyContinue)
                    $sb = Get-SumBytes $sub
                    $dirFiles += [int]$sub.Count
                    $dirBytes += [int64]$sb
                    $null = $dirRows.Add(('DIR | {0} | files={1} | bytes={2}' -f $krel, $sub.Count, [int64]$sb))
                    continue
                }
                $stack.Push($krel)
            } else {
                $skip = $false
                foreach ($p in $Xf) { if ($k.Name -like $p) { $skip = $true } }
                if ($skip) {
                    $fileBytes += [int64]$k.Length
                    $null = $fileRows.Add(('FILE | {0} | bytes={1}' -f $krel, $k.Length))
                }
            }
        }
    }
    return @{ DirRows = $dirRows; FileRows = $fileRows; DirFiles = $dirFiles; DirBytes = $dirBytes; FileBytes = $fileBytes }
}

function Normalize-Token {
    param([string]$Raw)
    if ($null -eq $Raw) { return '' }
    $t = $Raw
    $t = $t.Replace([string][char]0xFEFF, '')
    $t = $t.Trim()
    $t = [regex]::Replace($t, '\s', '')
    return $t
}

function Add-AuthToUrl {
    param([string]$Url, [string]$Token, [string]$Auth, [string]$User)
    if ([string]::IsNullOrEmpty($Url)) { return '' }
    if ([string]::IsNullOrEmpty($Token)) { return $Url }
    $m = [regex]::Match($Url, '^(https?://)(.*)$')
    if (-not $m.Success) { return $Url }
    $scheme = $m.Groups[1].Value
    $rest = $m.Groups[2].Value
    if ($rest.Contains('@')) { return $Url }
    if ($Auth -eq 'user-token' -and -not [string]::IsNullOrEmpty($User)) {
        return $scheme + $User + ':' + $Token + '@' + $rest
    }
    return $scheme + $Token + '@' + $rest
}

# Credential literals that must never reach the mirror repo. The quantifier
# {20,} matters: it matches real tokens (e.g. a 93-char github_pat_...) but not
# the bare prefixes that appear as prose in skill docs.
$Script:CredLiteralPattern = '(?i)(ghp_|github_pat_|gho_|ghs_|ghu_|glpat-|glft-)[A-Za-z0-9_\-]{20,}'

function Test-ResidualCredential {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return $false }
    return ($Text -match $Script:CredLiteralPattern)
}

# Redact the VALUES of credential-ish keys, key and structure preserved.
# Regex only rewrites the value part of "key: value" (also "- key: value").
function Get-RedactedYamlText {
    param([string]$Text)
    $sensKey = '(?i)token|secret|password|api_?key|webhook'
    $lines = New-Object System.Collections.ArrayList
    foreach ($line in ($Text -split "`n")) {
        $ln = $line
        $m = [regex]::Match($ln, '^(\s*(?:-\s+)?)([^:#\s][^:]*?)(\s*:\s*)(\S.*?)(\s*)$')
        if ($m.Success) {
            $pre = $m.Groups[1].Value
            $key = $m.Groups[2].Value
            $sep = $m.Groups[3].Value
            $val = $m.Groups[4].Value
            $tail = $m.Groups[5].Value
            if ($key -match $sensKey) {
                $ln = $pre + $key + $sep + '<redacted>' + $tail
            } else {
                $ln = $pre + $key + $sep + ([regex]::Replace($val, $Script:CredLiteralPattern, '<redacted>')) + $tail
            }
        } else {
            $ln = [regex]::Replace($ln, $Script:CredLiteralPattern, '<redacted>')
        }
        $null = $lines.Add($ln)
    }
    $result = ($lines -join "`n")
    return [regex]::Replace($result, $Script:CredLiteralPattern, '<redacted>')
}

# git fetch with an inline URL records that URL (with the token) in
# .git/FETCH_HEAD. Scrub it right after we are done with it.
function Clear-FetchHeadSecrets {
    param([string]$Repo)
    $fh = Join-Path $Repo '.git\FETCH_HEAD'
    if (-not (Test-Path -LiteralPath $fh)) { return }
    try {
        $txt = [System.IO.File]::ReadAllText($fh)
        $new = Get-RedactedText $txt
        if ($new -ne $txt) {
            Write-Utf8NoBom -Path $fh -Text $new
            Write-LogLine 'SANITIZE: .git/FETCH_HEAD scrubbed'
        }
    } catch {
        Write-LogLine ('WARN: could not scrub FETCH_HEAD: ' + (Get-RedactedText $_.Exception.Message))
    }
}

function Add-GitignoreLines {
    param([string]$Repo, [string[]]$Lines)
    $gi = Join-Path $Repo '.gitignore'
    if (Test-Path -LiteralPath $gi) {
        $bytes = [System.IO.File]::ReadAllBytes($gi)
        $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    } else {
        $text = ''
    }
    $text = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    $existing = @($text -split "`n")
    $add = @()
    foreach ($l in $Lines) {
        if (-not ($existing -contains $l)) { $add += $l }
    }
    if ($add.Count -eq 0) { return 0 }
    $base = $text
    if ($base.Length -gt 0 -and -not $base.EndsWith("`n")) { $base = $base + "`n" }
    $base = $base + '# dsh-repo-sync local state (never published)' + "`n"
    foreach ($l in $add) { $base = $base + $l + "`n" }
    Write-Utf8NoBom -Path $gi -Text $base
    return $add.Count
}

function Stop-Run {
    param([int]$Code, [string]$Reason)
    $Script:ExitCode = $Code
    $Script:Reason = (Get-RedactedText $Reason)
    $utc = [datetime]::UtcNow
    $local = [datetime]::Now

    if ($Code -ne 0) {
        $alert = @()
        $alert += '# ALERT - dsh-repo-sync failed'
        $alert += ''
        $alert += '- time (utc): ' + $utc.ToString('yyyy-MM-ddTHH:mm:ssZ')
        $alert += '- time (local): ' + $local.ToString('yyyy-MM-dd HH:mm:ss')
        $alert += '- exit code: ' + $Code
        $alert += '- reason: ' + $Script:Reason
        $alert += ''
        $alert += 'Load skill dsh-repo-sync to diagnose.'
        $alert += ''
        if ($Script:AlertPath) { Write-Utf8NoBom -Path $Script:AlertPath -Text ($alert -join "`n") }
    } else {
        if ($Script:AlertPath -and (Test-Path -LiteralPath $Script:AlertPath)) {
            Remove-Item -LiteralPath $Script:AlertPath -Force -ErrorAction SilentlyContinue
        }
    }

    if ($Script:StatePath) {
        $remotesObj = @{}
        foreach ($n in $RemoteNames) {
            $r = $Script:Results[$n]
            $remotesObj[$n] = @{
                ok         = [bool]$r['ok']
                pushed_sha = [string]$r['pushed_sha']
                error      = (Get-RedactedText ([string]$r['error']))
            }
        }
        $state = [ordered]@{
            last_run_local = $local.ToString('yyyy-MM-dd HH:mm:ss')
            last_run_utc   = $utc.ToString('yyyy-MM-ddTHH:mm:ssZ')
            upstream_head  = $Script:UpHead
            local_head     = $Script:LocalHead
            snapshot_files = $Script:SnapFiles
            changed        = $Script:Changed
            remotes        = $remotesObj
            exit_code      = $Code
        }
        $json = $state | ConvertTo-Json -Depth 6
        Write-Utf8NoBom -Path $Script:StatePath -Text $json
    }

    $parts = @()
    foreach ($n in $RemoteNames) {
        $r = $Script:Results[$n]
        if ($r['ok']) { $parts += ($n + '=ok:' + $r['pushed_sha']) }
        else { $parts += ($n + '=fail') }
    }
    $verdict = 'FAIL'
    if ($Code -eq 0) { if ($Script:Changed) { $verdict = 'SYNCED' } else { $verdict = 'NO_CHANGE' } }
    Write-LogLine ($utc.ToString('yyyy-MM-ddTHH:mm:ssZ') + ' | ' + $verdict + ' | local=' + $Script:LocalHead + ' | ' + ($parts -join ' '))

    Write-LogLine ''
    Write-LogLine '=== SUMMARY ==='
    Write-LogLine ('mode=' + $(if ($Script:IsDry) { 'DRY-RUN' } else { 'REAL' }))
    Write-LogLine ('SNAPSHOT_FILES=' + $Script:SnapFiles)
    Write-LogLine ('SNAPSHOT_BYTES=' + $Script:SnapBytes)
    Write-LogLine ('PRESET_FILES=' + $Script:PrsFiles)
    Write-LogLine ('PRESET_BYTES=' + $Script:PrsBytes)
    Write-LogLine ('EXCLUDED_ENTRIES=' + $Script:ExcEntries)
    Write-LogLine ('EXCLUDED_DIRS=' + $Script:ExcDirs)
    Write-LogLine ('EXCLUDED_FILES=' + $Script:ExcFiles)
    Write-LogLine ('EXCLUDED_BYTES=' + $Script:ExcBytes)
    Write-LogLine ('PRESET_EXCLUDED_ENTRIES=' + $Script:PrsExc)
    Write-LogLine ('exit=' + $Code)
    if ($Code -ne 0) { Write-LogLine ('reason=' + $Script:Reason) }
    if ($env:DSH_REPO_SYNC_NOEXIT -ne '1') { exit $Code }
}

# --------------------------------------------------------------------- main

function Invoke-Main {

    if ($DryRun.IsPresent) { $Script:IsDry = $true }

    if ($Script:IsDry) {
        $Script:RunSyncDir = Join-Path $DryRoot 'sync'
    } else {
        $Script:RunSyncDir = $SyncDir
    }
    $Script:LogPath   = Join-Path (Join-Path $Script:RunSyncDir 'logs') ('sync-' + [datetime]::Now.ToString('yyyy-MM') + '.log')
    $Script:StatePath = Join-Path $Script:RunSyncDir 'state.json'
    $Script:AlertPath = Join-Path $Script:RunSyncDir 'ALERT.md'
    $excludedDoc      = Join-Path $Script:RunSyncDir 'EXCLUDED.md'

    Write-LogLine ('dsh-repo-sync start utc=' + $Script:StartedUtc.ToString('yyyy-MM-ddTHH:mm:ssZ'))
    if ($Script:IsDry) {
        Write-LogLine 'MODE=DRY-RUN (nothing outside TEMP is written; no git command is run)'
    } else {
        Write-LogLine 'MODE=REAL'
    }
    Write-LogLine ('DSH_HOME=' + $DshHome)
    Write-LogLine ('MIRROR=' + $Mirror)
    Write-LogLine ('SYNC_DIR=' + $Script:RunSyncDir)

    # ---- mirror presence (real mode is fatal, dry mode only reports) --------
    $mirrorOk = Test-Path -LiteralPath (Join-Path $Mirror '.git')
    Write-LogLine ('MIRROR_PRESENT=' + $mirrorOk)
    if (-not $mirrorOk -and -not $Script:IsDry) {
        Write-LogLine ('ERROR: mirror repo not found or not a git repo: ' + $Mirror)
        Write-LogLine 'ERROR: clone it first, then re-run. Nothing was changed.'
        Stop-Run 3 ('mirror repo missing: ' + $Mirror)
    }
    if (-not $mirrorOk) {
        Write-LogLine 'WARN: mirror repo missing; dry run continues without it'
    }

    # ---- remotes.json (dry mode: read-only, warn and continue) -------------
    $remotesPath = Join-Path $SyncDir 'remotes.json'
    $remotes = $null
    if (Test-Path -LiteralPath $remotesPath) {
        try {
            $raw = [System.IO.File]::ReadAllText($remotesPath)
            $remotes = $raw | ConvertFrom-Json
            Write-LogLine ('REMOTES_JSON=found ' + $remotesPath)
        } catch {
            Write-LogLine ('WARN: remotes.json unparsable: ' + (Get-RedactedText $_.Exception.Message))
            $remotes = $null
        }
    }
    if ($null -eq $remotes) {
        if ($Script:IsDry) {
            Write-LogLine ('WARN: remotes.json missing or unparsable (' + $remotesPath + '); dry run continues without push targets')
        } else {
            Write-LogLine ('ERROR: remotes.json missing or unparsable: ' + $remotesPath)
            Write-LogLine 'ERROR: expected {"branch":"master","github":{"url":"...","token_file":"...","auth":"token-as-user","user":""},"gitcode":{"url":"...","token_file":"...","auth":"user-token","user":"<login>"}}'
            Stop-Run 3 ('remotes.json missing: ' + $remotesPath)
        }
    }

    # ---- collect token values for redaction --------------------------------
    if ($null -ne $remotes) {
        foreach ($n in $RemoteNames) {
            $cfg = Get-PropValue $remotes $n
            if ($null -eq $cfg) { continue }
            $tf = [string](Get-PropValue $cfg 'token_file')
            if ($tf -and (Test-Path -LiteralPath $tf)) {
                $tok = Normalize-Token ([System.IO.File]::ReadAllText($tf))
                if ($tok.Length -ge 6) { $Script:Secrets += $tok }
                Write-LogLine ('TOKEN_SOURCE[' + $n + ']=' + $tf + ' (value never printed)')
            } else {
                Write-LogLine ('WARN: token file missing for ' + $n + ': ' + $tf)
            }
        }
    }

    # ---- exclusion census --------------------------------------------------
    $repHome = Get-ExclusionReport -Root $DshHome -Xd $XdNames -Xf $XfNames
    if ($PresetOn) {
        $repPres = Get-ExclusionReport -Root $PresetSrc -Xd $XdPreset -Xf $XfPreset
    } else {
        $repPres = [pscustomobject]@{ DirRows = @(); FileRows = @() }
    }

    $Script:ExcDirs    = [int]$repHome.DirRows.Count
    $Script:ExcFiles   = [int]$repHome.FileRows.Count
    $Script:ExcEntries = [int]($Script:ExcDirs + $Script:ExcFiles)
    $Script:ExcBytes   = [int64]($repHome.DirBytes + $repHome.FileBytes)
    $Script:PrsExc     = [int]($repPres.DirRows.Count + $repPres.FileRows.Count)

    Write-LogLine ('EXCLUDED_ENTRIES=' + $Script:ExcEntries + ' (dirs=' + $Script:ExcDirs + ' files=' + $Script:ExcFiles + ' bytes=' + $Script:ExcBytes + ')')
    Write-LogLine ('PRESET_EXCLUDED_ENTRIES=' + $Script:PrsExc)

    # ---- snapshot targets --------------------------------------------------
    if ($Script:IsDry) {
        $snapTarget = Join-Path $DryRoot 'dsh-home'
        $presTarget = Join-Path $DryRoot 'dsh-presets\orchestrator-bundle'
        Assert-SafeMirrorTarget -Path $snapTarget -AllowedRoot $DryRoot
        Assert-SafeMirrorTarget -Path $presTarget -AllowedRoot $DryRoot
    } else {
        $snapTarget = $Snap
        $presTarget = $PresetDst
        Assert-SafeMirrorTarget -Path $snapTarget -AllowedRoot $Mirror
        Assert-SafeMirrorTarget -Path $presTarget -AllowedRoot $Mirror
    }
    Write-LogLine ('SNAPSHOT_TARGET=' + $snapTarget)
    Write-LogLine ('PRESET_TARGET=' + $presTarget)

    # ---- robocopy (0..7 = success, >=8 = failure) --------------------------
    $rc = Invoke-RobocopyMirror -Source $DshHome -Target $snapTarget -ExcludeDirs $XdNames -ExcludeFiles $XfNames
    Write-LogLine ('robocopy dsh-home rc=' + $rc.Code)
    if ($rc.Code -ge 8) {
        Write-LogLine ('ERROR: robocopy failed for dsh-home (rc=' + $rc.Code + ')')
        Write-LogLine (Get-RedactedText $rc.Text)
        Stop-Run 5 ('robocopy dsh-home rc=' + $rc.Code)
    }

    if ($PresetOn) {
        $rc2 = Invoke-RobocopyMirror -Source $PresetSrc -Target $presTarget -ExcludeDirs $XdPreset -ExcludeFiles $XfPreset
        Write-LogLine ('robocopy presets rc=' + $rc2.Code)
        if ($rc2.Code -ge 8) {
            Write-LogLine ('ERROR: robocopy failed for presets (rc=' + $rc2.Code + ')')
            Write-LogLine (Get-RedactedText $rc2.Text)
            Stop-Run 5 ('robocopy presets rc=' + $rc2.Code)
        }
    } else {
        Write-LogLine ('SKIP: preset source absent, preset lane skipped: ' + $PresetSrc)
    }

    # ---- root cordis.patch.yml: contains a plaintext PAT literal -----------
    # It must NOT reach the mirror. /XF is not used on purpose: a name pattern
    # would also drop profiles\*\cordis.patch.yml and the preset copies, which
    # are credential-free and must be kept.
    $cordisSrc = Join-Path $snapTarget 'cordis.patch.yml'
    $cordisOut = Join-Path $snapTarget 'cordis.patch.redacted.yml'
    $cordisRemoved = $false
    $cordisRedacted = $false
    if (Test-Path -LiteralPath $cordisSrc) {
        try {
            $cordisRaw = [System.IO.File]::ReadAllText($cordisSrc)
            $cordisRed = Get-RedactedYamlText $cordisRaw
            Remove-Item -LiteralPath $cordisSrc -Force
            $cordisRemoved = $true
        } catch {
            Stop-Run 5 ('could not remove root cordis.patch.yml from the snapshot: ' + (Get-RedactedText $_.Exception.Message))
        }
        if (Test-ResidualCredential $cordisRed) {
            Write-LogLine 'ERROR: cordis redaction guard tripped; a credential literal survived the rewrite'
            Stop-Run 5 'cordis.patch.yml redaction guard tripped (residual credential literal)'
        }
        Write-Utf8NoBom -Path $cordisOut -Text $cordisRed
        $cordisRedacted = $true
        Write-LogLine 'CORDIS_PATCH: root cordis.patch.yml removed from snapshot; redacted copy written'
    } else {
        Write-LogLine 'CORDIS_PATCH: no root cordis.patch.yml in the snapshot'
        if (Test-Path -LiteralPath $cordisOut) { Remove-Item -LiteralPath $cordisOut -Force -ErrorAction SilentlyContinue }
    }

    $s1 = Get-TreeStats -Path $snapTarget
    if ($PresetOn) {
        $s2 = Get-TreeStats -Path $presTarget
    } else {
        $s2 = [pscustomobject]@{ Files = 0; Bytes = 0 }
    }
    $Script:SnapFiles = [int]$s1.Files
    $Script:SnapBytes = [int64]$s1.Bytes
    $Script:PrsFiles  = [int]$s2.Files
    $Script:PrsBytes  = [int64]$s2.Bytes

    # ---- EXCLUDED.md (paths + byte sizes only, never contents) -------------
    $man = @()
    $man += '# EXCLUDED - items deliberately kept out of the snapshot'
    $man += ''
    $man += '- generated (utc): ' + [datetime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $man += '- generator: sync-dsh-repos.ps1'
    $man += '- relative paths and byte sizes only. No file content is recorded in this file.'
    $man += '- counts are a point-in-time measurement; the sessions trees grow while DSH runs.'
    $man += ''
    $man += '## Directory-level exclusions (whole subtree pruned, name-matched at any depth)'
    $man += '## rule: robocopy /XD ' + ($XdNames -join ' ')
    $man += '## "sessions" is the DSH session-record tree (session.v4.jsonl.zstd transcripts,'
    $man += '## raw conversation data) and is excluded as a whole.'
    $man += '## "storages" holds the session project cache (session_projcache\sessions).'
    $man += '## ".secrets" is the whole credential store (tokens, MS365 token cache,'
    $man += '## selected-account metadata); the directory is pruned as a unit.'
    $man += '## node_modules is the npm dependency tree (hundreds of MB, reproducible).'
    $man += ''
    foreach ($r in @($repHome.DirRows | Sort-Object)) { $man += $r }
    $man += ''
    $man += '## File-level exclusions (name patterns, matched at any depth)'
    $man += '## rule: robocopy /XF ' + ($XfNames -join ' ')
    $man += '## GAP CLOSED: *.token never matched .secrets\ms365\.token-cache.json, but the whole'
    $man += '## .secrets directory is now pruned by /XD .secrets, so no credential file can'
    $man += '## survive by pattern accident.'
    $man += ''
    foreach ($r in @($repHome.FileRows | Sort-Object)) { $man += $r }
    $man += ''
    $man += '## Root-level special handling (not expressible as a glob rule)'
    if ($cordisRemoved) {
        $man += 'FILE | cordis.patch.yml | REMOVED from the snapshot with Remove-Item: this file holds'
        $man += '     a plaintext credential literal as the value of GITHUB_PERSONAL_ACCESS_TOKEN.'
        $man += '     The value is never copied, never logged and never written anywhere.'
        $man += 'FILE | cordis.patch.redacted.yml | WRITTEN in its place: every value whose key matches'
        $man += '     (?i)(token|secret|password|api_key|webhook) is replaced with <redacted>, keys and'
        $man += '     structure preserved, UTF-8 without BOM. A residual-credential guard re-scans the'
        $man += '     result and aborts the run (exit 5) if any credential literal survives.'
    } else {
        $man += '(no root-level cordis.patch.yml was present in the snapshot)'
    }
    $man += ''
    $man += '## Preset bundle exclusions'
    if ($PresetOn) {
        $man += '## source: ' + $PresetSrc
        $man += '## rule: robocopy /XD ' + ($XdPreset -join ' ')
        if (@($repPres.DirRows).Count -eq 0 -and @($repPres.FileRows).Count -eq 0) {
            $man += '(nothing excluded in the preset bundle)'
        }
        foreach ($r in @($repPres.DirRows | Sort-Object)) { $man += $r }
        foreach ($r in @($repPres.FileRows | Sort-Object)) { $man += $r }
    } else {
        $man += '(preset lane skipped: source absent)'
    }
    Write-Utf8NoBom -Path $excludedDoc -Text (($man -join "`n") + "`n")
    Write-LogLine ('EXCLUDED_MD=' + $excludedDoc)

    if ($Script:IsDry) {
        Write-LogLine 'DRY-RUN complete: no git command was run, no file outside TEMP was written.'
        Stop-Run 0 'dry run'
        return
    }

    # ======================= real mode (git) ================================

    $null = Add-GitignoreLines -Repo $Mirror -Lines $GitignoreLines

    # ---- git identity: mirror-local first, then global, never invented -----
    $idName = ''
    $idMail = ''
    $r = Invoke-Git @('-C', $Mirror, 'config', 'user.name')
    if ($r.Code -eq 0) { $idName = $r.Text.Trim() }
    $r = Invoke-Git @('-C', $Mirror, 'config', 'user.email')
    if ($r.Code -eq 0) { $idMail = $r.Text.Trim() }
    if ($idName -eq '' -or $idMail -eq '') {
        $g = Invoke-Git @('config', '--global', 'user.name')
        if ($g.Code -eq 0 -and $g.Text.Trim() -ne '') { $idName = $g.Text.Trim() }
        $g = Invoke-Git @('config', '--global', 'user.email')
        if ($g.Code -eq 0 -and $g.Text.Trim() -ne '') { $idMail = $g.Text.Trim() }
    }
    if ($idName -eq '' -or $idMail -eq '') {
        Write-LogLine 'ERROR: no git commit identity available (mirror-local and global both unset)'
        Stop-Run 3 'git identity unavailable (mirror-local and --global user.name/user.email both empty)'
    }
    Write-LogLine ('GIT_IDENTITY=' + $idName + ' <' + $idMail + '>')

    # ---- upstream update ---------------------------------------------------
    $upMoved = $false
    if (-not $NoUpstream.IsPresent) {
        $r = Invoke-Git @('-C', $Mirror, 'fetch', '--prune', 'upstream', 'master')
        if ($r.Code -ne 0) {
            Write-LogLine 'WARN: upstream fetch failed or upstream remote absent; skipping upstream update'
            Write-LogLine $r.Text
        } else {
            $h = Invoke-Git @('-C', $Mirror, 'rev-parse', 'upstream/master')
            if ($h.Code -eq 0) { $Script:UpHead = $h.Text.Trim() }
            $c = Invoke-Git @('-C', $Mirror, 'rev-list', '--count', 'HEAD..upstream/master')
            $behind = 0
            if ($c.Code -eq 0) { $behind = [int]($c.Text.Trim()) }
            Write-LogLine ('UPSTREAM_HEAD=' + $Script:UpHead + ' behind=' + $behind)
            if ($behind -gt 0) {
                $m = Invoke-Git @('-C', $Mirror, 'merge', '--no-edit', 'upstream/master')
                if ($m.Code -ne 0) {
                    # Narrow self-heal gate, exactly one path: .github/dependabot.yml
                    # was deleted on purpose in the mirror (upstream keeps touching
                    # a Dependabot workflow we deliberately do not carry). When
                    # upstream later edits that file, git stops with
                    # "CONFLICT (modify/delete)" and the whole sync would jam.
                    # If that path is the ONLY unmerged path, keep our deletion
                    # and let the normal stage + commit below finish the merge.
                    # Any other conflict (or any other path) keeps the original
                    # abort + exit 4 behaviour, byte for byte.
                    $healed = $false
                    $u = Invoke-Git @('-C', $Mirror, 'diff', '--name-only', '--diff-filter=U')
                    if ($u.Code -eq 0) {
                        $un = @($u.Text -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
                        if ($un.Count -eq 1 -and $un[0].Trim() -eq '.github/dependabot.yml') {
                            $rm = Invoke-Git @('-C', $Mirror, 'rm', '--force', '--quiet', '--', '.github/dependabot.yml')
                            if ($rm.Code -eq 0) { $healed = $true }
                        }
                    }
                    if ($healed) {
                        Write-LogLine 'SELF-HEAL: .github/dependabot.yml modify/delete conflict resolved (deletion kept); merge continues'
                    } else {
                        Write-LogLine 'ERROR: upstream merge failed; aborting merge'
                        Write-LogLine $m.Text
                        $null = Invoke-Git @('-C', $Mirror, 'merge', '--abort')
                        Stop-Run 4 'upstream merge conflict while merging upstream/master'
                    }
                }
                $upMoved = $true
            }
        }
    } else {
        Write-LogLine 'UPSTREAM=skipped (-NoUpstream)'
    }

    # ---- stage + commit ----------------------------------------------------
    $null = Invoke-Git @('-C', $Mirror, 'add', '-A')
    $st = Invoke-Git @('-C', $Mirror, 'status', '--porcelain')
    $dirty = ($st.Text.Trim() -ne '')
    $Script:Changed = ($dirty -or $upMoved)

    if (-not $Script:Changed -and -not $Force.IsPresent) {
        Write-LogLine 'NO_CHANGE'
        Stop-Run 0 'no change'
        return
    }

    $hh = Invoke-Git @('-C', $Mirror, 'rev-parse', '--short', 'HEAD')
    $short = ''
    if ($hh.Code -eq 0) { $short = $hh.Text.Trim() }
    $stamp = [datetime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $msg = 'sync: ' + $stamp + ' upstream=' + $short + ' | dsh-home refresh'
    $c = Invoke-Git @('-C', $Mirror, '-c', ('user.name=' + $idName), '-c', ('user.email=' + $idMail), 'commit', '-m', $msg)
    Write-LogLine ('git commit rc=' + $c.Code)
    if ($c.Code -ne 0) {
        Write-LogLine (Get-RedactedText $c.Text)
        Stop-Run 5 ('commit failed rc=' + $c.Code)
    }

    $h = Invoke-Git @('-C', $Mirror, 'rev-parse', 'HEAD')
    if ($h.Code -eq 0) { $Script:LocalHead = $h.Text.Trim() }
    Write-LogLine ('LOCAL_HEAD=' + $Script:LocalHead)

    # ---- push to both remotes ---------------------------------------------
    $pushFail = $false
    $diverged = $false
    foreach ($n in $RemoteNames) {
        $res = $Script:Results[$n]
        $cfg = $null
        if ($null -ne $remotes) { $cfg = Get-PropValue $remotes $n }
        if ($null -eq $cfg) {
            $res['error'] = 'remote not configured in remotes.json'
            $pushFail = $true
            Write-LogLine ('PUSH[' + $n + '] skipped: not configured')
            continue
        }
        $tf = [string](Get-PropValue $cfg 'token_file')
        $tok = ''
        if ($tf -and (Test-Path -LiteralPath $tf)) { $tok = Normalize-Token ([System.IO.File]::ReadAllText($tf)) }
        if ($tok -eq '') {
            $res['error'] = 'token file missing or empty: ' + $tf
            $pushFail = $true
            Write-LogLine ('PUSH[' + $n + '] failed: token file missing or empty')
            continue
        }
        if ($tok.Length -ge 6 -and -not ($Script:Secrets -contains $tok)) { $Script:Secrets += $tok }
        $authMode = [string](Get-PropValue $cfg 'auth')
        $authUser = [string](Get-PropValue $cfg 'user')
        $pushUrl = Add-AuthToUrl ([string](Get-PropValue $cfg 'url')) $tok $authMode $authUser
        $pushArgs = @('-C', $Mirror, 'push', $pushUrl, 'HEAD:master')

        $p = Invoke-Git -GitArgs $pushArgs -TimeoutSec 900
        if ($p.Code -ne 0) {
            Write-LogLine ('PUSH[' + $n + '] attempt 1 failed; retrying once')
            Write-LogLine $p.Text
            Start-Sleep -Seconds 2
            $p = Invoke-Git -GitArgs $pushArgs -TimeoutSec 900
        }
        if ($p.Code -eq 0) {
            $res['ok'] = $true
            $res['pushed_sha'] = $Script:LocalHead
            Write-LogLine ('PUSH[' + $n + ']=ok ' + $Script:LocalHead)
            continue
        }

        Write-LogLine ('PUSH[' + $n + '] attempt 2 failed')
        Write-LogLine $p.Text
        if ($p.Text -match 'non-fast-forward|fetch first|Updates were rejected|rejected') {
            Write-LogLine ('PUSH[' + $n + '] non-fast-forward: trying fetch + merge then one more push')
            $f = Invoke-Git @('-C', $Mirror, 'fetch', $pushUrl, 'master')
            if ($f.Code -eq 0) {
                $m = Invoke-Git @('-C', $Mirror, 'merge', '--no-edit', 'FETCH_HEAD')
                if ($m.Code -eq 0) {
                    $p2 = Invoke-Git -GitArgs $pushArgs -TimeoutSec 900
                    Clear-FetchHeadSecrets -Repo $Mirror
                    if ($p2.Code -eq 0) {
                        $res['ok'] = $true
                        $res['pushed_sha'] = $Script:LocalHead
                        Write-LogLine ('PUSH[' + $n + ']=ok after reconcile ' + $Script:LocalHead)
                        continue
                    }
                    Write-LogLine ('PUSH[' + $n + '] failed after reconcile')
                    Write-LogLine $p2.Text
                    $res['error'] = 'push failed after fetch+merge: ' + $p2.Text
                } else {
                    Write-LogLine ('PUSH[' + $n + '] reconcile merge conflict; aborting')
                    Write-LogLine $m.Text
                    $null = Invoke-Git @('-C', $Mirror, 'merge', '--abort')
                    Clear-FetchHeadSecrets -Repo $Mirror
                    $res['error'] = 'remote diverged: merge of fetched master conflicted'
                    $diverged = $true
                }
            } else {
                Write-LogLine ('PUSH[' + $n + '] fetch failed')
                Write-LogLine $f.Text
                Clear-FetchHeadSecrets -Repo $Mirror
                $res['error'] = 'push rejected and fetch of remote master failed'
            }
        } else {
            $res['error'] = 'push failed: ' + $p.Text
        }
        $pushFail = $true
    }

    if ($diverged) { Stop-Run 7 ('remote diverged: ' + (Get-RedactedText ($Script:Results[$RemoteNames[0]]['error']))) }
    if ($pushFail) { Stop-Run 6 'one or more remotes rejected the push' }

    Stop-Run 0 'pushed to all remotes'
}

# ------------------------------------------------------------------- entry

try {
    Invoke-Main
} catch {
    $m = Get-RedactedText $_.Exception.Message
    Write-Host ('UNEXPECTED: ' + $m)
    try { Stop-Run 8 ('unexpected exception: ' + $m) } catch { exit 8 }
}
