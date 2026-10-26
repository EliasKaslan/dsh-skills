<#
.SYNOPSIS
    Create / repair the daily DSH skills publish task on this machine.

.DESCRIPTION
    Registers (or replaces) the scheduled task that runs run_daily.cmd once a day.
    The task is registered as S4U -> "run whether the user is logged on or not",
    so no password is stored and no interactive session is required.
    WakeToRun is enabled so a sleeping machine wakes up for the run.
    StartWhenAvailable is enabled so a missed run is caught up after boot.

    The script elevates itself when started without administrator rights.

.PARAMETER TaskName
    Scheduled task name. Default: DSH-Skills-Publish

.PARAMETER At
    Daily start time, HH:mm. Default: 02:00

.PARAMETER RunNow
    Trigger the task once right after registering it.

.PARAMETER ExportPath
    Also export the registration XML to this path (for reference / audit).

.PARAMETER Uninstall
    Unregister the task instead of creating it.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File install-task.ps1 -RunNow

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File install-task.ps1 -ExportPath C:\Temp\task.xml

.NOTES
    ASCII only on purpose: Windows PowerShell 5.1 reads a BOM-less script as GBK.
    Exit codes: 0 ok, 3 elevation failed, 4 registration failed, 5 missing files.
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'DSH-Skills-Publish',
    [string]$At = '02:00',
    [switch]$RunNow,
    [string]$ExportPath,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$skillDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$runner = Join-Path $skillDir 'run_daily.cmd'
$publisher = Join-Path $skillDir 'publish-dsh-skills.ps1'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $PSCommandPath + '"'))
    if ($TaskName -ne 'DSH-Skills-Publish') { $argList += @('-TaskName', $TaskName) }
    if ($At -ne '02:00') { $argList += @('-At', $At) }
    if ($RunNow) { $argList += '-RunNow' }
    if ($ExportPath) { $argList += @('-ExportPath', ('"' + $ExportPath + '"')) }
    if ($Uninstall) { $argList += '-Uninstall' }

    Write-Host 'not elevated - relaunching with RunAs ...'
    try {
        $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -Verb RunAs -PassThru -Wait -WindowStyle Hidden
    }
    catch {
        Write-Host ('elevation failed: ' + $_.Exception.Message)
        exit 3
    }
    Write-Host ('elevated run finished, exit code = ' + $p.ExitCode)
    exit $p.ExitCode
}

if (-not (Test-Path -LiteralPath $runner)) {
    Write-Host ('missing runner: ' + $runner)
    exit 5
}
if (-not (Test-Path -LiteralPath $publisher)) {
    Write-Host ('missing publisher script: ' + $publisher)
    exit 5
}

if ($Uninstall) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host ('unregistered task: ' + $TaskName)
    }
    else {
        Write-Host ('task not present: ' + $TaskName)
    }
    exit 0
}

try {
    $user = $env:USERDOMAIN + '\' + $env:USERNAME
    $action = New-ScheduledTaskAction -Execute $runner
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -WakeToRun `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType S4U -RunLevel Limited

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force | Out-Null
}
catch {
    Write-Host ('registration failed: ' + $_.Exception.Message)
    Write-Host 'S4U registration needs an elevated shell and the "log on as a batch job" right.'
    exit 4
}

$t = Get-ScheduledTask -TaskName $TaskName
$i = $t | Get-ScheduledTaskInfo
Write-Host ''
Write-Host '=== registered ==='
Write-Host ('TaskName        : ' + $t.TaskName)
Write-Host ('State           : ' + $t.State)
Write-Host ('RunAs / Logon   : ' + $t.Principal.UserId + ' / ' + $t.Principal.LogonType)
Write-Host ('Action          : ' + $t.Actions[0].Execute)
Write-Host ('Daily at        : ' + $At)
Write-Host ('WakeToRun       : ' + $t.Settings.WakeToRun)
Write-Host ('StartWhenAvail  : ' + $t.Settings.StartWhenAvailable)
Write-Host ('NextRunTime     : ' + $i.NextRunTime)

if ($ExportPath) {
    Export-ScheduledTask -TaskName $TaskName | Out-File -FilePath $ExportPath -Encoding Unicode
    Write-Host ('exported XML    : ' + $ExportPath)
}

$cfgPath = Join-Path $env:USERPROFILE '.dsh\.skill-publish\publish.config.json'
if (-not (Test-Path -LiteralPath $cfgPath)) {
    Write-Host ''
    Write-Host ('WARNING: config not found -> ' + $cfgPath)
    Write-Host '         copy publish.config.example.json there and fill in token_file / remote_url.'
}

if ($RunNow) {
    Write-Host ''
    Write-Host 'triggering one run ...'
    Start-ScheduledTask -TaskName $TaskName
}

exit 0
