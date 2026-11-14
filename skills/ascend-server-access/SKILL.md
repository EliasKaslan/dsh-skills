---
name: ascend-server-access
description: A5 隧道不通时：先数 TAP 张数，实例2 TAP 丢失就用原件 Switch 到 A5 应急
whenToUse: 昇腾服务器清单、凭据、可达性判据与 UniVPN 准入/双开（在册见 §12：A3×2 + A5×4）；模型看不到本节。
---

# 昇腾服务器清单与 UniVPN 准入

**一句话**：**在册 6 台（清单见 §12，2026-11-13 用户口径）**——蓝区A3 `192.168.13.188` / `.190` 走 **蓝区网关**，蓝区A5 `177.8.21.1` / `177.11.25.1` / `177.11.26.1` / `177.11.27.1` 走 **A5**。原生客户端单隧道、单 TAP，两配置互斥；**两个客户端（原件 + `UVP002` 实例）可同时在线**。
> **共享机红线**：卡上有别人的进程 ⇒ 整张卡不可用，不抢卡、也不蹭剩余显存（会毁掉别人的性能/精度数据）；长任务按可断点续跑写。唯一判据出处：`ascend-server-layout`「共享机占用铁律与断点续跑」。

## 何时调用

**加载本 skill 当：**
- 要确认「现在有哪些服务器可用 / 各走哪个 VPN / 凭据在哪」，或要连 / 断开 / 切换 VPN。
- 目标机 `192.168.13.188`（a3）、`192.168.13.190`（a3b）或 `177.8.21.1`（a5）连不上，怀疑 VPN 没连对 / 路由没下发 / 主机刚重装。
- 要同时访问 A3 与 A5（双实例），或要自动化驱动 UniVPN 界面（读状态、点连接、切配置）。
- VPN 卡在一直连不上、报认证失败、或界面「点什么都没反应」需要救回来。

**不要用本 skill（转交）：**
- 连上之后的 CANN / conda / torch / vllm 环境搭建 → 用 `ascend-env`（及 `ascend-*` 子 skill）。
- 本机 Windows PowerShell 5.1 的编码、BOM、执行策略、`-File` 传参等坑 → 用 `pwsh-on-windows`。
- 远端 Linux 上的目录与磁盘红线 → 用 `ascend-server-layout`。

**前置**：服务器 root 密码与 VPN 账号都在 `%USERPROFILE%\.dsh\.secrets\ascend-servers.txt`（`<host> <user> <password>`，被 `.dsh/.gitignore` 排除，**不进 git 也不进 mirror**；旧文写的「本 skill 目录内 credentials.txt」已作废——mirror 发布时 secrets 被剔除，本机也不再放）。**后继**：连上后按 §0 的连通性三测确认，再去目标机干活。

## 0. 服务器清单与准入（唯一出处，2026-11-03 实测）

> ⚠️ **在册清单只看 §12（2026-11-13，6 台）**：本节与 §11 的"有哪些机器"已过时，规格数字仍可参考。
> 用户口径（2026-11-03）：**当前只有这三台可用**。正文或记忆里若还有别的机器，一律按不可用处理，别去试。
> **2026-11-09 更正**：这条已不成立——当晚又发了 4 台 A5 环境（`177.2.25.1` / `177.2.26.1` / `177.11.25.1` / `177.11.26.1`，同一张 A5 隧道即可达），规格与坑见 **§11**。判「有没有机器可用」不要照抄本节，先按 §12 的在册清单。

| 代称 | 地址 / 账号 | 角色 | 系统与规格（现场实采） | 准入 |
|---|---|---|---|---|
| **a3** | `192.168.13.188` / root | A3 默认 | Debian 10，256 核 / 1448 GiB；8 NPU × 2 die = 16 个 `Ascend910`（65536 MB/die）；`/` 2.9T 已用 96%、`/home/vllm` 6.9T 余 1.6T；CANN 9.1.0 在 `/home/x00886548/env/cann/cann_9_1_0` | **蓝区网关**；免密 + 密码都通；**本机直连 OpenSSH 会卡 KEX，因隧道 MTU≈1420 吞大包 → 用 `.190` 跳板，见 §5 ⑨**；多租户重载机（2026-11-03 load≈800） |
| **a3b** | `192.168.13.190` / root | A3 备用 | **2026-11-03 重装**：openEuler 22.03 LTS-SP4，64 核 / 1384 GiB；16 个 `Ascend910` die（65536 MB/die，driver 26.0.rc1）；`/` 69G（8%）、`/home` 6.9T、`/mnt/share` NFS 287T；CANN 9.2.1 在 `/home/cann/921`；gcc 10.3.1 / python 3.9.9 | **蓝区网关**；**免密 + 密码都通**（2026-11-03 配的 key）；主机名 `localhost.localdomain` |
| **a5** | `177.8.21.1` / root | A5 | openEuler 24.03 LTS-SP3 aarch64，192 核 / 2261 GiB；8 × `Ascend950DT`（98304 MB/卡，npu-smi 25.1.rc3）；`/` 3.5T 已用 87%、`/mnt/share` NFS 350T；CANN 9.2.0 在 `/home/cann/920_b111`；gcc 12.3.1 / python 3.12.14 | **A5 配置**；**免密 + 密码都通**（2026-11-03 配的 key，原有 73 条其它 key 全部保留）；登录横幅 `Authorized users only. All activities may be monitored and reported.` |

> 表里的核数 / 内存 / NPU / CANN 路径可以长期参考；**磁盘占用、load、会话数只是 2026-11-03 快照**，动手前现场 `df -h` / `uptime` / `npu-smi` 取，别照抄数字。

**VPN ↔ 目标机映射（只此一份）**

| 目标 | 必连配置 | 网关推的路由 | 备注 |
|---|---|---|---|
| `.188`、`.190` | **蓝区网关**（账号 `x00886548`） | `192.168.0.0/16`、`114.114.114.114/32` | 两台 A3 同一张 TAP；连上后 `192.168.13.0/24` 全域可达 |
| `177.8.21.1` | **A5**（账号 `vpn_xmz`） | `177.0.0.0/8`、`170.70.0.0/16`、`197.0.0.0/8`、`1.2.16.0/21` | 蓝区网关**到不了** A5，反过来也一样 |
| 三台同时 | 原件连蓝区 + `UVP002` 实例连 A5 | 两套路由不重叠 | 2026-11-03 实测三台同时 `ping` / `tcp 22` 全通；做法见 §7 |

**凭据**：**唯一凭据文件是 `%USERPROFILE%\.dsh\.secrets\ascend-servers.txt`**（2026-11-13 已按在册 6 台更新，见 §12 / §13）；**正文不写密码**。本目录下的 `credentials.txt` **已不存在**（2026-11-13 核对），两个 python 脚本已改为**优先读 `.secrets/ascend-servers.txt`、缺了才退回 `../credentials.txt`**（同日实测 `read_creds('177.11.27.1')` / `password_for('177.11.27.1')` 都能命中）。目前实测能用的免密脚本：`D:\workspace\昇腾环境\setup_passwordless.py`（复制一份改 `HOSTS`）与 §0.1 的 `install-pubkey.py`。**新机器登录成功后先配免密，见 §0.1。**

**连通性三测（缺一不可，别把「连不上」混成一句）**

```powershell
Test-Connection -ComputerName 192.168.13.190 -Count 2 -Quiet       # ① ICMP
$c=New-Object Net.Sockets.TcpClient; $t=$c.BeginConnect('192.168.13.190',22,$null,$null)
$t.AsyncWaitHandle.WaitOne(4000,$false)                            # ② TCP 22（别用 Test-NetConnection）
ssh -n -o BatchMode=yes root@192.168.13.190 "hostname"             # ③ 认证（新机器没配 key 时会失败，属正常）
```

判读：①/② 不通 → 先查 VPN 与路由（§3 三条判据）；② 通但 ③ 超时 → 多半是 sshd 被高负载饿死（`.188` 常见）；③ 报 `Permission denied (publickey,password)` → 机器通、公钥没配，直接用密码。

**`.190` 重装后的已知变化（2026-11-03）**：主机名从 `zj-131` 变成 `localhost.localdomain`，系统从 Debian 11 换成 openEuler 22.03，SSH host key 也换了 ⇒ 旧 `known_hosts` 会报 `REMOTE HOST IDENTIFICATION HAS CHANGED!` / `Host key verification failed.`；修法 `ssh-keygen -R 192.168.13.190` 再连。旧的 Debian 11 / 64 核 / gcc 10.2 记录一律作废，按上表新规格。

### 0.1 新服务器接入的固定收尾：顺手配免密（用户 2026-11-03 要求）

每成功登录一台新机器（不管这次用的是密码还是已有 key），**先配免密再干别的**：

```powershell
# 密码由脚本自己从 %USERPROFILE%\.dsh\.secrets\ascend-servers.txt 读（"<host>  <user>  <pwd>" 行）
python scripts\install-pubkey.py 192.168.13.190 177.8.21.1
ssh -n -o BatchMode=yes root@192.168.13.190 "hostname; whoami"   # 必须看到主机名才算成
```

`install-pubkey.py` 的行为：登录 → `mkdir -p ~/.ssh` → **读原 `authorized_keys`** → 只在缺本机 `id_ed25519.pub` 时追加 → `chmod 700/600` + `chown` → 断开，再用 **key-only** 重连复核。没有 `--password` 时读 `%USERPROFILE%\.dsh\.secrets\ascend-servers.txt`（缺了才退回 `../credentials.txt`），再缺才用 `$env:SSH_PASSWORD`。

**红线：只追加，绝不覆盖。** 共享机的 `authorized_keys` 不是我们一个人的——2026-11-03 A5 原有 **73 条**其它 key，`cat >` / `>` 会把别人全部锁在门外。配完必须复核（`.190` / A5 用 `ssh -o BatchMode=yes`；`.188` 用 paramiko key，OpenSSH 可能卡 KEX），**不要只看文件里有那行**。

## 1. 机制（2026-10-22 实测，2026-11-03 复核）

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
| 虚拟 IP 池 | `192.168.200.0/21` | `1.2.16.0/21`（2026-11-03 实测 `1.2.16.162`） |
| 网关推的路由 | `192.168.0.0/16`、`114.114.114.114/32` | `177.0.0.0/8`、`170.70.0.0/16`、`197.0.0.0/8`、`1.2.16.0/21` |
| 能到 | **`.188`（a3）+ `.190`（a3b）✅** | **`177.8.21.1`（a5）✅** |
| 到另一边 | `177.8.21.1` ❌ | `192.168.13.188` / `.190` ❌ |

两点必须记住：

1. **都不是全隧道**。即使 A5 的 `DefaultGateway=-1`，`0.0.0.0/0` 仍然走物理网卡（`192.168.30.1` / WLAN），**推什么路由完全是网关侧按账号授权的**——客户端那个勾选框只是“请求”。所以“连上 A5 就能到 177.8.21.1”能不能成立，取决于**用哪个账号**（2026-10-22 那次误判见 `references/maintenance-log.md`）。
2. **虚拟 IP 每次都变**，永远不要写死；判“连上没连上”看 §3 的三条判据，不要看 IP 具体值。

三台规格、凭据与准入全部收进 §0（唯一出处），本节不再重复。**2026-11-03 复核**：两个 TAP 同时 Up 时，`.188` / `.190` / `177.8.21.1` 的 `ping` 与 `tcp 22` 全部通——旧文「A3 与 A5 只能二选一」只在**原生单客户端**成立。

## 3. 用脚本操作

脚本：`scripts\vpnctl.ps1`（UTF-8 带 BOM；本机只有 Windows PowerShell 5.1，必须显式 Bypass）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action State -TestHosts 177.8.21.1,192.168.13.188,192.168.13.190
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

**服务器免密脚本**：`scripts\install-pubkey.py`（Python 3.12 + paramiko 5.0.0；幂等追加、保留原 `authorized_keys`、配完自动 key-only 复核；密码从 `.dsh\.secrets\ascend-servers.txt` 取）：

```powershell
python scripts\install-pubkey.py 192.168.13.190 177.8.21.1
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

**⑧ 机器重装后 host key 变了，ssh 直接拒连。** 2026-11-03 `.190` 重装后实测：`ssh root@192.168.13.190` 报 `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` + `Host key verification failed.`（`Offending ECDSA key in C:\Users\admin/.ssh/known_hosts:9`）。这不是中间人，是本机 `known_hosts` 还记着旧机的 key。修法：`ssh-keygen -R 192.168.13.190`，再连；paramiko 用 `AutoAddPolicy` 不受影响。

**⑨ `.188` 连不上是「路径 MTU 黑洞」，不是 sshd 被饿死（2026-11-03 二次实测改判本条的旧结论）。**
现象照旧：`ping` 与 `tcp 22` 都通，OpenSSH 报 `ssh_dispatch_run_fatal: Connection to 192.168.13.188 port 22: Connection timed out`，`ssh -vv` 卡在 `expecting SSH2_MSG_KEX_ECDH_REPLY`（握手大包发不出去）。
**新证据（同日晚复测，旧结论被证伪）**：
- `ping -f -l 1472 192.168.13.188` **100% 丢**、`-f -l 1416` 通 ⇒ 本机→VPN→`.188` 这段路径 MTU ≈1420（不是 1500），超长包被黑洞且不返回 ICMP Frag Needed ⇒ PMTUD 失效 ⇒ SSH 的 KEX 包正好落在这条死路上。`.190` 目标同样验收（1416 通 / 1424 丢），说明瓶颈在本机侧隧道而非某台服务器。
- **跳板在 load≈800 时仍 100% 成功**（当日 10+ 次全通）：`ssh -o IPQoS=none -o ProxyJump=root@192.168.13.190 root@192.168.13.188` —— `.190→.188` 走内网 MTU 1500，完全绕开隧道。若真如旧条所写是"sshd 被负载饿死"，`KEX` 仍在 `.188` 上算，跳板不可能好用。
- `-o IPQoS=none` 单独用**只是偶发有效**（时通时不通），不要当解决方案。
- 改本机 MTU 走 `netsh interface ipv4 set subinterface` **需要管理员**；本机实测 `IsInRole(Administrator)=False`，改不了 ⇒ 别无脑推这条。
⇒ **判据顺序**：① 先 `ping -f -l 1472` / `-l 1416` 二分定位 MTU，丢 1472 通 1416 就直接判 MTU，**别去查 sshd、负载、VPN 认证**；② 首选跳板（见上）；③ paramiko 能用是因为它协商出的包更小，但别再把它当唯一出路。旧结论「sshd 被高负载饿死」作废。

**⑩ 免密公钥与「登录成功就先配」（2026-11-03 三台已全部配好）。** `.190` / A5 的 `ssh -o BatchMode=yes` 直接通；`.188` 的 key 用 paramiko 稳定，OpenSSH 会踩 ⑨ 的 MTU 黑洞（**不是 load**）。**新机器登录成功后仍要按 §0.1 先配**。坑在覆盖：A5 原有 **73 条**其它 key、`.190` 原有 1 条，直接 `cat >` / `>` 会把别人锁在外面——只能读出来、追加、写回。配完必须用 key-only 复核，别只看文件里有那行。密码 fallback 仍在 `%USERPROFILE%\.dsh\.secrets\ascend-servers.txt`（脚本已改读这里；paramiko 5.0.0；PowerShell 双引号里别拼 `!` / `$`）。

### 关键 AutomationId

`MainUI.frame.w_left.pushButton_connect` / `...pushButton_disconnect`（**只有连上时才存在**）/ `label_netName` / `lb_username` / `lb_ipAddress` / `lb_certifyStatus` / `MainUI.frame.le_select`（搜索框）/ `MainUI.frame.listWidget`；登录页：`MainUI.basewidget.frame.stackedWidget.stackedWidgetPage1.le_username` / `le_password` / `cb_savePass`（记住密码）/ `cb_autoLogin`（自动登录）/ `MainUI.basewidget.frame.pb_login_SSL`（“登录”）；新建连接对话框：`MainUI.basewidget.frame.stackedWidget.page_ssl.scrollArea_ssl.qt_scrollarea_viewport.scrollAreaWidgetContents_ssl.le_connectNameSSL` / `le_gatewayAddress` / `le_port` / `cb_routecover`，按钮 `MainUI.basewidget.frame.w_bottom.pb_ok`。

## 6. 未验证 / 未闭合

- **`Switch` 与「自动填登录表单 + 点 `pb_login_SSL`」都已验证**（2026-10-26：填入 `vpn_xmz` 后登录成功，隧道 8 秒内起来；此后勾了记住密码，连登录页都不再出现）。**唯一仍要注意**：自动填表必须走「点进输入框 + `SendKeys`」，`ValuePattern.SetValue` 写不进去（读回是空串）。
- **A5 是否也能到 `192.168.x`**：实测不能（路由里没有 `192.168.0.0/16`），未尝试手工 `New-NetRoute` 强加路由——2026-10-22 那次会话**非提权**（`BUILTIN\Administrators` 是 deny-only、中完整性），加路由与 `route add` 都需要管理员。若将来要试：连 A5 后在提权窗口跑 `New-NetRoute -DestinationPrefix 192.168.0.0/16 -InterfaceIndex 13 -NextHop 0.0.0.0`，再测 `.188`；**能不能通取决于 A5 网关是否转发**，不是客户端能决定的。⇒ **要两边同时通，直接走 §7 的多实例，别去改路由表。**
- **`.190` 与 A5 都只采到 §0 的「规格 + 路径」层，没跑过 torch 或 vllm**（`.188` 有实测，别混）：`.190` 能看到 CANN 9.2.1 的安装目录，但没 `source` 后 `import acl`；A5 能看到 CANN 9.2.0 的目录，同理。**别把「装了 CANN」写成「CANN 可用」**。`.190` / A5 的 conda 环境、模型目录也都没盘点。
- **`.190` 是新机，不是旧 `zj-131`**：2026-11-03 重装后，旧的 `/home/vllm/x00886548/...`、Debian 11、gcc 10.2 记录全部作废；当前只有 `/home/cann/921`、`/home/c30077422` 可见。别再按旧记录套 `.190`。
- **A5 规格以 §0 为准**：2026-11-03 实测 192 核 / 2261 GiB / npu-smi 25.1.rc3；2026-10-22 记的 384 核 / npu-smi 26.2.0.b020 已作废（重装或当时读错），别混用。

## 7. 双 VPN 同时在线（多实例补丁，2026-10-26 跑通 / 2026-11-03 复核）

目标：`192.168.13.188` / `.190`（A3，蓝区网关）与 `177.8.21.1`（A5）**同时**可达。做法：在**同一台机器**再复制出一个独立的 UniVPN 产品实例（`UniVPN2` / 产品名 `UVP002`），两套 GUI + 引擎 + 服务 + TAP 各走各的，原客户端一个字节都不动。工具：`https://github.com/UsernameFull/univpn-multi`（PowerShell，按 SHA256 锁版本）。

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
# 本地连接    ifIndex 13  Up   192.168.201.186 ← 蓝区（原件，IP 每次都变）
# 本地连接 2  ifIndex 55  Up   1.2.16.162      ← A5（副本，IP 每次都变）

Test-Connection 192.168.13.188 -Count 2 -Quiet    # True
Test-Connection 192.168.13.190 -Count 2 -Quiet    # True（2026-11-03 复核）
Test-Connection 177.8.21.1     -Count 2 -Quiet    # True
Get-Process UniVPNCS,UVP002CS                     # 两个引擎各一个
Get-NetRoute -AddressFamily IPv4 | ? DestinationPrefix -match '^(192\.168\.0\.0/16|177\.0\.0\.0/8|170\.70\.0\.0/16|197\.0\.0\.0/8|1\.2\.16\.0/21)$'
# 192.168.0.0/16 走 ifIndex 13；177/170/197/1.2.16 走 ifIndex 55
```

2026-11-03 复核：两 TAP 同时 Up（`本地连接` ifIndex 13 = 蓝区、`本地连接 2` ifIndex 55 = A5），三台目标（`.188` / `.190` / `177.8.21.1`）`ping` + `tcp 22` 全通；`UVP002.exe` 启动后按 `AutoLogin` 自动连回 A5（不必再手点）。两套服务并存，互不影响。

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

## 9. 两台 A3 之间互通体检（`188 ↔ 190`，2026-11-03 实测）

**网段互通 ≠ 能协同干活。** 分四层查，只做前一层就会把「能 ping」当成「能跑多机任务」：

| 层 | 命令（在任一台机器上跑） | 通过的样子（2026-11-03 实测） |
|---|---|---|
| L2 同广播域 | `ip neigh show <peer>` | `lladdr 00:e0:4c:68:07:b7 REACHABLE`（或 `STALE`，MAC 真实即可）⇒ 直连不经路由器；出现 `FAILED` / `incomplete` 说明跨网段或 ARP 不通 |
| L3 + 帧大小 | `ping -c 3 -W 2 <peer>`；`ping -c 2 -s 1472 -M do <peer>` | 0% loss、RTT 0.2~0.4 ms；1472+28=1500 带 DF 也 0% loss ⇒ 两端 MTU 都是 1500，没有隧道/PPPoE 卡点 |
| L4 端口 | `timeout 6 bash -c '</dev/tcp/<peer>/22'` | 立即成功；**别用 `Test-NetConnection` 代替** |
| 吞吐 | `nc` 灌 1 GiB（见脚本） | 见下「带宽天花板」 |

**一键体检**：`python scripts\node-pair-check.py 192.168.13.188 192.168.13.190 [--throughput]`——paramiko 走本机 key（失败自动用 `.dsh\.secrets\ascend-servers.txt` 里的密码），打印上表全部判据 + 网卡速率/错误计数 + NFS 挂载数 + 「能否 ssh 到对端」；`--throughput` 才跑 1 GiB 双向灌流。**不要用 OpenSSH 驱动**：`.188` 的 sshd 在高负载下会卡 KEX（§5 ⑨），本脚本不受影响。

**带宽天花板先看网卡再怀疑 TCP**：两台都是 `Speed: 1000Mb/s, Duplex: Full`（`.188` = `enxc8a362d975e9`，`.190` = `enp211s0u1`）⇒ `~110 MB/s` 就是上限。实测 `.188→.190` 71.6 MB/s、`.190→.188` 107.1 MB/s，**是线速不是故障**。`ethtool <ifc> | grep -E 'Speed|Duplex'` 看速率，`ip -s link show <ifc>` 看 `errors`（必须 0）；`.188` 的 RX `dropped` 是自开机累计（17 天 29 万，占 0.03%），高负载机器上属正常，别单看这个数判坏线。

### 9.1 2026-11-03 的实测结论（双向）

- 本机 → 两台：`ping` + `tcp 22` 全通；`.188` 用 paramiko key、`.190` 用 OpenSSH key 进。
- **两机之间网络层完全正常**：同广播域、双向 0% 丢包、MTU 1500、TCP22 双向通、1 GiB 灌流双向成功。
- **两机之间的 ssh 登录一层都没配**（这才是「不通」的那层）：
  - `.188 → .190`：先撞 `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!`（`.190` 重装换过 host key，`Offending ECDSA key in /root/.ssh/known_hosts:10`）⇒ `ssh-keygen -f ~/.ssh/known_hosts -R 192.168.13.190`；**清完仍然不行**——`.190` 的 `authorized_keys`（2 条）里没有 `.188` 的 `id_ed25519.pub`。
  - `.190 → .188`：`root@192.168.13.188: Permission denied (publickey,password)`——`.190` **整台机器没有私钥**（`/root/.ssh/` 只有 `authorized_keys` + `known_hosts`，`ls id_*` 为空），不是 key 没配，是压根没有 key 可配。
  - 要跑多机（ray / 多机 vllm / 分发脚本）先补这层：`.190` 上 `ssh-keygen -t ed25519 -N ''`，两边互相追加公钥（**只追加不覆盖**，`.188` 的 `authorized_keys` 已有 22 条别人的 key）。
- **共享存储不对等**：`.190` 挂 `suzblue.server:/share`(287T) + `/weight`；`.188` **一个 NFS 都没挂**（`mount | grep ' type nfs'` 返回 0），`/mnt/share` 是系统盘本地目录 ⇒ 「扔 `/mnt/share` 两边都读得到」只在 `.190` 成立。
- `.188` 每次非交互登录都会往 stderr 打 `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory`——不影响连通性，但会污染所有 `ssh` 输出，别当成连接失败。

## 10. 跨机（双机）NPU 通信可行性：三条硬闸门（2026-11-03 实测）

问「188 和 190 能不能双机拉起一个 vllm / 跨机跑 HCCL」时，**先过这三条**，任一不过就别去装环境了——装了也只会卡在建链：

1. **两端都必须有 NPU 互联网卡（RoCE）**：`lspci -nn | grep -iE 'mellanox|ethernet'`、`ls /sys/class/infiniband`、`ls /sys/class/net`。
   - `.190`：2× `ConnectX-6 Dx`，`roceo112` ACTIVE **100Gb/s**、`roceo113` DOWN；netdev `eno112np0`/`eno113np1`（均无 IP）。
   - `.188`：**只有一块 USB 1GbE（`enxc8a362d975e9`）+ iBMA 虚拟网卡，零 RoCE 网卡、无 `/sys/class/infiniband`、`lspci` 无 Mellanox** ⇒ 这一侧根本没有跨机通路。1GbE 管理网**不能**替代（HCCL 跨机只走 RoCE）。
2. **`hccn_tool` 链路 UP 且两端 IP 同网段**：`for i in $(seq 0 15); do hccn_tool -i $i -link -g; hccn_tool -i $i -ip -g; done`
   - 判读：`link status: DOWN`、或 `Get ipconf failed, because no ip was preset there!` ⇒ 这侧没配好。2026-11-03：两台 16 个 device **全 DOWN**；`.188` 有预置 IP（`90.14.123.21/24`、`90.14.122.21/24` 两平面）但链路不通，`.190` 连 IP 都没有。
3. **两端 CANN + driver 同版本**：`npu-smi info -t board -i 0 | grep -iE 'software|firmware'`、`ls /etc/Ascend/ascend_cann_install.info`。
   - 2026-11-03：`.188` = driver 25.5.1 / CANN 9.1.0；`.190` = driver 26.0.rc1 / CANN 9.2.1 ⇒ 混版本跨机 HCCL 不支持。

**判据模板**：第 1 条不过 = **硬件不具备，装软件无意义**；第 2/3 条不过 = 配置或版本问题，可修但必须两端同时动。别把「两台机器 ssh 能通 + 1GbE 能灌流」当成「能双机跑模型」——那是 CPU/管理网层面的事，跟 HCCL 无关（§9 的结论只覆盖前者）。

**顺带记**：`.188` 的 CANN 在 `/home/x00886548/env/cann/cann_9_1_0/`，`set_env.sh` 在 **`ascend-toolkit/set_env.sh`**；source 目录下同名文件不会报错但 `ASCEND_HOME_PATH` 仍为空，随后 `import torch_npu` 报 `ImportError: libhccl.so: cannot open shared object file`。`.190` 的 CANN 9.2.1 在 `/home/cann/921/`。

## 11. 2026-11-09 批 4 台 A5 环境（177.2.x / 177.11.x）

同一张 **A5 隧道**就能到，**蓝区网关到不了**；与 `.188/.190` 靠 §7 的双实例并存。全部 openEuler 24.03 LTS-SP3 / aarch64 / 192 核 / 2261 GiB / 9 个 `/dev/davinci*`。

> ⚠️ **在册状态（§12 为准）**：`177.11.25.1` / `177.11.26.1` 仍在册；**`177.2.25.1` / `177.2.26.1` 已不在用户 2026-11-13 的清单里**，按不可用处理。

| 批次 | 地址 | 主机名 | `/` 占用（11-09 快照） |
|---|---|---|---|
| 11-09 晚 | `177.2.25.1` | localhost.localdomain | 3.5T 用 93% |
| 11-09 晚 | `177.2.26.1` | localhost.localdomain | 3.5T 用 95% |
| 11-10 晚 | `177.11.25.1` | 177-11-25-1.btecdns.net.br | 3.5T 用 86% |
| 11-10 晚 | `177.11.26.1` | 177-11-26-1.btecdns.net.br | 3.5T 用 92% |

**让 A5 隧道起来（本机实测，最短路径）**：实例 2 早就建好且凭据已存（`%APPDATA%\UVP002\sysconfig.ini` 里 `AutoLogin=1`），只需

```powershell
Start-Process 'C:\Program Files (x86)\UniVPN2\UVP002.exe'   # 等价：双击 UniVPN2\Open-UniVPN2.cmd
# 等 ~20s，判据三条：本地连接 2 是 ifIndex 55 / Up；IP 非 169.254.*（实测 1.2.19.177/21）；
# 177.0.0.0/8 经 if55 的网段级路由已下发（断开后仍留 IP，所以只认路由）
```

`UVP002Service` 是 **Manual**、不随开机自启 ⇒ **每次重启电脑都要手动起一次**。蓝区那套（原件 `UniVPN.exe` + `本地连接` ifIndex 13）照常，互不影响。

**三个坑（这次全踩了）**：

1. **只有 ICMP 通 ≠ 能连**。没上 A5 隧道时，这 4 台从本机公网出口（119.8.178.38）和从 `.188` 打 22/2222/80/443 全是 SYN 被静默丢弃，但 `177.2.25.1` 的 ping 通（100ms）。判可达必须做 §0 的三测，别用 ping 下结论。
2. **刚发下来的环境 sshd 可能还没起**。`177.11.25.1` 首次测 TCP 22 超时，几分钟后同一地址自己就通了 ⇒ 先等 2~5 分钟再判死。
3. **同 IP 旧 host key 会挡住 OpenSSH**：`Host key verification failed.`（`known_hosts` 按哈希存，`Select-String` 搜不到那行）⇒ `ssh-keygen -R 177.11.25.1` 后重连。paramiko 用 `AutoAddPolicy` 不受影响，所以「paramiko 通、ssh 不通」时先查这条。

**免密**：4 台已配（2026-11-09，只追加未覆盖，原有 37~81 条他人 key 全部保留）。幂等脚本 `D:\workspace\昇腾环境\setup_passwordless.py`（改 `HOSTS` 即可复用；流程 = TCP 探活 → 密码登录 → 只追加公钥 → key-only 复核）。复核一律用

```powershell
ssh -n -o BatchMode=yes -o StrictHostKeyChecking=accept-new root@<ip> hostname
```

## 12. 2026-11-13 在册清单（用户口径）与共享机红线

**用户 2026-11-13 给定的"当前可能可用"清单就是这 6 台。与 §0 / §11 冲突时以本节为准**：那两节的核数、内存、卡型等规格仍可参考，但"有哪些机器"只认本节。

口语对照：用户说的「**蓝区A3**」= `192.168.13.x`（走蓝区网关）；「**蓝区A5**」= `177.x`（走 A5 隧道），与 §11 的 A5 批次是同一张隧道，别当成两套环境。

### 在册清单

| 代称 | 地址 | 账号 | 隧道 | 角色 | 规格 / 备注 |
|---|---|---|---|---|---|
| 蓝区A3 | `192.168.13.188` | root | 蓝区网关 | a3 默认 | Debian 10 / 256 核 / 1448 GiB / 8 NPU × 2 die = 16 `Ascend910`（65536 MB per die）/ 多租户重载机；本机连它要跳板，见 §5 ⑨ |
| 蓝区A3 | `192.168.13.190` | root | 蓝区网关 | a3b 备用 | openEuler 22.03 SP4 / 64 核 / 1384 GiB / 16 die（64 GB）/ CANN 9.2.1 在 `/home/cann/921`；**2026-11-13 密码已更换** |
| 蓝区A5 | `177.8.21.1` | root | A5 | a5 主 | openEuler 24.03 SP3 aarch64 / 192 核 / 2261 GiB / 8 × `Ascend950DT`（96 GB）/ CANN 9.2.0 |
| 蓝区A5 | `177.11.25.1` | root | A5 | A5 批次 | openEuler 24.03 SP3 / 192 核 / 2261 GiB / 9 个 `/dev/davinci*` |
| 蓝区A5 | `177.11.26.1` | root | A5 | A5 批次 | 同上 |
| 蓝区A5 | `177.11.27.1` | root | A5 | A5 批次（**2026-11-13 新入册**） | 同上；免密已于当日配好（§13） |

**不在册 = 按不可用处理**：`177.2.25.1` / `177.2.26.1`（2026-11-09 发过）已不在 2026-11-13 的清单里，别主动去连，用户重新给到再恢复。

### 凭据放哪：密码不进本文件

- **唯一凭据文件**：`%USERPROFILE%\.dsh\.secrets\ascend-servers.txt`，格式 `<host>  <user>  <password>`，已按这 6 台更新（`.190` 新密码在册、旧值留成注释；`177.11.27.1` 新增；`177.2.x` 两行注释留档）。
- **不要把密码抄进 skill 正文**。`~/.dsh/skills` 会被 `skill_publish` 发布到公开仓（GitCode + GitHub `dsh-skills`），明文密码贴进来就等于公开。用户说的"内置"= 内置"**清单 + 去哪拿密码 + 怎么用**"，不是把明文贴进会被公开的文件。
- 脚本取密码：读该文件第 3 列。密码含 `!` `$` `*` `@` `#`，**别在 PowerShell 命令行里手工拼**（双引号内 `$`、反引号会被展开），一律由 python 读文件。

### 共享机红线（用户 2026-11-13 明确要求）

**卡上有别人 → 整张卡不可用；判据是"有没有人"，不是"还剩多少显存"。** 不抢卡、不蹭别人的剩余显存（哪怕只跑个小评测）——会拖慢别人正在跑的**性能与精度**对比。判据与让路动作的唯一出处是 `ascend-server-layout` 文末「共享机占用铁律与断点续跑」（步骤 5 与 `ascend-vllm-serve` 步骤 1 都指向它）；长任务按其中 §3「长任务默认可断点续跑」写。**要一次性问清「在册 6 台现在哪几台有空卡」，直接跑 `ascend-server-layout` 的 `scripts/npu-free.py`**（六台并发、每台一条 `npu-smi info`、8~20 s，`.188` 自动走 `.190` 跳板）。

### 本机 TAP 的 ifIndex 会变（2026-11-13 实测，纠正 §7.5 / §11）

旧记录把 `本地连接`=13、`本地连接 2`=55 写死；本轮实测是 **14 / 15**（客户端重装或重启后会重排）。⇒ 判"哪条隧道通"只认 **网卡名 + 经该网卡的网段级路由**（`Get-NetRoute` 里 `192.168.0.0/16` → 蓝区、`177.0.0.0/8` → A5），`ifIndex` 只当打印值，**别写进脚本条件**。

## 13. 2026-11-13 实测：4 台 A5 的免密、磁盘与落位约束

2026-11-13 用 paramiko 逐台实登（A5 隧道已通、蓝区隧道未连，故 A3 两台本轮未测）。

| 地址 | 免密（key） | 凭据 | 主机名 | `/` 占用 | 备注 |
|---|---|---|---|---|---|
| `177.8.21.1` | ⚠️ **当日不通 → 当天已修好**（初测 `Permission denied (publickey,password)`，机上 75 条 key 里没有本机当前公钥；追加后 76 条、`BatchMode=yes` 复核 exit=0） | key（密码 fallback） | `ip-177-8-21-1.rev.wkve.net.br` | **100%，余 19G** | 当日快照：整卡曾被别人的 `VLLMWorker_TP0..7` 占着且分钟级 crash-restart，随后自行全部退出（只剩 NPU1 上一个 `attn_demo`）⇒ **卡状态是分钟级变量，动手前必须重采 `npu-smi`**；报错先查盘满 |
| `177.11.25.1` | ✅ | key | `177-11-25-1.btecdns.net.br` | 92%，余 282G | 8 卡全空（当日快照） |
| `177.11.26.1` | ✅ | key | `177-11-26-1.btecdns.net.br` | 95%，余 175G | 别人的 sglang TP8 在跑（当日快照） |
| `177.11.27.1` | ✅ **2026-11-13 新配** | key（密码 fallback） | `177-11-27-1.btecdns.net.br` | 70%，余 1016G | 8 卡全空（当日快照）；`/home` 下已有他人目录 `codex-a5-lab` |

四台都是 192 核 / 2261 GiB / 9 个 `/dev/davinci*`；**`/home` 与 `/` 是同一块盘**（`df` 只有 `nvme*p4` 两行）。

### 换过本机 SSH key 之后：旧免密会全部失效，逐台重配

坑的原形：本机 `id_ed25519` 在 **2026-11-06 10:41 重新生成**，而 `.8.21.1` 的公钥是 2026-11-03 配的 ⇒ 公钥对不上。

判读：`ssh -o BatchMode=yes -o ConnectTimeout=8 root@<ip> hostname` 失败、**但密码能登进去** ⇒ 认证层问题，不是隧道/网络问题（先 ping + tcp 22 排除网络）。修法：按 §0.1 重跑免密（**只追加**，这些机器上有 35~81 条别人的 key），配完立刻用 `BatchMode=yes` 复核 `hostname`。

### A5 上的落位约束（2026-11-13 实测，替换旧"待落地/未验证"）

`/home` 不是独立分区、且 `/` 已用到 70~100%（好的机器只剩 1016G，差的只剩 19G）⇒ **A5 上个人根不能想当然建真实目录**：先 `df -h /home`，要放 >10G 的权重/产物前再确认一次；个人根落位方案（软链到共享盘）**仍未验证**，别照抄 `.188` 的 `/home/vllm` 结论。

## 14. 190 的出网限制：github.com 不可达，GitHub 仓必须走 gh-proxy 中转（2026-11-14 实测）

## 14. 190 的出网限制：github.com 不可达，GitHub 仓必须走 gh-proxy 中转（2026-11-14 实测）

**判读顺序**：在 `.190` 上 `git clone` GitHub 仓卡住不动时，**先查是"出网被墙"还是"认证失败"**，别去折腾 key / 代理环境变量。

| 目标 | 190 上实测结果 |
|---|---|
| `gitcode.com` | **直连正常**（`git ls-remote` 秒回） |
| `github.com` | **不通**：DNS 能解析（实测 `20.6.7.17`），但 TCP 443 被黑洞——`curl` 25s 无任何输出、`git ls-remote` 45s 无输出（`timeout` 杀掉，不是报错） |
| `codeload.github.com` | 反而**能直连**（tarball 200 / 2.3s）⇒ 只要内容不要历史时可以下 tarball，但拿不到 `.git` |
| `/etc/profile.d/`、`/etc/environment` | 无任何 `*_proxy` 设置（别指望机器上有现成代理） |

**可用中转（逐个实测）**：

```bash
https://gh-proxy.com/https://github.com/<org>/<repo>      # 200 ✅ 唯一可用
https://ghfast.top/https://github.com/<org>/<repo>        # 403
https://ghproxy.net/https://github.com/<org>/<repo>       # 403
https://gitclone.com/github.com/<org>/<repo>             # 502
https://hub.gitmirror.com/...                            # DNS 不解析
```

`gh-proxy.com` **支持 git smart HTTP**：`git ls-remote` / `clone` / `fetch` 都能走，不只是下 tarball。

**正确配法：映射写在仓内本地，不要写全局**（`.190` 上所有人都是 root，`git config --global` 会污染别人的 git）：

```bash
git clone -b <branch> https://gh-proxy.com/https://github.com/<org>/<repo>
cd <repo>
git remote set-url origin https://github.com/<org>/<repo>          # origin 留规范 URL
git config url.https://gh-proxy.com/https://github.com/.insteadOf https://github.com/
git ls-remote --heads origin | head                                 # 复核 fetch 也能走
```

- 写完 `git fetch / pull` 自动改走中转，且**只影响这个仓**。
- 想一次性给某条命令加代理：`git -c url.https://gh-proxy.com/https://github.com/.insteadOf=https://github.com/ clone <url>`，同样不落盘。

**坑**：

- 内联 `ssh root@192.168.13.190 "..."` 里**不要出现 `\"`**：PowerShell 把反斜杠吞掉后远端 bash 报 `寻找匹配的"时遇到了未预期的文件结束符`，整条命令一行都不执行。带循环/引号的侦察脚本一律本地写 `.sh` → base64 → 远端 `base64 -d` 落盘再 `bash`（比管道传文件稳，天然避开 BOM/CRLF）：
  ```powershell
  $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes('D:\workspace\tmp\x.sh'))
  ssh -n -o BatchMode=yes root@192.168.13.190 "echo $b64 | base64 -d > /tmp/x.sh; bash /tmp/x.sh"
  ```
- `git clone` 非 tty 时默认不打进度，要看"还在不在动"必须显式 `--progress`，否则日志长时间一片空白、容易误判为卡死。

**已落位示例**（2026-11-14，DeepSeek-V4.1-Flash 部署）：4 仓克隆到 `/home/x00886548/work/dsv41/{FSDPTurbo,vllm-ascend,vllm,verl}`，其中 `FSDPTurbo` 走 gitcode 直连，另外三个走 gh-proxy 并按上式配好仓内 `insteadOf`；合 693 MB，工作区干净。仓库 provenance 与命令写在 `${个人根}/work/dsv41/README.md`，下次不用重新摸索。

## 15. 188 与 190 的出网差异、机器同名陷阱与远程重试纪律（2026-11-14 实测）

## 15. 188 与 190 的出网差异、机器同名陷阱与远程重试纪律（2026-11-14 实测）

**两台蓝区机的 GitHub 表现完全不同，别互相套用：**

| | `.190` | `.188` |
|---|---|---|
| `github.com` | TCP 443 黑洞，`ls-remote` 45s 无输出（见 §14） | **能连**，`ls-remote` 秒回，但 ~740 KB/s 且随机断 |
| 症状 | 静默超时 | `gnutls_handshake() failed: The TLS connection was non-properly terminated` / `error: RPC failed; curl 16 Error in the HTTP2 framing layer` / `Empty reply from server` |
| 对策 | 必须 gh-proxy | 小仓直连可试；**大仓（>50 MB）直接用 gh-proxy** |

- 加 `-c http.version=HTTP/1.1 -c http.postBuffer=524288000` 能减少 HTTP2 那类失败，但**不根治**：同一台 188 上 `gh-proxy` 克隆 48 MB 仓 **29 秒**成功，直连连试 3 次全败。⇒ 别在直连上反复耗，换中转。
- gh-proxy 的 URL 形状与仓内 `insteadOf` 配法见 §14。

### 机器同名陷阱：脚本名里的 "188" 不一定是这台 188

实例：`verl/my_scripts/1110_run_dsv41_188_longrun_v1.sh`，同名家族还有 `1110_dsv41_188_common.sh`。打开头注释才发现写的是「**单机 16 卡（80.5.27.188）**」——公网地址，不是 `192.168.13.188`；它硬编码的 `/mnt/share/m00899630/...`（repo / 493 GiB 权重 / parquet / py521 overlay）在蓝区两台机上**全部 MISS**，190 的 NFS（285T）里也没有。
⇒ **跑别人的脚本前，先 `head -30` 看头注释 + `grep -nE '/mnt/|/home/|主机名|IP'`，确认主机和路径对得上**；同名不代表同机。

### 远程重试的三条纪律（本轮真踩，代价是丢了一次好克隆）

1. **失败分支不要无条件 `rm -rf <目标目录>`。** 实测：脚本 B 11:37 克隆成功并核对到正确 HEAD，脚本 A 的第 3 次尝试 11:44 才失败、执行兜底的 `rm -rf verl`，把 B 的成果删了。重试脚本只在 `[ -d dir/.git ]` 为假时才克隆，删只对「本进程刚建的空目录」做。
2. **`pkill -f <脚本名>` 会匹配到你自己的 ssh 包装命令**，等于自杀：本轮 `pkill -f 188_verl_retry.sh` 把自己那条 `bash -c` 干掉，返回 `[exit code: 1]`、后续命令一行没跑。要停就按 PID，或先确认它已自行退出（`ps -eo pid,args | grep` 仅用于观测，不要拿它喂 kill）。
3. **`docker exec -d` 不把内层 stdout 交给调用方**：`docker exec -d ... 'bash x.sh' > host.log` 里宿主侧 `>` 收到 0 字节。重定向要写进容器内命令：
   ```bash
   docker exec -d $NAME bash -lc '{ bash /path/x.sh; echo "exit=$?"; } > /home/.../x.log 2>&1'
   ```
   日志落在 bind 挂载进容器的目录上，宿主就能直接 tail。
4. 反查自家进程别用会自匹配的 `pgrep -af <关键字>`：本轮 `pgrep -af 'docker pull' | head -1` 恰好命中自己的包装命令，误判成「pull 进程没了」。改成查 PID（`ps -o etime= -p <pid>`）或匹配更长的唯一串。

## 实例 2 的 TAP 丢失后 A5 不可达：用原件 Switch 应急（2026-11-14 实测）

## 实例 2 的 TAP 丢失后 A5 不可达：用原件 Switch 应急（2026-11-14 实测）

**现象**：`177.x` 四台 TCP 22 全不通、`177.0.0.0/8` 路由不存在，但 `UVP002.exe` / `UVP002CS.exe` / `UVP002Service` 都在跑、`sysconfig.ini` 里 `AutoLogin=1` 且 `ClientLastAccessSession=A5.ini`。`univpn-instance.ps1 -Action State -Instance 2` 回 `Connected=False`、`TapName` 为空。

**根因**：系统里**只剩一张 TAP**（`Get-PnpDevice -Class Net` 只有 `ROOT\NET\0000`），实例 2 那张 `本地连接 2` 连同设备节点一起消失（客户端重装会顺带清掉多实例 TAP；同日 `ifIndex` 从 13/55 变成单张 14 也指向重装）。没有 TAP，引擎自动登录也连不上；`-Action Connect` 会**挂死超过 120 s**（等一张永远不出现的网卡），别在前台等。

**应急（不修多实例，2 分钟内拿到 A5）**：原件客户端里同时有 `A5.ini` 与 `蓝区网关.ini`（`%APPDATA%\UniVPN\config\`），直接切配置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File vpnctl.ps1 -Action Switch -Profile A5 -Username vpn_xmz
# 成功输出：Connected True / Profile A5 / VirtualIP 1.2.x.x / TapRoutes 含 177.0.0.0/8 170.70.0.0/16 197.0.0.0/8
```

代价：**蓝区 A3 同时断**（`192.168.0.0/16` 路由消失），要回 A3 再 `-Action Switch -Profile 蓝区网关 -Username x00886548`。互斥是单 TAP 的硬约束，双隧道必须先把实例 2 的 TAP 修回来（`D:\workspace\tmp\univpn-multi` 与 `.univpn-multi\instance-002.json` 里的 `TapGuid {7706C901-...}` 都还在，重建 TAP 需管理员）。

**判读顺序**（别乱试）：`Get-PnpDevice -Class Net` 数 TAP 张数 → 只有 1 张就是本条；有 2 张再去查路由/认证。

## 实例 2 的 TAP 丢失：建 TAP + 按新 GUID 重打补丁真正修回来（2026-11-14 实测）

上一节只给了「原件 Switch 到 A5」的应急；**这里是把双隧道真正修回去的完整路径**（约 2 分钟，不重装实例、不动原件）。

**判据**：`Get-NetAdapter -IncludeHidden | ? InterfaceDescription -like 'TAP-Windows*'` 只剩 1 张（本轮 `{7AD1593C-...}` `本地连接` ifIndex 14）；`Get-PnpDevice -Class Net` 连非 present 的设备都没有；`instance-002.json` 里的 `{7706C901-...}` 在注册表 `HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e972-...}` 下也查不到 ⇒ 设备节点被整体删除，不是被禁用，`Enable-NetAdapter` 之类没用。

**为什么必须重打补丁**：UVP002 的 `UVP002.exe` 与 `serviceclient\UVP002CS.exe` 里**嵌着实例 TAP 的 GUID**（`PatchInstance` 把 `GUID大写\0GUID小写\0` 写进 `.rdata` 尾部 padding 并改指针）。`tapinstall install` 新建的 TAP 拿到的是**新随机 GUID**，不重打补丁仍然「等一张永远不出现的网卡」（`-Action Connect` 挂死 >120 s）。`promote\UVP002PromoteService.exe` 不含 GUID（kind=1 只改名/端口）。

步骤（全部提权，**先关 UniVPN / UVP002 全部进程**）：

1. `Stop-Service UVP002Service -Force` —— 要覆盖 `promote\UVP002PromoteService.exe`，服务在跑会锁文件。
2. `& 'C:\Program Files (x86)\UniVPN\driver\ev\tapinstall.exe' install OemVista.inf tap0901`（实测 exit 0，输出 `Device node created...` + `Drivers installed successfully.`；新网卡名 `本地连接 2`）。
3. 取**新增的那 1 张** TAP：比较操作前后 `InterfaceGuid` 集合的差集。**不要用 ifIndex 或网卡名判**（名字可能是 `本地连接 2`/`本地连接 3`，ifIndex 每次重排）。
4. 读**原件**三个 exe 的原始字节 → `[UniVpnMulti.BinaryPatch]::PatchInstance($bytes,$kind,$newGuid,2)` → 写回 `C:\Program Files (x86)\UniVPN2\` 对应路径（kind 0=`UVP002.exe`、1=`promote\UVP002PromoteService.exe`、2=`serviceclient\UVP002CS.exe`）。**必须从原件字节重打**，不能拿已打补丁的文件当输入：`.rdata` padding 已非零，`Payload` 会抛 `Padding is not empty`。
5. 更新 `C:\Program Files (x86)\UniVPN\.univpn-multi\instance-002.json`：`TapGuid` = 新 GUID（`"B"` 大写格式）+ `Files[].Hash` 换成新 SHA256 + `Status=Ready`。**不更新的话**：`vpnctl.ps1` 的排除逻辑按 json 里的 GUID 排除实例卡，会把两张 TAP 都当实例卡（`State` 报错/挑错网卡）；多实例工具的 `Open-Client` 也会 `Instance binary verification failed.`。
6. `Start-Service UVP002Service`，等 `Get-NetTCPConnection -State Listen -LocalPort 29191` 出现 1 个 listener。
7. `Start-Process 'C:\Program Files (x86)\UniVPN2\UVP002.exe'`，`AutoLogin=1` + `ClientLastAccessSession=A5.ini` 会在 ~20 s 内自己连回 A5，不用点登录。

`PatchInstance` 的 C# 在 `D:\workspace\tmp\univpn-multi\UniVPN-Multi.ps1` 的 `Add-Type` 里：把整块 `if (-not ('UniVpnMulti.BinaryPatch' -as [type])) { ... }`（该文件第 131~258 行，含结尾 `}`）原样抽出来拼到自己的修复脚本前面即可，C# 一行都不用改。本轮拼好的成品 `D:\workspace\tmp\vpn\repair-tap2.ps1`，日志 `D:\workspace\tmp\vpn\repair.log`。

**坑（本轮全踩）**：

- `Start-Process -Verb RunAs` **不能和 `-NoNewWindow` / `-RedirectStandardOutput` 同用**：`Start-Process : 无法使用指定的命名参数解析参数集。... FullyQualifiedErrorId : AmbiguousParameterSet`（skill 里记的 `-Verb RunAs -NoNewWindow -Redirect*` 写法在本机 PS 5.1.26100 上不成立）。改法：日志写进**目标脚本自己**——`Start-Transcript -Path <log> -Force` 开头、`Stop-Transcript` 收尾，外层只 `Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList $argLine`。
- 写带 BOM 的包装 `.ps1`：`[IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($true)))` **本身已写 BOM，不要在字符串前再拼 `[char]0xFEFF`**，否则双 BOM；PS 5.1 只剥掉一个，另一个进正文，报 `The ampersand (&) character is not allowed`（指向第 1 行 char 2，看着像语法错）。
- 补丁器对**原件**做 SHA256 白名单（`UniVPN.exe` `24f90f30...` / `promote\UniVPNPromoteService.exe` `e038021b...` / `serviceclient\UniVPNCS.exe` `cf07de7e...`，版本 `10781.19.0.1214`）；不匹配直接 `Unsupported UniVPN binary/version. No patch applied.`。打之前先用 `Get-FileHash -Algorithm SHA256` 对一遍，比事后猜错因快。
- 拼装脚本别手抄 C#：`(Get-Content $multi -Encoding UTF8)[130..256] + '}'` 取块，再和修复逻辑拼接，最后用 `[System.Management.Automation.Language.Parser]::ParseFile()` 验 `$errs.Count -eq 0`（`PSParser.Tokenize` 不查括号配对，会假通过）。
- 验收别只看 IP：`Get-NetRoute` 必须是 `192.168.0.0/16 经本地连接`、`177.0.0.0/8 经本地连接 2`；本轮 ifIndex 是 **14 / 24**（旧文 13/55、11-13 的 14/15 都作废，只当打印值，别写进脚本条件）。
- 修好后原件照常：`vpnctl.ps1 -Action ResetUi -Profile 蓝区网关` 一条命令就能把蓝区拉到默认会话（它先杀 UI → 把 `ClientLastAccessSession` 改写成 `蓝区网关.ini`（GBK）→ 重启 UI → 自动登录），中文 profile 名走**包装 .ps1** 别走命令行。

## A5 隧道掉线后的判读与 15 秒恢复（2026-11-14 晚实测）

**先分清三种"不通"**，别一上来就重建 TAP：

| 现象 | 结论 | 动作 |
|---|---|---|
| `本地连接 2` 还在、GUID 未变，但 `Disconnected` + IP 是 `169.254.*`，且 `Get-Process UVP002,UVP002CS` 为空 | **只是客户端进程没了**，TAP 完好 | `Start-Process 'C:\Program Files (x86)\UniVPN2\UVP002.exe'`，15 s 内回来 |
| 只剩 1 张 TAP / `instance-002.json` 的 GUID 查不到 | 设备节点被删 | 走上一节「建 TAP + 新 GUID 重打补丁」 |
| TAP Up、IP 正常但目标不通 | 路由/认证/远端问题 | 先 `Get-NetRoute` 看有没有 `177.0.0.0/8` 经该 TAP |

**恢复实测（只需一条命令）**：`Start-Process 'C:\Program Files (x86)\UniVPN2\UVP002.exe'` → t+10 s 拿到虚拟 IP（`1.2.19.18`）但 **`177.0.0.0/8` 路由还没有** → t+15 s 路由才下发。⇒ 判据必须等路由，别只看 IP（踩过一次：拿到 IP 就测目标机，全部误报不通）。

**区分「正常退出」与「被杀/崩溃」**（判断要不要查更深）：

- UI 日志 `%APPDATA%\UVP002\log\UVP002_UVP002UI_0.log`：正常退出会写 `[into main ui exit pre]` + `[#################UI exit!#################]`。**进程已消失却没有这两行 = 被杀或崩溃**（本轮 18:16 就是这种，日志里没有任何 logout/exit）。
- 引擎日志 `UVP002_UVP002CS_<pid>.log`：每约 1 MB 换一个文件（约 5~6 分钟一个）；进程突然消失时最后一个文件停在半截（本轮停在一条 route print 中间）。
- 先排除整机重启：`(Get-CimInstance Win32_OperatingSystem).LastBootUpTime`。
- 别把 Application 日志里的 `Application Hang` (Id 1002) 直接当成 VPN 崩溃证据——本轮那条指向 `codex-windows-sandbox-setup.exe`；**VPN 进程崩溃在这台机的 Application 日志里没有记录**。

**A5 没有自愈**：`UVP002Service` 是 Manual、无 auto-start 项，进程被杀后就是静默掉线，没人拉起。要长期在线得自己盯（或保留托盘进程）。**A3 侧不一样**：原件掉线后会自行重连（虚拟 IP 会变，本轮 `192.168.206.148` → `.177`），判据仍是 `192.168.0.0/16` 经 `本地连接`。
