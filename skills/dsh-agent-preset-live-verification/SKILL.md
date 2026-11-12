---
name: dsh-agent-preset-live-verification
description: DSH agent preset 的在线会话级验收——已起隔离 host 并真建会话才能做：RPC 核对 agentPreset 挂载、system prompt persona、session/page 权威工具清单，真跑一次委派核对子代理 config/persona/toolFilter 与父会话 turn/end，并多帧解压会话日志取证（单次 zstdDecompressSync 只解第一帧）。适用于"离线校验过了但插件行为不对 / preset 在真会话里 persona 和工具对不对 / 委派为什么失败 / 想看父会话 turn/end 原文 / 某个插件行搞坏委派要对照组"。不适用：还没起会话、只想先验能不能挂载 → 用 `dsh-agent-preset-verification`；只是要个干净实验环境（起隔离 host，不做验收） → 用 `dsh-isolated-web-host`；不知道 DSH 整体该改哪一层、改完何时生效或怎么撤 → 用 `dsh-agent-customization`（总纲）。
whenToUse: 离线校验已通过、要在真会话里核对 preset 的 persona、工具裁剪与委派是否符合预期，或要解压会话日志取证时用。
disable-model-invocation: true
warm-triggers: 旧式 preset 的在线会话验收 / 会话日志多帧解压
warm-reason: 同上：旧 preset 目录已失效，保留取证方法
---

# 在线验收 agent preset

> 本 skill 是总纲 `dsh-agent-customization` 的子 skill：只负责「在线会话级验收」这一段；DSH 的分层、生效时机与上线纪律见总纲。

**离线过了再来看这里。** 分工：`dsh-agent-preset-verification` 管**离线**（能不能挂载、配置键对不对）；本 skill 管**在线**（挂载后到底对不对）。离线只证明 YAML/配置/发现层没问题；**插件 apply 期错误、realm/工具裁剪、模型路由、真实委派是否跑通**都只能在真会话里看到。

## 何时调用

**加载本 skill 当：**

- 离线校验已通过，要确认新 preset 在真会话里的 persona / 工具集 / 委派行为符合预期。
- 怀疑某个实验插件行搞坏了委派，需要"有它 / 没它"的对照证据。
- 会话已经跑完，想不看 UI 直接从日志里取 `turn/end`、`tool/result` 原文。
- 已起会话 / 正在跑会话，想知道"挂载之后到底对不对"（`agentPreset`、persona、工具裁剪、委派结果）。

**不要用本 skill（转交）：**
- 还没起会话（或不想起会话），只想先确认这份 preset 静态上能不能挂载 → 用 `dsh-agent-preset-verification`。
- 只是要一个干净的隔离实验环境（重定向 `DSH_HOME`、`--no-open`、401 判就绪、taskkill 收尾） → 用 `dsh-isolated-web-host`。

**前置**：已用 `dsh-agent-preset-verification` 离线校验通过，且有隔离 host 与能发 RPC 的页面上下文。 ／ **后继**：验收失败且定位到插件行后，回到 preset 改动 + 离线校验，再重跑本 skill 的对照组。

## 前置检查

起隔离 host 见 skill `dsh-isolated-web-host`。**两个易漏点**：

1. **测试 home 必须能看到 preset 目录**。把真实 `C:\Users\admin\.dsh\.agent-presets` 用**目录 junction** 链到 `<测试home>\.agent-presets`，否则 `agentPresets/read` 返回 `agent-preset/not-found`。roster 每次读取都重扫，junction 后**无需重启** host。

   ```powershell
   New-Item -ItemType Junction -Path '<测试home>\.agent-presets' -Target 'C:\Users\admin\.dsh\.agent-presets'
   ```

2. **`settings.yaml` 里 `agent-presets.default`** 决定新会话用哪个 preset：

   ```yaml
   agent-presets:
     default: orchestrator
   ```

## 步骤

### 1. 在页面上下文里发 RPC

形态：`POST /api/<ns>/<method>`，body：

```json
{"type":"client-request","rpcId":"<uuid>","method":"<ns>/<method>","payload":{"args":{}}}
```

- 列 / 读 preset：`agentPresets/list {}`、`agentPresets/read {agentPreset:"<id>"}`
- **建会话（= 挂载验证）**：`session/create {request:{cwd:"<dir>"}}` → 返回里带 `agentPreset` 即挂载成功。实测：`{"sessionId":"session-…","agentPreset":"orchestrator"}`

### 2. 取权威工具清单（别让模型自述）

`session/page {request:{address:{kind:"session",sessionId},throughSeq:<cursor>,maxMessages:200}}`，读 `request/header.header.tools[].name`。

- 这是**服务端权威**清单；模型自述"我有哪些工具"不可信。
- 坑：`throughSeq` 必须**精确 ≤** 游标，报 `past cursor N` 就用 N 重试。

### 3. 核对 persona

会话 system prompt 首段应是预期 persona。实测原文：`You are an ORCHESTRATOR agent powered by the deepseek-v4.1-flash model`。

### 4. 真委派一次（核心）

不要只看工具在不在，必须**真调一次**，然后核对四件事：

1. 子代理 `config`（provider/model）——验证静态路由 pin；
2. 子代理 system prompt——验证子代理 persona；
3. 子代理工具目录——验证 `toolFilter` 裁剪；
4. **父会话 `turn/end` 是否为 `{"kind":"completed"}`**。

读子代理：address 用 `{kind:"subagent",parentSessionId,childSessionId,mode:"one-shot"}`；`childId` 取 `subagent/catalog` 事件里的值（**不带** `session-` 前缀）。

**负对照判挂载**：`pluginInventory/list` 结果按 `/team/i` 之类的关键字过滤，能一眼看出某插件 row 到底有没有生效——未挂载 → `[]`；挂载 → `enabled=true / fiberPhase=active`。

### 5. 对照组

把可疑插件 row 拿掉，再跑一遍**同样的委派**，用于判定"是不是这个插件造成的"。没有对照组就不要下结论。

### 6. 最省事的离线取证：直接解压会话日志

```
<DSH_HOME>\sessions\<workspace目录>\<sessionId>\session.v3.jsonl.zstd
```

**关键坑**：这些文件是**多个 zstd 帧拼接**的，`zlib.zstdDecompressSync()` 只解**第一帧**（只会得到 286 字节的 header，让人误以为日志是空的）。正确做法：按 zstd magic `28 B5 2F FD` 切帧，逐帧 `zstdDecompressSync` 再拼接。实测一个 19 KB 文件能解出 24 行 / 64 KB。

解压后：

- grep `"type":"turn/end"` 看 `reason.kind`（`completed` vs `error`）
- grep `tool/result` 看 `isError` 与子代理返回原文

## 坑与修法

- **`TEAM_NOT_MEMBER`：挂载 `@deepseek-ai/dsh-experimental-agent-team` + `-tool-agent-team` 后所有普通子代理委派都失败。**

  ```
  父会话 tool 结果 = Error: subagent run failed
  子会话 turn/end = {"kind":"error","error":{"message":"agent \"<id>\" is not a member of an active Agent Team"}}
  ```

  → 机制：tool 包的 `team:policy` 提示段 `text()`（`dsh-experimental-tool-agent-team/lib/index.js:242`）调的是**会抛**的 `TeamRoster.membership()`（`dsh-experimental-agent-team/lib/index.js:389` 抛 `TEAM_NOT_MEMBER`）。`install()` 由 `agent/created` 触发、门槛是 `tryMembership(agent) !== undefined`（tool 包 `lib/index.js:533`），而子代理创建瞬间 `subagent/descriptor` 尚未落盘 → 误走「隐式 Lead」分支（agent-team `lib/index.js:411-417`）把团队工具 + policy 段装进子代理；随后描述符落盘、`tryMembership` 变回 `undefined`，但段已装好 → 渲染即抛。
  → 修法：**没有配置级绕法**（两个包的 Config 都不含成员校验开关）。需要上游修：`text()` 改用 `tryMembership` 并对非成员返回空段，或 `install()` 延后到描述符落盘后。验收期只能把这两个包从 preset 里拿掉。
  → 附带问题一：团队工具**绕过** `toolFilter`（会往只读子代理里塞 9 个团队工具）。
  → 附带问题二：同名工具**静默遮蔽** `subagent-control` 的语义。

- **Playwright 页面上下文可能被其它代理抢占**（页面被导航到别的站点）→ 重新 `browser_navigate` 回带 token 的 URL 再重试；host 进程本身不受影响。

- **`throughSeq` 报 `past cursor N`** → 不是游标过期，是**必须精确 ≤**：直接用 N 重试。

- **`agentPresets/read` 返回 `agent-preset/not-found`** → 测试 home 里没有 `.agent-presets`。补 junction（见前置检查 1），roster 每次读取都重扫，不用重启。

- **子代理 address 用错 childId** → `subagent/catalog` 事件里的值**不带** `session-` 前缀，带上就读不到。

## 不要做什么

- 不要只凭 `session/create` 返回了 `agentPreset` 就宣称验收通过——那只证明挂载，不证明 persona / 工具 / 委派对。
- 不要用模型自述的工具列表当权威清单，用 `session/page` 的 `header.tools[]`。
- 不要用 `zstdDecompressSync()` 单次调用判断日志内容——只解第一帧，会误判"日志是空的"。
- 不要在没有对照组的情况下断言"是这个插件导致的"。
- 不要为了验收去动用户的真实 `~/.dsh` 或真实端口，用隔离 host。
- 不要在离线校验还没过时就上来跑在线验收——先回 `dsh-agent-preset-verification`。

## 验收标准

- `session/create` 返回的 `agentPreset` == 预期 id。
- `session/page` 的 `header.tools[].name` 里出现**全部**预期工具（实测例：`explore`/`implement`/`verify`/`distill_skill` 都在）。
- system prompt 首段 == 预期 persona 原文。
- 至少一次真实委派：子代理 `config` 的 provider/model 与 pin 一致、子代理 persona 正确、工具目录已按 `toolFilter` 裁剪、**父会话 `turn/end` 为 `{"kind":"completed"}`**。
- 可疑插件行有"有它 / 没它"两组对照结论。
- 若走日志取证：多帧解压后能 grep 到 `turn/end` 与 `tool/result`，且不是只解出 286 字节 header。
