# 隔离、装配、生效与恢复

## 隔离实验

- 使用唯一实验根、独立 DSH_HOME、loopback 地址与未占用端口；从当前安装的 manifest/launcher 找入口，先读参数实现。`--no-open` 等开关只在该版本支持时使用。
- 只复制审过的最小配置，凭据和真实 patch 不随手搬入。整目录 junction 会让 launcher 生成的 cordis.yml 写回真实 profiles；需要共享依赖时仅共享明确只读依赖目录。旧 preset 目录也用独立副本，避免把可写测试指向真实目录。
- 保存 PID、创建时间、可执行文件、命令行、日志路径和端口所有者；清理仅针对这些匹配的进程。HTTP 401 只证明某端点响应并要求认证，还需进程身份、期望路由和插件证据。实验会话可能消耗模型额度或触发工具，限定为无副作用任务。
- 语法错误、MCP 子进程失败、坏组合行可能分别表现为进程退出、宿主活着但工具缺失、或静默不服务。设置有限启动等待与宿主之外的恢复路径，不据“PID 还在”宣称成功。

## 装配和插件管理

`dump-config` 证明配置组合，不导入/apply 所有模块；schema 类型通过，也可能没有做未知键或跨字段语义检查。查插件真实导出及解析入口后再调用；import 本身也可能有顶层副作用。

对每次试验记录 base/bundle、manual patch、最终 row 身份及配置的差分。某版本 config override 是整对象替换，修改一个字段可能丢掉非默认同级字段；用完整解析结果或运行时读回验证。重复 bundle 注册和手工插入可能产生多个管理目标，`unaddressable` 不等于未激活。先定位候选 row，保留一个明确装载来源，不盲目再插入一行。

host-only 插件不一定出现在 client realm 的 `/plugins/events`；对管理面 `pluginInventory/list` 核对名称、enabled、fiberPhase、error，再用插件自己的行为验证。重载返回、日志 loading、页面更新是不同证据。Node ESM 缓存会使重新 apply 仍复用模块；先看当前热更实现与 restart-required 提示，再用新增唯一标记证明新实现生效。

本地插件需要与宿主的 peerDependencies/exports 对齐，避免把宿主运行时依赖私带一份。DSH defineTool 的属性与输出 DSL 不一定是 JSON Schema。生命周期回调中再次追加事件可能重入；延后到已验证的串行停止钩子，制作只记录顺序的 fixture，而非在生产 turn/end 里直接发 followup。

工具发现、可调用目录、授权面分别验证；discovery 减少 schema 不等于禁用写工具。测上下文开销时用实际发给模型的工具名、description、inputSchema 及当前 tokenizer，不把整个 tools/list 元数据字节数当 token，也不继承固定比率。环境变量传递只测人工生成的哨兵及其 codepoint/UTF-8，不打印全部 process.env。

## 守护与恢复

本机线索 `D:/workspace/agent/dsh-guard/dsh_guard.py`、selftest.py、`D:/dsh-vault`、`C:/ProgramData/dsh-guard` 在审计时存在。先检查当前守护源码、现有任务/服务的实际路径、备份排除和日志，再决定使用。

守护程序、锁和恢复源放在被保护 home 外。一次周期应区分检测、修复、快照；修复失败不能继续把删除提交为新的“健康”快照。恢复试验用空的独立目的地，比较路径清单、内容哈希，再让真实消费者在隔离副本上读取。不要通过删真实 AGENTS.md 来证明守护有效。

会话/工作区可能有内存状态回写；修改或恢复前按当前实现停止相应写入者并保留原始字节。session 文件名版本必须与其 header 匹配，和 app 版本分开。对多帧 zstd 用支持 concatenated frames 的流式解码器（如 python-zstandard 的 read_across_frames=True），不要按 magic 字节切割，magic 可能出现在帧载荷中。使用副本检查完整 JSONL、末尾 turn/end 和消费者兼容性；不直接重压在线日志。
