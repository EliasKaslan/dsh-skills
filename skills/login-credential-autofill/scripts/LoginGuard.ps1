# LoginGuard.ps1 -- per-account attempt budget for automated logins.
# ASCII only on purpose: Windows PowerShell 5.1 misparses UTF-8 (no BOM) with CJK text.
# Exit codes: 0 allow / recorded | 3 deny / error
param(
    [Parameter(Mandatory = $true)][ValidateSet('check', 'attempt', 'fail', 'success', 'lock', 'status')][string]$Action,
    [Parameter(Mandatory = $true)][string]$Account,
    [string]$Reason = '',
    [string]$LedgerPath = "$env:USERPROFILE\.dsh\.secrets\.login-ledger.json",
    [int]$MaxAttemptsPer24h = 1,
    [int]$CooldownMinutes = 60,
    [int]$LockHours = 24
)

$ErrorActionPreference = 'Stop'
$now = [DateTime]::UtcNow
$iso = { param($d) $d.ToString('o') }
$parse = { param($s) if ([string]::IsNullOrWhiteSpace($s)) { $null } else { [DateTime]::Parse($s, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() } }

if (Test-Path -LiteralPath $LedgerPath) {
    try {
        $ledger = Get-Content -LiteralPath $LedgerPath -Raw -Encoding utf8 | ConvertFrom-Json
    } catch {
        Write-Output ("BAD_LEDGER {0}" -f $_.Exception.Message)
        exit 3
    }
} else {
    $ledger = [pscustomobject]@{ version = 1; accounts = [pscustomobject]@{} }
}

if ($null -eq $ledger.accounts) {
    $ledger | Add-Member -NotePropertyName accounts -NotePropertyValue ([pscustomobject]@{}) -Force
}

$entry = $null
if ($ledger.accounts.PSObject.Properties.Name -contains $Account) {
    $entry = $ledger.accounts.$Account
} else {
    $entry = [pscustomobject]@{
        attemptsUtc        = [string[]]@()
        lastAttemptUtc     = ''
        lastResult         = ''
        failCount          = 0
        lockedUntilUtc     = ''
        lockReason         = ''
    }
    $ledger.accounts | Add-Member -NotePropertyName $Account -NotePropertyValue $entry -Force
}

$attempts = @()
if ($null -ne $entry.attemptsUtc) { $attempts = @($entry.attemptsUtc | Where-Object { $_ }) }
$recent = @($attempts | Where-Object { $d = & $parse $_; $d -and ($now - $d).TotalHours -lt 24 })
$lastAttempt = & $parse $entry.lastAttemptUtc
$lockedUntil = & $parse $entry.lockedUntilUtc

function Save-Ledger {
    $dir = Split-Path -Parent $LedgerPath
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($ledger | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $LedgerPath -Encoding utf8
}

switch ($Action) {
    'check' {
        if ($lockedUntil -and $lockedUntil -gt $now) {
            Write-Output ("DENY account={0} locked_until={1} reason={2}" -f $Account, (& $iso $lockedUntil), $entry.lockReason)
            exit 3
        }
        if ($entry.lastResult -eq 'fail' -and $lastAttempt -and ($now - $lastAttempt).TotalMinutes -lt $CooldownMinutes) {
            $left = [math]::Ceiling($CooldownMinutes - ($now - $lastAttempt).TotalMinutes)
            Write-Output ("DENY account={0} cooldown_left_minutes={1} last=fail" -f $Account, $left)
            exit 3
        }
        if ($recent.Count -ge $MaxAttemptsPer24h) {
            Write-Output ("DENY account={0} attempts_24h={1} max={2}" -f $Account, $recent.Count, $MaxAttemptsPer24h)
            exit 3
        }
        Write-Output ("ALLOW account={0} attempts_24h={1} max={2} left={3}" -f $Account, $recent.Count, $MaxAttemptsPer24h, ($MaxAttemptsPer24h - $recent.Count))
        exit 0
    }
    'attempt' {
        $attempts = @($recent) + @(& $iso $now)   # prune anything older than 24h
        $entry.attemptsUtc = [string[]]@($attempts)
        $entry.lastAttemptUtc = & $iso $now
        Save-Ledger
        $newCount = @($attempts).Count
        Write-Output ("RECORDED_ATTEMPT account={0} attempts_24h={1}" -f $Account, $newCount)
        exit 0
    }
    'fail' {
        $entry.lastResult = 'fail'
        $entry.failCount = [int]$entry.failCount + 1
        $entry.lastAttemptUtc = & $iso $now
        Save-Ledger
        Write-Output ("RECORDED_FAIL account={0} failCount={1} cooldown_minutes={2}" -f $Account, $entry.failCount, $CooldownMinutes)
        exit 0
    }
    'success' {
        $entry.lastResult = 'success'
        $entry.failCount = 0
        $entry.lockedUntilUtc = ''
        $entry.lockReason = ''
        Save-Ledger
        Write-Output ("RECORDED_SUCCESS account={0}" -f $Account)
        exit 0
    }
    'lock' {
        $entry.lockedUntilUtc = & $iso $now.AddHours($LockHours)
        $entry.lockReason = if ($Reason) { $Reason } else { 'challenge' }
        $entry.lastResult = 'challenge'
        Save-Ledger
        Write-Output ("LOCKED account={0} until={1} reason={2}" -f $Account, $entry.lockedUntilUtc, $entry.lockReason)
        exit 0
    }
    'status' {
        Write-Output ($entry | ConvertTo-Json -Depth 6 -Compress)
        exit 0
    }
}

Write-Output 'BAD_ACTION'
exit 3
