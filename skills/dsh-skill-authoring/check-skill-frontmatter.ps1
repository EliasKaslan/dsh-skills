param(
  [string]$SkillsRoot = (Join-Path $env:USERPROFILE '.dsh\skills'),
  [string]$YamlModule  = ''
)
# check-skill-frontmatter.ps1 - read-only validator for the "when to call" contract
# Run (PS 5.1 needs bypass):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\check-skill-frontmatter.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\check-skill-frontmatter.ps1 -SkillsRoot <dir>
#   -YamlModule <path> overrides the probe; an explicit MISSING path is honoured on purpose
#   (so the "round-trip skipped" branch stays forceable for fault tests).
# Exit code: 0 = no FAIL, 1 = FAIL present.
# ASCII-only on purpose: PS 5.1 decodes BOM-less .ps1 as GBK and mojibake breaks the parser.
#
# Per-skill checks = SHAPE + YAML ROUND-TRIP.
#   FAIL: NO_SKILL_MD / NO_FRONTMATTER / YAML_UNPARSEABLE(<yaml.parse error, first line>)
#         / YAML_DESC_NOT_STRING(<type>) / NAME_MISSING / NAME_BAD_FORMAT(<name>)
#         / NAME_NE_DIR(<name>) / CAMELCASE_KEY_REJECTS_SKILL / DESC_MISSING
#         / DESC_OVER_TRUNCATION(<len>)      <- len > 500: catalog keeps first 497 + "..."
#         / DESC_NO_APPLIES / DESC_NO_DISAMBIG / DESC_POINTS_TO_BODY
#         / WHENTOUSE_TOO_LONG(<len>)        <- len > 160 (hard, no spec source: a loose backstop)
#   R6 (THE spec, D:\workspace\agent\skill\_recon\skill-when-to-call-standard.md L30) says
#   whenToUse <= 150. $whenSoftMax = 150 below enforces the NORM; 160 is only a safety valve,
#   so 151..160 is a deliberate non-fatal WARN -- do not treat 160 as the contract.
#         / BODY_NO_WHEN_SECTION
#   WARN: DESC_OVER_BUDGET(<len>)            <- 480 < len <= 500: no truncation yet, no headroom
#         / WHENTOUSE_MISSING / WHENTOUSE_OVER(<len>) / FRONTMATTER_MULTILINE
#         / BODY_HAS_OLD_HEADING / DESC_LEN_NE_YAML(ps=<n>,yaml=<m>)
#         / YAML_NOT_CHECKED  <- node or the yaml package missing: see the loud banner
#
# WHY THE ROUND-TRIP IS THE CHECK THAT MATTERS: shape alone gives a FALSE OK. A halfwidth ": "
# inside a YAML plain scalar is a nested-mapping indicator, so yaml.parse() throws and
# dsh-skill-filesystem/lib/index.js:669-674 catches, logs ONE logger.warn and throws the WHOLE
# skill away -> it never enters the session catalog, with no other error anywhere. The file
# still looks perfectly compliant to every shape check in this script.
# If node or the yaml package is unavailable this script prints a loud WARN instead of silently
# skipping the round-trip (a silent skip would just be one more false OK). The yaml package is
# AUTO-DETECTED among candidates (DSH_YAML_MODULE env -> launcher\runtime -> npm-cache\_npx\* ->
# the legacy ~\.dsh\profiles path); a bare run on this box now yields YAML_SKIP=0.

$ErrorActionPreference = 'Stop'
$descHardMax = 500      # > this: DSH truncates to first 497 chars + "..." (dsh-tool-skill/lib/index.js:40)
$descSoftMax = 480      # > this and <= 500: WARN (budget from skill-when-to-call-standard.md)
$whenSoftMax = 150      # SPEC value: skill-when-to-call-standard.md L30 (R6) + L149 -- the norm, not a guess
$whenHardMax = 160      # SELF-INVENTED backstop, NO spec source: the standard names only 150 for whenToUse.
                        #   CONSULT THE STANDARD BEFORE CHANGING THIS NUMBER. Raising it makes real
                        #   over-length FAILs disappear; lowering it to 150 silently turns the intended
                        #   non-fatal WHENTOUSE_OVER WARN into a hard FAIL. Kept at 160 = behaviour unchanged.

function U([int[]]$cp) { -join ($cp | ForEach-Object { [char]$_ }) }
$P_APPLIES    = U 0x9002, 0x7528, 0x4E8E              # Applies-to marker
$P_NOTAPPLIES = U 0x4E0D, 0x9002, 0x7528              # Does-not-apply marker
$P_WHEN       = U 0x4F55, 0x65F6, 0x8C03, 0x7528      # "when to call" heading text
$P_TRIGGER    = U 0x89E6, 0x53D1, 0x6761, 0x4EF6      # legacy "trigger" heading text
$P_SEE        = U 0x8BE6, 0x89C1                      # "see details" spoiler

# --- YAML round-trip probe (runs once per skill) --------------------------------
# argv[1] = yaml module path, argv[2] = SKILL.md path. Exit codes:
#   0 = parsed (stdout "OK <name> <descLength>")
#   2 = yaml.parse threw (stdout "FAIL <first line of the error>")
#   3 = no frontmatter block seen (stdout "NOFM")
#   4 = frontmatter is not a mapping / description is not a plain scalar string
#   5 = yaml module could not be required
$yamlProbe = @'
const fs = require('fs');
let Y;
try { Y = require(process.argv[1]); }
catch (e) { console.log('NOMOD ' + String(e.message).split('\n')[0]); process.exit(5); }
const raw = fs.readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, '');
const m = raw.match(/^---\r?\n([\s\S]*?)\r?\n---/);
if (!m) { console.log('NOFM'); process.exit(3); }
let d;
try { d = Y.parse(m[1]); }
catch (x) { console.log('FAIL ' + String(x.message).split('\n')[0]); process.exit(2); }
if (d === null || typeof d !== 'object') { console.log('BADROOT ' + (d === null ? 'null' : typeof d)); process.exit(4); }
if (typeof d.description !== 'string') { console.log('DESCTYPE ' + typeof d.description); process.exit(4); }
console.log('OK ' + String(d.name) + ' ' + d.description.length);
'@

$nodeExe = $null
$cmd = Get-Command node -ErrorAction SilentlyContinue
if ($cmd) { $nodeExe = $cmd.Source }

# --- yaml module auto-probe ------------------------------------------------------
# The old static default (~\.dsh\profiles\node_modules\yaml) does NOT exist on this box, so a
# bare run used to degrade to YAML_SKIP=N / status=ok / exit 0 with only a WARN banner -- the
# same false OK the round-trip exists to prevent. Detect the first existing candidate instead;
# pass -YamlModule <path> to override (a missing explicit path is still honoured on purpose, so
# the failure branch stays forceable).
$yamlCandidates = @()
if ($env:DSH_YAML_MODULE) { $yamlCandidates += $env:DSH_YAML_MODULE }
$yamlCandidates += (Join-Path $env:USERPROFILE '.dsh\launcher\runtime\node_modules\yaml')
$yamlCandidates += (Join-Path $env:LOCALAPPDATA 'npm-cache\_npx\*\node_modules\yaml')
$yamlCandidates += (Join-Path $env:USERPROFILE '.dsh\profiles\node_modules\yaml')
if (-not $YamlModule) {
  foreach ($cand in $yamlCandidates) {
    if (Test-Path -LiteralPath $cand) { $YamlModule = $cand; break }
  }
}
$yamlWhy = $null
if (-not $nodeExe) {
  $yamlWhy = 'node not found on PATH'
} elseif (-not (Test-Path -LiteralPath $YamlModule)) {
  $yamlWhy = ('yaml module not found at ' + $YamlModule)
} else {
  $pre = & $nodeExe -e "require(process.argv[1]); console.log('YAML_MODULE_OK')" $YamlModule 2>&1
  if ($LASTEXITCODE -ne 0) { $yamlWhy = ('cannot require yaml module at ' + $YamlModule + ' : ' + (($pre | Select-Object -First 1) -as [string])) }
}
$yamlOk = ($null -eq $yamlWhy)

function Test-YamlFrontmatter([string]$Path) {
  $out = & $script:nodeExe -e $script:yamlProbe $script:YamlModule $Path 2>&1
  $code = $LASTEXITCODE
  $line = [string]($out | Select-Object -First 1)
  return [pscustomobject]@{ code = $code; text = $line }
}

function Get-Field([string[]]$fm, [string]$key) {
  $line = $fm | Where-Object { $_ -match ('^' + [regex]::Escape($key) + '\s*:') } | Select-Object -First 1
  if (-not $line) { return $null }
  return ($line -replace ('^' + [regex]::Escape($key) + '\s*:\s*'), '').Trim()
}

if (-not $yamlOk) {
  Write-Host ''
  Write-Host '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
  Write-Host ('WARN: YAML round-trip NOT performed (' + $yamlWhy + ').')
  Write-Host 'WARN: THIS RESULT IS NOT TRUSTWORTHY. A skill whose description makes yaml.parse()'
  Write-Host 'WARN: throw still passes every shape check below, but the loader drops the whole'
  Write-Host 'WARN: skill (one logger.warn only) and it silently vanishes from the catalog.'
  Write-Host 'WARN: Fix node / the yaml module (or pass -YamlModule <path>) and run again.'
  Write-Host '!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'
  Write-Host ''
}

$rows = @()
$failCount = 0
$warnCount = 0
$yamlFail = 0
$yamlSkip = 0

Get-ChildItem $SkillsRoot -Directory | Sort-Object Name | ForEach-Object {
  $dir = $_
  $file = Join-Path $dir.FullName 'SKILL.md'
  $issues = @()
  $warns = @()
  $dLen = 0; $wLen = 0; $name = ''
  $yamlCol = 'SKIP'
  $yamlDescLen = -1   # description length as yaml.parse() sees it; -1 = not measured

  if (-not (Test-Path $file)) {
    $issues += 'NO_SKILL_MD'
  } else {
    $raw = Get-Content -LiteralPath $file -Encoding utf8
    $joined = ($raw -join "`n")
    if ($joined -notmatch '(?s)^\s*---\s*\n(.*?)\n---') {
      $issues += 'NO_FRONTMATTER'
    } else {
      $fm = $Matches[1] -split "`n"
      $name = Get-Field $fm 'name'
      $desc = Get-Field $fm 'description'
      $when = Get-Field $fm 'whenToUse'

      # --- YAML round-trip: the only check that proves the loader can see this skill ---
      if (-not $yamlOk) {
        $yamlCol = 'SKIP'
        $warns += 'YAML_NOT_CHECKED'
        $yamlSkip++
      } else {
        $yr = Test-YamlFrontmatter $file
        switch ($yr.code) {
          0 {
            $yamlCol = 'ok'
            $parts = $yr.text -split ' '
            if ($parts.Count -ge 3) { [void][int]::TryParse($parts[2], [ref]$yamlDescLen) }
          }
          2 {
            $yamlCol = 'FAIL'
            $yamlFail++
            $issues += ('YAML_UNPARSEABLE(' + ($yr.text -replace '^FAIL\s*', '') + ')')
          }
          3 {
            $yamlCol = 'FAIL'
            $yamlFail++
            $issues += 'YAML_UNPARSEABLE(yaml probe saw no frontmatter block)'
          }
          4 {
            $yamlCol = 'FAIL'
            $yamlFail++
            if ($yr.text -match '^DESCTYPE\s+(\S+)') {
              $issues += ('YAML_DESC_NOT_STRING(' + $Matches[1] + ')')
            } else {
              $issues += ('YAML_FRONTMATTER_NOT_MAPPING(' + ($yr.text -replace '^BADROOT\s*', '') + ')')
            }
          }
          default {
            $yamlCol = 'FAIL'
            $yamlFail++
            $issues += ('YAML_PROBE_ERROR(' + $yr.text + ')')
          }
        }
      }

      if (-not $name) { $issues += 'NAME_MISSING' }
      elseif ($name -notmatch '^[a-z0-9]+(?:-[a-z0-9]+)*$') { $issues += "NAME_BAD_FORMAT($name)" }
      elseif ($name -ne $dir.Name) { $issues += "NAME_NE_DIR($name)" }

      if ($fm | Where-Object { $_ -match '^\s*(disableModelInvocation|modelInvocable|userInvocable)\s*:' }) {
        $issues += 'CAMELCASE_KEY_REJECTS_SKILL'
      }
      if ($fm | Where-Object { $_ -match '^\s+[-A-Za-z]' }) { $warns += 'FRONTMATTER_MULTILINE' }

      if (-not $desc) {
        $issues += 'DESC_MISSING'
      } else {
        $dLen = $desc.Length
        if ($dLen -gt $descHardMax) { $issues += "DESC_OVER_TRUNCATION($dLen)" }
        elseif ($dLen -gt $descSoftMax) { $warns += "DESC_OVER_BUDGET($dLen)" }
        if ($desc -notmatch $P_APPLIES) { $issues += 'DESC_NO_APPLIES' }
        if ($desc -notmatch $P_NOTAPPLIES) { $issues += 'DESC_NO_DISAMBIG' }
        if ($desc -match ($P_SEE + '\s*SKILL\.md')) { $issues += 'DESC_POINTS_TO_BODY' }
        # PS regex length vs yaml.parse length: a mismatch means quoting/folding/whitespace
        # differs between what this script measures and what the loader will actually see.
        if ($yamlDescLen -ge 0 -and $yamlDescLen -ne $dLen) {
          $warns += ("DESC_LEN_NE_YAML(ps=$dLen,yaml=$yamlDescLen)")
        }
      }

      if (-not $when) { $warns += 'WHENTOUSE_MISSING' }
      else {
        $wLen = $when.Length
        if ($wLen -gt $whenHardMax) { $issues += "WHENTOUSE_TOO_LONG($wLen)" }
        elseif ($wLen -gt $whenSoftMax) { $warns += "WHENTOUSE_OVER($wLen)" }
      }

      # Heading checks run on PROSE only: a skill may legitimately *document* these headings
      # (templates, before/after examples) inside a fenced block or an inline code span
      # without having them as real sections. Without this strip, such a skill gets a
      # bogus BODY_HAS_OLD_HEADING warn and a template-only file can even fake BODY_NO_WHEN_SECTION.
      $prose = ($joined -replace '(?s)```.*?```', '') -replace '`[^`\n]*`', ''
      if ($prose -notmatch ('##\s*' + $P_WHEN)) { $issues += 'BODY_NO_WHEN_SECTION' }
      if ($prose -match ('##\s*' + $P_TRIGGER)) { $warns += 'BODY_HAS_OLD_HEADING' }
    }
  }

  if ($issues.Count -gt 0) { $failCount++ }
  if ($warns.Count -gt 0) { $warnCount++ }
  $rows += [pscustomobject]@{
    skill  = $dir.Name
    status = $(if ($issues.Count -gt 0) { 'FAIL' } else { 'ok' })
    yaml   = $yamlCol
    desc   = $dLen
    when   = $wLen
    issues = ($issues -join ',')
    warns  = ($warns -join ',')
  }
}

$rows | Format-Table -AutoSize | Out-String -Width 400 | Write-Host
Write-Host ("TOTAL={0}  FAIL={1}  WARN={2}  YAML_FAIL={3}  YAML_SKIP={4}" -f $rows.Count, $failCount, $warnCount, $yamlFail, $yamlSkip)
if (-not $yamlOk) { Write-Host 'WARN: YAML round-trip was skipped -- the FAIL/WARN counts above are NOT trustworthy.' }
if ($failCount -gt 0) { exit 1 } else { exit 0 }
