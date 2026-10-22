---
name: univpn-vpn
description: UniVPN（联软 Leagsoft，C:\Program Files (x86)\UniVPN）——188 连不上、177.8.21.1 怎么连就看这条：蓝区网关(x00886548)推 192.168.0.0/16 → a3=192.168.13.188；A5(vpn_xmz)推 177.0.0.0/8 → a5=177.8.21.1（Ascend950DT）；两配置互斥，切配置必须先断开再真实鼠标点条目（UIA Select 无效）；含托盘态还原、APIPA 假连、路由晚于虚拟 IP 的时序坑。适用于"188 连不上 / 177.8.21.1 怎么连 / 切到 A5 / 现在连的是哪个 VPN / UniVPN 状态怎么看 / VPN 连上了但 ping 不通 / 一直连不上 / 该连蓝区还是 A5"。不适用：连上后装 CANN/conda/torch → 用 `ascend-env`；本机 pwsh 编码与执行策略坑 → 用 `pwsh-on-windows`。
whenToUse: UniVPN 连接/切换/排障与两台昇腾机(a3=.188 / a5=177.8.21.1)的准入路径。模型看不到本节。
---

# UniVPN（联软 SSL VPN）机制与自动化

**一句话**：`192.168.13.188` 只能走 **蓝区网关**，`177.8.21.1` 只能走 **A5**，两者互斥（单隧道、单 TAP 网卡），切换必然导致另一边断掉。

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
| 账号 | `x00886548`（`RemPwd=1`、`AutoLogin=1`，密码已存客户端） | `vpn_xmz`（`RemPwd=0`，**每次要填密码**） |
| 虚拟 IP 池 | `192.168.200.0/21` | `1.2.16.0/21`（实测拿到 `1.2.23.23`） |
| 网关推的路由 | `192.168.0.0/16`、`114.114.114.114/32` | `177.0.0.0/8`、`170.70.0.0/16`、`197.0.0.0/8`、`1.2.16.0/21` |
| 能到 | **`192.168.13.188`（a3）✅** | **`177.8.21.1`（a5）✅** |
| 到另一边 | `177.8.21.1` ❌ | `192.168.13.188` ❌ |

两点必须记住：

1. **都不是全隧道**。即使 A5 的 `DefaultGateway=-1`，`0.0.0.0/0` 仍然走物理网卡（`192.168.30.1` / WLAN），**推什么路由完全是网关侧按账号授权的**——客户端那个勾选框只是“请求”。所以“连上 A5 就能到 177.8.21.1”能不能成立，取决于**用哪个账号**（见 §7 那次误判）。
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

**A5 需要登录**：A5 没有已存凭据，`-Action Connect -Profile A5` 不带 `-Username/-Password` 会在推出登录页后停住。

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

`MainUI.frame.w_left.pushButton_connect` / `...pushButton_disconnect`（**只有连上时才存在**）/ `label_netName` / `lb_username` / `lb_ipAddress` / `lb_certifyStatus` / `MainUI.frame.le_select`（搜索框）/ `MainUI.frame.listWidget`；登录页：`MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_username` / `le_password` / `MainUI.basewidget.frame.pb_login_SSL`（“登录”）。

## 6. 未验证 / 未闭合

- **`Switch` 整体已验证**（2026-10-22 实测 A5 → 蓝区网关：断开 → 点条目 → 连接 → 路由就绪，全程无人工）。**唯一未验证的是「自动填登录表单 + 点 `pb_login_SSL`」那一段**：三个控件 `le_username` / `le_password` / `pb_login_SSL` 都能定位到，但自动填表后登录成功没跑通（那次工具调用被中断）。⇒ **切到 A5 时若停在登录页，手工输一次 `vpn_xmz` 的密码即可**；带已存凭据的配置（蓝区网关）根本不走登录页。
- **A5 是否也能到 `192.168.x`**：实测不能（路由里没有 `192.168.0.0/16`），未尝试手工 `New-NetRoute` 强加路由——本会话**非提权**（`BUILTIN\Administrators` 是 deny-only、中完整性），加路由与 `route add` 都需要管理员。若将来要试：连 A5 后在提权窗口跑 `New-NetRoute -DestinationPrefix 192.168.0.0/16 -InterfaceIndex 13 -NextHop 0.0.0.0`，再测 `.188`；**能不能通取决于 A5 网关是否转发**，不是客户端能决定的。
- `177.8.21.1` 上只采到 §2 那几项（hostname/核数/内存/磁盘/NPU 型号），**CANN、conda、模型目录一概未采**，别编。

## 7. 维护记录

- **2026-10-22 创建**。当天纠正了一个关键误判：原先用 `x00886548` 去连 A5 全部 `LOGIN_FAIL`，且因为 §4 的 `Select()` 无效问题，几次「以为连了 A5」其实连的还是蓝区网关（日志 `send the last connect name is 蓝区网关.ini`），一度错误地得出「A5 也到不了 177.8.21.1」的结论。**换 A5 专属账号 `vpn_xmz` 登录后 `177.8.21.1:22` 立刻可达**。
- **同一天证伪了 7 个 `ascend-*` skill 里「A5 已登记凭据但不可达、规格未采」的断言**——那些结论是在**没连 A5**的情况下测 `177.8.21.1` 得出的。真值是：**必须先连 A5，才可达**；`ascend-env` §1 已改，其余 skill 的同一句话以 `ascend-env` §1 与本 skill §2 为准。
