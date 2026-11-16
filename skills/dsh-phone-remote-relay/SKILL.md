---
name: "dsh-phone-remote-relay"
description: "诊断或维护 DSH Pocket 手机远程中继的建联、分片、重复请求、WebSocket 回放与版本生效；用于既有手机接管场景，需要区分出站中继与本机监听状态。"
---

# DSH 手机中继

先定位当前 Pocket 源码、插件的实际版本、宿主进程与入口。2026-11-16 本机 `D:/workspace/261102_mobile_dsh/dsh-pocket` 的 package 为 dsh-pocket-plugin 1.0.2（DSH>=0.2.2-rc.2、Node>=22.15）；cloud-service.mjs 当前明确是宿主进程内实现，无 spawned helper/pid 文件/daemon。旧 daemon 处理仅用于匹配旧版本。dsh-sidecar 是另一种会话侧栏，不要混用。文件存在不证明当前宿主装载了它。链接中的 fragment/密钥及 cloud.json 均视为凭据，不复制到日志或公开页面。

按路径拆故障：手机静态壳 → broker 连接 → 解密/方向校验 → RPC → DSH HTTP/WS → UI。读 [协议与验收](references/protocol.md)，先在纯本地 mock 做丢包、重复、乱序、超时测试；真实任务创建、连接第三方 broker、发布静态页由任务授权决定。

“插件 loading”不足以证明新代码；用构建标识、具体新路由和返回值核对。ESM 缓存可能需当前组件支持的重启；仅在匹配旧 daemon 实现时，才检查独立 daemon 与插件交接是否只有一个执行者，以及重放缓存跨交接的语义。

验收报告包含请求/响应字节数、重复执行次数、回放完整性、二维码解码一致性以及手机 UI 结果。历史吞吐和延迟只是旧环境测量。出站 broker 模式不需要公网入站端口，但仍检查当前代码是否另有本地 HTTP listener，不沿用“电脑零监听”的绝对断言。
