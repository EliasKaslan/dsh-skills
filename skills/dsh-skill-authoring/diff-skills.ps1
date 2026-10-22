param(
  [Parameter(Mandatory=$true)][string]$Backup,
  [string]$SkillsRoot = (Join-Path $env:USERPROFILE '.dsh\skills'),
  [int]$MaxRemoved = 3
)
# diff-skills.ps1 - prove that an edit round touched ONLY frontmatter + the "when to call" section.
# Method: strip the frontmatter from both sides, remove the old trigger section from the old body
# and the new when-to-call section from the new body, then line-diff the REMAINDER.
# A clean run means: every other line of the technical body is byte-identical.
# Run (PS 5.1, no pwsh on this box):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\diff-skills.ps1 -Backup <backup dir>
# Exit code: 0 = every skill's remainder is unchanged; 1 = something outside the allowed area changed.
# ASCII-only on purpose (PS 5.1 decodes BOM-less .ps1 as GBK; CJK literals break the parser).

$ErrorActionPreference = 'Stop'
function U([int[]]$cp) { -join ($cp | ForEach-Object { [char]$_ }) }
$WHEN    = U 0x4F55, 0x65F6, 0x8C03, 0x7528   # when-to-call heading
$TRIGGER = U 0x89E6, 0x53D1, 0x6761, 0x4EF6   # legacy trigger heading

function Split-Front([string[]]$lines) {
  # returns @{ fm = frontmatter lines; body = everything after the closing --- }
  if ($lines.Count -lt 3 -or $lines[0].Trim() -ne '---') { return @{ fm = @(); body = $lines } }
  for ($i = 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq '---') {
      return @{ fm = $lines[1..($i-1)]; body = $(if ($i + 1 -lt $lines.Count) { $lines[($i+1)..($lines.Count-1)] } else { @() }) }
    }
  }
  return @{ fm = @(); body = $lines }
}

function Drop-Section([string[]]$body, [string]$heading) {
  # drop the heading line through the line before the next '## ' heading
  $start = -1
  for ($i = 0; $i -lt $body.Count; $i++) {
    if ($body[$i] -match ('^##\s*' + $heading)) { $start = $i; break }
  }
  if ($start -lt 0) { return @{ rest = $body; found = $false } }
  $end = $body.Count
  for ($i = $start + 1; $i -lt $body.Count; $i++) {
    if ($body[$i] -match '^##\s') { $end = $i; break }
  }
  $rest = @()
  if ($start -gt 0) { $rest += $body[0..($start-1)] }
  if ($end -lt $body.Count) { $rest += $body[$end..($body.Count-1)] }
  return @{ rest = $rest; found = $true }
}

function Get-Field([string[]]$fm, [string]$key) {
  $line = $fm | Where-Object { $_ -match ('^' + [regex]::Escape($key) + '\s*:') } | Select-Object -First 1
  if (-not $line) { return $null }
  return ($line -replace ('^' + [regex]::Escape($key) + '\s*:\s*'), '').Trim()
}

$bad = 0
$report = @()
Get-ChildItem $Backup -Directory | Sort-Object Name | ForEach-Object {
  $skill = $_.Name
  $oldFile = Join-Path $_.FullName 'SKILL.md'
  $newFile = Join-Path (Join-Path $SkillsRoot $skill) 'SKILL.md'
  if (-not (Test-Path $newFile)) { $report += "MISSING_NEW  $skill"; $bad++; return }
  if (-not (Test-Path $oldFile)) { $report += "NEW_SKILL    $skill (no backup counterpart - review manually)"; return }

  $o = Split-Front (Get-Content -LiteralPath $oldFile -Encoding utf8)
  $n = Split-Front (Get-Content -LiteralPath $newFile -Encoding utf8)

  # frontmatter: which keys changed
  $keys = @('name','description','whenToUse','disable-model-invocation','user-invocable')
  $fmChanges = @()
  foreach ($k in $keys) {
    $ov = Get-Field $o.fm $k; $nv = Get-Field $n.fm $k
    if ($ov -ne $nv) { $fmChanges += ("{0}({1}->{2})" -f $k, $(if($ov){$ov.Length}else{'-'}), $(if($nv){$nv.Length}else{'-'})) }
  }
  $oKeys = ($o.fm | ForEach-Object { ($_ -split ':')[0].Trim() })
  $nKeys = ($n.fm | ForEach-Object { ($_ -split ':')[0].Trim() })
  $extraKeys = (Compare-Object $oKeys $nKeys | Where-Object SideIndicator -eq '=>' | ForEach-Object InputObject) -join ','

  $oldRest = (Drop-Section $o.body $TRIGGER).rest
  $oldRest = (Drop-Section $oldRest $WHEN).rest
  $newRest = (Drop-Section $n.body $WHEN).rest
  $newRest = (Drop-Section $newRest $TRIGGER).rest

  # Primary evidence: the remainder must be IDENTICAL, compared as one block.
  # (Line-alignment diffing is not evidence here: a mid-file insertion shifts every later line.)
  $exact = (($oldRest -join "`n") -ceq ($newRest -join "`n"))
  $d = Compare-Object $oldRest $newRest -SyncWindow 5
  $removed = @($d | Where-Object SideIndicator -eq '<=' | ForEach-Object InputObject | Where-Object { $_.Trim() -ne '' })
  $added   = @($d | Where-Object SideIndicator -eq '=>' | ForEach-Object InputObject | Where-Object { $_.Trim() -ne '' })

  $verdict = 'CLEAN'
  if (-not $exact) { $verdict = 'REVIEW'; $bad++ }
  $report += ("{0,-34} {1,-7} exact={2,-5} body={3}->{4} fm[{5}] extraKeys=[{6}] added={7} removed={8}" -f `
      $skill, $verdict, $exact, $o.body.Count, $n.body.Count, ($fmChanges -join ' '), $extraKeys, $added.Count, $removed.Count)
  if ($verdict -eq 'REVIEW') {
    foreach ($r in ($removed | Select-Object -First 8)) { $report += ("    -REMOVED> " + $r.Substring(0, [Math]::Min(120, $r.Length))) }
    foreach ($a in ($added | Select-Object -First 8))   { $report += ("    +ADDED  > " + $a.Substring(0, [Math]::Min(120, $a.Length))) }
  }
}

$report | Write-Host
Write-Host ("`nSKILLS_REVIEWED={0}  OUTSIDE_ALLOWED_AREA={1}" -f (Get-ChildItem $Backup -Directory).Count, $bad)
Write-Host "verdict: CLEAN = body outside frontmatter/when-section is identical to backup"
if ($bad -gt 0) { exit 1 } else { exit 0 }
