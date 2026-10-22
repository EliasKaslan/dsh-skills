---
name: dsh-agent-preset-live-verification
description: DSH agent preset 在线会话级验收——已起隔离 host 且真建会话才能做：RPC 核对 agentPreset、persona、权威工具清单，真跑一次委派核对子代理 config/persona/toolFilter 与父会话 turn/end。入口不能选 headless——one-shot 不合成 preset，且会改写真实 home（建 sessions、重写 profiles、吞 settings.yaml）⇒ 必须另给 DSH_HOME。适用于"离线过了但插件行为不对 / preset 在真会话里 persona 和工具对不对 / 委派为什么失败 / 能不能用 headless 验收 preset / headless 会污染 home 吗"。不适用：只想先验能不能挂载 → 用 `dsh-agent-preset-verification`；只要干净实验环境 → 用 `dsh-isolated-web-host`；不知改哪层、何时生效、怎么撤 → 用 `dsh-agent-customization`。
whenToUse: 离线校验已通过、要在真会话里核对 preset 的 persona、工具裁剪与委派是否符合预期，或要解压会话日志取证时用。模型看不到本节。
---

# 在线验收 agent preset

> 本 skill 是总纲 `dsh-agent-customization` 的子 skill：只负责「在线会话级验收」这一段；DSH 的分层、生效时机与上线纪律见总纲。

**离线过了再来看这里。** 分工：`dsh-agent-preset-verification` 管**离线**（包里那个插件包能不能解析、配置键对不对）；本 skill 管**在线**（挂载后到底对不对）。离线只证明 YAML / 配置 / 包解析这几层没问题；**插件 apply 期错误、realm/工具裁剪、模型路由、真实委派是否跑通**都只能在真会话里看到。

## 何时调用

**加载本 skill 当：**

- 离线校验已通过，要确认新 preset 在真会话里的 persona / 工具集 / 委派行为符合预期。
- 怀疑某个实验插件行搞坏了委派，需要"有它 / 没它"的对照证据。
- 会话已经跑完，想不看 UI 直接从日志里取 `turn/end`、`tool/result` 原文。
- 已起会话 / 正在跑会话，想知道"挂载之后到底对不对"（`agentPreset`、persona、工具裁剪、委派结果）。
- 刚**热重载**过配置，要判"验收到底通没通过"——**必须同时验新建会话与改动前就已存在的会话**（第 5 步对照组 B）。

**不要用本 skill（转交）：**
- 还没起会话（或不想起会话），只想先确认这份 preset 静态上能不能挂载 → 用 `dsh-agent-preset-verification`。
- 只是要一个干净的隔离实验环境（重定向 `DSH_HOME`、`--no-open`、401 判就绪、taskkill 收尾） → 用 `dsh-isolated-web-host`。

**前置**：已用 `dsh-agent-preset-verification` 离线校验通过，且有隔离 host 与能发 RPC 的页面上下文。 ／ **后继**：验收失败且定位到插件行后，回到 preset 改动 + 离线校验，再重跑本 skill 的对照组。

## 前置：别选错入口——headless 根本不能验收 preset

**本 skill 的入口必须是"已起隔离 host + 真建会话"（web / UI 侧发 RPC）。`dsh --profile headless "<task>"` 不是候选入口**，两条**独立**原因任一条都是硬否决：

1. **one-shot runner 根本不合成 preset**。它直接 `agents.create({ sessionId, meta, agentOptions, setup })`（`dsh-headless\lib\index.js:316-321`），**参数里没有任何 preset**；而且它**明确拒绝接纳挂在 preset 下的会话**——`assertAdoptable()` 原文（`:220-223`）：

   ```
   session "<id>" runs under agent preset "<preset>", which the one-shot runner does not compose
   ```

   ⇒ 用 headless 跑"验收"，你验的是**一份没有 preset 的组合**，结论与 preset 无关。**这是最隐蔽的假验收。**

2. **headless 入口并非只读，它会改写真实 home**。实测（隔离 home 里先放一个 `settings.yaml`，再跑 `dsh --profile headless "say hi"`，退出码 1）——它同时干了三件事：

   ```
   <home>\settings.yaml  →  消失，变成 <home>\settings.yaml.imported        # boot 把 legacy 导入源吞掉
   <home>\profiles\headless\{cordis.patch.yml, cordis.yml, package.json, pnpm-workspace.yaml}   # 组合产物被重写
   <home>\sessions\--D-workspace-agent-dsh-base--\session-<uuid>\           # 真建了一个会话目录
   <home>\storages\session_projcache\..., <home>\.anonymous-user-id

   进程输出：dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"
   ```

   ⇒ 拿它去碰真实 `~/.dsh`，**`settings.yaml` 会被吞掉、`profiles\<p>` 会被重写**。**要跑就必须显式另给 `DSH_HOME`**（骨架与收尾见 `dsh-isolated-web-host`）。

## 前置检查

起隔离 host 见 skill `dsh-isolated-web-host`。**两个易漏点**（**2026-10-08 更正**：下面第 1、2 条原写"junction `.agent-presets`"与"`settings.yaml` 里 `agent-presets.default`"，**两条都已被本轮证伪**——那套目录在 `0.2.0-rc.2` 上没有任何代码读，`settings.yaml` 则是被 boot 吞掉的一次性 legacy 导入源）：

1. **测试 home 里要有"你要验的那份 preset 的载体"**。preset 现在是 **profile 组合里的 `@deepseek-ai/dsh-agent-preset` 声明行**，所以测试 home 的 profile 组合（`<测试home>\profiles\<profile>\cordis.patch.yml`）必须挂着那条声明行。**载体形状、逐行离线校验与安装的正文单一归属在 `dsh-agent-preset-verification`，本 skill 不复制。**
2. **默认 preset 由 profile patch 决定**（`<profile>/cordis.patch.yml` 里 `- id: agent-preset-registry` 的**部署**默认 `config.default` / **用户**默认 volatile 的 `config.selectedDefault`；取值逻辑 `selectedDefault ?? default`），**不是** `settings.yaml`。**要改"新会话默认"该写哪个字段、以及为什么在正在运行的 host 上热改这一行会让已存在会话的工具面崩塌**（含 `Config field "default" is not volatile` 等错误原文）→ **单一归属在 `dsh-agent-customization` 2.13**，本 skill 不复制。`settings.yaml` 的顶层键必须**正好等于 profile entry id**，否则只 `logger.warn` 后**静默丢弃**（陷阱要点见总纲 `dsh-agent-customization` 第 1 节）。

## 步骤

### 1. 在页面上下文里发 RPC

形态：`POST /api/<ns>/<method>`，body：

```json
{"type":"client-request","rpcId":"<uuid>","method":"<ns>/<method>","payload":{"args":{}}}
```

**鉴权（实测）**：**不是** `Authorization: Bearer` —— 那样发**恒 401**。正确做法是先用浏览器打开启动打印的那条 URL 即 **`GET /?token=<t>`**，**取回签名 cookie**，之后的 RPC 都靠这个 cookie 通过（token 换 cookie 后页会重定向到不带认证参数的同一目录）。⇒ 发 RPC 前先确认"页面上下文是用带 token 的启动 URL 打开过的"；拿到恒 401 先查这一步，别去怀疑 RPC 方法名。

- 列 / 读 preset：`agentPresets/list {}`、`agentPresets/read {agentPreset:"<id>"}`
- **建会话（= 挂载验证）**：`session/create {request:{cwd:"<dir>"}}` → 返回里带 `agentPreset` 即挂载成功。实测样本（**注意这是旧机制时代的 id**，现行 shipped id 是 `standard` / `ptc` / `minimal` / `cordis`）：`{"sessionId":"session-…","agentPreset":"orchestrator"}`

**发一轮用户输入的形状（本轮实测）**：`session/prompt {request:{requestId:"<uuid>", sessionId:"<id>", mode:"queue"|"steer", content:[{type:"text", text:"…"}]}}`（`mode` 决定排队等当前轮结束，还是打断当前轮）。**两个观测点别记混**：`request/header` 是**重挂载时重发**（判"此刻注入了哪套 persona / 哪些工具"认它）、`system/message` 是**每轮重发**（判"这一轮实际注入的正文"认它）。

### 2. 取权威工具清单（别让模型自述）

`session/page {request:{address:{kind:"session",sessionId},throughSeq:<cursor>,maxMessages:200}}`，读 `request/header.header.tools[].name`。

- 这是**服务端权威**清单；模型自述"我有哪些工具"不可信。
- `throughSeq` 是**必填**（源码对 `-1` / 非安全整数直接抛 `throughSeq must be an integer greater than or equal to -1`）。**取游标的做法**：先发一个**明显过大**的值（实测用 `9999`）让它**报错带回游标**——`session page through seq 9999 is past cursor N`——**再用 N 重试**。即 `throughSeq` 必须**精确 ≤** 游标。
- **`records[].type` 恒为 `"event"`，真类型在 `records[].event.type`**（服务端把每条事件包成 `{type:"event", event}`）。⇒ 写成 `record.type === "turn/end"` 这类过滤**永远筛不到**；要写 `record.event.type`。

### 3. 核对 persona

会话 system prompt 首段应是预期 persona。实测原文：`You are an ORCHESTRATOR agent powered by the deepseek-v4.1-flash model`。

**判据口径（实测）**：会话内的 persona 段 = **静态 `config.prefix` 把 `{{model}}` 渲染之后**的结果（实测：模板 **2430** 字符 → 渲染后 **2440** 字符，渲染结果与"按模板渲染出的期望文本"**逐字节相等**；**这两个数是本次实测示例，不是常量**）。

⇒ 判据必须写成"**渲染后逐字包含**指定片段"，**不要**用整段 `sha256` 相等：

- 用 sha256（或"长度必须等于某个常量"）当判据，会把**正确**的渲染结果误判成"被截断 / 被改写"——换行与包装一变哈希就变，而内容其实没坏。
- 锚点取**语义片段**逐字 `contains` 即可（例：`You are an ORCHESTRATOR agent powered by the` ＋ 实际 model 名）。

### 4. 真委派一次（核心）

不要只看工具在不在，必须**真调一次**，然后核对四件事：

1. 子代理 `config`（provider/model）——验证静态路由 pin；
2. 子代理 system prompt——验证子代理 persona；
3. 子代理工具目录——验证 `toolFilter` 裁剪；
4. **父会话 `turn/end` 是否为 `{"kind":"completed"}`**——但**等的判据不能只是"出现了 `turn/end`"**：必须比 **`.data.turn == N`**（N = 本轮序号）。本轮实测坑：写成 `if "turn/end" in kinds:` 会**把上一轮的 `turn/end` 当成本轮结束**（有历史的会话上会立刻"完成"，读到的是旧轮结论）。⇒ 正确姿势：**发 prompt 前先记下当前最大 `turn`，再等严格大于它的那条**。

读子代理：address 用 `{kind:"subagent",parentSessionId,childSessionId,mode:"one-shot"}`；`childId` 取 `subagent/catalog` 事件里的值（**不带** `session-` 前缀）。

**负对照判挂载**：`pluginInventory/list` 结果按 `/team/i` 之类的关键字过滤，能一眼看出某插件 row 到底有没有生效——未挂载 → `[]`；挂载 → `enabled=true / fiberPhase=active`。

### 5. 对照组（**两组，缺一不可，尤其别漏 B**）

**对照组 A · 插件行差分**：把可疑插件 row 拿掉，再跑一遍**同样的委派**，用于判定"是不是这个插件造成的"。没有对照组就不要下结论。

**对照组 B · 热重载活动会话（最容易漏、也最容易给出假通过的一组）**：验收**必须在"改动之前就已经存在、且仍在活动"的会话里再发一次提问**——**不能只验新建的会话**。

- **为什么必须**：新建会话会走一遍新的 `composeAgent().setup`，**热重载后一切正常**；只有**热重载前就存在**的会话才会暴露问题。本轮就是**先漏掉、后靠这一组抓到**根因的。
- **判据**：同一 host、同一份改动下，**老会话**与**新会话**的工具面**必须一致**（两边都按第 2 步点名核对 `header.tools[].name`）。**老会话少工具 = 验收失败**，哪怕新会话全绿。
- **适用范围**：这一组才抓得到"在**正在运行的 host** 上改 `agent-preset-registry` 行 ⇒ 已存在会话工具面当场崩塌、且**热重载不自愈**"那类故障。机制、字段判据（volatile `selectedDefault`）与错误原文的**单一归属在 `dsh-agent-customization` 2.13**，本 skill 不复制、只留这条指针。

### 6. 最省事的离线取证：直接解压会话日志

```
<DSH_HOME>\sessions\<workspace目录>\<sessionId>\session.v4.jsonl.zstd
```

**版本口径（实测）**：**当前 rc.2 写的是 `session.v4.jsonl.zstd`**；`session.v3.jsonl.zstd` 是 **2026-09-30 之前的旧代**（实测 431 份 v3 的 mtime 全落在 2026-09-16~09-30，89 份 v4 全在 2026-10-08 之后）⇒ **同一 `sessions` 目录下会两代并存**。取证时**按目录里的实际文件名取，别按固定版本号拼路径**。

**关键坑（配方不在本节，只留指针）**：这些文件是**多帧拼接**的，单次 `zstdDecompressSync()` 只解**第一帧** ⇒ 会误判"日志是空的"。**为什么在 live-verification 里必须知道它**：第 6 步的取证判据（下面两行 grep 的 `turn/end` / `tool/result`）只能从**完整解压**后的日志里取，而"委派到底发生了什么"除日志外没有第二个来源 ⇒ 解不全会把"没解出来"误读成"没发生"。**逐帧切分、magic 判据与实测数字的完整配方单一归属在 `dsh-agent-customization` §2.12**（该节含现成工具 `tools\session\read-session-log.mjs`），本节不复制。

解压后：

- grep `"type":"turn/end"` 看 `reason.kind`（`completed` vs `error`）
- grep `tool/result` 看 `isError` 与子代理返回原文

## 从会话日志**本体**判「persona 真生效」（本轮实测；方法本身即配方）

**纪律：结论锚在结果本体上。** 判据**不是**"我重启了 host"，而是"**日志本体里的 `system/message` 长度与标记变了**"——报告、页面、自我声明都不算（用户冷启动后就是这样验收的）。

**一条命令**（现成工具，与 `tools\session\read-session-log.mjs` 并列）：

```powershell
node tools\session\probe-persona-injection.mjs "<...\sessions\<workspace目录>\<session-id>\session.v4.jsonl.zstd>"
```

它内部按 multi-frame zstd 解**全部帧**，分别打印三块：**`system/message`（persona）/ `request/header`（工具面）/ `user/message`（宪法）**。漏参数会打 `usage` 并 **`exit 2`**。

**怎么判（本轮实测值，可当对照样例）**：

| 判什么 | 认哪个事件 | 本轮实测（冷启动前 → 后） | 判据（**不是**"等于某个数"） |
|---|---|---|---|
| persona 真换上 | `system/message` | 恰好 **2 条**；**12,510 → 10,490 字符**，旧标记 `Hard rules` 消失、新标记出现 ⇒ **Δ = −2,020 字符** | **Δ ≠ 0 且旧标记消失**；与文件层（2,430→410）及隔离 lab 预测**三方吻合** |
| 工具面没被削掉 | `request/header` → `data.header.tools` | 全部 **`tools=106`**、**名字哈希唯一**（`distinct name-sets = 1`） | **Δ = 0**。⚠️ **106 ≠ lab 的 31**（真实 host 挂了 MCP）⇒ **判据是"跨重启零变化"，不是"等于 31"** |
| 宪法仍在注入 | **重复出现的 `user/message`** | 同时含 `§2`/`§3` 标题 + `§8` + 判据字串（`YAML_SKIP`） | 四项同时为真 |

**三个坑（本轮逐字踩过）**：

1. **事件类型字段是 `type`、不是 `kind`** ⇒ 用 `ev.kind` 过滤会**静默零命中**，然后得出"日志里没有这种事件"的**错误结论**（第一版就报出 `request/header events = 0`）。工具里的 `kindOf` 用 `ev.kind || ev.type` 兜底，但**别依赖这个兜底**。
2. **绝不要裸 grep 原始日志找 persona 标记**：**你自己的工具调用也会被写进日志**，脚本里含标记字面量就会**命中自身** ⇒ 报出**假证据**（命中的是你写下的字、不是被注入的 prompt）。⇒ 标记必须**用字符串拼接构造**（如 `'Hard' + ' rules:'`），让脚本匹配不到自己。
3. **三件事在三种事件类型里**，查一种证明不了另一种：persona → `system/message`；工具面 → `request/header.data.header.tools`；宪法（`~/.dsh/AGENTS.md`）→ **重复出现的 `user/message`**。**在 `system/message` 里找宪法只会得到 `false`**——差点误判成"宪法没注入"。

**边界（别过度外推）**：这**只证明"这一条会话"拿到了什么**；要断言"所有新会话都拿到新 persona"仍需**多次采样**（本轮样本 = 1 个会话、跨一次冷启动）。

## 坑与修法

- **挂载 `@deepseek-ai/dsh-experimental-agent-team` + `-tool-agent-team` 后普通子代理委派会坏**（2026-10-08 修正：旧版本本条写的"**所有**普通委派都失败 + **没有任何配置级绕法**"**说过头了**；实际是**两个可分开的症状**，旧版把两者混成一句）。

  **症状一（工具名被顶掉，更常见）**：Team 插件在**每个成员的 `agent.ctx`** 里重新注册 `send_message` / `list_agents` / `interrupt_agent`（+ Team 专有 `wait_agent`），同作用域**后注册者胜出** ⇒ 你以为在调原生工具，实际拿到 Team 版 schema。把 Team 版 `send_message` 指向普通子代理时的原文：

  ```
  父会话 tool 结果 = Error: active teammate "<childId>" not found      # code = TEAM_MEMBER_NOT_FOUND
  ```

  取证（差分对照）：把**未打补丁**的 team 插件与原生 `dsh-tool-subagent-control` + `.../list-agents` 依次装进**同一个**录制作用域，3 个原生名**全部归 team**；换成**改名后**的 team 插件，3 个原生名**全部归原生**、`team_*` 4 个名并存。真会话对照：只挂 `-agent-team-profile` bundle 时会话工具面 **29 个、原生 3 个全缺席**；把原生行重插后**同一组合 32 个、两族并存**。

  **症状二（`TEAM_NOT_MEMBER`，scope 装错）**：

  ```
  父会话 tool 结果 = Error: subagent run failed
  子会话 turn/end = {"kind":"error","error":{"message":"agent \"<id>\" is not a member of an active Agent Team"}}
  ```

  → 机制：tool 包的 `team:policy` 提示段 `text()`（`dsh-experimental-tool-agent-team/lib/index.js:242`）调的是**会抛**的 `TeamRoster.membership()`（`dsh-experimental-agent-team/lib/index.js:389` 抛 `TEAM_NOT_MEMBER`）。`install()` 由 `agent/created` 触发、门槛是 `tryMembership(agent) !== undefined`（tool 包 `lib/index.js:533`），而子代理创建瞬间 `subagent/descriptor` 尚未落盘 → 误走「隐式 Lead」分支（agent-team `lib/index.js:411-417`）把团队工具 + policy 段装进子代理；随后描述符落盘、`tryMembership` 变回 `undefined`，但段已装好 → 渲染即抛。（本条机制来自早前静态阅读，2026-10-08 **未复测**。）
  → **修法（"只能把两个包拿掉"已被证伪）**：① 只需要普通委派 ⇒ 别让原生行被 `disabled` 掉（组件 / 组合层）；② 要两族并存 ⇒ 把 Team 的 4 个工具**改名**再注册（代码补丁，实测两族并存且原生语义完好）——总纲 `dsh-agent-customization` 2.5 有判据、2.10 有做法；③ 上游修法仍是 `text()` 改用 `tryMembership` 并对非成员返回空段，或 `install()` 延后到描述符落盘后。
  → 附带问题一：团队工具**绕过** `toolFilter`（会往只读子代理里塞团队工具）。
  → 附带问题二：同名工具**静默遮蔽** `subagent-control` 的语义（= 上面的症状一，已用差分对照坐实）。

- **从会话日志里取正文/工具清单要认准嵌套层级**：工具清单在 **`ev.data.header.tools`**（不在事件顶层）——写成 `ev.header?.tools` 会得到 `tools (0)`，让人误判"工具全没了"；注入的策略/persona 正文在 **`ev.data.message.content[0].text`**（`system/message` 事件）。实测一个正常会话 `request/header` 里能列出 32 个工具的完整 `{name, description, parameters}`，**参数名就是判"同名工具到底是谁"的权威依据**（例如原生 `send_message` 是 `agent_id, message`，Team 版是 `target, message`）。

- **Playwright 页面上下文可能被其它代理抢占**（页面被导航到别的站点）→ 重新 `browser_navigate` 回带 token 的 URL 再重试；host 进程本身不受影响。

- **`throughSeq` 报 `past cursor N`** → 不是游标过期，是**必须精确 ≤**：直接用 N 重试。

- **`agentPresets/read` 返回 `agent-preset/not-found`** → 测试 home 的组合里**没有你要验的那条声明行**（**不是**"缺 `.agent-presets` 目录"，那套已死）。按前置检查 1 把声明行挂进 profile 组合；载体的正文归 `dsh-agent-preset-verification`。

- **子代理 address 用错 childId** → `subagent/catalog` 事件里的值**不带** `session-` 前缀，带上就读不到。

## 不要做什么

- 不要只凭 `session/create` 返回了 `agentPreset` 就宣称验收通过——那只证明挂载，不证明 persona / 工具 / 委派对。
- 不要用模型自述的工具列表当权威清单，用 `session/page` 的 `header.tools[]`。
- 不要用 `zstdDecompressSync()` 单次调用判断日志内容——**症状**：只解第一帧、把"解不全"误判成"日志是空的"；**判据与完整配方**（逐帧切分 / magic 判据 / 实测数字）**单一归属在 `dsh-agent-customization` §2.12**。
- 不要在没有对照组的情况下断言"是这个插件导致的"。
- **不要只验"新建会话"就宣布验收通过**——新建会话走的是新 `setup`，热重载后必然正常；**改动之前就存在**的会话才是判据（第 5 步对照组 B）。
- **不要用 `Authorization: Bearer` 发 RPC**（恒 401）——先用带 token 的启动 URL `GET /?token=<t>` 取回**签名 cookie**（第 1 步）。
- **不要用整段 `sha256` 或"固定长度"判 persona 是否完整**——`{{model}}` 渲染后长度必变，会把正确结果误判成被截断（第 3 步）。
- 不要为了验收去动用户的真实 `~/.dsh` 或真实端口，用隔离 host。
- 不要在离线校验还没过时就上来跑在线验收——先回 `dsh-agent-preset-verification`。
- **不要用 headless（`dsh --profile headless "<task>"`）当 preset 验收入口**：它不合成 preset，验不到你要验的东西；而且它会写你的 real home。
- **不要把 `.agent-presets` 目录当 preset 载体**：`0.2.0-rc.2` 上没有任何代码读它，写进去 / 删掉都无行为变化。

## 验收标准

- `session/create` 返回的 `agentPreset` == 预期 id。
- `session/page` 的 `header.tools[].name` 里出现**全部**预期工具（实测例：`explore`/`implement`/`verify`/`distill_skill` 都在）。
- system prompt 首段**渲染后逐字包含**预期 persona 片段（`config.prefix` 的 `{{model}}` 已渲染；**不要**用整段 sha256 相等当判据，见第 3 步）。
- 至少一次真实委派：子代理 `config` 的 provider/model 与 pin 一致、子代理 persona 正确、工具目录已按 `toolFilter` 裁剪、**父会话 `turn/end` 为 `{"kind":"completed"}`**。
- 可疑插件行有"有它 / 没它"两组对照结论；**且做过对照组 B**——改动**之前就存在**的会话在热重载后工具面与新会话**一致**（第 5 步）。
- 若走日志取证：多帧解压后能 grep 到 `turn/end` 与 `tool/result`，且不是只解出 286 字节 header。
