# 团队化协作（9.0–9.6）：引用基线 / 触发 / 写域 / 工具陷阱 / 状态机 / 复核 / 清台账（原样拆出）

> 从 `orchestrating-subagents/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

### 9.0 引用基线（先对指纹，再读行号）

| 别名 | 绝对路径 | 版本 | bytes | sha256 前 16 |
|---|---|---|---|---|
| **TP** | `C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-experimental-tool-agent-team\lib\index.js` | 0.2.0-rc.2 | 18707 | `cafdbb7a050431b1` |
| **DP** | `C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-experimental-agent-team\lib\index.js` | 0.2.0-rc.2 | 72893 | `7e8122ed7ae6723d` |
| **DPT** | `C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-experimental-agent-team\lib\types\task-board.js` | 0.2.0-rc.2 | 12036 | `eb4f0b9229c9f2ca` |
| **DPR** | `C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-experimental-agent-team\README.md` | 0.2.0-rc.2 | 17873 | `d54ab03a26bfbc99` |
| **TPR** | `C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-experimental-tool-agent-team\README.md` | 0.2.0-rc.2 | 10903 | `613ebf098c032d49` |
| **SA**（旧代，仅 §9.5 用） | `D:\workspace\agent\dsh_base\artifacts\staged\a\package\lib\index.js` | 0.1.5-rc.2 | — | 仅作代际对比 |
| **SB**（旧代，仅 §9.5 用） | `D:\workspace\agent\dsh_base\artifacts\staged\b\package\lib\index.js` | 0.1.5-rc.2 | — | 仅作代际对比 |

> README 的**中文版 `README.zh.md` 与被引行的英文行同号**（如 `Prompt policy is coordination, not confinement` = **TPR:146**，中文版 `dsh-experimental-tool-agent-team\README.zh.md:146` 是「提示词策略只负责协调，不负责 confinement」）——引中文版时按同一行号即可。
> ⚠️ 这句**只在工具包 README 里**；域包 `DPR` 的 `:146` 是**空行**（本轮踩过：grep 同时命中两个包的 `:146`，误当成域包也有）。

按**失败模式**分四类（触发 → 资源冲突 → 工具陷阱 → 状态机），不按工具列。

### 9.1 触发：什么时候必须记账（触发类）

- **谁有权组队**：`create teammates only when the user explicitly asks to use Agent Teams or teammates.`（**TP:21**）；`The fixed policy creates teammates only when you explicitly ask for a team or teammates, so ordinary tasks never trigger delegation on their own.`（**TPR:32**）。
- **触发条件**（**我方**判定，官方无此条）：预计跨多轮，或 ≥3 个并行长任务。**别再引官方文本当依据**——官方没有"何时建账"的规则。
- **协作状态不进对话、落进文件**：官方把 roster / task / mailbox 全做成 **log-only** —— `team/member`、`team/task`、`team/message/queued`、`team/message/delivered` **永不进对话面**：`… are log-only: they never enter the conversation surface, so derived model history is untouched by coordination records.`（**DPR:147**）；`Roster, task, and mailbox records are log-only and never enter derived model history.`（**DPR:187**）。
- **设计原则（逐字）**：`Durable log, derived state.` / `The Lead Session log is the single source of truth; roster, mailbox, and task state are replayed from it on every read.`（**DPR:105**）；`Explicit authority. Every service method takes the exact live calling Agent; only the Lead spawns, reassigns, or interrupts.`（**DPR:107**）。
- **落盘位置**：`<cwd>\.dsh-run\<日期>-ledger.md`（**我方**约定，无官方出处）。不进对话，按需 `read`。

台账表格样例（直接抄，一个成员一行）：

```markdown
| 角色名 | target (agent_id / job_id) | 任务 | 写域 | 交付物路径 | 状态 |
|---|---|---|---|---|---|
| auditor  | session-1a2b… | 复核纪律条目判定表 | 只读 | %TEMP%\agreement-audit.md | done |
| builder  | job-7f3c…     | 重建索引           | D:\w\idx\ | D:\w\idx\idx.json | 在跑 |
| verifier | session-9d4e… | 反驳 auditor 的某条判定 | 只读 | 无 | 待发 |
```

- **台账状态机**：`待发 → 在跑 → done / partial / blocked / killed`（**我方**约定，无官方出处）；`killed` 也是一种**归宿**，不是失败。**一条任务一个 owner**——owner 只用 `list_agents` / `subagent` 返回的 `target`，**不许按名字猜、不许复用已结束的 id**（官方原话见 §9.2）。认领要连带记下**你基于哪次读**（revision）——内容变了就重做，规则同 §9.3。

### 9.2 资源冲突：写域互斥，但重叠只是建议（资源冲突类）

- **写域互斥（官方原话，一整行）**：`Split write work into disjoint scopes, record expected write scopes on shared tasks, and use task dependencies when work must be ordered.`（**TP:23**）
- **写域是纪律，不是锁（官方原话，同一行）**：`Write-scope overlap is advisory, not a lock.`（**TP:23**，注意：**只有这一处**，原 §9 标成 `:26、:40` 两处是错的）。README 侧同义：`writeScopes are normalized workspace-relative prefixes; views warn on overlap with in-progress tasks but never block claim or authorize writes.`（**DPR:139**）。
- **实现就是"加一条 warning"**，不拦任何东西：`if (task.writeScopes.some((left) => other.writeScopes.some((right) => scopesOverlap(left, right)))) warnings.add(\`write scopes overlap with ${other.id}\`);`（**DP:1073**，函数头注释 `Derive one task view with owner name, readiness, and advisory write overlaps.` = **DP:1060**）。
- ⇒ **收尾必须核验越界写，落点在"点名 + 宿主自算 sha256"**（我方动作，无官方出处——DSH 没有按 agent 归因的改动清单，别设计在它上面；核验能做/不能做到的边界见 §8 末「边界」，跨写域的改动一律由你复验，别信约定）。
- **官方对"绕过"的定性（照抄即可）**：`Advisory write scopes — Bash, formatters, code generators, and direct external writers can bypass filesystem version checks; Leads must coordinate ownership and review the final diff.`（**DPR:207**）
- **有依赖的必须显式串行**：把上游产物路径写进下游 prompt 的【已知】，并写明"先 A 后 B"；**就绪不会自动开工（官方原话）** `Task readiness never starts an owner.`（**TP:27**）。域包侧"就绪"只是 claim 的前置条件，不唤醒任何人 —— `TEAM_TASK_BLOCKED`（**DP:1538** / **DP:1597** / **DPT:115** / **DPT:168**）。
- **owner 只用官方返回的 `target`，不许按名字猜**：`Use the target returned by spawn_teammate or list_agents for send_message and interrupt_agent, or as owner when assigning or filtering shared tasks.`（**TP:27**）；`Creation and listing results identify members by target, with no member Session ID.`（**TPR:64**）。
- **报错原文（可直接贴进事故记录）**：`stale team task "<id>" revision <expected>; current revision is <current>`（**DP:1527** `TEAM_TASK_STALE_REVISION`，同族 **DPT:98**）、`team task "<id>" is not ready to claim`（**DP:1538**）、`task mutation requires its owner or Team Lead`（**DP:1532** `TEAM_TASK_UNAUTHORIZED`）、`team task "<id>" is owned by another member`（**DP:1537** `TEAM_TASK_ALREADY_CLAIMED`）、`team task "<id>" still blocks "<dep>"`（**DP:1609** `TEAM_TASK_HAS_DEPENDENTS`）。

### 9.3 工具陷阱：stale 写与"脚本直写"（工具陷阱类）

- **官方原话（一整行，含三件事）**：`Prefer read/edit/write for file changes. If a file operation returns FS_STALE_VERSION, read the current file, rebase your intended change onto the new content, and retry. Bash, formatters, code generators, and scripts are not fully protected by the filesystem version guard; coordinate them explicitly and have the Lead review the final diff and run tests.`（**TP:25**）
- 两条硬纪律（**我方**）：① **能 `read`+`edit` 就别用脚本覆盖式写盘**；② 非程序化写不可时，**写前记 sha256、写后读回并给行号证据**——读回要比对"我打算写进去的那几行真的在"，而不是"文件变大了"。
- **撞车处置（官方原话）**：`read the current file, rebase your intended change onto the new content, and retry`（**TP:25**）。**不许**拿"我读过"当理由覆盖别人的新内容。
- **写作用域必须是工作区相对路径**（写错直接抛）：`invalid workspace-relative write scope ${JSON.stringify(value)}`（**DP:336**，`TEAM_INVALID_WRITE_SCOPE`）。
- **官方明确说没有文件锁**：`One process and one shared checkout — members share cwd and observe edits immediately; this package provides no worktree, remote member, merge, or filesystem lock.`（**DPR:206**）。
- ⇒ 「写前 `read`、写后**立即重读**、两次读之间变了就停下报告」、「派子代理改共享文件之前先留副本并记 sha256」这两条是**我方纪律，无官方出处**，别引官方文本。
- 多会话/多成员共享同一目录时：写前 `read`、写后**立即重读**；两次读之间内容 / 大小 / 时间戳变了 = 有别的写手 → **停下报告**，不要回滚，也不要"顺手修正"。
- **派子代理去改共享文件之前，先留副本并记 sha256**（快照池之外的 skill 没有自动回滚源；池的权威定义 = `D:\workspace\agent\dsh_base\config\manifest.json`）：副本落 `artifacts\backups\<name>.<日期>.bak`（整树改动用目录），**派活之前**就存——改完再存就晚了。改前/改后各记一次 sha256，作为"我只改了该改的"的第二个 oracle（**改前/改后 sha256 只证明变了、不证明只改了申报的那些**；不给备份也能做的逐字节范围反证——把本次新文本逆替换回旧文本、重建改前 bytes+sha256——见 `dsh-skill-authoring` §8 oracle 5）。
- **订阅侧一致性由官方保证**：`Session event seq and time own ordering and timing`（**DPR:147**）；`replays each candidate Team event against its committed prefix and rejects invalid transitions before append`（**DPR:147**）。

### 9.4 状态机：等待纪律 + 状态≠成果 + 载体选择（状态机类）

**等待纪律**（除注明外全部出自 TP:27 这一行官方策略文本）

1. 等之前先确认**真有成员在跑**：`Before wait_agent, use list_agents and make sure another required member is running or provisioning; use send_message first when the required member is inactive.`（**TP:27**）。生效的"活跃态"只两个：`const ACTIVE_WAIT_STATUSES = new Set(["running", "provisioning"]);`（**TP:28**，判定点 **TP:343**）。
2. **只观察调用之后的变化，且不会唤醒对方**：`wait_agent observes only changes after that call starts, never wakes a member, and returns noProgress immediately when no other member can produce a change.`（**TP:27**）；工具描述 `Wait for the next teammate status, mailbox, or shared-task change after this call starts. This never wakes inactive members and returns noProgress immediately when no other member is running or provisioning. Re-list after wakeup or timeout instead of polling.`（**TP:333**，超时区间 `from 10000 through 3600000` = **TP:336**，README 侧 `from ten seconds through one hour` = **DPR:143**）。
3. **noProgress 的固定回话（逐字）**：`No other Team member is running or provisioning. wait_agent cannot make progress or wake inactive teammates. Re-list with list_agents and team_task_list, then use send_message to wake each required inactive teammate before waiting again.`（**TP:29** `NO_ACTIVE_PEER_MESSAGE`，返回点 **TP:343–348**；schema 注释 `/** noProgress is present only on the model-only shortcut that skips the wait. */` = **TP:160**，字段定义 = **TP:169**）。
4. **超时或唤醒后重新清点，禁止轮询**：`Re-list after wakeup or timeout.`（**TP:27**）。
5. **已返回 id 的任务绝不重发**：`A successful send is already durable even when its result says queued; do not resend it.`（**TP:27**）——重派 = 重复劳动 + 双重写入；要纠偏用 `send_message` 引导。共享任务的正规流程同源：`Shared-task workflow is list, get, claim with the current revision, perform the work, then complete.`（**TP:27**）。
6. **收尾：不等齐不下结论**：`The Lead must wait for required teammates before giving the final answer.`（**TP:27**）。每个"在跑"的成员都要**收结果或明确 kill**，并在最终回答里给出归宿（收了几条、杀了几条、为什么）。

**状态 ≠ 成果（官方原话）**

- `inactive means no turn is executing; it does not describe task completion, success, failure, or waiting for other agents. provisioning means member creation is in progress; failed means member creation failed.`（**TP:27**）
- 工具侧同义：`List the Lead and every durable teammate with an addressable target and current availability. inactive means no turn is executing, not a task result. provisioning and failed describe member creation.`（**TP:324**）
- README 同义：`inactive means no turn is executing, whether the member is loaded or must be resumed; it does not describe task completion or outcome.`（**TPR:64**）
- ⇒ 「后台 job 的 `finished` **只表示进程结束**、`exit code` 可能是 1（Windows 上被强杀也以 exit 1 静默收场）、`list_agents` 的 inactive 同理；判完成只认三件套」是**我方**对这条官方语义的映射，**不是**官方原文。
- ⇒ **判完成只认三件套**：① 交付物**在磁盘上且可读**；② 验收命令**真跑过且 `exit=0`**（后台 job **回读 exit code**，不认 `finished` 这类状态名）；③ 结论与证据对得上，且 `STATUS` 不是 `PARTIAL`/`BLOCKED`。**缺一条 = 未完成**。

**载体选择 fresh vs fork（官方原话）**

- `fresh starts without Lead history; fork inherits completed Lead turns. Defaults to fresh.`（**TP:264**）；默认值本身：`freshProvider: z.string().default("spawn"),` / `forkProvider: z.string().default("fork")`（**TP:17–18**）。
- **委派 prompt 必须自报身份**——官方就是这么注入的，逐字原文（**TP:276–282**）：`You are teammate "${args.name.trim()}".` / `Your Team Lead is named "lead".` / `Use list_agents({}) to find your teammates and their names.` / `To message your Team Lead, use send_message({ target: "lead", message: "..." }).`
- **Lead-only 是执行期强制，不是靠提示**：`only the Team Lead can create teammates`（**DP:546**）/ `only the Team Lead can interrupt teammates`（**DP:505**）/ `only the Team Lead can reassign tasks`（**DP:1588**）；工具描述逐字 `Create one named, durable teammate. Only the Team Lead may call this tool.`（**TP:244**）、`Interrupt one teammate's current turn while preserving its pending inbox. Team Lead only.`（**TP:355**）。

| 子任务需要什么 | 用哪个 | 代价 |
|---|---|---|
| **这段对话的上下文**（接着刚讨论的设计、基于本轮已确认的结论） | `subagent_fork` | 继承**整段**历史 ⇒ 更贵，也更容易被这段对话的既有结论带偏 |
| 其余一律 | `subagent`（fresh，默认） | 必须写全【已知】，但便宜、不受本对话偏见影响 |

→ 默认 fresh；只有"解释背景的成本 > 继承历史的成本"时才 fork。

**其余可由行号直接引用的硬机制**

| 机制 | 行号 | 原文关键词（逐字） |
|---|---|---|
| 名字**不重用** | **DP:563** | `teammate name "${name}" was already used in this Team`（`TEAM_MEMBER_NAME_TAKEN`） |
| 成员上限 | **DP:564** | `Team member limit ${this.maxMembers} reached`（`TEAM_MEMBER_LIMIT`） |
| 上限默认值 | **DP:1669** | `const DEFAULT_MAX_MEMBERS = 16;` |
| 名字格式 | **DP:704** | `teammate name must be lower-kebab-case, at most 64 characters, and not "lead"` |
| 信箱容量 | **DP:826** | `teammate "${target.name}" has ${pendingForTarget} pending messages`（`TEAM_MAILBOX_FULL`） |
| 单条消息上限 | **DP:834** | `team message exceeds ${this.maxMessageBytes} bytes`（`TEAM_MESSAGE_TOO_LARGE`） |
| 信箱/任务默认值 | **DP:1671–1672** | `DEFAULT_MAX_PENDING_MESSAGES = 64` / `DEFAULT_MAX_MESSAGE_BYTES = 65536` |
| DAG 环检测 | **DP:1027** | `task dependency cycle includes "${id}"`（→ `TEAM_TASK_DEPENDENCY_CYCLE`，映射表 **DP:1446**） |
| 自依赖 | **DP:1017** / **DP:1637** | `cannot block itself` / `a team task cannot block itself` |
| 重复 blocker | **DP:1638** | `duplicate blocker "${id}"` |
| 任务数上限 | **DP:1470** | `Team task limit ${this.maxTasks} reached`（`TEAM_TASK_LIMIT`，默认 `256` = **DP:1670**） |
| 信箱去重语义 | **DPR:133** | `process-local retry plus target-Session de-duplication, not cross-process exactly-once delivery` |
| 去重边界（已知限制） | **DPR:210** | `Mailbox is not cross-process exactly-once — concurrent harness processes over one Team are unsupported.` |
| 名字/成员不可变 | **DPR:208** | `Flat immutable roster — only the Lead creates direct teammates; there is no nested Team, rename, deletion, or name reuse.` |
| 所有权不自动释放 | **DPR:209** | `No automatic ownership release — inactivity, interruption, process exit, and failed work do not release a task owner.` |
| 名字首次预留 | **DPR:129** | `Names are reserved by the first provisioning record and never reused.` |

### 9.5 复核旧结论：行号一致 ≠ 语义未变（实测判据）

**判据（保留原意）**：复核**以前写下的结论**时，只对行号会骗人。本轮实测（两代包都在磁盘上，见 §9.0 的 SA / SB）：

- **行号确实命中**：`TEAM_NOT_MEMBER` 的抛错行在**旧代与新代同为 `:389`** —— 原文 `if (membership === void 0) throw new TeamError(\`agent "${agent.id}" is not a member of an active Agent Team\`, "TEAM_NOT_MEMBER");`（旧代 `SA:389` ＝ 新代 `DP:389`）。
- **但因果链的末环已被上游删掉**：`team:policy` 段的 `text` 换代了。
  - 0.1.5-rc.2 = **闭包**：`text: () => {`（**SB:241**）+ `const membership = ctx.agentTeams.membership(agent);`（**SB:242**）—— 而 `membership()` 在成员不是 Team 成员时**会抛** `TEAM_NOT_MEMBER`。
  - 0.2.0-rc.2 = **静态字符串**：`text: POLICY`（**TP:240**，`POLICY` 定义 **TP:21**）；原先由闭包拼进去的身份行，改成 spawn 时注入初始 prompt 前缀（**TP:276–282**）。
- ⇒ **行号只是定位手段，不是证据**：复核旧断言至少要抓 **2~3 个白名单关键行原文片段**做逐字比对（本例白名单 = 抛错那行 + `team:policy` 的 `text:` 行 + 注册块），并且**前后各算一次 sha256**，两次相同（`changed=0`）才下结论；行号只用于**定位**，不用于**判变**。
- **复核期间文件本身会动**：多写手并发时行号会漂移 ⇒ 报行号**必须声明口径**（改前 / 改后）。原 §9.5 里"45 秒内 269 行长到 270 行"的实测记录本轮**无留存物可复算**（没有当时的副本 / 哈希），已删除。
- **报行号必须声明改前 / 改后口径**（实测）：插入 1 行后原 `:98` 变 `:99`，复核者按旧口径核会直接判"行号对不上"；本轮就是靠**声明口径**避免了 Lead 与写手之间的假冲突。

### 9.6 收尾清空台账（硬）

- 台账里每个"在跑"的成员必须收敛成 `done / partial / blocked / killed`，**没有第三条路**；收敛不了的写清"为什么留它跑"。
- kill 只按自己的 `target`（agent_id / job_id）精确杀，**不用 pid 快照差集**；进程与端口的清理纪律见 §7。
- 台账是**临时协作状态**：不进 skill、不进宪法，也不因此免掉 §4 的校验。该不该沉淀走 `sedimenting-skills`。

