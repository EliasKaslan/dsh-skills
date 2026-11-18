---
name: "dsh-agent-customization"
description: "DSH配置、插件与运行时维护总纲；定位改哪层、何时生效、隔离验证、preset取证与守护恢复，按模式转入具体参考。"
whenToUse: "DSH配置、插件与运行时维护总纲；定位改哪层、何时生效、隔离验证、preset取证与守护恢复，按模式转入具体参考。 模型触发仍以description为准。"
---


# DSH 改造与运行时维护

## 何时调用

修改DSH自身行为、插件装配/组合、MCP工具、生效时机或恢复时使用；先确认安装版本、DSH_HOME、profile、目标进程和用户授权范围。写skill文件另用 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)，网络/编码问题另用 [pwsh-on-windows](../pwsh-on-windows/SKILL.md)。

2026-11-16本机安装包为0.2.2-rc.3；旧profiles/node_modules启动路径不存在。版本、路径和工具名是快照，不是永久契约。读当前源码/schema，再执行改变；不要以旧工具名或模型自述推断本会话具备能力。

1. 将变化定位到指令、skill、profile/组合、插件实现或运行时实例，记录有效配置、来源和回退材料。配置展示只保留必要键，移除密钥/令牌/URL fragment。
2. 先在独立home、工作区、loopback端口做最小试验，再判断是否部署真实环境；完整配置组合不等于模块能加载，插件active也不等于模型路由/工具行为正确。
3. 对照新旧配置与运行时证据，区分进入组合树、模块装载、实例激活、会话实际行为；热重载返回或日志loading不能单独证明生效。
4. 对真实环境的修改按任务已授权范围推进；恢复/停用/发布等动作分别核对目标。skills目录可能自动发布，批量落盘先读 [发布事务边界](references/publisher-transaction.md)，不能靠自造.lock或“写快一点”避免中间态外发。

## 按模式加载

| 模式 | 参考与验证目标 |
|---|---|
| 隔离host | [runtime.md](references/runtime.md)：启动入口、独立DSH_HOME、最小配置、PID/端口身份与有限等待 |
| 配置装配与重载 | [runtime.md](references/runtime.md)：override对象语义、候选row、realm、管理面和真实工具行为 |
| preset-offline | [preset-evidence.md](references/preset-evidence.md)：旧loader是否还存在、overlay/base/bundle/patch、Config与语义检查 |
| preset-live | [preset-evidence.md](references/preset-evidence.md)：persona、权威工具清单、子会话provider/model/toolFilter、父turn/end和单row对照 |
| 守护恢复 | [runtime.md](references/runtime.md)：外置守护、失败不固化删除、独立目的地恢复+hash+消费者验证 |
| 市场与安装包 | [market-asar.md](references/market-asar.md)：当前schema、来源固定、SemVer、ASAR有界读取 |
| DSH委派编排 / 工具能力预检 | [delegation.md](references/delegation.md)：当前schema、只读probe、任务边界与产物验收 |
| 退役同步审查 | [legacy-sync.md](references/legacy-sync.md)：旧repo-sync只保留安全经验，不恢复旧脚本/任务 |

报告区分静态检查、隔离运行、真实会话验证和未验证项。只有当前宿主指令允许且当前schema实际公开时，才使用DSH委派、浏览器、邮件、插件和自动化接口；本skill不改变其权限。

## 配置覆盖的回滚验收：字节一致 + 组合树复核

## 适用

撤掉自己写进 `cordis.patch.yml` 的**按 id 覆盖**（改 config / 加 disabled）时。这类回滚看着只是「删几行」，但两份风险都不显眼：删不干净会留空行或换行风格变化；而这 4 天里文件可能被别的改动动过，直接拿备份整体还原会**吞掉别人的修改**。

## 做法：只摘自己的段，再用两个证据收口

1. **先备份当前版本**（`.bak-<用途>-<时间戳>`），**不要覆盖**改前那份备份——两份都要留着：一份是"开着的状态"，一份是"改前基准"。
2. **外科式摘除**：按自己写的那行注释上方的标记定位，截断到标记之前，再 `rstrip("\r\n") + 原换行符`，不要用"还原整个文件"。
3. **证据一（硬）**：`sha256` 与**改前基准备份**比对，必须逐字节相等；再看字节数是否回到改前的值。相等 = 既没残留、也没误伤这期间别人做的改动。
4. **证据二（语义）**：跑一次组合校验 `--profile headless --dump-config`，确认该行 config 里**不再有**你加的那个键（回落到 schema 默认）。

两条都过才算回滚完成；只看"文件看着没问题"或只看 YAML 能解析，都会漏掉残留与误伤。

## 坑

- **拿旧备份整体还原**：若这期间文件有过别的改动，还原即回滚别人的改动。除非能证明期间无人改过，否则一律外科摘除。
- **只核 YAML 可解析**：解析通过不证明"没了"，多留一行 `- id: ...` 仍是有效 YAML，而且会静默继续覆盖配置。
- **回滚默认值 ≠ 关掉已开启的会话**：默认值只影响之后新建的会话；已经开了的会话是它自己日志里的状态，要单独在会话菜单里关（见上一节）。
