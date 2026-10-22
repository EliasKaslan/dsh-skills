<#
  publish-dsh-skills.ps1

  Snapshot the local DSH skill tree into a public GitCode repository:
    * copy  %USERPROFILE%\.dsh\skills  ->  <work_repo>\skills   (robocopy /MIR)
    * regenerate README.md + index.json from skill frontmatter
    * scan the staged tree for live credentials (literal + pattern based)
    * commit on <branch_main>, push it, then push the same commit to a
      date-named branch (<date_format>, default YYYY-MM-DD)
    * verify that both remote refs point at the local HEAD

  Exit codes
    0  success (pushed, or NO_CHANGE with refs already consistent)
    3  environment / configuration problem
    4  secret scan found a live credential in the staged tree
    5  snapshot or generated-file failure
    6  push failed
    7  post-push verification failed (main != date branch)
    8  unexpected exception

  This file is ASCII only on purpose: Windows PowerShell 5.1 decodes a
  BOM-less script as ANSI/GBK, so any non-ASCII literal here would corrupt
  parsing.  Chinese text lives in readme.template.md and SKILL.md and is
  read back as UTF-8 data.

  The token is read from the file named in the config, used only inside the
  push URL, never written to disk and never printed (all output is redacted).
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoPush,
    [string]$DateStamp = ''
)

$ErrorActionPreference = 'Stop'

$script:Stage    = 'init'
$script:GitExe   = 'git'
$script:Token    = ''
$script:StateDir = ''
$script:LogFile  = ''
$script:WorkRepo = ''
$script:State    = [ordered]@{
    last_run_local   = ''
    last_run_utc     = ''
    exit_code        = 0
    stage            = 'init'
    message          = ''
    dry_run          = [bool]$DryRun
    changed          = $false
    head_sha         = ''
    main_remote_sha  = ''
    date_branch      = ''
    date_remote_sha  = ''
    skill_count      = 0
    file_count       = 0
    total_bytes      = 0
    new_commit       = ''
}

function Get-Utf8NoBom {
    return (New-Object System.Text.UTF8Encoding $false)
}

function Redact-Text {
    param([string]$Text)
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $t = $Text
    if ($script:Token.Length -ge 8) { $t = $t.Replace($script:Token, '<redacted>') }
    $t = [regex]::Replace($t, 'https://[^/@\s]+@', 'https://<redacted>@')
    return $t
}

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = '{0} {1} {2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, (Redact-Text $Message)
    Write-Host $line
    if ($script:LogFile) {
        try { [IO.File]::AppendAllText($script:LogFile, $line + "`r`n", (Get-Utf8NoBom)) } catch { }
    }
}

function Save-State {
    if ([string]::IsNullOrEmpty($script:StateDir)) { return }
    $script:State.last_run_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    $script:State.last_run_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $script:State.stage = $script:Stage
    $json = $script:State | ConvertTo-Json -Depth 6
    $json = ($json -replace "`r`n", "`n") + "`n"
    [IO.File]::WriteAllText((Join-Path $script:StateDir 'state.json'), $json, (Get-Utf8NoBom))
}

function Write-Alert {
    param([int]$Code, [string]$Message, [string]$Stage)
    if ([string]::IsNullOrEmpty($script:StateDir)) { return }
    $lines = @(
        '# DSH skills publish FAILED',
        '',
        ('- time  : ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
        ('- stage : ' + $Stage),
        ('- exit  : ' + $Code),
        ('- error : ' + (Redact-Text $Message)),
        '',
        'Fix the cause, then run publish-dsh-skills.ps1 again.',
        'This file is deleted by the next successful run.'
    )
    $text = ($lines -join "`r`n") + "`r`n"
    [IO.File]::WriteAllText((Join-Path $script:StateDir 'ALERT.md'), $text, (Get-Utf8NoBom))
}

function Fail {
    param([int]$Code, [string]$Message)
    $script:State.exit_code = $Code
    $script:State.message = (Redact-Text $Message)
    Write-Log $Message 'ERROR'
    Write-Alert -Code $Code -Message $Message -Stage $script:Stage
    Save-State
    exit $Code
}

function Invoke-Git {
    param([string[]]$ArgList, [int]$TimeoutSec = 120)
    $parts = @()
    foreach ($a in $ArgList) {
        if ($a -match '[\s"]') { $parts += ('"' + ($a -replace '"', '\"') + '"') }
        else { $parts += $a }
    }
    $argLine = $parts -join ' '

    # Start-Process -PassThru returns a .ExitCode that stays $null on PS 5.1
    # even after WaitForExit(ms), so drive System.Diagnostics.Process directly.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:GitExe
    $psi.Arguments = $argLine
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    $outTask = $proc.StandardOutput.ReadToEndAsync()
    $errTask = $proc.StandardError.ReadToEndAsync()
    $finished = $proc.WaitForExit($TimeoutSec * 1000)
    if (-not $finished) {
        try { $proc.Kill() } catch { }
        try { [void]$proc.WaitForExit(5000) } catch { }
        return [pscustomobject]@{ Code = 124; Out = ('TIMEOUT after ' + $TimeoutSec + 's') }
    }
    $code = $proc.ExitCode
    $stdout = ''
    $stderr = ''
    try { $stdout = $outTask.Result } catch { }
    try { $stderr = $errTask.Result } catch { }
    return [pscustomobject]@{ Code = $code; Out = (Redact-Text (($stdout + $stderr).Trim())) }
}

function Invoke-RepoGit {
    param([string[]]$ArgList, [int]$TimeoutSec = 120)
    $full = @('-c', 'credential.helper=', '-c', 'core.autocrlf=false', '-C', $script:WorkRepo) + $ArgList
    return Invoke-Git -ArgList $full -TimeoutSec $TimeoutSec
}

function Read-Config {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw ('config file not found: ' + $Path) }
    $raw = [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8)
    return ($raw | ConvertFrom-Json)
}

function Get-SkillMeta {
    param([string]$Dir)
    $leaf = Split-Path -Leaf $Dir
    $name = $leaf
    $desc = ''
    $md = Join-Path $Dir 'SKILL.md'
    if (Test-Path -LiteralPath $md) {
        $text = [IO.File]::ReadAllText($md, [Text.Encoding]::UTF8)
        $lines = $text -split "`r?`n"
        if ($lines.Count -gt 1 -and $lines[0].Trim() -eq '---') {
            for ($i = 1; $i -lt $lines.Count; $i++) {
                if ($lines[$i].Trim() -eq '---') { break }
                if ($lines[$i] -match '^name:\s*(.+)$') {
                    $name = $matches[1].Trim().Trim([char]34).Trim([char]39)
                }
                elseif ($lines[$i] -match '^description:\s*(.+)$') {
                    $desc = $matches[1].Trim().Trim([char]34).Trim([char]39)
                }
            }
        }
    }
    $files = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -Force)
    $bytes = 0
    foreach ($f in $files) { $bytes += $f.Length }
    if ([string]::IsNullOrWhiteSpace($desc)) { $desc = '(no description)' }
    $desc = ($desc -replace '\s+', ' ').Trim()
    return [pscustomobject]@{
        name        = $name
        path        = ('skills/' + $leaf)
        description = $desc
        files       = $files.Count
        bytes       = $bytes
    }
}

function Get-SkillTreeMeta {
    param([string]$SkillsRoot)
    $list = @()
    foreach ($d in @(Get-ChildItem -LiteralPath $SkillsRoot -Directory -Force | Sort-Object Name)) {
        $list += (Get-SkillMeta -Dir $d.FullName)
    }
    return $list
}

function ConvertTo-JsonString {
    param([string]$Value)
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    foreach ($c in $Value.ToCharArray()) {
        $code = [int]$c
        if ($code -eq 34) { [void]$sb.Append('\"') }
        elseif ($code -eq 92) { [void]$sb.Append('\\') }
        elseif ($code -eq 10) { [void]$sb.Append('\n') }
        elseif ($code -eq 13) { [void]$sb.Append('\r') }
        elseif ($code -eq 9) { [void]$sb.Append('\t') }
        elseif ($code -lt 32) { [void]$sb.Append(('\u{0:x4}' -f $code)) }
        else { [void]$sb.Append($c) }
    }
    [void]$sb.Append('"')
    return $sb.ToString()
}

function Write-GeneratedFiles {
    param(
        [string]$RepoRoot,
        [object[]]$Skills,
        [int]$FileCount,
        [int]$TotalBytes,
        [string]$TemplatePath
    )

    $encoding = Get-Utf8NoBom

    # .gitattributes: keep bytes exactly as they are, no CRLF normalisation.
    [IO.File]::WriteAllText((Join-Path $RepoRoot '.gitattributes'), "* -text`n", $encoding)

    # index.json (deterministic: sorted by name, no timestamps).
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('{' + "`n")
    [void]$sb.Append('  "schema": 1,' + "`n")
    [void]$sb.Append('  "generated_by": "publish-dsh-skills.ps1",' + "`n")
    [void]$sb.Append(('  "skill_count": ' + $Skills.Count + ',') + "`n")
    [void]$sb.Append(('  "file_count": ' + $FileCount + ',') + "`n")
    [void]$sb.Append(('  "total_bytes": ' + $TotalBytes + ',') + "`n")
    [void]$sb.Append('  "skills": [' + "`n")
    for ($i = 0; $i -lt $Skills.Count; $i++) {
        $s = $Skills[$i]
        [void]$sb.Append('    {' + "`n")
        [void]$sb.Append(('      "name": ' + (ConvertTo-JsonString $s.name) + ',') + "`n")
        [void]$sb.Append(('      "path": ' + (ConvertTo-JsonString $s.path) + ',') + "`n")
        [void]$sb.Append(('      "description": ' + (ConvertTo-JsonString $s.description) + ',') + "`n")
        [void]$sb.Append(('      "files": ' + $s.files + ',') + "`n")
        [void]$sb.Append(('      "bytes": ' + $s.bytes) + "`n")
        if ($i -lt ($Skills.Count - 1)) { [void]$sb.Append('    },' + "`n") }
        else { [void]$sb.Append('    }' + "`n") }
    }
    [void]$sb.Append('  ]' + "`n")
    [void]$sb.Append('}' + "`n")
    [IO.File]::WriteAllText((Join-Path $RepoRoot 'index.json'), $sb.ToString(), $encoding)

    # README.md from the UTF-8 template.
    $rows = @()
    for ($i = 0; $i -lt $Skills.Count; $i++) {
        $s = $Skills[$i]
        $sum = $s.description
        if ($sum.Length -gt 120) { $sum = $sum.Substring(0, 120) + '...' }
        $sum = $sum.Replace('|', '\|')
        $rows += ('| {0} | [`{1}`]({2}/SKILL.md) | {3} | {4} |' -f ($i + 1), $s.name, $s.path, $sum, $s.files)
    }
    $table = ($rows -join "`n")
    if (Test-Path -LiteralPath $TemplatePath) {
        $tpl = [IO.File]::ReadAllText($TemplatePath, [Text.Encoding]::UTF8)
    }
    else {
        $tpl = "# DSH Skills`n`nAuto-generated snapshot of my local DSH skills.`n`n{{SKILL_TABLE}}`n"
    }
    $readme = $tpl.Replace('{{SKILL_COUNT}}', [string]$Skills.Count)
    $readme = $readme.Replace('{{FILE_COUNT}}', [string]$FileCount)
    $readme = $readme.Replace('{{TOTAL_BYTES}}', [string]$TotalBytes)
    $readme = $readme.Replace('{{SKILL_TABLE}}', $table)
    $readme = ($readme -replace "`r`n", "`n").TrimEnd("`n") + "`n"
    [IO.File]::WriteAllText((Join-Path $RepoRoot 'README.md'), $readme, $encoding)
}

function Invoke-SecretScan {
    param([string]$Root, [string[]]$SecretFiles)

    $secrets = @()
    foreach ($f in $SecretFiles) {
        if (-not (Test-Path -LiteralPath $f)) { continue }
        $txt = ''
        try { $txt = [IO.File]::ReadAllText($f, [Text.Encoding]::UTF8) } catch { continue }
        foreach ($line in ($txt -split "`r?`n")) {
            $v = $line.Trim()
            if ($v.Length -ge 12 -and $v -notmatch '^(#|//)') { $secrets += $v }
            foreach ($m in [regex]::Matches($v, '[A-Za-z0-9_\-]{16,}')) {
                if ($m.Value.Length -ge 16) { $secrets += $m.Value }
            }
        }
    }
    $secrets = @($secrets | Sort-Object -Unique)

    $patterns = @(
        @{ Name = 'github_classic_pat'; Regex = 'ghp_[A-Za-z0-9]{20,}' },
        @{ Name = 'github_fine_grained_pat'; Regex = 'github_pat_[A-Za-z0-9_]{20,}' },
        @{ Name = 'private_key_block'; Regex = '-----BEGIN [A-Z ]*PRIVATE KEY-----' },
        @{ Name = 'aws_access_key'; Regex = 'AKIA[0-9A-Z]{16}' }
    )

    $hits = New-Object System.Collections.ArrayList
    foreach ($fi in @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force)) {
        $text = ''
        try { $text = [IO.File]::ReadAllText($fi.FullName, [Text.Encoding]::UTF8) } catch { continue }
        $rel = $fi.FullName.Substring($Root.Length).TrimStart('\')
        foreach ($s in $secrets) {
            if ($text.IndexOf($s, [StringComparison]::Ordinal) -ge 0) {
                [void]$hits.Add($rel + '  <- literal value from a credential file')
                break
            }
        }
        foreach ($p in $patterns) {
            if ([regex]::IsMatch($text, $p.Regex)) {
                [void]$hits.Add($rel + '  <- pattern ' + $p.Name)
            }
        }
    }
    return $hits.ToArray()
}

# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

$gitCmd = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $gitCmd) { $gitCmd = Get-Command git -ErrorAction SilentlyContinue }
if (-not $gitCmd) { Write-Host 'ERROR: git executable not found in PATH'; exit 3 }
$script:GitExe = $gitCmd.Source

$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'

$configPath = $env:DSH_SKILLS_PUBLISH_CONFIG
if ([string]::IsNullOrEmpty($configPath)) {
    $configPath = Join-Path (Join-Path $env:USERPROFILE '.dsh') '.skill-publish\publish.config.json'
}

try {
    $stageCfg = 'config'
    $cfg = Read-Config -Path $configPath
}
catch {
    Write-Host ('ERROR: ' + $_.Exception.Message)
    exit 3
}

$script:WorkRepo = $cfg.work_repo
$script:StateDir = $cfg.state_dir
$script:Stage = 'config'

try {
    if (-not (Test-Path -LiteralPath $script:StateDir)) {
        New-Item -ItemType Directory -Force -Path $script:StateDir | Out-Null
    }
    $logDir = Join-Path $script:StateDir 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    $script:LogFile = Join-Path $logDir ('publish-' + (Get-Date -Format 'yyyy-MM') + '.log')
}
catch {
    Write-Host ('ERROR: cannot create state dir: ' + $_.Exception.Message)
    exit 3
}

try {
    Write-Log ('publish-dsh-skills start (dry_run=' + [string][bool]$DryRun + ', no_push=' + [string][bool]$NoPush + ')')

    if (-not (Test-Path -LiteralPath $cfg.source_dir)) { Fail 3 ('source_dir not found: ' + $cfg.source_dir) }
    if (-not (Test-Path -LiteralPath $cfg.token_file)) { Fail 3 ('token_file not found: ' + $cfg.token_file) }
    if (-not (Test-Path -LiteralPath $cfg.work_repo)) {
        $parent = Split-Path -Parent $cfg.work_repo
        if ($parent -and -not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
    }

    $script:Token = ([IO.File]::ReadAllText($cfg.token_file, [Text.Encoding]::UTF8)).Trim()
    if ($script:Token.Length -lt 8) { Fail 3 'token_file is empty or too short' }

    $mainBranch = [string]$cfg.branch_main
    if ([string]::IsNullOrEmpty($mainBranch)) { $mainBranch = 'main' }
    $dateFormat = [string]$cfg.date_format
    if ([string]::IsNullOrEmpty($dateFormat)) { $dateFormat = 'yyyy-MM-dd' }

    if ([string]::IsNullOrEmpty($DateStamp)) { $DateStamp = (Get-Date).ToString($dateFormat) }
    if ($DateStamp -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { Fail 3 ('invalid date branch name: ' + $DateStamp) }
    $script:State.date_branch = $DateStamp

    $remoteUri = [Uri]$cfg.remote_url
    $authUrl = 'https://' + $cfg.user + ':' + $script:Token + '@' + $remoteUri.Host + $remoteUri.AbsolutePath

    # ---- repository (bootstrap before the snapshot so the work tree exists)
    if (-not $DryRun) {
        $script:Stage = 'repo'
        if (-not (Test-Path -LiteralPath $script:WorkRepo)) {
            Write-Log ('cloning ' + $cfg.remote_url + ' into ' + $script:WorkRepo)
            # Clone through the public URL on purpose: the token must never land
            # in .git/config via remote.origin.url.  Pushes pass it inline.
            $r = Invoke-Git -ArgList @('clone', '--no-checkout', $cfg.remote_url, $script:WorkRepo) -TimeoutSec 300
            if ($r.Code -ne 0) { Fail 3 ('git clone failed: ' + $r.Out) }
        }
        $originUrl = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'remote', 'get-url', 'origin')
        if ($originUrl.Code -eq 0 -and $originUrl.Out.Trim() -match '@') {
            $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'remote', 'set-url', 'origin', $cfg.remote_url)
            Write-Log 'scrubbed credentials from remote.origin.url'
        }
        $r = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'rev-parse', '--git-dir')
        if ($r.Code -ne 0) { Fail 3 ('work_repo is not a git repository: ' + $script:WorkRepo) }

        $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'config', 'core.autocrlf', 'false')
        $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'config', 'core.safecrlf', 'false')
        $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'config', 'user.name', [string]$cfg.author_name)
        $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'config', 'user.email', [string]$cfg.author_email)

        $head = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'rev-parse', '--verify', 'HEAD')
        if ($head.Code -ne 0) {
            Write-Log 'repository has no commit yet, preparing an unborn main branch'
            $null = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'symbolic-ref', 'HEAD', ('refs/heads/' + $mainBranch))
        }
        else {
            $branch = Invoke-Git -ArgList @('-C', $script:WorkRepo, 'rev-parse', '--abbrev-ref', 'HEAD')
            if ($branch.Code -eq 0 -and $branch.Out.Trim() -ne $mainBranch) {
                $co = Invoke-RepoGit -ArgList @('checkout', '-f', $mainBranch)
                if ($co.Code -ne 0) { Fail 3 ('cannot switch work_repo to ' + $mainBranch + ': ' + $co.Out) }
            }
        }
    }

    # ---- snapshot destination -------------------------------------------
    $script:Stage = 'snapshot'
    if ($DryRun) {
        $root = Join-Path $env:TEMP 'dsh-skills-publish-dryrun'
        if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        $skillsDst = Join-Path $root 'skills'
    }
    else {
        $root = $script:WorkRepo
        $skillsDst = Join-Path $root 'skills'
    }
    if (-not (Test-Path -LiteralPath $skillsDst)) { New-Item -ItemType Directory -Force -Path $skillsDst | Out-Null }

    $rc = 0
    & robocopy.exe $cfg.source_dir $skillsDst /MIR /XJ /R:1 /W:1 /NFL /NDL /NP /NJH /NJS `
        /XD '.git' 'node_modules' '__pycache__' '.venv' `
        /XF 'credentials.txt' '*.key' '*.pem' '*.p12' '*.pfx' '*.token' '.env' '.env.*' '*.pyc' '.DS_Store' 'Thumbs.db' | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { Fail 5 ('robocopy failed with rc=' + $rc) }
    Write-Log ('snapshot copied (robocopy rc=' + $rc + ')')

    # ---- generated files -------------------------------------------------
    $script:Stage = 'generate'
    $skills = @(Get-SkillTreeMeta -SkillsRoot $skillsDst)
    $fileCount = 0
    $totalBytes = 0
    foreach ($f in @(Get-ChildItem -LiteralPath $skillsDst -Recurse -File -Force)) {
        $fileCount++
        $totalBytes += $f.Length
    }
    $script:State.skill_count = $skills.Count
    $script:State.file_count = $fileCount
    $script:State.total_bytes = $totalBytes

    $templatePath = Join-Path $PSScriptRoot 'readme.template.md'
    Write-GeneratedFiles -RepoRoot $root -Skills $skills -FileCount $fileCount -TotalBytes $totalBytes -TemplatePath $templatePath
    Write-Log ('generated README.md and index.json for ' + $skills.Count + ' skills / ' + $fileCount + ' files / ' + $totalBytes + ' bytes')

    # ---- secret scan -----------------------------------------------------
    $script:Stage = 'secret-scan'
    $secretFiles = @($cfg.token_file)
    if ($cfg.extra_secret_files) { $secretFiles += @($cfg.extra_secret_files) }
    $hits = @(Invoke-SecretScan -Root $skillsDst -SecretFiles $secretFiles)
    if ($hits.Count -gt 0) {
        foreach ($h in $hits) { Write-Log ('SECRET HIT: ' + $h) 'ERROR' }
        Fail 4 ('secret scan refused to publish: ' + $hits.Count + ' hit(s), see log')
    }
    Write-Log 'secret scan clean'

    if ($DryRun) {
        Write-Log 'dry run finished, no git operation performed'
        $script:State.exit_code = 0
        Save-State
        Write-Host ''
        Write-Host '=== SUMMARY ==='
        Write-Host ('SKILLS=' + $skills.Count)
        Write-Host ('SNAPSHOT_FILES=' + $fileCount)
        Write-Host ('SNAPSHOT_BYTES=' + $totalBytes)
        Write-Host 'DRY_RUN=true'
        exit 0
    }

    # ---- commit ----------------------------------------------------------
    $script:Stage = 'commit'
    $add = Invoke-RepoGit -ArgList @('add', '-A')
    if ($add.Code -ne 0) { Fail 5 ('git add failed: ' + $add.Out) }

    $status = Invoke-RepoGit -ArgList @('status', '--porcelain')
    if ($status.Code -ne 0) { Fail 5 ('git status failed: ' + $status.Out) }
    $changed = ($status.Out.Trim().Length -gt 0)
    $script:State.changed = $changed

    if ($changed) {
        $msg = 'sync: dsh skills snapshot ' + $DateStamp + ' (' + $fileCount + ' files, ' + $totalBytes + ' bytes)'
        $msgFile = Join-Path $env:TEMP ('dsh-skills-commit-' + [guid]::NewGuid().ToString('N') + '.txt')
        [IO.File]::WriteAllText($msgFile, $msg + "`n", (Get-Utf8NoBom))
        $commit = Invoke-RepoGit -ArgList @('commit', '-F', $msgFile) -TimeoutSec 120
        Remove-Item -LiteralPath $msgFile -Force -ErrorAction SilentlyContinue
        if ($commit.Code -ne 0) { Fail 5 ('git commit failed: ' + $commit.Out) }
        Write-Log ('committed: ' + $msg)
    }
    else {
        Write-Log 'NO_CHANGE: working tree already matches the last snapshot'
    }

    $headSha = (Invoke-RepoGit -ArgList @('rev-parse', 'HEAD')).Out.Trim()
    if ($headSha -notmatch '^[0-9a-f]{40}$') { Fail 5 ('cannot resolve HEAD: ' + $headSha) }
    $script:State.head_sha = $headSha
    $script:State.new_commit = $headSha

    # ---- push ------------------------------------------------------------
    $script:Stage = 'push'
    if ($NoPush) {
        Write-Log 'no_push requested, skipping push and verification'
        $script:State.exit_code = 0
        Save-State
        Write-Host ''
        Write-Host '=== SUMMARY ==='
        Write-Host ('SKILLS=' + $skills.Count)
        Write-Host ('SNAPSHOT_FILES=' + $fileCount)
        Write-Host ('SNAPSHOT_BYTES=' + $totalBytes)
        Write-Host ('HEAD=' + $headSha)
        Write-Host 'PUSH=skipped'
        exit 0
    }

    $pushMain = Invoke-RepoGit -ArgList @('push', $authUrl, ('HEAD:refs/heads/' + $mainBranch)) -TimeoutSec 600
    if ($pushMain.Code -ne 0) { Fail 6 ('push ' + $mainBranch + ' failed (rc=' + $pushMain.Code + '): ' + $pushMain.Out) }
    Write-Log ('pushed ' + $mainBranch)

    $pushDate = Invoke-RepoGit -ArgList @('push', $authUrl, ('HEAD:refs/heads/' + $DateStamp)) -TimeoutSec 600
    if ($pushDate.Code -ne 0) { Fail 6 ('push ' + $DateStamp + ' failed (rc=' + $pushDate.Code + '): ' + $pushDate.Out) }
    Write-Log ('pushed ' + $DateStamp)

    # ---- verify ----------------------------------------------------------
    $script:Stage = 'verify'
    $ls = Invoke-RepoGit -ArgList @('ls-remote', $authUrl, ('refs/heads/' + $mainBranch), ('refs/heads/' + $DateStamp)) -TimeoutSec 120
    if ($ls.Code -ne 0) { Fail 7 ('ls-remote failed: ' + $ls.Out) }

    $mainSha = ''
    $dateSha = ''
    foreach ($line in ($ls.Out -split "`r?`n")) {
        if ($line -match '^([0-9a-f]{40})\s+refs/heads/(.+)$') {
            if ($matches[2] -eq $mainBranch) { $mainSha = $matches[1] }
            elseif ($matches[2] -eq $DateStamp) { $dateSha = $matches[1] }
        }
    }
    $script:State.main_remote_sha = $mainSha
    $script:State.date_remote_sha = $dateSha
    if ([string]::IsNullOrEmpty($mainSha) -or [string]::IsNullOrEmpty($dateSha)) {
        Fail 7 ('one of the remote refs is missing (main=' + $mainSha + ', ' + $DateStamp + '=' + $dateSha + ')')
    }
    if ($mainSha -ne $dateSha -or $mainSha -ne $headSha) {
        Fail 7 ('ref mismatch: head=' + $headSha + ' main=' + $mainSha + ' ' + $DateStamp + '=' + $dateSha)
    }

    $script:State.exit_code = 0
    Save-State
    $alertPath = Join-Path $script:StateDir 'ALERT.md'
    if (Test-Path -LiteralPath $alertPath) { Remove-Item -LiteralPath $alertPath -Force }

    Write-Log ('OK: ' + $mainBranch + ' and ' + $DateStamp + ' both at ' + $headSha)
    Write-Host ''
    Write-Host '=== SUMMARY ==='
    Write-Host ('SKILLS=' + $skills.Count)
    Write-Host ('SNAPSHOT_FILES=' + $fileCount)
    Write-Host ('SNAPSHOT_BYTES=' + $totalBytes)
    Write-Host ('CHANGED=' + [string]$changed)
    Write-Host ('HEAD=' + $headSha)
    Write-Host ('MAIN=' + $mainSha)
    Write-Host ('DATE_BRANCH=' + $DateStamp)
    Write-Host 'EXIT=0'
    exit 0
}
catch {
    $msg = $_.Exception.Message
    if ([string]::IsNullOrEmpty($script:StateDir)) {
        Write-Host ('FATAL: ' + $msg)
        exit 8
    }
    Fail 8 ('unexpected: ' + $msg)
}
