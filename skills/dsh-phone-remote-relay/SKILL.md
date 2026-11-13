---
name: dsh-phone-remote-relay
description: 手机接管电脑上的 DSH：中继丢包 / 唤醒断连 / 建联失败 / 多标签互斥 / 任务落到未分组 / 版本是否生效
---

# 手机跨网络接管 DSH（零公网暴露）

## 何时调用

- 用户要**手机在任何网络**（5G/公司网）看和操作电脑上的 DSH，且明确**不许把电脑暴露到公网**。
- 已经在用「公共中转 + 端到端加密」这条路，出现**随机请求超时 / 任务列表为 0 / 首屏很久**。
- 改完插件代码，热重载后**行为没变**（页面还是旧的）。
- 要给手机一份可扫码的入口，且不想自建服务器。

## 1. 架构（一句话）

电脑与手机各自**出站**连同一个公共 MQTT broker，主题 `dshm/<room>/u|/d`；
载荷 AES-256-GCM 封箱（密钥只在二维码 `#` 片段里，不上行），AAD 绑定方向主题。
手机侧由 `remote.js` 把 `fetch`/`WebSocket` 换成走中继的实现，然后 `import` 同一份 `app.js`。
**电脑侧零监听**，所以不违反"不许反向代理/端口映射"。

## 2. 五个必踩的坑

**① 热重载 ≠ 新代码（最坑）**：Node 的 ESM 缓存是进程级的，Cordis 重新 `apply()` 时
`import` 还是缓存里的旧模块。判据：日志出现 `plugin loading` 但新路由仍 404、页面没有新增元素。
要么**冷启动宿主**，要么把通道跑成**独立进程**（`tools/cloud-daemon.mjs`），
两者共用同一个 `cloud.json`，二维码不变；宿主重启后插件接管，守护进程自查 `/cloud/status` 在线后自杀。

**② hello 自激**：双方都"收到 hello 就回 hello" → 无限回声，几百毫秒一轮，
把公共 broker 打到限流 → **随机丢帧 → RPC 超时**。回复必须限速（≤1 次/10 s）或干脆不回，
只靠周期 beat 维持在场。

**③ 大帧被丢**：公共 broker 对包大小/速率有限制。明文单帧压到 **24 KiB**
（封箱后约 33 KiB），超出按 `{t:'part',id,seq,total,d}` 分片，接收端按 id 重组。
把 96 KiB 时的丢包率和 24 KiB 对比过：96 KiB 下 5 次里能丢 2 次。

**④ 重发必须幂等**：手机超时用**同一个请求 id** 重发；PC 侧 `id -> 响应` 缓存 120 s，
命中就重放、**不再执行**。否则重发的 `POST /tasks` 会建出两个任务。
重试节奏按"每次 4 s × 4 次"，不要用一个 40 s 的大超时（丢一帧要等 13 s 才重发）。

**⑤ WS 帧合批**：会话回放一次能推 300+ 个小帧，一帧一条 MQTT 消息必然触发限流。
按 40 ms / 24 帧聚成 `{t:'ws.msg',id,frames:[…]}`，实测 309 条消息降到 27 条。

## 3. 手机端 shim 要点

- 造一个假 origin（如 `https://dsh-remote.local`），`app.js` 完全不用改。
- `window.fetch` 返回**真的 `Response`**；`content-encoding: gzip` 用 `DecompressionStream('gzip')` 解。
- `WebSocket` 用 EventTarget 形状（`CONNECTING/OPEN/CLOSING/CLOSED` + `onopen/onmessage/onclose`），
  并把 `EventSource` 置为 `undefined`，让 UI 自动退回 WS。
- 首屏先渲染 splash，连上再 `await import('./app.js')`；链接参数缺失时给手工输入页。
- `app.js` 里 `register('/app/sw.js')` 是绝对路径，静态托管必须重写成 `./sw.js` 并真的产出一个 SW，
  否则控制台一直报 404。

## 4. 托管与发布

- `cdn.jsdelivr.net` 把 `.html` 当 `text/plain` 发 → 不能用来托管外壳。用 GitHub Pages。
- **本机 `git push` 挂满 120 s 无任何输出 —— 真因是凭据助手弹了一个看不见的 GUI 框在等输入，不是 TLS/schannel。**

  **现象**：`push` 挂满 120 s 一个字都不吐；同一时间同一台机器 `ls-remote` 1 s 就返回。
  **`ls-remote` 走的是匿名读，它的成功不能证明凭据是好的** —— 这正是把人带上"网络 / schannel"错路的假线索。

  **真因**：`credential.helper`（wincred / GCM）在等 GUI 输入。`GIT_TERMINAL_PROMPT=0` 只关终端提示，
  **拦不住 GCM 弹出的窗口**；进程既不报错也不退出，看起来就是"网卡住了"。

  **两条实测可用推法**（绕开那个窗口）：

  ```powershell
  # GitHub（实测 2.2 s 成功）：清掉 helper，把 PAT 直接写进 URL
  git -c credential.helper= -c http.version=HTTP/1.1 push https://x-access-token:<PAT>@github.com/<owner>/<repo>.git main
  #   PAT 在 ~/.dsh/.secrets/github-pr-flow.token

  # GitCode（实测 4 s 成功）：**保留**默认助手即可，wincred 里已有 git:https://gitcode.com 缓存
  git -c http.version=HTTP/1.1 push gitcode main
  ```

  **鉴别方法**（一句话记住）：`-c credential.helper=` 在 GitCode 上 **0.8 s 快失败** `fatal: could not read Username`；
  在 GitHub 上却**挂满 120 s**。同样是"没凭据"，一个快失败、一个假死
  ⇒ **看到假死先怀疑 GUI 凭据框，别去查网络。**

  **收尾校验**：`origin` / `gitcode` / 本地三处 SHA 逐字符相同才算推送完成：

  ```powershell
  git ls-remote --heads origin main    # GitHub
  git ls-remote --heads gitcode main   # GitCode
  git rev-parse HEAD                   # 本地
  ```

  **最后手段**（两条推法都不通、或只改静态文件不想碰 git）：Contents API
  `PUT /repos/{o}/{r}/contents/{path}` 逐文件上传（base64），
  `POST /repos/{o}/{r}/pages` + `{"source":{"branch":"main","path":"/"}}` 开启 Pages。
  建仓用 MCP `create_repository`，不必先有 PAT。
- 发布后轮询到 `200` 且内容含新标记再算完成（Pages 构建有 1–3 分钟延迟）。

## 5. 验收（缺一步都不算通）

1. **Node 侧协议探针**：同进程起 `CloudLink`，再当"手机"用 MQTT 发一条 `req`，断言 `status/字节数`
   —— 先证明 PC 侧分片与压缩没问题，再去怀疑浏览器。
2. **手机视口 E2E**（Playwright，390×844）：`header` 出现「实时同步中」、任务数 > 0、
   点开一条任务能看到工具调用；再 `POST /api/v1/tasks` 建一个"只回两个字"的任务，
   验证 **WS 推送**让它不刷新就出现。
3. **二维码必须解码验证**：渲染 PNG 后用 `jsqr` 解一遍，断言与 `cloud-url.txt` **逐字符相等**。
   肉眼"看着像二维码"不算。
4. 记录数字：单次 RPC ≈ 0.5 s、300 条任务（179 KB）1–3 s、吞吐 ≈ 110 KB/s。

## 6. 必须交代给用户的

- 流量经**第三方公共 broker**（`broker-cn.emqx.io` 是 EMQX 测试用），只承载密文，
  但**元数据**可见、**不保证可用性**；换自建只需改一处 `broker`。
- **链接等同凭据**：泄露就删 `cloud.json` 重启（旧码立即失效）。别截图外传。
- 想更低延迟/更大带宽可叠加 Tailscale（私有网状网，**不开 Funnel** 仍不算公网暴露），
  HarmonyOS NEXT 用 MeshArc；防火墙只放行 `InterfaceAlias "Tailscale"`、`Profile Private`。

**"端到端加密"要能当场自证，否则别写进交付物。** 做法：起一个**不知道密钥**的
第三方客户端，匿名连同一个公共 broker、只凭主题名订阅 `dshm/<room>/#`，抓真实帧：

```
原始帧: {"v":1,"n":"Hw1KrPwSslExf3QR","c":"EOR0ahdn3MJpxLLIyUsQcga56WUlm8U7JUVwQf…"}
明文关键词命中: 无
错钥匙  : Unsupported state or unable to authenticate data
真钥匙  : {"t":"beat","name":"我的电脑","ts":…,"peers":5}
改 AAD  : Unsupported state or unable to authenticate data
```

三条缺一不可：**信封只有 {v,n,c}**（12B IV + 密文 + 16B GCM tag）、
**错钥匙报认证失败而不是乱码**、**AAD 绑主题名**（改一个字符就解不开，防跨主题重放）。
信封就是 `{v,n,c}` 三字段——别按 `{iv,tag,d}` 去写解包器，会得到
`The first argument must be of type string …` 这种误导性报错。

## 6.5 三条「假断连」根因：手机先喊、电脑后知

界面反复「正在连接 / 已断连」，而电脑端其实是好的——三条根因全在时序上，且都表现为**手机先喊**。

1. **首连误判 stale**
   现象：刚建好的健康链路 2 s 后被自己推倒重建（实测 85 s 内建 4 条隧道、`slots 1→4`）。
   根因：手机侧 `startStaleWatch` 用 `idle = now - max(pcSeenAt, lastRxAt, readyAt)` 判「电脑端离线」，而首连只置 `ready=true`、不置 `readyAt` ⇒ `idle≈Date.now()` 必判 stale。
   修法：首连同时置 `readyAt`。教训一句话：**任何"多久没消息"的看门狗，下界必须是"本次连接建立时刻"，不能是 0。**
2. **孤儿槽位**
   现象：用户感知就是「有时重连要非常久」——12 槽占满后回 `too many channels`，只能干等 10 分钟空闲 sweep。
   根因：`_close()`（open timeout / open failed / 中继重建）只删本地表、**不通知电脑端**，而电脑端 `ws.close` 对未知 id 直接丢弃 ⇒ 迟到的 `ws.open` 照建隧道，没人再关。
   修法两层：关闭路径一律通知对端 + 服务端加 **60 s「墓碑」**（迟到的 open 只回 close 不建链）；满员时强制回收最旧一条。
3. **探测顺序反了**
   现象：每次半死链路都必然是手机先喊离线、先折腾，电脑端永远慢一步。
   根因：电脑端没有应用层探活，靠 `keepalive:40` 让 mqtt.js 最坏 60 s 才判死，而手机 26 s 就判离线。
   修法：电脑端 **3 s 采样 / 17 s 判死 / 连续 2 次 strike 才重建**（上界 ≈23 s < 手机 26 s），并**用测试把「电脑端判死上界 < 手机端阈值」这条不变量钉死**，否则日后有人调阈值就会悄悄退化。

## 7. 路径 B（Tailscale）在 Windows 上的七个坑

**① 提权：`Start-Process -Verb RunAs -Wait` 会假挂。** 提权其实成功了（探针跑出
`High Mandatory Level`），但 `-Wait` 不返回，命令被工具判超时转后台。可靠写法是
**标记文件 + 轮询**：写一个 `.cmd` 把 powershell 调用和 `echo done=%errorlevel%> marker`
放进去，`Start-Process cmd.exe -Verb RunAs "/c <cmd>"` 后轮询 marker（别加 `-Wait`）。

**② `tailscale up` 的登录链接走 stderr。** PS 5.1 把原生命令 stderr 变成 ErrorRecord，
`$ErrorActionPreference='Stop'` 时直接抛 `NativeCommandError`，链接就丢了。用
`$ErrorActionPreference='Continue'` 包住 `(& $ts up --timeout=10s 2>&1 | Out-String)`，
再正则取 `https://login\.tailscale\.com/\S+`。`--timeout` 让它在没人点登录时自己退出。

**③ userspace 路线在 Windows 走不通。** `tailscaled --tun=userspace-networking` 可以启动，
但 `--socket` 必须是命名管道：传文件路径报
`namedpipe.Listen: open ...: Incorrect function`；改 `\\.\pipe\...` 又报
`not under \\.\pipe\ProtectedPrefix\Administrators\ ... must pass --windows-mode=dev`。
想免管理员就得走 dev 模式，且还要自己解决入站转发——**不值得**，老实装 MSI。

**④ 放行规则要绑接口而不是绑 IP。** `New-NetFirewallRule -InterfaceAlias 'Tailscale'
-Profile Private` 可用，前提是适配器已存在；Tailscale 的适配器
（`Tailscale Tunnel`）在登录前就已创建，且网络类别**默认就是 Private**，
所以规则建完立刻生效、公网网卡（通常是 Public）完全不受影响。
用 `Get-NetFirewallInterfaceFilter` 复核 alias 真的写进去了。

**另附**：MSI 可以免管理员解包看内容——`msiexec /a tailscale-setup.msi /qn TARGETDIR=<dir>`，
产物在 `<dir>\PFiles64\Tailscale\`，用于临时实验很方便。

**读状态优先用 Node 而不是 PS**：`execFileSync(exe, ['status','--json'],
{ encoding:'utf8', timeout:4000, windowsHide:true, stdio:['ignore','pipe','ignore'] })`
—— `stdio` 把 stderr 丢掉，就绕开了 PS 5.1 把 stderr 变成 ErrorRecord 的老坑；
返回 `BackendState` / `Self.TailscaleIPs[0]` 两个字段足够判断"能不能给手机用"。

**⑤ 先看 `Health`，再让人去登录——否则会连坑好几轮。**
实测现象：浏览器里登录成功，`BackendState` 始终 `NeedsLogin`，`HaveNodeKey`/`Self.ID` 空，
登录链接时有时无、点开可能 502（正文 `backend not found or not available; reqType=a/auth-path`）。
根因不在浏览器，在客户端：

```powershell
(& 'C:\Program Files\Tailscale\tailscale.exe' status --json | ConvertFrom-Json).Health
# Unable to connect to the Tailscale coordination server to synchronize the state of your tailnet.
```

协调服务器连不上 ⇒ 授权回调根本落不到这台机器，点一百次登录链接也没用。
**修复 = 重启 `Tailscale` 服务**（`Restart-Service Tailscale -Force`），重启后 Health 清空、
`tailscale up` 拿到的链接才稳。判"稳"的标准是**连续采样**：

```
t+5s … t+60s  state=NeedsLogin  authURL=…36dc970135e8  health=[]   ← 12 次采样全部稳定
```

不稳的表现是 AuthURL 过一会儿消失/变化，或点开是 502。
别用"网页能打开"当网络没问题的证据——`GET /ts2021` 返回 400、Node 的 HTTP/2 也能
连上（`missing next protocol`），说明 TLS/HTTP2 都通，**问题只出在守护进程自身的连接状态**。

**⑥ 防火墙规则不会跟着脚本默认值改；"本机 curl 自己 IP 通了"证明不了手机连得上。**
把默认端口从 8765 改到 47901 之后，**已经建好的规则还停在 8765**：

```powershell
(Get-NetFirewallRule -DisplayName 'DSH Bridge (Tailscale)' | Get-NetFirewallPortFilter).LocalPort
# 8765   ← 脚本默认值早就是 47901 了
```

更要命的是**本机访问自己的 tailnet IP 会绕开这条入站规则**：规则只放行 8765 时，
本机 `http://100.88.235.20:47901/healthz` 照样 200。所以验收不能只看本机 curl。
修法就一条（管理员）：

```powershell
$pf = (Get-NetFirewallRule -DisplayName 'DSH Bridge (Tailscale)') | Get-NetFirewallPortFilter
$pf | Set-NetFirewallPortFilter -LocalPort 47901 -Protocol TCP
```

改完复核 `port=47901 / iface=Tailscale / profile=Private / enabled=True`，
再跑 `verify-tailscale.ps1 -Port 47901` 七项全 PASS。

**⑦ 给手机一条"打开即配对"的链接，别让它手输 6 位码。**
`/app` 在非 127.0.0.1 的来源上会要求配对（设计如此），但外壳支持
`#pair=<base64 {v,u,c,n,f}>`：把 `u` 换成本机 tailnet 地址、`c` 换成当前配对码，
手机点开就直接进主界面。配对码 10 分钟失效，做成命令随用随生成：

```js
// tools/tailnet-link.mjs —— 自动读 tailscale status 的 IPv4 + /api/v1/pairing 的 code
const link = `http://${ip}:47901/app#pair=` + Buffer.from(JSON.stringify({ v:1, u:base, c:code, n, f })).toString('base64');
```

实测 `HTTP 200` + `STATE: 已进入主界面` + `TASK CARDS: 301`，控制台只有 http 源上的
COOP 提示与未交互前的 vibrate 警告（无害）。

> 边界要说清：这条浏览器验证跑在**电脑本机**访问自己的 tailnet IP，
> 证明了「地址 + 一次性配对 + 外壳 + 数据」整链通，但**不证明外部节点入站可达**。


## 8. 常驻进程、发布与防火墙的四个实测结论

**① 别用抓管道的 `-Wait` 去包"会拉起常驻进程"的脚本。**
`Start-Process powershell -NoNewWindow -Wait -RedirectStandardOutput out.txt -File deploy.ps1`
会**永久挂起**——即使 deploy 已经打印完所有内容、daemon 已 online。原因是 daemon 继承了
那条捕获管道的写端句柄，父进程退出后句柄不关，调用方一直在等 EOF。脚本本身没问题
（输出完整、退出正常）；**判据**：out.txt 里内容已经是完整的成功输出，但进程不返回。
要拿输出就**重定向到文件 + 不 wait**，然后自己轮询状态文件。

**② 常驻 daemon 不能放在"随时会被 job_kill 的作业"里。**
`job_kill` 收的是整棵进程树：把 `deploy.ps1` 当后台作业跑，deploy 拉起的 daemon 是它的
孙子进程，**kill 作业会把 daemon 一起带走**（现象：pid 文件还在、`/healthz` 仍 200，
但 `Get-CimInstance ... cloud-daemon.mjs` 查到 0 个，状态文件停在几十秒前）。
daemon 一律用 `Start-Process`（脱离作业树）启动，收尾只 kill 作业本身。

**③ Windows 防火墙默认拦「公用网络」入站——连**本机访问自己的局域网 IP** 也会超时。**
实测同一台机器：`http://127.0.0.1:8765/healthz` → 200，`http://192.168.30.222:8765/healthz`
→ 操作超时（`以太网` 的 `NetworkCategory=Public`）。所以"局域网直连打不开"多半不是程序问题。
放行要既加规则又让网络类别不是 Public；**只放行专用/域网络**（`-Profile Private,Domain`）+
按提示把家庭网切成 Private，不要把 8765 开给 Public 网络。

**④ GitHub Pages 的 `sw.js` 缓存名是内容哈希，长度不变。**
只比文件大小会漏判"其实已经改了"（哈希 12 位换一个字符，字节数一模一样）。
发布后必须**按内容复核**：抓线上 `sw.js` 正则取 `dsh-remote-[0-9a-f]+`、抓线上 `app.js`
断言旧字符串已消失，再跑一次真浏览器 E2E。
另外 `powershell -File x.ps1 -Files a,b` 里 **数组参数会退化成单个字符串 `"a,b"`**
（不是两个元素），要么在脚本里 `-split ','`，要么在进程内用 `& x.ps1 -Files @('a','b')` 调用。

## 9. 端口被抢、守护进程崩、离线假象——链式故障（实测）

**① "端口被别的程序占用"会伪装成"插件坏了"。**
共享主机上别人起 `python -m http.server 8765` 抢走端口后，插件热重载绑不上，
`http://127.0.0.1:8765/` 回的是 **HTML 目录列表**、`/healthz` 404。判据：

```powershell
(Invoke-WebRequest "http://127.0.0.1:8765/" -UseBasicParsing).Content   # "Directory listing for /" ⇒ 不是我们的服务
```

**修法**：哨兵端口默认别选 8765 这类"人手会随手挑"的圆整数（本项目已迁到 **47901**）；
客户端 `fetch(...).json()` **必须先看 `content-type`**，否则对 HTML 解析抛
`SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON` 把守护进程直接打死；
启动阶段对"桥还不存在"要**等 + 重试**（本项目 2 分钟 × 5 s），不要一碰就退出。
`deploy.ps1` 要把 `--bridge http://127.0.0.1:<Port>` 显式传给 daemon，别让两边各自用默认值。

**② 改插件 `port` 会触发热重载，不用重启整个 DSH。**
实测改完 `cordis.patch.yml` 的 `port: 47901` 保存后 **8 s 内**新端口 `/healthz` 200
（`uptimeMs` 可自证是新进程）、旧端口释放。这跟"改代码要冷启动"是两件事——代码在 ESM
缓存里，配置是每次 apply 重新读的。

**③ "实时同步中"必须是会被推翻的断言。**
中继还连着时手机和 broker 的 MQTT 不会 close，电脑死掉**不会触发任何事件**；而 RPC 要
16 s × 4 次才判定失败，所以界面上会一直挂着"实时同步中"——列表早就旧了。
判活只能靠**电脑端心跳静默**：心跳 8 s 一条、阈值 26 s（≈3.25 拍）、
横幅挂 `body` 下的固定层（`#dsh-remote-offline`）而不是塞进 `<header>`。
实测：停中继 +27 s 出横幅、拉起后 +6 s 消失。**探针只读 `<header>` 文本会漏判横幅**。

**④ PS 5.1 里 `New-Object System.Text.UTF8Encoding($true)` 可能不写 BOM。**
用 `[IO.File]::WriteAllText($p, $t, (New-Object System.Text.UTF8Encoding($true)))` 改中文
`.ps1` 后实测 `bom=False`，脚本随即报 `缺少 '}' 终止符`（PS 5.1 按 GBK 解码 UTF-8 字节）。
可靠写法：

```powershell
$enc = New-Object System.Text.UTF8Encoding($true)
[IO.File]::WriteAllBytes($p, $enc.GetPreamble() + [Text.Encoding]::UTF8.GetBytes($text))
```

改完**立刻回读校验** `[IO.File]::ReadAllBytes($p)[0] -eq 0xEF`，别信构造函数。
**`edit`/`write` 这类文本工具写回 `.ps1` 会顺手把 BOM 抹掉**——每次用它们改完中文 `.ps1`，
必须再补一次 BOM 再 `ParseFile` 校验，否则下一次 `powershell -File` 直接解析崩。

**⑤ 插件热重载后，中继守护进程里那条长连 WS 会变成"僵尸"——重启中继即可。**

实测：同步插件文件（robocopy）触发 Cordis 热重载后，手机外壳标题栏变成
「**连接中断，正在重试**」，但**任务数据照常加载**（353 条、汇总都对）。原因是
HTTP 每次都是一次新请求，而 WS 是一条长连接——宿主重载后它指向的旧连接已废。
本机直连 WS 用 ticket 探针（`POST /api/v1/ws-ticket` → `ws://127.0.0.1:47901/ws?ticket=`）
仍能秒连并收到 `hello`/`summary` 洪流，证明桥接自身健康，问题只在中继那条隧道。

判据与修法：**HTTP 通 + WS 不通 = 重启中继进程**（`deploy.ps1 -Restart`），
重启后 5 秒内恢复「实时同步中」。别去查 broker、别重扫码。
**⑥ MQTT 半开连接：`connected=true` 但帧到不了，状态文件还在骗你说 online。**

实测症状（手机端）：**显示「已连接 我的电脑」，但任务永远 0 条**，40 s 后转成
「连接中断，正在重试」。同时电脑侧 `cloud-status.json` 每 3 s 刷新、`state` 一直是 `online`。
排除法：本机 `/api/v1/tasks` 16–38 ms 返回 300 条（桥接好的）、broker 8084 建连 416 ms（网络好的）。

根因在 `mqtt.connect({ reconnectPeriod: 0, ... })` 这一行：**自动重连是关的**，
只有收到 `close` 事件才会走 `retry()`。TCP 半开时不会发 `close`，`client.connected`
和 `link.state` 都还是真值——于是守护进程照旧发帧，发进一条已经死掉的管道。
小帧（连接时那条 `hello`）早走了，**大响应（任务列表要分块）全堵死**，看起来就像"连上了但没数据"。

修法（两层）：

```js
// 1) publish 一定带回调，别静默丢
this.client.publish(topic, sealed, { qos: 1 }, (err) => { if (err) logger.warn('publish failed: ' + err.message); });

// 2) 守护进程里加链路看门狗，15 s 一查，连续 3 次异常就重建连接
const connected = client?.connected === true;
const queued = client?._outgoing?.length ?? 0;      // mqtt.js 发件队列，卡住时会一直涨
if (link.state === 'online' && connected && queued < 100) { strikes = 0; return; }
if (++strikes >= 3) link.retry();                    // retry() 会 end(true) 掉死连接再 connect()
```

> 判据一句话：**状态文件说 online、hello 能收到、但大响应不来 = 半开连接**，
> 重启中继立刻恢复；别去重扫码、别怀疑密钥。
**⑦ 两个中继实例同时在线：`-Restart` 看不见手动起的那个，手机端分片来自两条连接。**

实测：先用 `Start-Process` 手动起了中继（pid 40768），它不写 `cloud-daemon.pid`；
后来跑 `deploy.ps1 -Restart`，脚本只认 pid 文件 → 认为没在跑 → 又起一个（39156）。
两个实例都订阅同一上行主题、都往下行主题发应答，手机端拿到的分片可能来自两条连接，
任务列表永远拼不成 —— 表现和"半开连接"几乎一样，但**状态文件一直是 online**。

判据：`Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*cloud-daemon.mjs*' }`
返回**多于一行**就是双实例。

修法（放守护进程自己身上，别只靠启动脚本记账）：

```js
// 启动时接管：pid 文件 + 全量扫描双保险，身份按"命令行含 cloud-daemon.mjs"核验
process.kill(storedPid);                                  // 核不上就不杀，打 warn 跳过
writeFileSync(PID_FILE, String(process.pid), 'ascii');     // 自己登记，谁启动的都算
process.on('exit', () => { if (文件里还是我) unlinkSync(PID_FILE); });
```

验证方式：故意再起第二个实例，日志应打印「接管：已停止重复的中继 pid=…」，
`实例数` 仍为 1。

**⑧ 隧道槽位只增不减：手机被强杀时不发 close，刷几次就再也连不上（HTTP 还通）。**

实测：中继侧 `MAX_SOCKETS = 6`，每部手机占一条 WS 隧道；页面刷新 / 强杀 / 切后台都不会发
`ws.close`，槽位一个个被僵尸占满。满之后手机仍能拉 HTTP（每次新请求），但 `ws.open` 被拒，
界面永远停在「正在连接…」——**和"电脑没开"长得一样，实际链路是好的**。修复前 15 次冷启动里
挂 1 次，跑完 7 项回归后基本必挂。

三层修法（缺一层都会复发）：

```js
// 1) 槽位放宽 + 满时按最近活动时间顶掉最旧的（正在握手的 10 s 内不抢）
const MAX_SOCKETS = 12, SOCKET_IDLE_MS = 60 * 60 * 1000, SOCKET_EVICT_AFTER_MS = 10 * 1000;
this.socketActivity.set(id, Date.now());            // 收到上行帧就 touch
if (this.sockets.size >= MAX_SOCKETS) this.evictOldestSocket();  // 先扫过期，再顶最旧
this.publish({ t: 'ws.close', id, code: 1001, reason: 'evicted for a new channel' });
// 2) 手机侧 pagehide / beforeunload 主动发 ws.close（尽力而为，强杀时不会执行）
// 3) 握手超时：CONNECTING 状态 12 s 没等到 ws.open 就 _close(1006) 让上层重连
```

验证：造 13 个「屏蔽 pagehide 后关掉 context」的僵尸把 12 个槽位占满，再开正常客户端，
仍能 5.9 s 内连上（`_spike/zombie.mjs`）；串行开关 15 次后 `sockets` 必须归零。

**⑨ 用 `Start-Process -RedirectStandardOutput` 拉起常驻进程，会让调用方的管道永远等不到 EOF。**

实测：`deploy.ps1 -Restart` 直接在控制台跑没事，但把它接进管道（`| Out-String`、
`Start-Job`、CI 捕获）就**挂死 75 s 以上**，进程其实早就起来了。原因：`Start-Process`
用 `bInheritHandles=TRUE` 创建进程，调用方 stdout 管道的写端被孙进程一并继承，捕获端等不到 EOF。

修法：改成 `cmd` 的 `start /b` + 三条显式重定向，彻底断开继承链：

```powershell
$launcher = Join-Path $dataDir 'start-relay.cmd'
[System.IO.File]::WriteAllText($launcher, (
  '@echo off' + "`r`n" +
  ('start "" /b "{0}" tools\cloud-daemon.mjs --bridge http://127.0.0.1:{1} > "{2}" 2> "{3}" < NUL' -f $node, $Port, $logFile, $errFile)
), (New-Object System.Text.ASCIIEncoding))
Start-Process -FilePath $launcher -WorkingDirectory $pluginDir -WindowStyle Hidden | Out-Null
# pid 别再靠 -PassThru 拿：让常驻进程自己写 pid 文件，脚本轮询 10 s 读它
```

判据：同样的管道调用从「>75 s 挂死」变成 5.3 s 正常返回。

**⑩ 分片大小别拍脑袋：24 KiB → 64 KiB 有意义，128 KiB 没有。**

同一配置连测 6 次取中位数（端到端「冷启动→标题变实时同步中」）：

| MAX_FRAME | 中位 | p90 | 备注 |
|---|---|---|---|
| 24 KiB | 8.9 s | 12.5 s | 原值，过于保守 |
| 64 KiB | 8.0 s | 10.0 s | **采用**，密文 ~88 KiB，远低于 EMQX 1 MiB 上限 |
| 128 KiB | 7.9 s | 9.1 s | 无实质收益，风险更高 |

注意：单次数字毫无意义（公共 broker 抖动可达 ±40%），必须看同一时段的多轮中位数。
## 10. 一键安装器的四个实测坑（写 `install.ps1` 时踩的）

**① `-File` 启动时，`param()` 默认值里的 `$PSScriptRoot` 可能是空的。**
`[string]$Source = (Split-Path -Parent $PSScriptRoot)` 直接报
`Cannot bind argument to parameter 'Path' because it is an empty string`。
默认值改 `''`，进函数体再算：`$here = $PSScriptRoot; if (空) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }`。

**② `?.` 是 PS7 语法。** `(Get-Command node -ErrorAction SilentlyContinue)?.Source`
在 PS 5.1 报 `表达式或语句中包含意外的标记"?.Source"`。写成两行判空。

**③ 从 patch 里删插件行，必须顺手删"变空的 `- insert:` 头"。**
只删 `- id: X` 那几行会留下 `- insert:`（值 null），YAML 合法但 Cordis 语义变了，
下次追加还可能叠出第二个空 insert。删行的算法：行缩进 ≤ 起始 `-` 缩进即行尾；
删完再扫一遍，`- insert:` 后面没有更深缩进的子项就一起删。**验收用真解析器**：

```powershell
python -c "import yaml,io; d=yaml.safe_load(io.open(r'<patch>',encoding='utf-8')); print(len(d), [list(x.keys()) for x in d])"
```

**④ 装完必须自证，别只打印"完成"。**
`install.ps1` 复制完就轮询 `http://127.0.0.1:<Port>/healthz`（90 s），
非 200 就退出 1 并提示"重启 DSH"。幂等也要实测：已有行时**改前改后 patch 的 SHA256 必须一致**。
真机验收顺序：临时 DSH home 首次安装 → 再跑一次（幂等）→ `-Force` 换端口（旧行消失、
别的插件行还在、YAML 解析通过）→ 对真实 home 跑一次（应当是 no-op）。

## 11. 安全核查清单（本机回环服务，实测）

被审计对象就是本 skill 描述的插件（PC 侧常驻桥 + 手机外壳）。它的攻击面不是"外网能打进来"，
而是 **用户浏览器里打开的任意网页去打 `127.0.0.1`**。整份清单只回答两个问题：
**跨源页能不能读**（CORS / WS Origin）、**跨源页能不能写**（CSRF 三元 / relay 头 / 幂等键）。
六个必查点，漏一个就等于全开。

**① 六个必查点（判据 + 实测结论）**

| # | 必查点 | 判据（查什么） | 实测结论 |
|---|---|---|---|
| 1 | Host 闸 | 白名单除 `127.0.0.1` / `localhost` 还收什么 | `hostAllowed()` 还收 `os.hostname()` 与 `<主机名>.local` ⇒ DNS rebinding **理论残余**。公开 DNS 注册不了单标签名，`.local` 要同网段 mDNS 投毒，不构成实际可利用 |
| 2 | WS Origin | `/ws` 升级除 Host + 一次性 ticket，**有没有 Origin 校验** | 原先**没有**。WS 握手不受同源策略约束 ⇒ 跨源页能连上并读到**全部下行帧**，而这时 Host 就是合法的 `127.0.0.1`（Host 闸救不了）。修法：**只在带 Origin 时**校验其 host 是否在 `allowedHosts()` 里；Node 客户端不发该头，中继与测试都不受影响 |
| 3 | CSRF 三元 | 写操作的三级判定与兜底 | `Sec-Fetch-Site → Origin → x-pocket-csrf`；兜底是"无任何浏览器信号时放行回环"。判据：Chromium 实测 `ping` / `form` / `fetch` / `beacon` **全都带** `Origin` + `Sec-Fetch-Site: cross-site` ⇒ 跨源页写操作全 403 |
| 4 | CORS | `Access-Control-*` 是否存在、`OPTIONS` 回什么 | **CORS 是特性不是缺陷**：全库 `access-control` 零命中、`OPTIONS` 回 204 但**不带 ACAO** ⇒ 跨源读不到响应，这正是"本机服务不给网页读"的关键。别把"没配 CORS"当漏洞报 |
| 5 | relay nonce | 中继头是"先验后剥"还是"先剥后判" | `stripRelayHeader` **先剥后判**：只要发现该头就把请求**降权为远程** ⇒ 本机伪造该头等于自杀，不是越权 |
| 6 | 幂等缓存键 | 键里含不含"方法 + 路径" | 必须含。只用客户端自选 id 时，`GET /me`（id=X）之后的 `POST /prompt`（同 id）会**命中缓存** ⇒ POST 不转发、客户端收到 200 和**上一份 body**（静默错误）。A/B 数字见 ④ |

**残余（实测，别改成 fail-closed）**：seq 表是 **64 条 FIFO**，灌满新 sid 会挤掉真实手机条目 ⇒
同一帧可再被接受一次（重放）。改 fail-closed 会连正常手机一起拒——可用性换完整性不值当，
故列为残余 + 用 `res` 幂等缓存兜 120 s。

**② 前端注入面：拿真实模块跑 payload，别读代码（最值得复用）**

外壳的 markdown 渲染若用 `createElement` + `textContent`，它**不产出 HTML 串** ⇒ 读代码判"安全"不可靠。
正确做法是**零构建地拿真实模块跑一遍**：

1. `npm i jsdom`（一次性），用 `jsdom` 造 `window` / `document`。
2. `import` 仓库里**真实的**渲染模块（如 `web/lib/markdown.js`）——不要照抄一份"差不多"的实现，那验的是你的复述。
3. 喂 **22 组** payload：`<img src=x onerror=…>`、`</script><script>…`、`javascript:`、`data:text/html,…`、
   `<svg onload>`、markdown 图片/链接注入、代码块反引号逃逸等。
4. 取渲染结果的 `innerHTML`，断言 payload 的 `<` `>` `"` 已被转成实体（`&lt;` 等）。
5. **必须加对照组**：把同一 payload **直接赋**给 `innerHTML`，`onerror` 应当真被编译进 DOM。
   对照组不红 ⇒ 探针是空转，那一堆"全绿"等于没测。

**③ 凭据布局决定泄露后果（必须写进用户文档）**

先查**凭据存在哪、每帧带不带**，再写"泄露会怎样"：

- 手机端 `localStorage` **明文**存房间密钥与设备令牌，且**每帧自动附加 token** ⇒
  **链接泄露 = 完全控制**，不是"还要口令"。
- 文档必须按这个写，否则用户会把二维码当"入口"而不是"钥匙"。
- 判据：能用一句话答完"拿到链接的人能做到什么"；答不上就是没看凭据布局。

**④ A/B 纪律：用数字差证明修好了，不信 PoC 打印的结论**

1. `git worktree add <dir> HEAD` 拿一份**原始副本**（改前代码）。
2. 同一个 PoC 在「原始副本」与「修后工作树」各跑一遍，**各记一个数字**（转发次数 / 403 数 / 接受次数）。
3. 用数字差下结论：本例旧代码 `fetch=1`、修后 `fetch=2`。
4. **不要信 PoC 里硬编码的结论文字**。血证：PoC 打印「POST 没被转发」，而同一轮 `fetch=2` 说明**已转发**——
   那行字是写死的。判据只看计数。

**⑤ 验收时的两个假绿坑**

1. **没 `cd` 进仓库就跑 glob ⇒ 0 个测试也 `exit=0`。** `node --test "test/**/*.test.mjs"` 在错误目录下
   匹配 **0 个文件**，但退出码 0、输出 `tests 0`。判据：**先看 `tests N` 的 N**，N=0 就是没跑。
2. **用目录形态传测试路径 ⇒ Node 24 直接报错。** `node --test test/relay/ test/protocol/` 报
   `Cannot find module` 指向 `test/protocol`（把目录当文件模块解析）。必须用 glob 形态。

> 相关：只核第三方静态扫描报告的结论（可达性 / 定级 / 漏报）→ `vuln-scan-report-verification`；
> 假绿的全分类与变异测试验法 → `node-test-false-green-audit`。

## ## 多标签互斥与「外壳 vs 插件」版本可观测性

需求形态：同一台手机开多个页面时，只让**最后打开**的那个生效，旧页面断开并提示。

**错的做法（实测失败）：服务端按页面标识判"谁更新"。**
同一页面重连时会带上不同的页面标识，服务端于是把它的**新隧道**当成"别的页面"顶掉，
日志特征一眼可辨：`ws open <id> slots=2` 紧跟 `ws close <id> code=4002`（新隧道被自己杀死）。
页面被反复重建，而每次重连 1 秒内就成功、横幅又有去抖，**用户看到的是"两个页面都正常"**。
再加"被顶掉的页面身份拉黑"只会变成**静默失效**（请求超时、界面不提示），更糟。

**第二个坑：下行是广播的。**
别的页面被顶掉时，那条 `ws.close` 也会到达本页。客户端必须先确认
"被关的 id 属于本页（或帧里的页面标识就是本页 sid）"才认输；
否则每个页面都会因为别人的关闭帧而自杀（实测三页全灭）。

**正确的层次：客户端选举，服务端只做自替换。**
- 用 `localStorage`（同源跨标签共享）：每个页面启动时写入自己的 id，每 ~1.5 s 校验一次；
- 发现不是自己 → 认输：**停止一切重连**（`restart()` 早退 + 清看门狗/快重连 + 掐掉 App 实时通道）并盖整屏提示；
- `pagehide` 时让位，否则"最新"这个名字会被带进坟墓；
- 服务端只保留"同一页面换隧道"的 `1000` 替换，**不要按不稳定的身份互踢**；
- 只关连接不停重连 = 旧页面立刻反抢，回到乒乓。

**版本可观测性（比功能本身更容易出事）。**
设置页只显示「插件版本」时，那个数字是**电脑端**的；手机加载了哪一版外壳完全看不出来，
排查"改了没生效"会连续几轮误判（曾把电脑端版本当成手机版本，得出错误结论）。
必须**分两行**显示「外壳版本 / 插件版本」，外壳版本**跟随发布**、不要写死；
外壳版本值若挂在"传给视图的 context"上而设置页读 store，会永远显示 `—`——
用 `globalThis` 暴露一个值最不容易被后续重构漏掉。
判据一句话：两个数字不一致 → 先解决外壳发布/缓存，**别去查逻辑**。

## 发布核对：构建哈希 / 代码标记 / 版本字面量三处

发布之后"用户说版本没变"，第一嫌疑通常被归到 Service Worker 缓存——**但先别改缓存策略，先核对线上产物**。

**坑：版本常量漂移。**
发版脚本往往只改 `package.json`、后端常量、patch 注释，**漏掉外壳/前端自己那份手写的版本常量**。
于是线上确实是新代码，页面自报的版本号却还是旧的。用户「重启很多次版本都不变」，
看起来和"缓存没更新"一模一样，很容易连着几轮往缓存方向白查。

**判据：三处独立验证，缺一不可。**
1. 线上构建产物的**构建哈希**（如 `sw.js` 里的 `BUILD`）== 本地构建的哈希；
2. 线上产物里能搜到**本次改动特有的代码标记**（新函数名、新文案、新字段）；
3. 线上产物里的**版本字面量** == 本次发的版本号。

三者的读法：
- ①② 通过、③ 落后 ⇒ **发布脚本漏改常量**，不是缓存，别去动 SW；
- ① 落后 ⇒ Pages/部署还没好，或推送没到位；
- ①②③ 都对但用户仍报旧号 ⇒ 这才是真的客户端缓存，再上"带版本号路径"之类的终局方案。

**防线**：把所有对外可见的版本号收敛成一份可被脚本批量替换的清单，发版脚本一次改完；
每次发版后按上面三步核对线上，而不是只看 CI 绿或推送成功。

> 与本文另一节「外壳版本 / 插件版本必须分开展示」配套：先能看见版本，再能核对版本，最后才谈缓存。

## 任务落到「未分组」：工作区选择器混入非注册目录

现象：手机端选了工作目录（例如 `tmp`），建出来的任务在电脑端落到**「未分组」**。

**根因是两层叠加，先看判据再看修法。**

判据（一眼定性）：
1. 打开电脑端工作区注册表 `~/.dsh/storages/workspace.json`，看目标路径在不在里面；
2. 看会话目录 `~/.dsh/sessions/<cwd 转义>/<session-id>/` 的叶子是否就是该路径。
两条一对：**路径存在、但不是注册工作区** ⇒ DSH 没有它的分组，只能归到未分组。

两层的来源：
- `listWorkspaces()` 除了返回注册工作区，还会把**"历史会话里出现过、但未注册"**的目录
  一并返回（带 `recent: true`）。这些目录在 DSH 里没有工作区。
- 客户端更隐蔽的一条：草稿目录为空时，会拿**最近一条会话的 cwd** 直接预选，
  而它与 `listWorkspaces` 是**并发**跑的，谁先返回谁生效 —— 于是未注册目录被悄悄选中，
  用户按"默认"提交就复现。

修法（三处一起改才有用）：
- 自动填充只在"该 cwd 确实匹配一个注册工作区"时才采用（路径比较要去掉尾部分隔符、忽略大小写）；
- 工作区列表加载完后，若发现草稿指向未注册目录，**改回可用的注册工作区**；
- 选择器给 `recent` 条目加显式标注（如「未注册工作区·会归到未分组」），让后果可见。

不要在插件里擅自替用户把目录注册成工作区——那会改动用户的 DSH 工作区列表，属于越权；
正确做法是提示用户"在电脑端 DSH 里打开一次该目录"。

## 要点索引（升回热目录说明）

手机跨网络接管电脑上的 DSH，电脑不暴露公网（公共 broker 中继 + AES-256-GCM + 静态外壳）。

**要点索引**（详细内容见正文各节）：
- 多标签互斥靠客户端 localStorage 选举；服务端按页面标识顶替会自伤，下行广播必须校验归属；
- 外壳版本与插件版本必须分开展示，发版后按"构建哈希 / 代码标记 / 版本字面量"三处核对线上；
- 任务落到「未分组」= 选了非注册工作区目录（`recent: true`），修法见正文；
- 排查断连：`ws close` 要同时记 code 与 reason（1000 有三种来源）；
- 本机 `git push` 假死的真因是凭据助手 GUI，不是 TLS。

## 唤醒即断连：重连函数防重入 + 半开短窗验证

症状：手机息屏/长后台再唤醒后，界面长时间停在「与电脑的连接中断了，正在重试」，有时好几分钟不恢复。

**先判"是不是客户端自己拆自己"。**
看桥日志里两条：`cloud link closed` 是否也为 0；隧道关闭的 reason 是不是固定一种。
判据组合：
- `cloud link closes = 0`（电脑与小机链路一次没断）+ `rx/tx/rpc` 仍在增长 ⇒ 链路是通的；
- 隧道日志成对出现 `ws open <新 id>` 紧跟 `ws close <旧 id> reason="replaced by newer tunnel"`，
  且周期**稳定等于握手超时的整数倍** ⇒ **客户端在拆自己**，不是网络抖动。

**根因一：重连函数无防重入。**
典型的 `connect()` 一进来就 `teardown()` 再重开：只要它被多调一次
（回前台、踢一次、定时器误判），健康隧道就被拆掉重建，形成稳定的重建周期。
修法：入口处"已在线且 socket OPEN"或"正在连接中"时**直接返回**，
另设显式 `{ force: true }` 通道给真正需要的重建路径；再加一个 `forceKick()` 封装
（teardown + 置 offline + connect(force)）。

**根因二：半开连接判死太慢。**
冻结唤醒后 WebSocket 常常"本地 OPEN、状态在线、但收不到任何帧"（半开）。
只靠一个几十秒的 dead-timer 判死，用户感知就是"断了很久"。
修法：回前台时先 probe，同时开一个**约 10 秒的验证窗**——窗口内一帧都没到，
直接 `forceKick()` 重建一次。把最坏恢复时间从几十秒压到 10 秒级。

**定位手段：关闭原因必须进日志。**
同一个 `code`（例如 1000）可能有三种来源：客户端换隧道、本地桥关闭、异常断开，
三者修法完全不同。只记 `code` 等于没记；要同时记 `reason`。

**局限（未验证）**：headless 浏览器 / CDP 不会真正冻结定时器，
"息屏唤醒"场景在本机复现不出来（后台冻结数十秒再切回，实测零重连）。
这类问题只能靠真实桥日志 + 代码路径推导，改完必须让真机复测。

## 重放/新鲜度闸门：独立拒绝码 + 时钟偏移自愈

**先分清"网络断"和"闸门拒"。**
链路状态显示 `closes = 0`、心跳与请求计数仍在增长，但界面一直「正在重试」——
这不是网络问题，是请求被**重放/新鲜度闸门**拒了。判据组合很干脆：
链路关闭计数为 0 + 业务请求失败 + 日志出现"拒绝重放/过期帧" ⇒ 闸门，不是链路。

**第一个坑：多种判据压成同一个 code。**
一个 `checkFreshness` 若把「seq 非法 / 时间戳超窗 / sid 非法 / 重放」全返回 `'stale'`，
日志里就是同一行反复刷，**看不出是哪条在拒**，排查只能靠猜。
做法：给每种判据独立 code——`bad-seq` / `bad-ts` / `bad-sid` / `replay`；
日志同时打出判据相关的**原值**：`seq`、`tsDelta`（当前时刻减帧时间戳，换算成秒）、`sid` 前缀。
这条价值极高：看一行就知道是"手机时钟比电脑慢了三分钟"还是"seq 回退了"。

**第二个坑：重试时用固定的时钟偏移重算 ts，会形成永久死循环。**
请求重试确实会换新 `seq`/`ts`，但 `ts = Date.now() + clockOffset`——
一旦 `clockOffset` 本身是错的，**每一次重试都同样超窗**，永远过不去。
用户看到的是"断了很久，重启页面也没用"（旧标签页还在后台跑）。
修法：客户端收到 `bad-ts` 时**清零 clockOffset 并重新对时**，再照常重试；
`replay` 只需换新 seq 重试；其它 code 终止请求并抛错，不要无限重试。

**验证技巧：让前后端用同一个版本号。**
把外壳（前端）与插件（后端）的版本号**改成同一个号**（例如都 `0.1.0`），
设置页把两个号并列显示。用户看一眼两个数字是否都变了，就能确认前后端是否都用上新代码。
这比"刷新试试"可靠得多——本项目此前多次把"前端没换"误判成"改动无效"。

## 首次建联必失败：传输层就绪晚于客户端首次发送

症状：**每次**打开页面，第一次建联必定失败，紧接着第二次迅速成功。

**判据（三步定位）**
1. 看发送层入口有没有"未就绪就立刻抛"的判断，例如
   `if (client === undefined || !ready) throw new Error('中继尚未就绪')`；
2. 比较两个时刻：**客户端发起首次连接的时刻**（页面加载后几百毫秒）与**传输层就绪的时刻**
   （公共 broker/WebSocket 连上，真实环境常需 1~2 s）；
3. 若前者稳定早于后者 ⇒ 首次请求必然落进"未就绪"窗口，这不是偶发抖动，是**确定性竞态**。

**修法：未就绪时等待，而不是立刻失败。**
在发送入口加一个有界等待窗口（例如 8 s，50 ms 轮询），窗口内等到就绪就正常发送；
超时仍按原逻辑抛错，避免真断时无限挂起。
只改"未就绪"这一条路径，正常发送不引入额外延迟。

**为什么本地复现不出来**
隔离环境的本地 broker 就绪极快（百毫秒级），而客户端要几百毫秒后才发起连接 —— 窗口根本不存在，
所以本地永远一次成功。真实环境的公共 broker 慢 1~2 s 才暴露。
遇到"只在真机出现、本地怎么跑都正常"的启动/重连问题，先量化这两个时刻的先后，别急着加日志。

**同类问题的通用形态**：任何"传输层异步就绪 + 上层立即使用"的结构（MQTT 会话、WebSocket 隧道、
鉴权令牌、缓存预热）都会有这个形状。统一原则是**让使用方等待就绪事件并设上限**，
而不是让使用方探测到"未就绪"就报错重试——否则重试路径会把确定性的首次失败固化成固定行为。

## seq 高水位打死实时通道：跳号自救要放在查表之前

症状：界面**永远**停在「电脑已经中断，正在重试」，重连多次无效，硬刷新也无效；
但同一时刻普通请求仍在成功（`rpc` / `rx` / `tx` 都在增长）。**数据通、控制通道死**。

**判据（两条就能定性）**
- 日志出现 `code=replay`（而不是 `bad-ts`）；
- 同一行里 `tsDelta` 很小（几秒级）⇒ **不是时钟问题**，是 `seq` 落在了对端记住的高水位之下。

**为什么致命**
开长连接/隧道的那一帧（`ws.open`）与业务请求**共用同一道新鲜度/重放闸**。
它的 ack 被拒 ⇒ 上层永远收不到"通道已开" ⇒ 状态永远 offline ⇒ 无限重试，
而每次重试的 seq 仍然低于水位 ⇒ **确定性死循环**，刷新页面也只是换一批低 seq。
注意区分措辞：用户看到的是"电脑中断"（网络口径），实际是闸门拒绝（协议口径）。

**修法的两个要点（第二个最容易做错）**
1. 客户端收到 `replay` / `bad-seq` 时**跳号自救**：本地 seq 直接加上几百越过水位再重试。
   seq 单调递增、跳号没有副作用，一次就能恢复。
2. **跳号必须放在"查找 pending 条目"之前**。控制帧（`ws.open` / `ws.msg`）走的是"直接发送"
   而不是"带 pending 的请求"，没有 pending 记录；若把自愈写在 `pending.get(id)` 之后，
   控制帧被拒时根本进不到自愈分支 —— 上一版就是这样：业务请求能自愈、隧道帧永远不能，
   于是数据通、界面永远转圈。

**验证纪律**
发版后让两端版本号同号，并让用户核对设置页那两个数字是否都变成新号；
否则"用户已用上新版"这个前提本身就是假的，会把问题归错方向。

## 闸门只该拦有副作用的帧：控制帧被拦会锁死界面

**闸门要按"有没有副作用"分类，而不是一律拦。**
重放/新鲜度闸的正确作用域是**有副作用的请求帧**（会改数据、会触发执行）。
控制帧（开隧道 / 发消息 / 关隧道）通常满足两个条件：**由令牌授权 + 按 id 幂等**，
重复一次最多多建一条资源，而这类资源本身已有"同源替换"逻辑兜着。
把控制帧也拦下来，代价是它的 **ack 被丢掉**：上层永远收不到"通道已开"，
状态机停在连接中，用户看到的就是**界面反复"正在重试"、而数据面一切正常**。

判据组合（一眼可分）：
- 数据面在动（请求数/响应计数增长、详情能正常返回）；
- 实时通道反复重建（开隧道日志成对出现，间隔几秒到几十秒）；
- 日志里出现"拒绝/重放"一类的记录。

修法：给闸门加一个"跳过 seq 检查"的选项，只对控制帧开启；
**时间戳与 sid 校验必须保留**（这两条才是真正防重放），并且
**水位只增不减**——即使是允许跳过的类型，也不能让一次低 seq 把水位拉回去。

**改闸门语义必须同步改断言**：原测试往往断言"控制帧重放也要被拒"（安全口径），
新语义下要显式改成两条——"不再因 seq 被拒"与"低 seq 不降低水位"，
否则要么测试变红被草率删掉，要么语义悄悄回退。

## 观测上的两个坑（本轮实际被它们拖慢）

1. **日志节流会掩盖证据**：计数在涨而日志行为 0，是因为 warn 只在第 1 次与每 N 次打印。
   "日志没有" ≠ "没发生"，排查时必须**同时看计数器**（stats 里的 reject/stale 计数）。
2. **关闭路径缺埋点会让证据链断裂**：如果关闭日志只在"这条 id 还在表中"时才写，
   那么"隧道悄悄消失"就完全不留痕——你会看到 N 次 open 只对应 1 次 close，
   然后无法判断是手机放弃、还是本地桥关闭。**关闭日志应当无条件记录**
   （code、reason、当前槽位、是否已从表中移除）。

## 手机端答不了 agent 提问：缺 UI 与缺状态，附 DSH 答题契约

## 手机端答不了 agent 提问：缺 UI + 缺状态（附 DSH 答题契约）

**症状**：电脑端 agent 调了 `ask_user_question` 等人作答，手机端"发什么都没反应"——既看不到问题，打字也没用。

**这不是传输层问题，别去查中继/闸门。** 两个判据：

1. 手机外壳（`web/`）里 grep `question|提问|询问|回答` **0 命中** —— 根本没有提问卡片，用户唯一能做的就是往输入框打字；
2. 那条发送走的是普通会话消息 `POST /tasks/:id/prompt` → `agent.followup(...)`，turn 卡在提问上时它只是**排队**，不会推进任何东西。

所以先确认"前端有没有入口"，再谈网络。

### DSH 侧答题契约（0.2.2 实测源码）

- **进程内答题**：`ctx.userQuestions.answer(agent, callId, { answers })`
  - `answers` 必须**每个问题恰好一条**：`{ id: string, selected: string[], custom?: string }`
  - `selected` 是**选项标签**；单选自定义时 `selected=[]` 只给 `custom`；多选时 `custom` 补充 `selected`
  - 数量不匹配抛 `BAD_ANSWER`；该题已有排队回复抛 `REPLY_QUEUED`
- **问题形状**：`{ id, question, detail?, header?, options?: [{ label, description? }], multiSelect?, intent? }`
- **待答状态**：会话投影 `userQuestions` → `{ active: [{ callId, questions }], settled: [...] }`
- **事件兜底**：`tool/call`（`data.callId` + `data.arguments`）入 active；同 `callId` 的 `tool/result`，或 `user/message` 且 `data.source.kind === 'user-question-reply'` 出 active
- **服务怎么进插件**：沿用 pocket 现有的 `bind('userQuestions')` 模式（`ctx.inject([name], child => …)`）；服务不存在时自然不会绑定 —— 这就是"老版本 DSH 降级返回 501 / 不显示卡片"的判据，不要抛未捕获异常。

### 实现要点（本轮只定位契约，**实现与真机验证未完成**）

- host：`pendingQuestions` 必须**恒为数组**（空数组而不是省略字段），客户端据此渲染；答完要立即从 active 移除，否则卡片会残留。
- web：轮询/流式刷新**不能清掉用户已选未提交**的选择（以 `callId` 为键暂存），否则用户每次刷新都要重选。
- 验收：改 web 后必须重建外壳再 `--check`；插件代码改动需**冷启动宿主**（ESM 缓存），配置才是热生效。

## 接手移交包的动作顺序；需要用户注意的信号与能力边界

**接手别人（或另一个会话的 agent）移交的功能包时，动作顺序固定。**

1. 先读 `HANDOFF.md` 全文：状态、根因、对外契约、**已跑过的验证命令**、未完成项。没有"未完成项"章节的移交包不要信。
2. 用 `git apply --check <patch>` **先试应用不落盘**，退出 0 才动手；同时看 `git stash list` 有没有第二份备份。
3. 应用后**必须重建产物**（静态外壳之类），再跑全部门禁（语法 / 单测 / e2e / 产物一致性）。四条都绿才算"合入成功"。
4. 再补自己那份需求；**别在第一轮就重构别人的实现**。
5. 改完先不删 patch 与 stash——等真机验证过再说，它们是回滚路径。

## 给列表加"需要用户注意"的信号：先 O(1)，再考虑重查

列表有几百行时，**逐行去读重状态（投影、聚合视图）会拖垮列表**。正确顺序：
- 先用内存里的**事件兜底表**判（O(1)，命中就返回）；
- 只有未命中、且该行处于**可能挂起**的状态（如 `running`）时，才去读投影；
- 判定函数写成独立方法并单独测试，别埋在列表装配里。

## 「置顶」和「高亮」必须成对

只置顶 → 用户不一定会看第一屏；只高亮 → 沉在第 300 行没人翻。
两者配合才有用：**排序把该处理的东西推到眼前，视觉让人一眼认出**。
配套细节：徽标文案要直白（"需要回答"而不是图标），动效尊重 `prefers-reduced-motion`，
高亮用主题色而非新配色（否则浅色/深色主题里会失衡）。

## 能力边界要显式化，不能让用户"点了没反应"

涉及需要用户输入的交互，先确认**这条通道在目标客户端上到底能不能走通**。
本项目实测的边界：DSH 里 `open`（前台仍在等待）的提问只能由 **owner 主体的远程事件客户端**
结算 waterfall；第三方 App 走自己的 HTTP API **无法接答**，`answer()` 对 `open` 只会静默返回 false。
所以产品必须做成矩阵：
- 能答的状态 → 正常可答；
- 不能答的状态 → **卡片可见、按钮禁用、文案说明去电脑端**；
- 未知状态 → 显式提示"稍后刷新"，不假装成功。

把"不可答"当成"可答但其实失败"，是这类功能最伤用户的失败模式。

## 新增路由要改三处：业务、转发白名单、回归用例

**新增一条 HTTP 路由时，要改的是三处，不是一处。**
业务处理、**转发层的路径白名单**、回归用例。漏掉中间那处，症状就是
「本地全绿、真机全挂」：本地直连桥接时路由存在，经中继转发时被白名单拒绝。

**先认报文，别猜。** 三种失败长得完全不同，修法也不同：

| 症状 | 含义 | 去哪查 |
| --- | --- | --- |
| 403 + 固定文案（如"不在白名单内"） | **策略层主动拒绝**，请求没到业务层 | 转发层的路由表 / allowlist |
| 404 | 业务层路由没挂或路径不匹配 | 桥接路由注册 |
| 超时 / 连接中断 | 链路或握手问题 | 中继链路、鉴权 |

看到"不在白名单"这种**明确的策略文案**，就别去业务代码里找 bug 了。

**回归用例要三断言，不能只断言"能通"：**
1. 正确方法放行（`POST /.../answer` 之类）；
2. **错误方法必须被拒**（`GET` 不能变成写操作）——方法白名单本身是 CSRF 硬化；
3. **敏感路径仍然被拒**（如设备管理、配对、管理接口）——防止新增路由时顺手放宽整体。

**测试层次也要对齐**：只测"本地处理函数"会漏掉转发这一跳。
端到端用例必须走**真实转发路径**（本地直连 + 经中继各一条），
否则"本地验证通过"这句话在这类缺陷面前没有意义。

**附带经验**：读接口（`GET /tasks/:id`）与写接口（`POST /tasks/:id/answer`）
在白名单里是两条独立条目，只放行读不会让写自动可用——加功能时要显式确认这两条都在。

## 外壳更新不生效：导航 cache-first 与构建号漏掉 SW

症状：在浏览器里**手动刷新**拿不到新前端外壳，只有关掉页面重新打开（或重新扫码）才更新。

**根因几乎总是同一处：导航请求是纯 cache-first。**
Service Worker 里这段是致命的：

```js
if (request.mode === 'navigate') {
  event.respondWith(caches.match(INDEX_URL).then((hit) => hit ?? fetch(request)));
}
```

刷新就是一次导航 → 永远命中缓存的旧 `index.html` → 继续加载旧 JS。
"关掉重开能更新"恰好是反证：那次导航之前，浏览器的 SW 更新检查刚好完成、新 SW 已接管。

**修法三件套（缺一件体验都不对）**
1. **壳资源与导航改成 network-first**，网络失败再回退缓存（离线能力不变）。
   壳文件小、部署在静态 CDN 上，先网络的延迟可忽略。
2. **新 SW 接管后自动刷新一次**：监听 `controllerchange` → `location.reload()`，
   并用"加载时是否已有 controller"（`hadController`）排除首次安装，
   否则用户第一次注册就会莫名刷新。
3. **页面加载时主动 `registration.update()`**：等用户手动刷新才开始查更新太晚。

**连带陷阱：构建号必须覆盖 SW 源码。**
若构建哈希是在**写入 `sw.js` 之前**算完的，那么"只改 SW 的发布"会得到同一个构建号：
缓存名不变，客户端靠"比缓存名"的旧外壳检测全部失效，旧 SW 也可能长期驻留。
自检：只改 SW 源 → 构建 → 构建号必须变；还原 → 必须回到原值。

**验证纪律**：这条链路上"改了源文件"毫无意义，必须核对**构建产物**里
导航分支是否真的先 `fetch`。产物里还是 `caches.match(...)` 就说明你改错了文件
（同名副本、构建 skip 列表）——这属于另一类问题，见"断言指向未被构建使用的文件"。

## 断连归因：服务端故障 vs 客户端静默的四条判据

用户报"又断了"，第一步不是改代码，是**判归因：服务端故障还是客户端静默**。两者修法完全不同。

## 判据组合（一次就能分开）

| 读数 | 含义 |
| --- | --- |
| 链路关闭计数 = 0、心跳的 ack 年龄正常（亚秒级） | 传输层健康，不是"连不上 broker" |
| 拒帧/重放计数 = 0 | 不是协议闸门在拒 |
| **对端上行年龄持续增长**（分钟级） | 手机侧**没在发任何东西** |
| 观察窗口内日志**零新增** | 对端没有在尝试重连 |

四条同时成立 ⇒ **服务端健康、客户端静默**。此时去改服务端参数是白费力气。

## 结构性结论：恢复机制不能只依赖页面内的定时器

浏览器后台/息屏会**冻结 setInterval**，而大多数"看门狗"正是 `setInterval` 实现的。
于是最坏的组合出现：页面对端沉默 → 看门狗本该重启 → 但它没跑 → **没人重启**，用户回来看到"一直断着"。

可用的恢复层次（从便宜到硬）：
1. **事件驱动优先**：`visibilitychange` / `pageshow` 里检查"最后一次收到数据距今多久"，超阈值就**直接重建**，而不是只重置时钟。
2. **服务端兜底**：对端长时间无上行时，在它下一次 `hello` 上主动下发"重置"指令，让页面重载。代价是可能打断正在看的会话。
3. 不要指望页面自己"过一会儿会好"——冻结期间它连"过一会儿"都不会发生。

## 遥测：只写"已知 id"的关闭日志会漏掉一半

若关闭日志写成"仅当这条隧道还在表里才记"，被清理/替换的路径全都不留痕。
实测比例可以达到 open 84 : close 38 —— 此时"隧道是怎么消失的"永远无法回答。
**关闭日志必须无条件记录**（code / reason / 是否仍在表中 / 存活时长），这是排查这类问题的前提。

## 「中继断开」的归因：能加载但连不上 broker

界面显示「中继断开，正在重连」时，**先分清是"页面加载不了"还是"页面能加载但连不上 broker"**——这两类修法完全不同。

## 判据：能加载 + 连不上

- 横幅能出现，说明**静态资源已经加载成功**（HTTPS/443 通），页面本身是活的；
- 但 MQTT 客户端反复重连失败，说明 **WSS 那条连接不通**。

公共 broker 的 WSS 常用**非标端口**（如 8084），而移动网络/公司网络经常只放行 443。
所以"页面打得开、就是连不上"高度指向：**端口被封** 或 **broker 对该出口 IP 限流**。

## 三步归因（每步都很便宜）

1. **对端有没有留痕**：在服务端日志里找该用户的 `hello` / 建连记录。
   完全没有 ⇒ 它的连接**没到达 broker**，不是你的网关/鉴权在拒（别去查白名单）。
2. **自己直连同一个 broker**：用 `ws` 包按同一 URL、同一子协议（`mqtt`）、
   `handshakeTimeout` 8 秒试一次。通则 broker 与其证书链没问题，问题在对端的网络路径。
3. **核对"告诉对端连哪儿"**：配对/分享链接里通常带 broker 提示值（常见是 URL fragment 的
   `s=` 参数）。先把它解出来确认地址正确，再怀疑网络——否则会花大量时间改代码修一个不存在的问题。

## 用"换网络"做决定性区分

让用户把手机在 **WiFi ↔ 移动数据** 之间切一次再重连：

- 换网就能连 ⇒ 端口/网络策略问题（或临时限流，等待几分钟自愈）；
- 换网仍不能连 ⇒ 设备侧状态（缓存了错误的连接参数、系统拦截长连接），才轮到改客户端。

## 一条产品教训

横幅只写「中继断开」会让归因永远停在猜测：用户看到的是同一句话，
排查的人却需要知道**是超时、被拒、还是 HTTP 状态码不对**。
所以连接失败时横幅（或诊断信息）应当带上**具体错误与尝试过的候选地址**，
否则每次故障都要回到"从服务端反推"的老路。

## WiFi 能连、蜂窝连不上：按屏幕文案二分 + 公共 broker 端口事实 + 换 broker 的两个坑

## 手机「WiFi 能连、蜂窝流量连不上」：先按屏幕文案二分，再查 broker 端口

### 一、用文案二分，两类根因完全不同

- 屏幕停在 **「无法建立中继连接」** → 首次握手就没成功：DNS 解析 / 端口被封 / TLS。结论在 splash 的 detail 里。
- 屏幕停在 **「中继断开，正在重连…」** → 说明 `connect()` 曾经成功过（`onstate('offline')` 只在这条路径上产生），是**连上之后被切断**。根因通常是运营商 DPI/NAT 掐长连接，或公共 broker 对共享出口 IP 限流。
- 两者可能同时出现在屏幕上（横幅 + 致命页）。**以致命页的 detail 为准**，那是首次失败的结论；只看横幅会误判成"曾经连上"。

### 二、公共 broker 的端口事实（实测，别指望「换个现成 443」）

- `broker-cn.emqx.io`：只有 A 记录（无 IPv6）；`:443/mqtt` 返回 `301`（443 是网页服务，不是 WS 监听），WSS 只在 `:8084/mqtt`（`101 Switching Protocols`）。
- `mqtt.eclipseprojects.io:443/mqtt`：从国内直连超时，不可用。
- 可用的**非 443** 公共 broker：`broker.hivemq.com:8884/mqtt`、`test.mosquitto.org:8081/mqtt`（都实测 `101`）。

→ 「换一台 443 的公共 MQTT」这条路不存在。443 只能自建：反代把 `wss://<你的域名>/mqtt` 转到内网 broker 的 8083。

### 三、换 broker 的两个必踩坑

- **房间与 broker 绑定**：手机把整条链接（含 `s=<broker>`）存在 `localStorage`。桌面改 `cloud.broker` 后**必须重新扫码**，否则手机继续连旧 broker —— 两边各自都健康，只是不在同一台服务器上，表现和"连不上"一模一样。
- **运行时切换不持久化**：`CloudService.setBroker` 只改内存、明确不写回 profile 配置。插件热重载或 DSH 重启后桌面回到配置里的 broker，而手机还指向切换过的那个 → 又落回同一个坑。长期方案必须写进配置。

### 四、把现场变成可诊断的（比猜有用得多）

中继层必须把 `mqtt` 的 `error` / `connack` / `close` 三个事件的 `code` 与返回码留下来并显示，否则手机上永远只有一句通用横幅，每次都不可诊断：

- 横幅保留用户已认识的主句，后面补**短标签**（如「（连接被重置）」）；保留原有的短抖动去抖，不要因为要显示原因就把抖动也露出来。
- 连接页给完整项：中继地址 / 连续失败次数 / 最后成功时刻 / 原始 code，再加一键复制。
- **「一次都没连上」的致命页也要给断因 + 复制入口**——那条路径渲染不出连接页，只靠截图会把 `error.code` 丢掉。
- 诊断文本走白名单字段：房间密钥 `k`、设备令牌、链接里的 `r`/`t` **绝不能进**（它会被用户复制粘贴给别人）。

### 五、处置顺序

1. 先读断因（横幅短标签 / 连接页诊断块 / 致命页的复制按钮）。
2. 「被重置」「超时」→ 换一台 broker 重扫码试一次（用来判别是端口还是 broker 本身）；换过仍断 = 运营商在掐非常规端口。
3. 「返回码 5 / 3」→ 公共 broker 对你的出口 IP 限流（蜂窝是 CGNAT，一个公网 IP 背后有大量用户）。
4. 「域名解析失败」→ 当前网络 DNS 解析不了该域名。
5. 全都换过仍不通 → 自建 443 中继，这是唯一稳定的长期解。
