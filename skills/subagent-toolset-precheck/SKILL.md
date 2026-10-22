---
name: subagent-toolset-precheck
description: 子代理工具集预检——子代理说没有 web_fetch、工具受限怎么办：派活前先让它如实回报函数清单，避免把联网调研或要求落盘的任务派给工具受限的 `explore` 子代理（2026-10-09 实测只拿到 glob/grep/read/subagent 4 个，无 web_search/web_fetch/pwsh/写文件工具），否则产出一堆"未验证"且交付文件落不了盘。适用于"子代理说没有 web_fetch / 子代理说工具受限 / 子代理回了一堆未验证条目 / 没生成交付文件 / 联网调研派给谁 / explore 和 subagent 怎么选 / 子代理到底有哪些工具"。不适用：拆解、派发、校验与上下文预算的通用编排规则 → 用 `orchestrating-subagents`；把跑通的流程写成 skill → 用 `sedimenting-skills`。
whenToUse: 当子任务需要联网、需要写文件落盘、或需要跑命令，而你要用 explore 类只读子代理下发时，先做工具集预检；子代理回报"工具受限/未验证/无法落盘"时按本 skill 改派 subagent。模型看不到本节。
---

# 子代理工具集预检

## 何时调用

- 触发信号（任一）：
  - 任务要**联网**（查官方来源、抓 REST API、核外部仓库/发布），或要**产出交付文件**，而你准备用 `explore` 下发。
  - 子代理收尾消息里出现："本会话无 web_search/web_fetch 工具""本会话无写文件工具""以下条目未直接验证，仅从工作区既有文件倒推"。
  - 子代理结论里出现批量 `未验证：` 条目，或它声称完成但**没有任何新文件落盘**。
- 转交边界：通用拆分/派发/校验/上下文预算 → 用 `orchestrating-subagents`；收尾沉淀判定与写 skill 流程 → 用 `sedimenting-skills`。
- 前置：能往子代理 prompt 里塞一段探测指令。 ／ 后继：确认工具集后再按 `orchestrating-subagents` 正式下发。

## 已知工具集差异（实测）

| 下发方式 | 子代理实际拿到的工具 | 关键缺失 |
|---|---|---|
| `explore` | **4 个**（2026-10-09 schema 探测实测）：glob / grep / read / subagent | 无 web_search、无 web_fetch、无 pwsh、无 write / edit、无 `skill` 工具；**`list_subagent_models` 不存在**（旧文记的 5 个已证伪） |
| `subagent` | 96 个（含 web_fetch / web_search / pwsh / write / `skill`） | 实测 `web_fetch` 抓 GitHub REST API 返回 HTTP 200 |

- **勘误（2026-10-09 schema 探测）**：本 skill 旧文记的"`explore` 拿到 5 个工具、含 `list_subagent_models`"**已被证伪**——`explore` 实测只有 **4 个**（glob / grep / read / subagent），`list_subagent_models` **不存在**。旧结论里"无 web_search / web_fetch / pwsh / 写文件工具"以及"立论：派活前先让子代理如实回报函数清单"**仍然成立**，只是工具数与 `list_subagent_models` 这一项作废。
- `explore` 子代理**可以**再往下派 `subagent`（嵌套），嵌套子代理能拿到完整工具集——这是补救路径，不是首选路径（多一跳、多一份上下文开销）。**风险提示**：`explore` 手里**有** `subagent` 工具 ⇒「只读子代理不会再派活」**只由 `maxDepth:1` 保证，不是工具面保证**。
- 未验证：上述 4 与 96 会随 DSH 版本、agent preset、toolFilter 变化；每次关键任务仍以本次探测回报为准，不要背数字。
- `explore` **没有** `skill` 工具 ⇒ 它**加载不了 skill**；要让它按某个 skill 干活，必须把绝对路径 `C:\Users\admin\.dsh\skills\<name>\SKILL.md` 写进 prompt 让它 `read`（规则、判据与兜底见 `orchestrating-subagents` §3.1）。

## 决定工具面的是「用哪个委派工具」，不（只）是「角色名」（2026-10-09 实证）

**机制事实**：`## 已知工具集差异` 那张表给的是**按角色推的默认基线**，**不是保证**。本轮血证：Lead 用 **`distill_skill`** 下发沉淀任务（`distill_skill` **不在**宪法 §4 第 8 条那四类表里），并在 prompt 里**明确写了**"你有完整工具集（含 `pwsh`）"——**这句广告是错的**：该子代理实际函数面是 `read` / `write` / `edit` / `grep` / `glob` / `skill` / `subagent`，**无 `pwsh`、无 `web_*`、无 `job_*`**。它没被广告带偏、直接报「无该能力」= **正确行为**；反倒是靠"角色名/prompt 广告"推工具面的做法被证伪。

**可操作的检查项（派活前照此过一遍）**：

1. **先定"这条任务依赖哪个工具"，再选通道**。只要依赖 `pwsh`（跑命令 / 算 sha256 / 量 `len(description)` / 真跑校验器）或 `web_*`，就**不许默认任何通道都有它**——包括 `distill_skill` 这类未入表的工具。
2. **禁止用"角色名"或"prompt 里的广告"推断工具面**。要求子代理**首步原样逐字抄回它自己的函数清单**（`## 步骤` 第 2 条的探测指令仍有效，且是唯一可信来源）。
3. **依赖 shell 的验收闸门，要么派给明确带 `pwsh` 的通道**（表内 `verify` / `implement` / `subagent`），**要么留在 Lead 侧自己跑**。本轮三项硬闸门（写前哈希 / 写后重读比对 / `len(description)` 实测）**全部由 Lead 兜底**——这是正解，不是将就。
4. **与宪法 §4 那张表的关系**：那张表是 **2026-10-09 探针的"当时基线"**，用途是**选通道的默认判断**；**"这次实际拿到了什么"必须当次核实**。两者不冲突——**基线 vs 当次实测**。**不要因为一次反例去改宪法里的 4 个数字**（那组数字本轮未被复核）；要改的是**纪律**：预检 + Lead 兜底。

**本轮反例的判定要点（可直接照抄进 prompt）**：

- 该子代理**拒的是"能力"不是"指令"**：它照常完成了写入、只把跑不了的测量如实标成"无该能力" ⇒ 属 `PARTIAL` 的成因②（角色约束/能力边界正确生效），**不是任务失败**，不要回炉重派，也不要要求它"再试一次"。
- 反过来说：**把测量类验收判据写在无 shell 通道的 prompt 里，等于制造一个注定 PARTIAL 的任务**。判据放 Lead 侧，或放表内带 `pwsh` 的通道。
- **`subagent`（工具）的有无与能否使用也必须当次核实，两件事分开记**：本轮 `distill_skill` 通道的函数清单逐字为 `edit` / `glob` / `grep` / `read` / `skill` / `subagent` / `write` ⇒ **带 `skill`、也带 `subagent`，但无 `pwsh`**；而它的 `subagent` 调用**被运行时深度限制拦下**：`Error: subagent depth 2 exceeds maxDepth 1`。⇒ **有工具 ≠ 能用**：**能力存在性**（工具在不在函数清单里）与**运行时限制**（`maxDepth=1` 拦深度 2）是两件不同的事，别混成一条去查错方向（`explore` 不带 `skill` 是宪法基线，**不能拿它去描述本通道**）。结论：**"是否注入 skill 目录 / 能否嵌套"不可跨通道外推，只能当基线，当次核实**。

## 步骤

1. 识别任务是否**依赖联网或落盘**：只要需要 web_fetch/web_search 或输出文件，就必须先做工具集预检。
   - 验证：任务描述里能圈出"查外部来源"或"交付文件路径"任一项。
2. 下探测指令（放进子代理 prompt 的【交付】段，二选一或都放）：
   - 形状 A（要求罗列）：`先回报你本会话可用的工具函数清单（逐个名称），并明确回答：是否有 web_fetch / web_search / pwsh / 写文件工具？没有就直说"无"，不要用其它方式代替。`
   - 形状 B（能力断言，更硬）：`在动任何检索之前，先尝试一次 web_fetch 抓 https://api.github.com/rate_limit 并回报 HTTP 状态码；若你没有 web_fetch 工具，直接回报"无 web_fetch 工具，停止执行"。`
   - 验证：回报里出现**逐条函数名**，且对缺哪个工具给了明确"无"；若只回"我尽量试试"即为不合格回报。
3. 按回报决定改派：出现任一关键缺失 → 同一个任务改用 `subagent` 重派（prompt 里带 web_fetch/web_search/write 的明确要求与目标文件路径）。
   - 验证：重派后的子代理能给出 HTTP 状态码、或目标文件真实出现在磁盘上。
4. 若已先用 `explore` 跑过一轮：把它产出的"未验证"条目当**线索**而非结论，改派 `subagent` 时要求**逐条给原始证据**（URL / HTTP 码 / 文件:行号）。
   - 验证：新回报里每条结论都带可核验的原始出处。

## 坑与修法

- 现象：两个 `explore` 子代理调研 MiniMax 官方来源，双双回报"本会话无 web_search/web_fetch/写文件工具"，只能从工作区既有文件倒推，产出大量"未直接验证"条目，且**无法落盘交付文件**；任务实质未完成。
  → 原因：`explore` 的工具面被裁到 4 个（glob / grep / read / subagent），天然做不了联网与写盘；派活时按"只读侦察"分类匹配了错误的角色。
  → 修法：同一任务改用 `subagent` 重派（`subagent` 子代理实测带 web_fetch/web_search/pwsh/write，`web_fetch` 抓 GitHub REST API 返回 HTTP 200），即解决。
- 现象：子代理回了一堆"未验证：…"但仍声明任务完成。
  → 原因：它没有能力验证，只在既有文件上做推断；"完成"指它写完了消息，不是任务达成。
  → 修法：不采信；不把此类条目并入交付。改派 `subagent` 重新取证，或降级为线索标注。
- 现象：以为"只读侦察一律用 `explore` 最省上下文"。
  → 原因：忽略了 `explore` 无 pwsh，也无法把中间产物写盘（上下文预算策略里"落盘只回路径"对它是死路）。
  → 修法：侦察任务**只在纯仓内检索**（glob/grep/read）时用 `explore`；一旦要联网、跑命令或落盘，直接用 `subagent` 并把只读约束写进【边界】。

## 不要做什么

- 不要把联网调研、外部来源核查、需要产出文件的活派给 `explore`——缺 web_fetch/web_search/write，必然退化成"从工作区文件倒推"。
- 不要让 `explore` 子代理"写个文件到磁盘"作为交付：它没有写文件工具，只会失败或改写结论。
- 不要靠猜测数字（4 / 96）代替当次探测回报。
- 不要用嵌套 `explore → subagent` 当常规方案；能用 `subagent` 一次下发就别多绕一跳。

## 验收标准

- 探测回报里能看到逐条函数名，并对 web_fetch/web_search/pwsh/写文件工具给出明确"有/无"。
- 依赖联网的任务由 `subagent` 执行，且回报里出现 HTTP 状态码或 API 原文片段。
- 要求落盘的任务，目标文件路径在磁盘上真实存在（`read` 或 `glob` 可确认）。
- 交付里不再出现批量"未直接验证"条目；每条结论都有原始出处。
