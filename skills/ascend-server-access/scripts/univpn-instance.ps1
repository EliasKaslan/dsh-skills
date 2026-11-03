#requires -Version 5.1
<#
  univpn-instance.ps1 - drive a generated UniVPN instance (UniVPN2 / UVP002 ...) created by
  UsernameFull/univpn-multi, so a second VPN can stay online beside the original client.

  ASCII-only on purpose: Windows PowerShell 5.1 reads UTF-8-without-BOM as ANSI and would
  mangle any Chinese literal. Keep it that way.

  Examples:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\univpn-instance.ps1 -Action State  -Instance 2
    powershell -NoProfile -ExecutionPolicy Bypass -File .\univpn-instance.ps1 -Action Connect -Instance 2 -Profile A5 -Username vpn_xmz -Password '***'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\univpn-instance.ps1 -Action Disconnect -Instance 2

  Exit codes: 0 = connected / action ok, 3 = not connected, 2 = instance or window missing.
#>
param(
    [ValidateSet('State', 'Connect', 'Disconnect')]
    [string]$Action = 'State',
    [int]$Instance = 2,
    [string]$Profile,
    [string]$Username,
    [string]$Password,
    [int]$TimeoutSec = 90
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class UVPInstanceNative {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, IntPtr e);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr p);
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern int GetClassName(IntPtr hWnd, System.Text.StringBuilder s, int n);
}
'@

# ---------------------------------------------------------------- instance metadata
$stateRoot = 'C:\Program Files (x86)\UniVPN\.univpn-multi'
$jsonPath  = Join-Path $stateRoot ('instance-{0:D3}.json' -f $Instance)
if (-not (Test-Path -LiteralPath $jsonPath)) { throw "instance record not found: $jsonPath" }
$info = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
$product = $info.Product
$tapGuid = [string]$info.TapGuid

function Get-ClientProcess {
    Get-Process -Name $product -ErrorAction SilentlyContinue | Select-Object -First 1
}
function Get-MainWindow {
    $proc = Get-ClientProcess
    if (-not $proc) { return $null }
    $c = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
    $wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children, $c)
    foreach ($w in $wins) { if ($w.Current.AutomationId -eq 'MainUI') { return $w } }
    return $null
}
function Find-ById {
    param($Window, [string]$Id)
    if (-not $Window) { return $null }
    $c = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Id)
    $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
<#
  After a successful connect the Qt window hides into the tray and its whole accessibility
  subtree disappears. The only working way back is Qt's own "tray icon double-click" path;
  ShowWindow alone leaves a torn state (window painted, UIA still empty).
#>
function Restore-MainWindow {
    param([int]$TimeoutSec = 15)
    $w = Get-MainWindow
    if ($w) { Focus-ClientWindow $w; return $w }
    $proc = Get-ClientProcess
    if (-not $proc) { return $null }

    $script:trayHwnd = [IntPtr]::Zero
    $script:trayPid = $proc.Id
    $cb = [UVPInstanceNative+EnumWindowsProc] {
        param([IntPtr]$h, [IntPtr]$l)
        $p = 0
        [void][UVPInstanceNative]::GetWindowThreadProcessId($h, [ref]$p)
        if ($p -eq $script:trayPid) {
            $sb = New-Object System.Text.StringBuilder 256
            [void][UVPInstanceNative]::GetClassName($h, $sb, 256)
            if ($sb.ToString() -match 'TrayIconMessageWindow') { $script:trayHwnd = $h }
        }
        return $true
    }
    [void][UVPInstanceNative]::EnumWindows($cb, [IntPtr]::Zero)
    if ($script:trayHwnd -eq [IntPtr]::Zero) { return $null }

    $qtTrayNotify = 0x8000 + 101     # Qt MYWM_NOTIFYICON
    $wmDblClk = 0x0203
    [void][UVPInstanceNative]::PostMessage($script:trayHwnd, [uint32]$qtTrayNotify,
                                           [IntPtr]::Zero, [IntPtr]$wmDblClk)
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        Start-Sleep -Milliseconds 400
        $w = Get-MainWindow
        if ($w) { Focus-ClientWindow $w; return $w }
    }
    return $null
}
function Get-Tap {
    # InterfaceGuid is a STRING in Windows PowerShell 5.1 - never compare it to [guid].
    Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object { ([string]$_.InterfaceGuid) -eq $tapGuid } | Select-Object -First 1
}
function Click-El {
    param($El, [string]$What)
    if (-not $El) { throw "element not found: $What" }
    $r = $El.Current.BoundingRectangle
    $x = [int]($r.X + $r.Width / 2); $y = [int]($r.Y + $r.Height / 2)
    [void][UVPInstanceNative]::SetCursorPos($x, $y)
    Start-Sleep -Milliseconds 250
    [UVPInstanceNative]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [UVPInstanceNative]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 450
}
function Set-TextViaKeyboard {
    <# Qt's QLineEdit ignores UIA ValuePattern.SetValue here: click it, select all, type. #>
    param($El, [string]$Text, [string]$What)
    Click-El $El $What
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    Start-Sleep -Milliseconds 120
    [System.Windows.Forms.SendKeys]::SendWait($Text)
    Start-Sleep -Milliseconds 350
}
function Focus-ClientWindow {
    <#
      SetForegroundWindow is silently ignored unless the caller already owns the foreground,
      so a restored window can stay buried under a maximised terminal - and then every
      SetCursorPos + mouse_event click lands in THAT window instead (the client logs nothing).
      The HWND_TOPMOST/NOTOPMOST bounce raises the window without needing foreground rights.
    #>
    param($Window)
    if (-not $Window) { return }
    $h = [IntPtr]$Window.Current.NativeWindowHandle
    [void][UVPInstanceNative]::ShowWindow($h, 9)              # SW_RESTORE
    [void][UVPInstanceNative]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0001 -bor 0x0002 -bor 0x0040)  # HWND_TOPMOST, NOSIZE|NOMOVE|SHOWWINDOW
    Start-Sleep -Milliseconds 150
    [void][UVPInstanceNative]::SetWindowPos($h, [IntPtr](-2), 0, 0, 0, 0, 0x0001 -bor 0x0002)               # HWND_NOTOPMOST
    [void][UVPInstanceNative]::BringWindowToTop($h)
    [void][UVPInstanceNative]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 400
}
function Get-TunnelRoutes {
    param($Tap)
    if (-not $Tap) { return @() }
    @(Get-NetRoute -InterfaceIndex $Tap.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.DestinationPrefix -notmatch '/32$' -and $_.DestinationPrefix -ne '224.0.0.0/4' })
}
function Test-Connected {
    <#
      Truth = a subnet route pointing at the instance TAP. After a disconnect the TAP keeps
      its last virtual IP for a while and the UI can still show "successfully connect!"
      for a second or two, so neither the IP nor the status label can be trusted alone.
    #>
    param($Tap)
    if (-not $Tap -or $Tap.Status -ne 'Up') { return $false }
    $a = Get-NetIPAddress -InterfaceIndex $Tap.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if (-not $a -or $a.IPAddress -like '169.254.*') { return $false }
    return ((Get-TunnelRoutes $Tap).Count -gt 0)
}
function Get-State {
    $tap = Get-Tap
    $ip = $null
    if ($tap) {
        $a = Get-NetIPAddress -InterfaceIndex $tap.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
             Select-Object -First 1
        if ($a) { $ip = $a.IPAddress }
    }
    $w = Restore-MainWindow
    $selected = ''
    $statusText = ''
    if ($w) {
        $n = Find-ById $w 'MainUI.frame.w_left.label_netName'
        if ($n) { $selected = $n.Current.Name }
        $s = Find-ById $w 'MainUI.frame.w_left.lb_certifyStatus'
        if ($s) { $statusText = $s.Current.Name }
    }
    $routes = Get-TunnelRoutes $tap
    [pscustomobject]@{
        Product      = $product
        Instance     = $Instance
        Running      = [bool](Get-ClientProcess)
        TapName      = if ($tap) { $tap.Name } else { $null }
        TapIfIndex   = if ($tap) { $tap.ifIndex } else { $null }
        TapStatus    = if ($tap) { $tap.Status } else { $null }
        TapIP        = $ip
        StatusText   = $statusText
        Connected    = (Test-Connected $tap)
        TapRoutes    = ($routes | ForEach-Object { $_.DestinationPrefix }) -join ','
        SelectedName = $selected
    }
}

$main = Restore-MainWindow
if (-not $main -and $Action -ne 'State') { throw "$product GUI is not running (start it with the Open-UniVPN$Instance.cmd in the instance folder)" }
if ($main) {
    [void][UVPInstanceNative]::ShowWindow([IntPtr]$main.Current.NativeWindowHandle, 9)
    [void][UVPInstanceNative]::SetForegroundWindow([IntPtr]$main.Current.NativeWindowHandle)
    Start-Sleep -Milliseconds 500
}

switch ($Action) {
    'State' { Get-State | Format-List }

    'Disconnect' {
        $btn = Find-ById $main 'MainUI.frame.w_left.pushButton_disconnect'
        if (-not $btn) { 'not connected'; Get-State | Format-List; exit 3 }
        Click-El $btn 'disconnect'
        # The click returns before the client finishes logging out (~2 s: ssl logout finish,
        # routes pulled). Poll the ROUTE fingerprint - the status label and the TAP IP
        # both stay stale for a second or two and would report a false "still connected".
        $end = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $end) {
            Start-Sleep -Milliseconds 700
            if (-not (Test-Connected (Get-Tap))) { break }
        }
        Get-State | Format-List
        if ((Get-State).Connected) { exit 3 }
    }

    'Connect' {
        if (-not $Profile) { throw '-Profile is required for Connect' }
        $st = Get-State
        if ($st.Connected) {
            if ($st.SelectedName -eq $Profile) { "already connected to $Profile"; Get-State | Format-List; exit 0 }
            throw "instance is already connected to '$($st.SelectedName)'; disconnect first"
        }

        # 1) filter the connection list, then click the single row with a REAL mouse click
        $search = Find-ById $main 'MainUI.frame.le_select'
        if (-not $search) { throw 'search box MainUI.frame.le_select not found' }
        $search.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Profile)
        Start-Sleep -Milliseconds 900
        $list = Find-ById $main 'MainUI.frame.listWidget'
        $ct = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::ListItem)
        $items = @($list.FindAll([System.Windows.Automation.TreeScope]::Children, $ct))
        if ($items.Count -ne 1) {
            $search.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('')
            throw "search '$Profile' matched $($items.Count) entries (expected exactly 1)"
        }
        Click-El $items[0] "list item '$Profile'"

        # the click rebuilds the widget tree - re-resolve everything
        $main = Restore-MainWindow
        Click-El (Find-ById $main 'MainUI.frame.w_left.pushButton_connect') 'Connect'

        # 2) login form only appears when this instance has no stored credential
        $base = 'MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.'
        $loginDone = $false
        for ($i = 0; $i -lt 25; $i++) {
            Start-Sleep -Seconds 1
            $w = Restore-MainWindow
            $u = Find-ById $w ($base + 'le_username')
            if ($u) {
                if (-not $Username) { throw 'login form appeared but -Username was not supplied' }
                Set-TextViaKeyboard $u $Username 'username'
                if ($Password) { Set-TextViaKeyboard (Find-ById $w ($base + 'le_password')) $Password 'password' }
                # Tick "remember password" + "auto login" so the instance stores ProfileInfo in
                # its own sysconfig (RemPwd=1 / AutoLogin=1) and stops prompting - verified:
                # the next connect and even a full client restart then come up by themselves.
                foreach ($id in @('cb_savePass', 'cb_autoLogin')) {
                    try {
                        $cbEl = Find-ById $w ($base + $id)
                        if ($cbEl) {
                            $tp = $cbEl.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
                            if ($tp.Current.ToggleState -ne [System.Windows.Automation.ToggleState]::On) { $tp.Toggle() }
                        }
                    } catch { "  (could not toggle $id : $($_.Exception.Message))" }
                }
                Click-El (Find-ById $w 'MainUI.basewidget.frame.pb_login_SSL') 'Login'
                $loginDone = $true
                break
            }
            $t = Get-Tap
            if ($t -and $t.Status -eq 'Up') { break }
        }

        # 3) wait for the tunnel: TAP Up + non-APIPA IPv4 + a subnet route through it
        $end = (Get-Date).AddSeconds($TimeoutSec)
        while ((Get-Date) -lt $end) {
            if (Test-Connected (Get-Tap)) { break }
            Start-Sleep -Milliseconds 900
        }
        $st = Get-State
        $st | Format-List
        if ($st.Connected) { exit 0 } else { "login submitted: $loginDone"; exit 3 }
    }
}
