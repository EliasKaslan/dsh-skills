---
name: dsh-phone-remote-relay
description: 手机跨网络接管电脑上的 DSH，且电脑不暴露公网——公共 broker 中继 + 端到端加密 + 静态外壳托管；含 ESM 缓存导致热重载跑旧代码、hello 自激打爆限流、大帧被公共 broker 丢弃、按请求 id 幂等重发、WS 帧合批、GitHub Pages 用 REST 上传（git push 在本机挂死）、二维码必须解码验证。适用于"手机远程控制电脑上的 DSH / 不在同一局域网 / 不要反向代理和端口映射 / 二维码链接怎么生成 / 中继丢包超时 / 热重载不生效"；不适用：只改插件行生效时机 → `dsh-agent-customization`，本机 pwsh 编码坑 → `pwsh-on-windows`。
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
- **本机 `git push` 会挂死**（schannel 重协商后不再回包，`ls-remote` 却正常）：
  改用 Contents API `PUT /repos/{o}/{r}/contents/{path}` 逐文件上传（base64），
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




