---
name: "dsh-phone-remote-relay"
description: "诊断或维护 DSH Pocket 手机远程中继的建联、分片、重复请求、WebSocket 回放与版本生效；用于既有手机接管场景，需要区分出站中继与本机监听状态。"
---

# DSH 手机中继

先定位当前 Pocket 源码、插件的实际版本、宿主进程与入口。2026-11-23 复核：`D:/workspace/261102_mobile_dsh/dsh-pocket` 的 package 仍是 dsh-pocket-plugin 1.0.2（dsh>=0.2.2-rc.2、node>=22.15）；`lib/cloud-service.mjs` 文件头明确写着 "Everything here runs inside the DSH host process: no spawned helpers, no pid files, no daemons"，`~/.dsh/pocket` 下也只有 auth/cloud/runtime/sessions/state 与 bridge.log，没有 pid 文件。旧 daemon 处理仅用于匹配旧版本。dsh-sidecar 是另一种会话侧栏，不要混用。文件存在不证明当前宿主装载了它。链接中的 fragment/密钥及 cloud.json 均视为凭据，不复制到日志或公开页面。

按路径拆故障：手机静态壳 → broker 连接 → 解密/方向校验 → RPC → DSH HTTP/WS → UI。读 [协议与验收](references/protocol.md)，先在纯本地 mock 做丢包、重复、乱序、超时测试；真实任务创建、连接第三方 broker、发布静态页由任务授权决定。

“插件 loading”不足以证明新代码；用构建标识、具体新路由和返回值核对。ESM 缓存可能需当前组件支持的重启；仅在匹配旧 daemon 实现时，才检查独立 daemon 与插件交接是否只有一个执行者，以及重放缓存跨交接的语义。

验收报告包含请求/响应字节数、重复执行次数、回放完整性、二维码解码一致性以及手机 UI 结果。历史吞吐和延迟只是旧环境测量。出站 broker 模式不需要公网入站端口，但本机确有 loopback listener（bridge.log: `bridge listening on 127.0.0.1:47901`），不要沿用“电脑零监听”的绝对断言。

## 审查一段改动：先查三份前端镜像，再取线上实例证据

审「别人（含外部模型）改了这个插件」时，先确定改动落在哪棵树上、那棵树是不是线上真正被服务的，再读 diff。下列路径均相对 `D:/workspace/261102_mobile_dsh/dsh-pocket`。

1. **改工作树 = 改线上代码**：`~/.dsh/profiles/desktop/node_modules/dsh-pocket-plugin` 是指向该源码目录的 **Junction**（2026-11-23 实测），没有独立副本。改完只需热重载插件（日志自称「关掉再打开本插件即可热重载，无需重启 DSH」）。
2. **三棵树的分工**：插件把 `web/` 作为静态根托管（`lib/index.mjs:47` 的 `webRoot: path.join(import.meta.dirname,'..','web')`）；`docs/` 是 `node tools/build-shell.mjs` 从 `remote/`+`web/` 生成的 GitHub Pages 壳产物；`remote/remote.js` 是手机端单文件。
3. **哪些差异是设计、哪些是漂移**：`remote/remote.js` 与 `docs/remote.js` 应逐字节相同；`web/app.js`、`web/store.js`、`web/lib/net.js`、`web/views/compose.js` 与 `docs/` 同名文件也应相同（2026-11-23 实测 SHA256 全等）。但 `sw.js` 和 `index.html` **本就该不同**——`web/sw.js` 是手写清单源码（服务端注入哈希），`docs/sw.js` 是产物；`docs/index.html` 行尾是 LF、`remote/index.html` 是 CRLF。别把这两处报成"漏同步"。
4. **判据用 `build-shell --check` 而不是肉眼或 hash**：`node tools/build-shell.mjs --check`（只读，不落盘）直接说 `docs/` 是否与源码一致；手改 `CACHE`/`Build stamp` 会在下次构建被覆盖。
5. **判断新旧代码看 boot id，不看版本号**：`~/.dsh/pocket/bridge.log` 的启动行带 `plugin loading; data=… pid=…` 与 `boot=<hash>`。插件常在不升 `package.json` 的情况下被改，`runtime.json` 的 `version` 也是写死的 → "版本没变"证明不了"代码没变"；反过来宿主进程启动早于改动、靠热重载生效时，ESM 是否有缓存也未定，验证新代码要用**具体新行为/新路由**取证。

坑：两棵树在改动前就已经分叉时，本次只动一侧并不自动等于本次引入的缺陷——必须 `git show <base>:<path> | git hash-object --stdin` 算基线 hash 定性，否则会把历史漂移算到改动人头上。
