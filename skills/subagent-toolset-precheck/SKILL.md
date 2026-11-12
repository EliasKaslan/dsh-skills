---
name: subagent-toolset-precheck
description: 子代理工具集预检——子代理说没有 web_fetch、工具受限怎么办：派活前先让它如实回报函数清单，避免把联网调研或要求落盘的任务派给工具受限的 `explore` 子代理（实测只拿到 glob/grep/list_subagent_models/read/subagent 5 个，无 web_search/web_fetch/pwsh/write），否则产出一堆"未验证"且交付文件落不了盘。适用于"子代理说没有 web_fetch / 子代理说工具受限 / 子代理回了一堆未验证条目 / 没生成交付文件 / 联网调研派给谁 / explore 和 subagent 怎么选 / 子代理到底有哪些工具"。不适用：拆解、派发、校验与上下文预算的通用编排规则 → 用 `orchestrating-subagents`；把跑通的流程写成 skill → 用 `sedimenting-skills`。
whenToUse: 当子任务需要联网、需要写文件落盘、或需要跑命令，而你要用 explore 类只读子代理下发时，先做工具集预检；子代理回报"工具受限/未验证/无法落盘"时按本 skill 改派 subagent。
disable-model-invocation: true
warm-triggers: 子代理工具受限 / 让它回报函数清单
warm-reason: 低频小技巧，已并入编排知识
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
| `explore` | 5 个：glob / grep / list_subagent_models / read / subagent | 无 web_search、无 web_fetch、无 pwsh、无写文件工具 |
| `subagent` | 96 个（含 web_fetch / web_search / pwsh / write） | 实测 `web_fetch` 抓 GitHub REST API 返回 HTTP 200 |

- `list_subagent_models` 在两种下发的子代理里都在，可用来回报"自己有哪些模型路由"，**不代表**有联网/写盘能力。
- `explore` 子代理**可以**再往下派 `subagent`（嵌套），嵌套子代理能拿到完整工具集——这是补救路径，不是首选路径（多一跳、多一份上下文开销）。
- 未验证：上述 5 与 96 会随 DSH 版本、agent preset、toolFilter 变化；每次关键任务仍以本次探测回报为准，不要背数字。

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
  → 原因：`explore` 的工具面被裁到 5 个只读工具，天然做不了联网与写盘；派活时按"只读侦察"分类匹配了错误的角色。
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
- 不要靠猜测数字（5 / 96）代替当次探测回报。
- 不要用嵌套 `explore → subagent` 当常规方案；能用 `subagent` 一次下发就别多绕一跳。

## 验收标准

- 探测回报里能看到逐条函数名，并对 web_fetch/web_search/pwsh/写文件工具给出明确"有/无"。
- 依赖联网的任务由 `subagent` 执行，且回报里出现 HTTP 状态码或 API 原文片段。
- 要求落盘的任务，目标文件路径在磁盘上真实存在（`read` 或 `glob` 可确认）。
- 交付里不再出现批量"未直接验证"条目；每条结论都有原始出处。
