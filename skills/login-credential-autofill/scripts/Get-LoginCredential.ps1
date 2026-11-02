# Get-LoginCredential.ps1 -- read ONE field of ONE account from the local store.
# ASCII only on purpose: Windows PowerShell 5.1 misparses UTF-8 (no BOM) with CJK text.
# Exit codes: 0 ok | 3 store/account problem | 4 password requested without -Reveal
param(
    [Parameter(Mandatory = $true)][ValidateSet('microsoft', 'github')][string]$Account,
    [ValidateSet('identifier', 'username', 'password', 'flags')][string]$Field = 'identifier',
    [string]$StorePath = "$env:USERPROFILE\.dsh\.secrets\accounts.json",
    [switch]$Reveal
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $StorePath)) {
    Write-Output "MISSING_STORE $StorePath"
    exit 3
}

try {
    $store = Get-Content -LiteralPath $StorePath -Raw -Encoding utf8 | ConvertFrom-Json
} catch {
    Write-Output ("BAD_STORE {0}" -f $_.Exception.Message)
    exit 3
}

$acc = $store.accounts.$Account
if ($null -eq $acc) {
    Write-Output "NO_ACCOUNT $Account"
    exit 3
}

switch ($Field) {
    'identifier' { Write-Output ([string]$acc.identifier) }
    'username'   { Write-Output ([string]$acc.username) }
    'flags'      { Write-Output ("mfa={0} auto_submit={1}" -f $acc.mfa, $acc.auto_submit) }
    'password' {
        if (-not $Reveal) {
            Write-Output ("HIDDEN len={0}  reuse with -Reveal only at the moment of typing" -f ([string]$acc.password).Length)
            exit 4
        }
        Write-Output ([string]$acc.password)
    }
    default {
        Write-Output 'BAD_FIELD'
        exit 3
    }
}
exit 0
