# 旧 preset 与当前 overlay 的分层取证

两份旧 preset 笔记明确标为手动调用/历史材料，称 0.2.2-rc.1 起不再扫描 `.agent-presets`。本机 rc.3 安装包未发现同名 preset 包，而目录仍存在；目录存在不证明 loader 正在读。先从当前 app-boot、profile、bundle 和管理接口定位实际入口，勿重新启用旧机制作为默认修复。

## 离线与 overlay

1. 建立 base composition → profile/bundle → manual patch → 最终行列表/配置的对照，包含 row id、来源、module、enabled 与有效配置。旧机制的 `agent.cordis.yml` 是组合文件，`preset.yml` 是展示元数据；二者不能互换。只有已安装版本仍提供该 loader 时才使用旧 scanRoot。
2. 旧 discovery 规则是 id `^[a-z0-9][a-z0-9-]*$`、每次读重扫，元数据只读 name/description/order；缺组合文件会占用 id 并报告 broken。保留原始 broken 原因，而不是只打印 healthy。当前 overlay 机制要以当前实际解析结果替代这些假设。
3. 对每个包区分 `Config`、`resolveConfig`、构造期检查和 apply；不把类型校验等同语义校验。历史 compaction-basic 不拒绝 Config 中未知键，语义在内部 resolveConfig：retainRatio 小于 thresholdRatio、retainRatio 与 retainTokens 互斥。pruner 的 head+marker+tail 必须不超过阈值，marker 长度从当版源码取，不固定为39。
4. 静态 agentOptions 中的 provider/model pin 与 allowedModels 这种“模型主动选择”策略分别检查；后者可能不约束静态 pin。保存最终 row 与解析配置证据。
5. 历史 `maxDepth` 比较的是 parentDepth+1，因此顶层 maxDepth=0 阻止首个子代理；toolFilter.allow 的拼写可能直到子代理创建才检查。当前版本复核这两条实现，随后用最小真实委派验证。

## 在线会话证据

只在隔离 host 使用当前已公开且查过 schema 的 API。历史 DSH RPC 是 POST /api/<ns>/<method>，外层 client-request/rpcId/method/payload.args；不要把旧 envelope 或方法名直接发给新版本。

| 要证明的事 | 证据 | 单独不足的证据 |
|---|---|---|
| preset/overlay 被选中 | session/create 返回的标识与最终组合 row | 目录存在、展示名称 |
| persona 生效 | 服务端请求 header/system prompt 实际段落，隐去敏感内容 | 模型说“我是某角色” |
| 工具可见性 | session/page 的 request/header.header.tools[].name 或当版同等权威清单 | 模型列出的工具、插件装载日志 |
| 模型路由 | 子会话实际 config.provider/config.model，与静态 pin/provider 请求记录交叉验证 | persona 中的模型名称 |
| 裁剪与权限 | 子代理实际工具目录，并对允许的无副作用工具做调用；禁止面用安全负对照 | schema 被隐藏 |
| 委派完整完成 | 子代理结果和父会话 turn/end.reason.kind，错误时保留 tool/result.isError | 子会话已创建、父工具返回一段字符串 |

历史 session/page 的 throughSeq 不能超过当前 cursor，报 past cursor N 时用返回的合法 N；子代理 address 用 subagent/catalog 中 childSessionId，不手工加 session- 前缀。当前版本先核对 schema。页面 token 和完整会话原文保留本地，不粘贴到交付物。

可疑插件做“唯一改变是该 row”的两组对照，保持模型、输入、工具和 overlay 其余部分相同。旧实验 agent-team 曾在 descriptor 落盘前误判子代理为 Lead，动态 persona 渲染抛 TEAM_NOT_MEMBER，并额外注入团队工具；这是复现线索，不能直接当作 rc.3 仍有的缺陷。查看当版 membership/install/text 生命周期，再选最小对照。不要为了测试改真实 preset 或先升级全部插件。
