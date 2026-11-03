#Requires -Version 5.1
<#
  vpnctl.ps1 —— 联软 Leagsoft UniVPN 客户端控制（本机 C:\Program Files (x86)\UniVPN）

  用法（本机没有 pwsh，只有 Windows PowerShell 5.1，必须显式 Bypass）：
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action State
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action State -TestHosts 192.168.13.188
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Connect -Profile 蓝区网关
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Disconnect
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Switch -Profile A5 -Username vpn_xmz -Password ***
    powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action ResetUi -Profile 蓝区网关

  退出码：0 = 已连接 / 成功；3 = 未连接；其它 = 出错。

  ★ 中文配置名不要走命令行参数（会被代码页改坏），写成包装 .ps1（UTF-8 带 BOM）再调本脚本。

  已验证（2026-10-22 实测）：State / Connect / Disconnect / Switch / ResetUi（Switch 实测 A5 -> 蓝区网关 成功）。
  ★ 未完全验证：Switch 里的「登录表单填写 + 点登录」（只验证到能切出登录页，见 SKILL.md §6）。
#>

[CmdletBinding()]
param(
    [ValidateSet('State', 'Connect', 'Disconnect', 'Switch', 'ResetUi')]
    [string]$Action = 'State',

    # VPN 配置名 = %APPDATA%\UniVPN\config\<名字>.ini 去掉 .ini。已确认存在：蓝区网关 / A5
    [string]$Profile,

    # 仅当目标 profile 没有已存凭据时需要（A5 需要）
    [string]$Username,
    [string]$Password,

    [int]$TimeoutSec = 120,

    # 就绪判据里要检查的、必须经 TAP 生效的路由前缀；不填 = 只要有一条非 /32 的 TAP 路由即可
    [string]$ExpectRoute,

    # 仅 State：顺带测这些目标的 TCP 22
    [string[]]$TestHosts
)

$ErrorActionPreference = 'Stop'
# -File invocation passes "a,b" as ONE string; split it back into an array.
if ($TestHosts) { $TestHosts = @($TestHosts | ForEach-Object { $_ -split ',' } | Where-Object { $_ }) }
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

if (-not ('UniVpnNative' -as [type])) {
    Add-Type -Namespace '' -Name 'UniVpnNative' -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, System.IntPtr p);
public delegate bool EnumWindowsProc(System.IntPtr hWnd, System.IntPtr lParam);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hWnd, out uint pid);
[DllImport("user32.dll")] public static extern bool PostMessage(System.IntPtr hWnd, uint msg, System.IntPtr wParam, System.IntPtr lParam);
[DllImport("user32.dll")] public static extern int GetClassName(System.IntPtr hWnd, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, System.IntPtr e);
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr hWnd, int c);
'@
}

$ExePath = 'C:\Program Files (x86)\UniVPN\UniVPN.exe'
$QtTrayNotify = 0x8000 + 101         # Qt 的 MYWM_NOTIFYICON
$WM_LBUTTONDBLCLK = 0x0203

# 每个 profile 推送的路由指纹 —— 托盘态下这是唯一可靠的「现在连的是哪个」判据
$ProfileFingerprint = @{
    '蓝区网关' = '192.168.0.0/16'
    'A5'       = '177.0.0.0/8'
}

# ---------------------------------------------------------------- 窗口

function Get-VpnProcess {
    Get-Process -Name 'UniVPN' -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Find-ById {
    param($Window, [string]$Id)
    if (-not $Window) { return $null }
    $c = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Id)
    $Window.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}

function Txt { param($Window, [string]$Id) $e = Find-ById $Window $Id; if ($e) { $e.Current.Name } else { '' } }

<#
  两个坑都必须处理：
  1) 进程另有一个 Qt 窗口（标题「登录」，AutomationId=MainUI.basewidget）。按 ProcessId 取第一个
     可能拿到它 → 于是主界面所有控件"消失"。必须按 AutomationId -eq 'MainUI' 挑。
  2) 连上后主窗口收进托盘，UIA 树整个为空（Qt 不可见时不建辅助功能子树）。
     还原只能用「托盘图标被双击」这条 Qt 自己的消息路径。
     ★ 绝不要用 ShowWindow 硬显：只置 WS_VISIBLE，Qt 内部仍 hidden → 撕裂态，UIA 依旧读不到。
#>
function Get-MainWindow {
    $proc = Get-VpnProcess
    if (-not $proc) { return $null }
    $c = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $proc.Id)
    $wins = [System.Windows.Automation.AutomationElement]::RootElement.FindAll(
        [System.Windows.Automation.TreeScope]::Children, $c)
    foreach ($w in $wins) { if ($w.Current.AutomationId -eq 'MainUI') { return $w } }
    return $null
}

function Restore-MainWindow {
    param([int]$TimeoutSec = 20)
    $w = Get-MainWindow
    if ($w) { return $w }

    $proc = Get-VpnProcess
    if (-not $proc) { return $null }

    $script:trayHwnd = [IntPtr]::Zero
    $script:trayPid = $proc.Id
    $cb = [UniVpnNative+EnumWindowsProc] {
        param([IntPtr]$h, [IntPtr]$l)
        $p = 0
        [void][UniVpnNative]::GetWindowThreadProcessId($h, [ref]$p)
        if ($p -eq $script:trayPid) {
            $sb = New-Object System.Text.StringBuilder 256
            [void][UniVpnNative]::GetClassName($h, $sb, 256)
            if ($sb.ToString() -match 'TrayIconMessageWindow') { $script:trayHwnd = $h }
        }
        return $true
    }
    [void][UniVpnNative]::EnumWindows($cb, [IntPtr]::Zero)
    if ($script:trayHwnd -eq [IntPtr]::Zero) { return $null }

    [void][UniVpnNative]::PostMessage($script:trayHwnd, [uint32]$QtTrayNotify,
                                      [IntPtr]::Zero, [IntPtr]$WM_LBUTTONDBLCLK)
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        Start-Sleep -Milliseconds 400
        $w = Get-MainWindow
        if ($w) { return $w }
    }
    return $null
}

function Focus-Window {
    param($Window)
    $h = [IntPtr]$Window.Current.NativeWindowHandle
    [void][UniVpnNative]::ShowWindow($h, 9)          # SW_RESTORE
    [void][UniVpnNative]::SetForegroundWindow($h)
    Start-Sleep -Milliseconds 700
}

function Invoke-El { param($El) $El.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }

# ---------------------------------------------------------------- 状态

function Get-TapInfo {
    # 多实例（§7）装上以后本机会有两张以上 TAP-Windows 网卡：`本地连接`（原件）与 `本地连接 2`
    # （UVP002 副本）。`Select-Object -First 1` 会随机挑到副本那张，导致 Profile/TapIfIndex 报错。
    # 判据：副本的网卡 GUID 都登记在 <安装目录>\.univpn-multi\instance-*.json 的 TapGuid 里，
    # 排除它们，剩下的才是原件那张。
    $foreign = @()
    $instanceRoot = 'C:\Program Files (x86)\UniVPN\.univpn-multi'
    if (Test-Path -LiteralPath $instanceRoot) {
        Get-ChildItem -LiteralPath $instanceRoot -Filter 'instance-*.json' -ErrorAction SilentlyContinue |
            ForEach-Object {
                try {
                    $g = (Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json).TapGuid
                    if ($g) { $foreign += ([string]$g).Trim('{}').ToUpperInvariant() }
                } catch { }
            }
    }
    $candidates = @(Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceDescription -match 'TAP-Windows' } |
        Where-Object { $foreign -notcontains ([string]$_.InterfaceGuid).Trim('{}').ToUpperInvariant() })
    if ($candidates.Count -eq 0) {
        # 全部 TAP 都属于副本（原件没装 / 已卸载）时退回原行为
        $candidates = @(Get-NetAdapter -ErrorAction SilentlyContinue |
            Where-Object { $_.InterfaceDescription -match 'TAP-Windows' })
    }
    $tap = $candidates | Sort-Object @{ Expression = { $_.Status -ne 'Up' } }, ifIndex | Select-Object -First 1
    if (-not $tap) { return $null }
    $ip = Get-NetIPAddress -InterfaceIndex $tap.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
          Select-Object -First 1
    [pscustomobject]@{
        Name = $tap.Name; IfIndex = $tap.ifIndex; Status = $tap.Status
        IP = if ($ip) { $ip.IPAddress } else { $null }
    }
}

# 隧道态判据：① TAP Up ② 有 IPv4 且不是 APIPA ③ 有经 TAP 的「网段级」路由（/32 只是接口自身）
# 实测：刚点连接时 TAP 先拿 169.254.* 临时地址；虚拟 IP 下来后路由还要 1~3 秒才下发 ——
# 这两个时点都会骗过"有 IP 就算连上"，必须等判据全绿。
function Test-Tunnel {
    param([string]$Route)
    $tap = Get-TapInfo
    if (-not $tap -or $tap.Status -ne 'Up' -or -not $tap.IP) {
        return [pscustomobject]@{ Up = $false; Reason = 'TAP 未 Up 或无 IPv4'; Tap = $tap }
    }
    if ($tap.IP -like '169.254.*') {
        return [pscustomobject]@{ Up = $false; Reason = 'TAP 只有 APIPA(169.254)，隧道未通'; Tap = $tap }
    }
    $routes = @(Get-NetRoute -InterfaceIndex $tap.IfIndex -ErrorAction SilentlyContinue |
                Where-Object { $_.DestinationPrefix -match '/[0-9]+$' -and $_.DestinationPrefix -notmatch '/32$' })
    if ($Route) {
        if (-not ($routes | Where-Object { $_.DestinationPrefix -eq $Route })) {
            return [pscustomobject]@{ Up = $false; Reason = "路由 $Route 未走 TAP"; Tap = $tap }
        }
    }
    elseif ($routes.Count -eq 0) {
        return [pscustomobject]@{ Up = $false; Reason = '还没有任何经 TAP 的网段路由'; Tap = $tap }
    }
    return [pscustomobject]@{ Up = $true; Reason = 'ok'; Tap = $tap; Routes = $routes }
}

function Get-ProfileFromRoutes {
    param($TapRoutes)
    if (-not $TapRoutes) { return $null }
    foreach ($k in $ProfileFingerprint.Keys) {
        if ($TapRoutes | Where-Object { $_.DestinationPrefix -eq $ProfileFingerprint[$k] }) { return $k }
    }
    return $null
}

function Get-LastSession {
    # sysconfig.ini 是 GBK(936)；config\*.ini 是 UTF-8 —— 两种编码不要混用
    $p = Join-Path $env:APPDATA 'UniVPN\sysconfig.ini'
    if (-not (Test-Path $p)) { return $null }
    foreach ($line in [IO.File]::ReadAllLines($p, [Text.Encoding]::GetEncoding(936))) {
        if ($line -match '^\s*ClientLastAccessSession\s*=\s*(.+?)\s*$') { return ($Matches[1] -replace '\.ini$', '') }
    }
    return $null
}

function Get-VpnState {
    $proc = Get-VpnProcess
    if (-not $proc) { return [pscustomobject]@{ UiRunning = $false; Connected = $false; Ready = $false } }

    $win = Get-MainWindow                  # 查状态不还原窗口，避免仅仅查询就把界面弹出来
    $tun = Test-Tunnel
    $tap = $tun.Tap

    $s = [pscustomobject]@{
        UiRunning   = $true
        Connected   = $false
        Ready       = $tun.Up
        Reason      = $tun.Reason
        Profile     = $null
        User        = ''
        VirtualIP   = ''
        AuthStatus  = ''
        TapAdapter  = if ($tap) { $tap.Name } else { $null }
        TapIP       = if ($tap) { $tap.IP } else { $null }
        TapIfIndex  = if ($tap) { $tap.IfIndex } else { $null }
        TapRoutes   = if ($tun.Routes) { ($tun.Routes | ForEach-Object { $_.DestinationPrefix }) -join ' ' } else { '' }
        LastSession = Get-LastSession
        WindowLive  = [bool]$win      # False = 在托盘里，GUI 字段读不到（正常，不是故障）
    }

    if ($win) {
        $s.Connected  = [bool](Find-ById $win 'MainUI.frame.w_left.pushButton_disconnect')
        $s.Profile    = Txt $win 'MainUI.frame.w_left.label_netName'
        $s.User       = Txt $win 'MainUI.frame.w_left.lb_username'
        $s.VirtualIP  = Txt $win 'MainUI.frame.w_left.lb_ipAddress'
        $s.AuthStatus = Txt $win 'MainUI.frame.w_left.lb_certifyStatus'
    }
    else {
        $s.Connected = $tun.Up
        # 托盘态：先用路由指纹判 profile（可靠），退不到才用 sysconfig 的 last-access
        $s.Profile = Get-ProfileFromRoutes $tun.Routes
        if (-not $s.Profile) { $s.Profile = $s.LastSession }
    }
    if (-not $s.VirtualIP) { $s.VirtualIP = $s.TapIP }
    return $s
}

# ---------------------------------------------------------------- 动作

function Wait-Tunnel {
    param([bool]$Up, [int]$TimeoutSec, [string]$Route)
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        $t = Test-Tunnel -Route $Route
        if ($t.Up -eq $Up) { return $t }
        Start-Sleep -Milliseconds 700
    }
    $t = Test-Tunnel -Route $Route
    throw ("等待隧道 Up={0} 超时({1}s)：{2}" -f $Up, $TimeoutSec, $t.Reason)
}

function Clear-Filter {
    param($Window)
    if (-not $Window) { return }
    $le = Find-ById $Window 'MainUI.frame.le_select'
    if ($le) { try { $le.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('') } catch {} }
}

function Get-FilteredItems {
    param($Window, [string]$Name)
    $le = Find-ById $Window 'MainUI.frame.le_select'
    if (-not $le) { throw '找不到搜索框 MainUI.frame.le_select' }
    $le.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Name)
    Start-Sleep -Milliseconds 900
    $list = Find-ById $Window 'MainUI.frame.listWidget'
    $ct = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::ListItem)
    @($list.FindAll([System.Windows.Automation.TreeScope]::Children, $ct))
}

<#
  切换 profile 只能靠「真实鼠标点条目」：
  · UIA 的 SelectionItemPattern.Select() 只改视觉选中，不改客户端内部的 last-connect-name
    → 日志仍是 send the last connect name is <旧的>.ini，连接还连旧的那个。
  · 连着的时候点条目会被直接丢掉：日志 [item clicked][stop,status is logined]。
  ⇒ 必须先断开，再用 SetCursorPos + mouse_event 点条目；成功标志是日志出现
    [item clicked][end][vpn name:<名字>] 且左侧 label_netName 变成它。
#>
function Select-ProfileByClick {
    param($Window, [string]$Name)
    $items = Get-FilteredItems -Window $Window -Name $Name
    if ($items.Count -eq 0) { throw "搜索 '$Name' 无结果（可用配置见 $env:APPDATA\UniVPN\config\*.ini）" }
    if ($items.Count -gt 1) { throw "搜索 '$Name' 命中 $($items.Count) 个，请给更精确的名字" }

    $r = $items[0].Current.BoundingRectangle
    $x = [int]($r.X + $r.Width / 2)
    $y = [int]($r.Y + $r.Height / 2)
    Focus-Window $Window
    [void][UniVpnNative]::SetCursorPos($x, $y)
    Start-Sleep -Milliseconds 200
    [UniVpnNative]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)   # LEFTDOWN
    Start-Sleep -Milliseconds 80
    [UniVpnNative]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)   # LEFTUP
    Start-Sleep -Milliseconds 1500

    # 点击可能触发界面重建 → 之前抓的元素会失效，必须重新取窗口
    $w2 = Restore-MainWindow
    if ($w2) {
        $now = Txt $w2 'MainUI.frame.w_left.label_netName'
        if ($now -ne $Name) { Write-Warning "左侧名称仍是 '$now'，可能没切成功" }
    }
}

function Invoke-LoginForm {
    param($Window, [string]$User, [string]$Pass)
    if (-not $User) { return $false }
    $eu = Find-ById $Window 'MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_username'
    $ep = Find-ById $Window 'MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_password'
    if (-not ($eu -and $ep)) { return $false }
    $eu.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($User)
    Start-Sleep -Milliseconds 300
    if ($Pass) { $ep.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($Pass) }
    Start-Sleep -Milliseconds 500
    $btn = Find-ById $Window 'MainUI.basewidget.frame.pb_login_SSL'
    if (-not $btn) { return $false }
    Invoke-El $btn
    Write-Host '已提交登录表单（未完全验证，见 SKILL.md §6）'
    return $true
}

function Disconnect-Vpn {
    param([int]$TimeoutSec = 60)
    if (-not (Get-VpnProcess)) { throw 'UniVPN 未运行' }
    $win = Restore-MainWindow
    if (-not $win) { throw '主窗口拿不到（托盘消息路径失败）' }

    $btn = Find-ById $win 'MainUI.frame.w_left.pushButton_disconnect'
    if (-not $btn) { Write-Host '当前未连接'; return (Get-VpnState) }

    Write-Host '断开...'
    Invoke-El $btn
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        if (-not (Test-Tunnel).Up) { break }
        Start-Sleep -Milliseconds 700
    }
    return (Get-VpnState)
}

function Connect-Vpn {
    param([string]$Name, [string]$User, [string]$Pass, [int]$TimeoutSec = 120, [switch]$ForceSwitch)

    if (-not $Name) { throw '-Profile 必填' }
    if (-not (Get-VpnProcess)) {
        Write-Host 'UniVPN 未运行，启动中...'
        Start-Process $ExePath
        Start-Sleep -Seconds 5
    }

    $st = Get-VpnState
    if ($st.Connected) {
        if ($st.Profile -eq $Name -and -not $ForceSwitch) { Write-Host "已连接 '$Name'"; return $st }
        Write-Host "当前 '$($st.Profile)'，先断开..."
        Disconnect-Vpn | Out-Null
        Start-Sleep -Seconds 2
    }

    $win = Restore-MainWindow
    if (-not $win) { throw '主窗口拿不到' }

    Write-Host "选择配置 '$Name' ..."
    Select-ProfileByClick -Window $win -Name $Name

    $win = Restore-MainWindow
    $btn = Find-ById $win 'MainUI.frame.w_left.pushButton_connect'
    if (-not $btn) { throw '找不到「连接」按钮' }
    Write-Host '连接（实测 6~7 秒，另加路由下发 1~3 秒）...'
    Invoke-El $btn

    # 没有已存凭据的 profile（如 A5）会弹出登录页：点连接后它才被创建出来
    if ($User) {
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Seconds 1
            $w2 = Restore-MainWindow
            if (Find-ById $w2 'MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_username') {
                Invoke-LoginForm -Window $w2 -User $User -Pass $Pass | Out-Null
                break
            }
            if ((Test-Tunnel).Up) { break }
        }
    }

    $route = $ProfileFingerprint[$Name]
    Wait-Tunnel -Up $true -TimeoutSec $TimeoutSec -Route $route | Out-Null
    return (Get-VpnState)
}

<#
  ResetUi：把 UI 从 "Do not open repeated / reject login" 死状态里救出来。
  该状态会在「登录流程被打断」后残留，此后点什么连接都只打 [Do not open repeated] 不动作。
  实测可靠的恢复路径 = 杀 UI（CS 服务与隧道独立，不受影响）+ 把 sysconfig 的
  ClientLastAccessSession 改回目标 profile + 重启 UI（AutoLogin=1 的那条会直接自动登录）。
#>
function Reset-VpnUi {
    param([string]$PreferProfile, [int]$TimeoutSec = 120)
    Get-Process -Name UniVPN -ErrorAction SilentlyContinue | Stop-Process -Force
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Milliseconds 300
        if (-not (Get-VpnProcess)) { break }
    }
    if (-not (Get-VpnProcess)) { Write-Host 'UI 已退出（UniVPNCS 服务应仍在）' }

    if ($PreferProfile) {
        $sc = Join-Path $env:APPDATA 'UniVPN\sysconfig.ini'
        $enc = [Text.Encoding]::GetEncoding(936)
        $t = [IO.File]::ReadAllText($sc, $enc)
        $t = [regex]::Replace($t, '(ClientLastAccessSession\s*=\s*)[^\r\n]*', '${1}' + $PreferProfile + '.ini')
        [IO.File]::WriteAllText($sc, $t, $enc)
        Write-Host "ClientLastAccessSession -> $PreferProfile.ini"
    }

    Start-Process $ExePath
    $end = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $end) {
        Start-Sleep -Seconds 1
        if ((Test-Tunnel).Up) { break }
    }
    return (Get-VpnState)
}

# ---------------------------------------------------------------- main

switch ($Action) {
    'State' {
        $s = Get-VpnState
        $s | Format-List
        if ($TestHosts) {
            foreach ($h in $TestHosts) {
                $ok = Test-NetConnection -ComputerName $h -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue
                Write-Output ("reach {0}:22 = {1}" -f $h, $ok)
            }
        }
        if (-not $s.Connected) { exit 3 }
    }
    'Connect' {
        if (-not $Profile) { throw 'Connect 需要 -Profile' }
        Connect-Vpn -Name $Profile -User $Username -Pass $Password -TimeoutSec $TimeoutSec | Format-List
    }
    'Disconnect' { Disconnect-Vpn -TimeoutSec $TimeoutSec | Format-List }
    'Switch' {
        if (-not $Profile) { throw 'Switch 需要 -Profile' }
        Connect-Vpn -Name $Profile -User $Username -Pass $Password -TimeoutSec $TimeoutSec -ForceSwitch | Format-List
    }
    'ResetUi' {
        Reset-VpnUi -PreferProfile $Profile -TimeoutSec $TimeoutSec | Format-List
    }
}
