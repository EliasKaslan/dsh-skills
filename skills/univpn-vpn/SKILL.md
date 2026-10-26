---
name: univpn-vpn
description: UniVPN（联软 Leagsoft，C:\Program Files (x86)\UniVPN）——188 连不上、177.8.21.1 怎么连就看这条：蓝区网关(x00886548)推 192.168.0.0/16 → a3=192.168.13.188；A5(vpn_xmz)推 177.0.0.0/8 → a5=177.8.21.1（Ascend950DT）；单客户端两者互斥，多实例补丁可双开同时在线：切配置要真实鼠标点条目（UIA Select 无效）、托盘态还原、APIPA 假连、路由晚于虚拟 IP。适用于"188 连不上 / 177.8.21.1 怎么连 / 切到 A5 / 同时连 A3 和 A5 / 两个 VPN 一起连 / 多开 UniVPN / 现在连的是哪个 VPN / VPN 连上了但 ping 不通 / UniVPN 状态怎么看 / 该连蓝区还是 A5"。不适用：连上后装 CANN/conda/torch → 用 `ascend-env`；本机 pwsh 编码与执行策略坑 → 用 `pwsh-on-windows`。
whenToUse: UniVPN 连接/切换/排障与两台昇腾机(a3=.188 / a5=177.8.21.1)的准入路径。模型看不到本节。
---

# UniVPN（联软 SSL VPN）机制与自动化

**一句话**：`192.168.13.188` 只能走 **蓝区网关**，`177.8.21.1` 只能走 **A5**。原生客户端单隧道、单 TAP，两配置互斥，切换必然导致另一边断掉；**要两边同时在线走 §7 的多实例补丁**（2026-10-26 已实测：a3、a5 同时 `ping` 通且 `tcp 22` 通）。

## 何时调用

**加载本 skill 当：**
- 要连 / 断开 / 切换 VPN，或要先确认「现在连的是哪个、能不能到目标机」。
- 目标机 `192.168.13.188`（a3）或 `177.8.21.1`（a5）连不上，怀疑是 VPN 没连对。
- 要自动化驱动 UniVPN 界面（读状态、点连接、切配置）时踩到「控件读不到 / 点了没反应 / 中文配置名乱码」。
- VPN 卡在一直连不上、报认证失败、或界面「点什么都没反应」需要救回来。

**不要用本 skill（转交）：**
- 连上之后的 CANN / conda / torch / vllm 环境搭建 → 用 `ascend-env`（及 `ascend-*` 子 skill）。
- 本机 Windows PowerShell 5.1 的编码、BOM、执行策略、`-File` 传参等坑 → 用 `pwsh-on-windows`。
- 远端 Linux 上的目录与磁盘红线 → 用 `ascend-server-layout`。

**前置**：凭据在 `credentials.txt`（本 skill 目录内）。**后继**：连上后按 §2 做一次可达性确认，再去目标机干活。

## 1. 机制（2026-10-22 实测）

### 1.1 进程与数据面

| 角色 | 进程 / 对象 | 说明 |
|---|---|---|
| 界面 | `UniVPN.exe` | Qt5 GUI（版本 `10781.19.0.1214`）；**同时是 Chrome/Firefox 的 Native Messaging host**（`chrome_univpn.json`、扩展 `bgbbfnhficapockahamfncjdialfcbgp`）。杀了它不影响已建立的隧道 |
| 隧道引擎 | `UniVPNCS.exe` | `SYSTEM`，跑 CSDK + CNEM，独立于 GUI 持有 SSL 隧道；RPC 监听 `127.0.0.1:19060`；**每 10 s 发一次 CNEM UDP 保活**（`NEM_CMD_UDP_AVAILABLE_ACK`） |
| 提权助手 | `UniVPNPromoteService.exe` | 服务名 `UniVPNService`，`LocalSystem`，监听 `127.0.0.1:29190` |
| 数据面 | `tap0901` / TAP-Windows Adapter V9 | 网卡显示名 `本地连接`，**ifIndex 一直是 13**；虚拟 IP 就挂在这张卡上，断开时被摘掉 |

目录：`C:\Program Files (x86)\UniVPN\`（厂商 = 联软科技 Leagsoft）。配置：`%APPDATA%\UniVPN\config\<配置名>.ini`（**UTF-8**）与 `%APPDATA%\UniVPN\sysconfig.ini`（**GBK/936**）。日志：`%APPDATA%\UniVPN\log\UniVPN_UniVPNUI_0.log`（界面）、`UniVPN_UniVPNCS_113.log`（隧道引擎）。

### 1.2 连接阶段

界面日志按序出现：`Process ssl link select` → `Process ssl login`（→ `AUTH_MSGCODE_LOGIN_SUCCESS` / `..._LOGIN_FAIL`）→ `Process ssl cnem start` → `Cnem succed!`。**实测总耗时 6~7 秒**，随后再花 1~3 秒下发路由。

`TunnelMode = 2` = 自适应（TCP 可靠传输 / UDP 快速传输 自动二选一）。

### 1.3 配置键的语义（别按字面猜）

| 键 | 蓝区网关 | A5 | 真实含义 |
|---|---|---|---|
| `GatewayAddress` / `GatewayPort` | `123.60.114.225:30010` | `120.46.228.63:49999` | 网关入口（两个都能从公网直连） |
| `DefaultGateway` | `0` | `-1` | “默认网关”勾选框。**勾了也不等于全隧道**——推什么路由由网关决定 |
| `iroutecoverEnable` | `0` | `1` | “路由覆盖”：网关推的路由是否覆盖本地同段 |
| `TunnelMode` | `2` | `2` | 自适应 |

`sysconfig.ini` 的 `[SessionN]` 记录每个配置的账号：`ProfileName` / `ProfileUser` / `RemPwd` / `AutoLogin`，以及加密的 `ProfileInfo`（256 hex，**不要去解密**）；`ClientLastAccessSession` 是“上次连的配置”。

## 2. 两个配置各给什么（实测对照）

| | **蓝区网关** | **A5** |
|---|---|---|
| 账号 | `x00886548`（`RemPwd=1`、`AutoLogin=1`，密码已存客户端） | `vpn_xmz`（`RemPwd=1`、`AutoLogin=1`，密码存在 `ProfileInfo` blob 里；本文早期误记为 `RemPwd=0`）。**新建实例不继承这份凭据**，首次登录勾上「记住密码 + 自动登录」后才会自己存（§4） |
| 虚拟 IP 池 | `192.168.200.0/21` | `1.2.16.0/21`（实测拿到 `1.2.23.23`） |
| 网关推的路由 | `192.168.0.0/16`、`114.114.114.114/32` | `177.0.0.0/8`、`170.70.0.0/16`、`197.0.0.0/8`、`1.2.16.0/21` |
| 能到 | **`192.168.13.188`（a3）✅** | **`177.8.21.1`（a5）✅** |
| 到另一边 | `177.8.21.1` ❌ | `192.168.13.188` ❌ |

两点必须记住：

1. **都不是全隧道**。即使 A5 的 `DefaultGateway=-1`，`0.0.0.0/0` 仍然走物理网卡（`192.168.30.1` / WLAN），**推什么路由完全是网关侧按账号授权的**——客户端那个勾选框只是“请求”。所以“连上 A5 就能到 177.8.21.1”能不能成立，取决于**用哪个账号**（见 §8 那次误判）。
2. **虚拟 IP 每次都变**，永远不要写死；判“连上没连上”看 §3 的三条判据，不要看 IP 具体值。

`a5` = `177.8.21.1` 实测规格（`root`）：hostname `ip-177-8-21-1.rev.wkve.net.br`，`aarch64`，**384 核**，内存 **2262 GiB**，`/` 3.5 T 用了 88%，NPU `Ascend950DT`，`npu-smi 26.2.0.b020`，**没有 nvidia-smi**。`a3` = `.188` 见 `ascend-env`。

## 3. 用脚本操作

脚本：`scripts\vpnctl.ps1`（UTF-8 带 BOM；本机只有 Windows PowerShell 5.1，必须显式 Bypass）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action State -TestHosts 177.8.21.1,192.168.13.188
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Connect -Profile 蓝区网关
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Disconnect
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Switch -Profile A5 -Username vpn_xmz -Password ***
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action ResetUi -Profile 蓝区网关
```

退出码 `0` = 已连接/成功，`3` = 未连接。

**多开实例脚本**：`scripts\univpn-instance.ps1`（纯 ASCII，不依赖 BOM；`-Instance N` 会去读 `C:\Program Files (x86)\UniVPN\.univpn-multi\instance-00N.json` 取 `Product` / `TapGuid`，换实例号不用改脚本）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File univpn-instance.ps1 -Action State      -Instance 2
powershell -NoProfile -ExecutionPolicy Bypass -File univpn-instance.ps1 -Action Connect    -Instance 2 -Profile A5 -Username vpn_xmz -Password ***
powershell -NoProfile -ExecutionPolicy Bypass -File univpn-instance.ps1 -Action Disconnect -Instance 2
```

**`State` 输出的含义**：`Connected` / `Ready` / `Profile` / `VirtualIP` / `AuthStatus` / `TapRoutes` / `WindowLive`。`WindowLive=False` 表示界面在托盘里——正常现象，此时 `User`/`AuthStatus` 读不到（Qt 不可见时不建辅助功能子树），`Profile` 改由**路由指纹**判定（见下）。

**「真的连上了」三条判据**（缺一不可，脚本已内置）：
1. TAP 网卡 `Up` 且有 IPv4；
2. 该 IPv4 **不是 `169.254.*`**；
3. 有一条**经 TAP 的网段级路由**（非 `/32`）。

**profile 指纹**（托盘态唯一可靠判据）：经 TAP 有 `192.168.0.0/16` ⇒ 蓝区网关；有 `177.0.0.0/8` ⇒ A5。

**中文配置名不要走命令行**——会被代码页改坏。把调用写进一个包装 `.ps1`（UTF-8 带 BOM）再执行。

## 4. 切换配置：唯一可行路径

```
断开  →  （等 TAP 上 IPv4 消失）→  真实鼠标点列表条目  →  验证左侧名称已变  →  点「连接」
```

三个反直觉的点，全是实测：

- **UIA 的 `SelectionItemPattern.Select()` 切不了配置**。它只改视觉选中，客户端内部仍用“上次连接的配置名”，日志会继续打 `send the last connect name is <旧的>.ini`，连的还是旧的。**必须用 `SetCursorPos` + `mouse_event` 发真实鼠标点击**，成功标志是日志 `[item clicked][end][vpn name:<名字>]` 且左侧 `label_netName` 变成该名字。
- **连着的时候点条目会被直接丢掉**：日志 `[item clicked][stop,status is logined]`。所以必须**先断开**。
- **点完条目后界面元素会重建**，之前抓到的 `AutomationElement` 全部失效（表现为“点了连接没反应”，日志里连 `begin to conect btn clicked` 都没有）。**每次操作后重新获取窗口元素**。

条目文字无法通过 UIA 读取（列表项的 accessible name 是空的），定位方法是：把配置名写进搜索框 `MainUI.frame.le_select`（列表被过滤成正好 1 条）→ 取该条 `BoundingRectangle` 中心坐标 → 真实点击。

**A5 的登录与"记住密码"**：原客户端早已存好 A5 凭据（见 §2），**新建的实例没有** —— 第一次连接必弹登录页。表单控件 `le_username`/`le_password` **不认 UIA `ValuePattern.SetValue`**，必须点进输入框 + `SendKeys`（`scripts\univpn-instance.ps1` 已内置）。

登录页上有两个勾选框，**必须勾上**（`TogglePattern`，实测可用）：

- `MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.cb_savePass`（记住密码）
- `MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.cb_autoLogin`（自动登录）

勾上后客户端把加密凭据写进**该实例自己的** `sysconfig.ini`：`[Session0] RemPwd=1` + `ProfileInfo`（334 字符密文）+ `AutoLogin=1` + `ClientLastAccessSession=A5.ini`。**实测效果**：此后断开再连不用填密码，**连 `UVP002.exe` 整个重启后 20 秒内也自己连回来**（杀掉 GUI 后路由清零 → 重启 → 自动重连，虚拟 IP 换成新的）。不勾则每次连接都弹登录页。

**凭据只填一次**：出现 `AUTH_MSGCODE_LOGIN_FAIL` 立刻停手问人（企业账号会锁），别重试。

## 5. 坑与修法

**① 托盘态 UIA 全空。** 连上后窗口收进托盘，Qt 不建辅助功能子树 ⇒ 所有控件查不到。
修法：向类名匹配 `TrayIconMessageWindow` 的窗口 `PostMessage(0x8000+101 /*MYWM_NOTIFYICON*/, 0, 0x0203 /*WM_LBUTTONDBLCLK*/)`——走 Qt 自己的“托盘图标被双击”路径，它会 `show()`，树随之恢复。
**绝不要用 `ShowWindow` 硬显**：那只置 Win32 的 `WS_VISIBLE`，Qt 内部仍是 hidden ⇒ 撕裂态（窗口画出来了但 UIA 依旧全空，界面上还会短时显示错误的连接状态）。

**② APIPA 假连。** 刚点连接时 TAP 会先拿到 `169.254.*` 临时地址，此时隧道根本没通。只判“有 IP 就算连上”会假阳。

**③ 路由晚于虚拟 IP。** 虚拟 IP 下来后路由还要 1~3 秒才下发，这段窗口里 `192.168.13.188` 依旧不通。**别在拿到 IP 的瞬间就测目标机**——这是本轮反复误报“连上了但不通”的根因。

**④ 界面卡在 "Do not open repeated / reject login"。** 登录流程被打断后会残留该状态，此后点什么连接都只打 `[Do not open repeated]` 而不动作。
修法（`-Action ResetUi`）：**杀 `UniVPN.exe`（隧道引擎 `UniVPNCS.exe` 独立，不受影响）→ 把 `sysconfig.ini` 的 `ClientLastAccessSession` 改成目标配置（GBK 写回）→ 重启 UI**。`AutoLogin=1` 的那条配置会自动登录回来，实测 8 秒恢复。

**⑤ 两个 `windows` 容易拿错。** 进程有两个 Qt 窗口：`MainUI`（主界面）和 `MainUI.basewidget`（标题「登录」）。按 ProcessId 取第一个可能拿到登录窗，于是主界面控件全查不到。必须按 `AutomationId -eq 'MainUI'` 挑。

**⑥ 编码。** `sysconfig.ini` 是 **GBK(936)**，`config\*.ini` 是 **UTF-8**，两种混用必乱码。`.ps1` 里含中文必须存成 **UTF-8 带 BOM**，否则 PS 5.1 按 ANSI 读会毁掉中文字面量。

**⑦ 认证失败会真的失败。** 日志 `AUTH_MSGCODE_LOGIN_FAIL` 出现就停下问人，别重试——企业账号会锁。本轮就因为拿蓝区的账号去登 A5 连失败两次（日志里 `qstr_usernameUTF8` 还不是完整用户名），直到换成 A5 的 `vpn_xmz` 才成功。

### 关键 AutomationId

`MainUI.frame.w_left.pushButton_connect` / `...pushButton_disconnect`（**只有连上时才存在**）/ `label_netName` / `lb_username` / `lb_ipAddress` / `lb_certifyStatus` / `MainUI.frame.le_select`（搜索框）/ `MainUI.frame.listWidget`；登录页：`MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_username` / `le_password` / `cb_savePass`（记住密码）/ `cb_autoLogin`（自动登录）/ `MainUI.basewidget.frame.pb_login_SSL`（“登录”）；新建连接对话框：`MainUI.basewidget.frame.stackedWidget.page_ssl.scrollArea_ssl.qt_scrollarea_viewport.scrollAreaWidgetContents_ssl.le_connectNameSSL` / `le_gatewayAddress` / `le_port` / `cb_routecover`，按钮 `MainUI.basewidget.frame.w_bottom.pb_ok`。

## 6. 未验证 / 未闭合

- **`Switch` 与「自动填登录表单 + 点 `pb_login_SSL`」都已验证**（2026-10-26：填入 `vpn_xmz` 后登录成功，隧道 8 秒内起来；此后勾了记住密码，连登录页都不再出现）。**唯一仍要注意**：自动填表必须走「点进输入框 + `SendKeys`」，`ValuePattern.SetValue` 写不进去（读回是空串）。
- **A5 是否也能到 `192.168.x`**：实测不能（路由里没有 `192.168.0.0/16`），未尝试手工 `New-NetRoute` 强加路由——2026-10-22 那次会话**非提权**（`BUILTIN\Administrators` 是 deny-only、中完整性），加路由与 `route add` 都需要管理员。若将来要试：连 A5 后在提权窗口跑 `New-NetRoute -DestinationPrefix 192.168.0.0/16 -InterfaceIndex 13 -NextHop 0.0.0.0`，再测 `.188`；**能不能通取决于 A5 网关是否转发**，不是客户端能决定的。⇒ **要两边同时通，直接走 §7 的多实例，别去改路由表。**
- `177.8.21.1` 上只采到 §2 那几项（hostname/核数/内存/磁盘/NPU 型号），**CANN、conda、模型目录一概未采**，别编。

## 7. 双 VPN 同时在线（多实例补丁，2026-10-26 实测跑通）

目标：`192.168.13.188`（a3）与 `177.8.21.1`（a5）**同时**可达。做法：在**同一台机器**再复制出一个独立的 UniVPN 产品实例（`UniVPN2` / 产品名 `UVP002`），两套 GUI + 引擎 + 服务 + TAP 各走各的，原客户端一个字节都不动。工具：`https://github.com/UsernameFull/univpn-multi`（PowerShell，按 SHA256 锁版本）。

### 7.1 为什么能共存 / 前置条件

- 原客户端是**单例**：产品名 `UniVPN`、RPC `29190` + `19060`、服务 `UniVPNService`、配置 `%APPDATA%\UniVPN`、TAP 显示名 `本地连接`。多实例把这三样逐实例改名、改端口、**新建一张 TAP**：第 2 个实例 = `UVP002` + `29191`/`19061` + `UVP002Service` + `%APPDATA%\UVP002` + `本地连接 2`。
- 两边网关推的路由**天然不重叠**（蓝区 `192.168.0.0/16`、A5 `177.0.0.0/8`），所以双隧道并存不打架。**不要**去手工 `New-NetRoute` 把 A5 的路由引到蓝区的 TAP（§6 那条死路），要两边通就走这里。
- 前置（缺一不可）：
  1. **管理员权限**：要往 `C:\Program Files (x86)\UniVPN\` 写文件、建服务、加 TAP。
  2. **所有 UniVPN 客户端先完全退出**。脚本的 `Assert-NoRunningClients` 会拦：任何匹配 `^(UniVPN|UniVP2|UVP\d{3})(CS)?$` 的进程，**或任何 TAP 网卡 `Status = Up`**（哪怕是别的 VPN 的）。⇒ 先断开蓝区隧道。
  3. 版本要匹配：脚本按 SHA256 校验三个 exe，版本 `10781.19.0.1214` 实测匹配（`UniVPN.exe` / `promote\UniVPNPromoteService.exe` / `serviceclient\UniVPNCS.exe`）。

### 7.2 创建实例（一次性）

```powershell
git clone https://github.com/UsernameFull/univpn-multi.git D:\workspace\tmp\univpn-multi
# 把 UniVPN-Multi.ps1 复制进安装目录再提权执行（脚本用 $PSScriptRoot 定位源目录）
```

提权执行要点（**两个都会静默坑人**）：

```powershell
$argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $dst + '"'   # 路径带空格必须自己加引号
Start-Process powershell -Verb RunAs -NoNewWindow -Wait -ArgumentList $argLine `
    -RedirectStandardInput  "$tmp\empty.txt" `                        # 脚本末尾有 Read-Host，不重定向会挂死
    -RedirectStandardOutput "$tmp\univpn-multi-run.log" `
    -RedirectStandardError  "$tmp\univpn-multi-err.log"
```

- `-ArgumentList` 传**数组**时元素之间只空格连接、**不加引号** ⇒ 报 `处理 -File"C:\Program"失败，因为该文件不具有 '.ps1' 扩展名`（exit code `-196608`）。必须像上面那样拼成一个字符串。
- 成功标志：日志 `Status: Ready`、`C:\Program Files (x86)\UniVPN\.univpn-multi\instance-002.json`、新 TAP `本地连接 2`、服务 `UVP002Service`（**Manual，不自启**）、`C:\Program Files (x86)\UniVPN2\Open-UniVPN2.cmd`。
- 脚本装完会**顺手用提权身份起一次 GUI**。那个窗口是管理员进程，普通权限会话的 UIA 点它不动（UIPI），`Stop-Process -Name UVP002` 也会 `Access is denied`。⇒ **提权杀掉，再从普通会话重开**：`Start-Process 'C:\Program Files (x86)\UniVPN2\UVP002.exe'`。

### 7.3 让它看得见 + 连得上 A5（三个坑，缺一个就失败）

副本**不继承**原客户端任何配置：`%APPDATA%\UVP002\` 里只有裸的 `sysconfig.ini` / `key.ini` / `log\`。

1. **连接列表由引擎提供，不是 UI 扫目录。** 把 `%APPDATA%\UniVPN\config\A5.ini` 拷进 `%APPDATA%\UVP002\config\` 之后**只重启 GUI 无效**（列表仍空）；必须重启**引擎**：`Stop-Service UVP002Service -Force` → `Start-Service UVP002Service`。旁证：文件在时点 `+ New Connection` 会报 `The connection name already exists.`（UI 查得到文件），但列表就是不显示 ⇒ 列表来自引擎启动时的扫描 / `GetLogined`。
   更省事的替代：直接在 UI 里 `+ New Connection` 建一条（名称 `A5`、网关 `120.46.228.63`、端口 `49999`、勾 `Route Overwrite`、Tunnel Mode 保持 `Auto-sensing`）——客户端自己写出的 `A5.ini` 与原件**逐字节一致**。
2. **`ClientServerCheck` 必须改成 `0`**，否则 TLS 直接失败（安装器生成的副本默认 `1`，原件是 `0`）：
   ```
   [NETC ERROR][SSL Connect error][...tls_post_process_server_certificate:certificate verify failed...]
   [CAUTH ERROR][Service cert failed][reason:get service cert socket new code 3]
   ```
   这个失败发生在**证书校验阶段、认证之前**，所以不会消耗登录次数、也不会锁账号；表现是 TAP 拿到 `169.254.*` 后一直不动。改 `%APPDATA%\UVP002\sysconfig.ini`（**GBK/936**）后重启服务。
3. **`ClientMtuValue = 0`** 会让引擎反复打 `[Pref set mtu][val:0][mtu value invalid]` + `VNIC Set MTU failed`；填 `1500` 与原件一致。

### 7.4 连接 + 记住密码

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File univpn-instance.ps1 -Action Connect -Instance 2 -Profile A5 -Username vpn_xmz -Password ***
```

首次连接会弹登录页；脚本自动填账号密码、勾上 `cb_savePass`（记住密码）+ `cb_autoLogin`（自动登录）再提交。之后 `%APPDATA%\UVP002\sysconfig.ini` 里出现：

```ini
[Session0]
RemPwd = 1
ProfileName = A5.ini
ProfileUser = vpn_xmz
ProfileInfo = D8624493...        ; 334 字符密文
AutoLogin = 1
LastLoginAddr = 120.46.228.63:49999
```

**实测效果**：断开重连不用再填密码；连 `UVP002.exe` 整个重启也会自己连回来（杀 GUI → 路由清零 → 重启 → 20 秒内重新 Up，虚拟 IP 换新的）。

### 7.5 验收（两边同时通才算成）

```powershell
Get-NetAdapter | ? InterfaceDescription -match 'TAP' | select Name,ifIndex,Status
# 本地连接    ifIndex 13  Up   192.168.201.2   ← 蓝区（原件）
# 本地连接 2  ifIndex 55  Up   1.2.17.209      ← A5（副本，IP 每次都变）

Test-Connection 192.168.13.188 -Count 2 -Quiet    # True
Test-Connection 177.8.21.1     -Count 2 -Quiet    # True
Get-Process UniVPNCS,UVP002CS                     # 两个引擎各一个
Get-NetRoute -AddressFamily IPv4 | ? DestinationPrefix -match '^(192\.168\.0\.0/16|177\.0\.0\.0/8|170\.70\.0\.0/16|197\.0\.0\.0/8|1\.2\.16\.0/21)$'
# 192.168.0.0/16 走 ifIndex 13；177/170/197/1.2.16 走 ifIndex 55
```

2026-10-26 实测：两目标 `ping` + `tcp 22` 全通，两 TAP 同时 Up，两套服务并存，互不影响。

### 7.6 卸载 / 回退（按项目 `docs/MAINTENANCE.md`，本轮**未实做**）

顺序固定，别跳步：

```powershell
# 1) 先在副本里断开 VPN 并从托盘退出；2) 管理员窗口：
Get-CimInstance Win32_Service -Filter "Name='UVP002Service'" | Select-Object Name,State,PathName
#    确认 PathName 指向 .univpn-multi\UVP002\promote\UVP002PromoteService.exe，再：
Stop-Service -Name UVP002Service
sc.exe delete UVP002Service
```

然后删 `C:\Program Files (x86)\UniVPN2\`（及可选的 `%APPDATA%\UVP002\`）；TAP 的设备 GUID 记在 `.univpn-multi\instance-002.json` 的 `TapGuid`，要删网卡得在设备管理器里核对目标，**绝不要执行 `tapinstall remove tap0901`**（它会匹配多张网卡、可能拖垮共享驱动）。原版 `UniVPNService` 与其文件一律不碰。

### 7.7 这一节踩到的通用坑

- **`Get-NetAdapter` 的 `InterfaceGuid` 在 PS 5.1 是字符串**，和 `[guid]` 比较恒为 `false` ⇒ 静默拿到 `$null`，然后每条命令都报 `Cannot validate argument on parameter 'InterfaceIndex'. The argument is null.`。比较前 `[string]` 两边都转。
- **窗口被最大化窗口盖住时 `SetForegroundWindow` 会静默失败**（调用方没有前台权限），随后 `SetCursorPos` + `mouse_event` 点在**别的窗口**上，客户端日志里一条都不出现——表现得像“点了没反应”。修法：`SetWindowPos(HWND_TOPMOST)` → `SetWindowPos(HWND_NOTOPMOST)` → `BringWindowToTop` → 再点。
- **Qt 的 `QLineEdit` 不认 `ValuePattern.SetValue`**（读回是空串）：必须点进输入框 + `SendKeys`（`^a` 再输入）。
- **新建连接对话框比窗口高**：`MainUI.basewidget.frame.w_bottom.pb_ok` 的坐标会落到窗口之外，点在桌面上。要么先把窗口 `SetWindowPos` 拉高，要么用 UIA `InvokePattern`。
- **副本 UI 是英文**（`ClientLanguageID = 1000`）、原件是中文：AutomationId 相同、文字不同，**按 id 找控件，别按文字**。登录窗标题反而是中文 `登录`。
- **“连上了”不能只看 IP 也不能只看状态文字**：断开后 TAP 会留着上一个虚拟 IP、状态标签还会短暂显示 `successfully connect!`。判据是**有没有经该 TAP 的网段级路由**（`-notmatch '/32$'`、排除 `224.0.0.0/4`）。
- **本机 `-Verb RunAs` 不弹 UAC 确认**（静默提权成功），所以自动化里不要“等用户点确认”，也不会因为没人点而失败。
- **装完多实例后，`vpnctl.ps1` 必须能分辨两张 TAP**：`本地连接`（原件）与 `本地连接 2`（副本）都是 `TAP-Windows Adapter V9`，原来的 `Select-Object -First 1` 会挑到副本那张，于是 `-Action State` 把 `Profile` 报成 `A5`、`TapIfIndex` 报成 55。修法已内置：排除 `.univpn-multi\instance-*.json` 里登记的 `TapGuid`，剩下的才是原件。⇒ **将来再加实例，这个排除会自动生效，别改回 `-First 1`**。
- **改这两个脚本要注意编码**：`vpnctl.ps1` 原本是 GBK/无 BOM，用 UTF-8 **无 BOM** 覆写后 PS 5.1 按 GBK 解析，中文串会吞掉后面的引号，报一堆假语法错（`Missing type name after '['`、`哈希文本不完整`）。写完补 BOM：`[IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($true)))`。`univpn-instance.ps1` 是纯 ASCII，不受影响。

## 8. 维护记录 → `references/maintenance-log.md`

逐轮改动与取证时间。**用户不会问这个**，只在怀疑本文机制描述过时时才读。