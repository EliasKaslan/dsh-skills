---
name: orchestrating-subagents
description: 编排手册——两通道模型：生产动作（读文件、跨模块检索、跑命令、联网、试错、写代码/文档、改配置）一律下发给子代理，主 Agent 保留全套工具、只做交付前独立复核（真跑验收命令、核"文件:行号"、读本体与 exit code）；判据权威出处是宪法 §2/§3，本 skill 只写操作配方。适用于"任务很大一次读不完 / 该不该派子代理 / 帮我并行跑几件事 / 上下文快满了 / 子代理说的对不对 / 它答错了要不要重派 / 怎么关掉自己起的进程 / 收尾清理能不能用 pid 差集 / 运行台账该怎么记 / 子代理写域重叠怎么办 / 等待子代理要等多久 / 长时间编译怎么等 / 目标文件被别的会话并发改怎么办 / 子代理说完成了我怎么验 / 验收判据该怎么写 / 复核旧结论行号一致算不算没过时 / 判据被证伪怎么办"。不适用：任务收尾判定"值得沉淀"、要动手写 skill → 用 `sedimenting-skills`。
whenToUse: 当你要编排子代理——生产全下发、主 Agent 只做交付前复核（判据见宪法 §2/§3）；或要并行推进 / 派只读代理反驳 / 并发时记台账、切写域（触发见 §9.1）。收尾沉淀不走这里，用 `sedimenting-skills`。模型看不到本节。
---

# 编排手册

## 何时调用

**加载本 skill 当：**
- 用户说"任务很大一次读不完""该不该派子代理""帮我并行跑几件事""上下文快满了"。
- 上下文预算信号：已用 ≥5 次工具调用还没收敛、预期单条工具结果 >8KB、要读 ≥3 个文件、要跑 ≥2 条命令——**这些数字只是"该收敛 / 该落盘"的提示，不是委派理由**；该不该委派只走下方的两通道模型。
- 子代理已返回，你要判断"它说的对不对 / 它答错了要不要重派"。
- 子代理给的证据是「文件与提交的 blob 逐字节相同」「几处 hash/md5 一致」这类**同一性声明**时（先看 §4 第 6 条）。
- 需要只读子代理去**反驳**一个已经拿到的结论。
- 预计跨多轮、或有 ≥3 个并行长任务（要记台账、切写域、收尾清空），或要判断"子代理说完成了到底算不算完成""等待要等多久"时（见 §9）。
- 要给子代理写【验收判据】时（**判据本身必须可独立复现**，别写自己估的区间，见 §9.7）。

**不要用本 skill（转交）：**
- 任务已收尾、要判定"这次做法值不值得沉淀"或动手写 skill → 用 `sedimenting-skills`。
- 只是单条命令 / 读 1~2 个小文件就能答 → **不是"自己做"的许可**：归属仍按两通道模型判（**用途**，不是工作量）——只有**审计动作**（核 `文件:行号`、读本体 / exit code、最小复验、取证与回滚）才允许主 Agent 自己动手；**"活儿小"不再是理由**，生产性的动作量再小也下发（判据见宪法 §2/§3）。
- 要的是跨多轮持续的目标跟踪（`create_goal`）而不是隔离上下文 → 按 `## 1.` 表格选工具。

**前置**：能写清【目标/边界/交付】三要素；写不清就先拆到自己能写清。 ／ **后继**：收尾时若流程可复用 → 转 `sedimenting-skills` 做沉淀判定。

## 两通道模型（判据的权威出处是宪法 §2/§3，本节只写操作配方）

**判据只有一份**：`~/.dsh/AGENTS.md` §2/§3 是权威出处，本 skill 不复制条文，只写"落到工具调用上怎么做"。判断只看一句：**这个动作是在生产，还是在复核？**（判据是**用途**，不是工作量——"我就顺手看一眼"不是理由。）

**通道一 · 生产（默认全部下发）**——一切**产生工作成果**的动作归子代理：

| 生产动作 | 典型形态 |
|---|---|
| 读文件 / 跨模块检索 / 定位调用链 | `read`、`glob`、`grep` |
| 跑命令 / 跑测试 / 试错 / 装环境 | `pwsh`、后台 job |
| 联网调研 / 抓页面 / 核外部事实 | `web_search`、`web_fetch` |
| 写代码 / 文档 / 改配置 / 生成产物 | `write`、`edit` |

**通道二 · 审计（主 Agent 唯一该自己动手的地方）**——主 Agent **保留全套工具**，用途只有一个：**交付前独立复核子代理的声明**。允许的动作（配方）：真跑一次验收命令、核 `文件:行号`、读交付物本体 / 日志 / **exit code**、最小复验（一条 grep、一次 read、一次 HTTP 探针）、取证与回滚（算哈希、还原备份）。

三条纪律：

1. **不可答即生产**：每次自用工具前必须能说出「我在复核谁的哪条声明」；说不出 → 那是生产动作，必须委派。
2. **审计只读不写**：唯一例外是回滚 / 还原备份，且**先备份**。
3. **查出不一致不许自己顺手修**：回炉给原子代理（`send_message`）或重派；自己修 = 既当运动员又当裁判。

**阈值不是触发条件**：`≥3 个文件 / ≥2 条命令 / ≥5 次工具调用未收敛` 这类数字**只是"该收敛 / 该落盘"的信号与预算提示**（落地位置见 §5），**一律不作为委派理由**。

**唯一仍要先问用户的例外**：用户可见的持久结构（新建服务 / 守护进程、改仓库配置、往共享目录写别人会依赖的东西）；判据是"别的会话 / 别的成员 / 用户会不会看到或依赖它"（宪法 §2 末段）。

## 1. 先分类，再决定派谁

| 子任务性质 | 用哪个工具 | 角色约束 |
|---|---|---|
| 只读侦察：定位代码、查调用链（**纯仓内 glob/grep/read**） | `explore`（若可用）否则 `subagent` | 只回情报，不回贴文件 |
| 要**联网**、要跑命令、要**落盘交付文件** | 必须 `subagent` | `explore` 实测只有 4 个工具（glob/grep/read/subagent），无 web_fetch/web_search/pwsh/write/edit/`skill` → 用 `subagent-toolset-precheck` 先探测 |
| 单模块改动 + 跑测试 | `implement`（若可用）否则 `subagent` | 给死边界：可写哪些路径 |
| 验证某个结论是否成立 | `verify`（若可用）否则 `subagent` | **只读**，任务就是"反驳它" |
| 对 N 个文件/条目做同一件事 | `workflow` | 每个 agent 独立上下文，结果结构化 |
| 每轮都要全新视角的迭代 | `ralph` | 上下文天然不累积 |
| 长目标跨多轮 | `create_goal` | 不是隔离，是持续 |

> 没有 `explore`/`implement`/`verify` 这些工具名时，用 `subagent` 并把角色约束写进 prompt 的【边界】里。
>
> `explore` 的工具面（2026-10-09 实测 schema，共 **4 个**）：`glob` / `grep` / `read` / `subagent`；**没有** `write` / `edit` / `pwsh` / `web_search` / `web_fetch` / `skill` / `list_subagent_models`。联网 / 跑命令 / 落盘一律用 `subagent`；**怕派错就先用 `subagent-toolset-precheck` 探一次**。
>
> **成本理由（换角色就省工具面）**：工具面字符量**实测**（2026-10-09；口径 = 会话日志 `request/header` 的 `$.data.header.tools`；脚本 `artifacts\orchestration-opt-2\20261009\toolface_cost.py`，复跑 `python toolface_cost.py --report`）：
> `explore`（4 工具）**2,993** ｜ `implement`（8 工具）**9,290** ｜ `subagent`（106 工具，其中 MCP 占 **53,419（72 个）**）**82,044**。
> ⇒ `subagent − implement = 82,044 − 9,290 = 72,754` 字符；再算上 skill 目录（`subagent` 注入 **32 条 / 15,436 字符**，**另外三角色实测均 0 条**）= **88,190**。
> `implement − explore = 9,290 − 2,993 = 6,297 = 6,293（新增 4 工具自身）+ 4（多出的逗号）` ⇒ **无同名工具变贵**。
> **三档落点**：只读侦察 → `explore`（2,993）；**写盘 / 跑命令 → `implement`（9,290）**；**只有需要联网或需要 MCP（GitHub / Outlook / Playwright）才落 `subagent`（82,044）**。
> （原先这里的 token 估算量**已删除**：本机无 tokenizer、测不到，估算不能当判据（`§9.7`）。工具面是**会话级不变量**——每会话只有 1 条 `header.tools` 记录，**不许写成"每轮付 82,044"**；"每轮重发"是**推断**（`dsh-agent-customization` §2.8），此处不据此计总成本。）
>
> **风险**：`explore` 手里**有** `subagent` 工具 ⇒「只读子代理不会再派活」**只由 `maxDepth:1` 保证，不是工具面保证**。
>
> **反例〔已实测证伪〕：`toolFilter.allow` 不能用来反推子代理工具面。** patch 里 explore 那行写的是 `allow: [read, glob, grep]`（**3 个**，生效件 `:238`），而 **2026-10-09 探针实测 explore 的工具面是 4 个**（多一个 `subagent`）；同日 **11:59 的备份**（`artifacts\backups\orchestration-opt-20261009\016__workspace__agent__dsh_base__artifacts__presets__orchestrator-bundle__cordis.patch.yml`，24,503 B，其 `:250` 同样只列 3 个）时期探针仍报 **4 个** ⇒ **两者不对应，已实测证伪**。判工具面只认 schema 探测（`subagent-toolset-precheck`），**不要读 patch 的 `allow`**。
> （机制上的**观察、非判据**：4 个已探角色都满足 `工具面 = allow ∪ {subagent}`——4=3+1、5=4+1、8=7+1 ⇒ `subagent` 疑似由 provider 在过滤**之后**注入。这只解释现象；**未经探测的角色不得据此断言工具面**。）

## 2. 拆解标准（不满足就别派）

一个子任务合格的标志：

- **可验收**：能用一句话说清"完成的样子"（文件存在？命令返回 0？输出含某个字段？）——**判据本身必须是可独立复现的量**（哈希 / 双向回放 / 真跑命令的退出码），**别用自己估出来的尺寸或行数区间**，见 §9.7
- **自包含**：子代理看不到主对话，凭这条 prompt 就能干
- **边界清晰**：读/写范围明确，与其它子任务**不重叠**
- **粒度合适**：1 个子代理 3~15 次工具调用能干完；更小就合并，更大就再拆

反模式：
- 「帮我总结我刚才读的内容」——主对话里已经有了，纯浪费
- 「看看这个项目」——没有验收标准
- 把同一个文件交给两个子代理去改——必冲突

**生产通道的边界**：判据与官方原话（含 `create teammates only when the user explicitly asks`）**见宪法 §2 末段**，本 skill 不重述——一句话：用户可见的持久结构仍要先问用户。

## 3. 委派 prompt 模板（直接套）

```text
【身份】你是被委派的子代理，我是你的 Lead；你的角色名是 <auditor / builder / verifier / ...>。
       你的返回必须严格按**宪法 §5** 的返回契约（首两行可机判；**返回契约的唯一正文在宪法 §5**，本 skill 不重述）。
【技能】开工前先 `skill <名字>` 加载本任务所需的 skill：<逗号分隔的名字>。加载不到就直说，不要凭记忆编流程（机制与判据见 §3.1）。
【你的工具面】<它能用哪些、不能用哪些（`explore` = glob/grep/read/subagent；`subagent` = 全套）；缺工具时报"无该能力"，不要绕、不要编、不要假装落盘>
【目标】<一句话，可验收：完成时应该看到什么>
【验收判据】<判它做没做成的**命令或事实**，如"某文件存在且含 X""某命令 exit=0""grep 到 N 行"——别只写"做好">
【已知】<路径 / 版本 / 约束 / 已确认结论；不要粘贴整段文件内容>
【写域】只允许写 <路径白名单>，其余一律只读；禁止 <改测试 / 提交 / 动别人的文件 / 改全局配置>
【交付】按**宪法 §5** 的返回契约输出（**唯一正文在宪法 §5**，本 skill 不重述）；要收紧 / 放宽行数或证据上限时，必须在本 prompt 里**显式写明**。
【失败】报错原文 + 已尝试方案 + 你的判断（环境问题还是方案问题）
```

独立子任务**在同一条消息里一起下发**，不要串行等。只有下一步动作依赖某个结果时才前台等待。
并行下发的子任务**写域必须互不相交**；有先后依赖的必须写明"先 A 后 B"，并把上游产物路径写进下游的【已知】（理由与做法见 §9）。

### 3.1 子代理的 skill 供给（它不会自己加载）

**实测事实（2026-10-09 本机，本轮亲自探针）**：`subagent` 子代理**有** `skill` 工具，其上下文里带**完整 skill 目录**（实测 32 条），`skill(name)` 实测返回完整正文（24932 B / 245 行）。

**`explore` 类只读子代理没有 `skill` 工具**：其工具面**已实测**（2026-10-09 schema 探测）= 4 个（`glob` / `grep` / `read` / `subagent`），确实没有 `skill` ⇒ 只能靠 prompt 给绝对路径让它 `read`。勘误：`subagent-toolset-precheck` 旧文记的"5 个只读工具、含 `list_subagent_models`"**已被该探测证伪**（`list_subagent_models` 不存在），现行值以本行为准。

**但子代理不会自己想到去加载**——它只看到目录里的一行 description，不加载就只有那一行。⇒ **委派 prompt 必须点名它要加载哪些 skill**（模板里的【技能】行就是干这个的）。

判据（可核验）：

- 合规：子代理回报里出现它加载过的 skill 名，或引用该 skill 的**具体章节锚点**（如「见 §3」「坑 5」）。
- 不合规：「我按 skill 做了」却不给名字；或引用了该 skill 里**不存在**的章节。
- 兜底（对没有 `skill` 工具的子代理）：把绝对路径写进 prompt 让它 `read`——`C:\Users\admin\.dsh\skills\<name>\SKILL.md`。
- 反模式：写「照着你的 skill 做」「按你了解的流程办」——子代理没有你的流程。

**已挂上这条供给线的 skill（8 个；新增/删除委派段时同步这张表）**：`ascend-env`（4 条 lane 各取对应子 skill）、`ascend-conda-env`、`ascend-model-adaptation-recon`、`ai-vendor-official-source-audit`、`upstream-docs-refresh-audit`、`github-org-delta-watch`、`dsh-skill-self-audit`、`sedimenting-skills`。

## 4. 结果校验（必做，子代理会自信地出错）

1. **抽查**：随机挑 1~2 个「文件:行号」，自己 `read` 确认存在且内容对得上
2. **复验关键结论**：用最小代价（一条 `grep`、一条命令）验证
3. **"已完成"必须有证据**：没看到命令输出/文件内容就不算完成
4. **对抗验证**：结论重要且可疑时，再派一个**只读**子代理，任务是"找出它错在哪、给反例"
5. **不一致就重派**：prompt 更具体、或换更窄的边界，而不是自己接手
6. **「文件与提交的 blob 逐字节相同」这类声明，先归一化行尾再比**：子代理常做「本地 `Get-FileHash` / `scp` 后远端 `md5sum` / 跑完再 `md5sum`，三处一致」就断言「实测文件与你提交的 blob 逐字节相同」——**三处 hash 一致只能证明传输无损，不能证明与 blob 同字节**。本机 `core.autocrlf=true` 时工作副本是 **CRLF**、git 库里存 **LF**，直接比 hash 必然不同；把工作副本的 CR 去掉后与 blob 逐字节相同（Python 按通用换行读，执行行为无差异）。判据：

   ```python
   blob = subprocess.run(["git", "cat-file", "blob", f"HEAD:{rel}"],
                         capture_output=True, check=True).stdout
   norm = disk.read_bytes().replace(b"\r\n", b"\n")     # 工作副本去掉 CR
   assert norm == blob and b"\r\n" not in blob          # 逐字节 == blob，且 blob 里无 CRLF
   ```

   推广：任何「远端实测文件 == 仓库内容」的断言都先统一行尾，**别拿 hash 相等代替字节同一性**。

## 5. 上下文预算

| 信号 | 动作 |
|---|---|
| 预期单条工具结果 >8KB | 改由子代理做，或落盘只回路径 |
| 子代理返回超 40 行 | 退回让它压缩；或只让它回文件路径 |
| 上下文 >60% | 停止新探索，只允许委派 + 汇总 |
| 已用 ≥5 次工具调用未收敛 | 预算提示：停下来重新拆解，别继续摸（**不是委派判据**，判据见上方「两通道模型」） |

主 Agent 的上下文里**只应该留下**：委派 prompt、子代理的结构化结论、你自己的最终交付物。

## 6. 失败处理顺序

1. 换更具体的 prompt 重派（补上它缺的【已知】）
2. 换角色重派（侦察失败 → 换成实现者去看）
3. 降级自己做，并记账（说明为什么委派失败）
4. 连续 2 次失败 → 停下来向用户报告卡点，不要空转

## 7. 收尾清理（共享机器上最容易伤人的一步）

**只按"自己的 pid / 端口"精确杀，绝不用"pid 快照差集"判身份。**

```bash
# 正确：认自己起的那一个进程（端口是起进程时自己选的）
PID=$(ss -ltnp | grep :<你选的端口> | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1); kill -TERM "$PID"
ss -ltnp | grep :<你选的端口> || echo "PORT RELEASED"
```

**血证（实测）**：用 `comm` 对「清理前 / 清理后」的 pid 快照求差集来判"哪些是我起的进程"，结果把**同机另一个子代理正在跑的 pytest** 判成新进程并 TERM 掉，破坏了它那一轮测试。逐字原文：`KILLED 217589 timeout 1800 python -m pytest -sv --color=no --durations=0 ...`。
→ 根因：`comm` **要求两个输入都已按字典序排序**，实际喂进去的是 `sort -n`（数值序）→ 差集错位、凭空多出不属于自己的 pid。**前提不满足时 `comm` 不报错，只给错结果**（同族的静默错结果见 `pwsh-on-windows`）。

纪律：

1. 起进程时**记下 pid / 端口**（写进文件），清理只认这份记录。
2. 收尾断言写成"**我那个端口 / pid 没了**"（`ss -ltnp | grep :<port>` 为空、`ps -p <pid>` 无输出），**不要**写成"没多出别的进程"。
3. 共享机上多个子代理并行时这条尤其致命：**你看到的"新"进程很可能正是别人的活**。
4. 真要按模式杀，用不自匹配的写法（`pkill -f "[t]est_x"`，机制见 `ascend-vllm-serve` 坑 16）；但 `pkill -f` 仍可能命中别人的命令行——能精确到 pid 就别用模式。

## 8. 证据而非断言（把"子代理可信"做成机制，而不是靠人品）

**核心判据（一句话）**：**子代理的汇报是"声明"，不是"证据"。** 一条声明要能验收，必须能还原成"**宿主自己算出来的、与子代理无关的量**"。

| 来源 | 算不算证据 | 为什么 |
|---|---|---|
| 子代理说"我写好了 `x.md`" | ❌ 声明 | 它可能记错、可能写的是另一个路径、可能根本没写 |
| 子代理贴的**它自己算的** md5 / sha256 | ❌❌ 双重声明 | 哈希是它算的 ⇒ 它写错文件时哈希也会"自洽"。**子代理给的哈希等于没给** |
| 子代理贴的命令原文 + 输出 + exit code | ⚠️ 半证据 | 可核对、可复跑，但**贴出来的**仍可能是拼接/裁剪的；只有**你能自己复跑**时才升级为证据 |
| **宿主（Lead / 框架）自己 `stat` + 读字节算出的 sha256** | ✅ 证据 | 与子代理的声明完全解耦 |
| **你亲自 `read` 到的文件内容 / 亲自复跑的命令输出（含 exit code）** | ✅ 证据 | 同上 |

**把这条落成机制（推荐做法）**：

1. **给子代理一个"只能问事实、不能自报事实"的校验工具**：参数是**路径清单**，由**宿主**去 `stat` + 读字节算哈希，返回 `{path, exists, bytes, sha256}`。子代理**无法**伪造这个返回值——它不经过子代理的手。
   - 路径必须**限定在工作区内**（拒绝绝对路径、盘符、`.`、`..`、空串），否则这个工具就是任意文件读取的放大器。
   - 大文件设**上限**，超限返回一个明确的错误 code，而不是把几 GB 读进内存。
   - 工具描述里要**明写**"这是宿主算的、可信；你自己贴的哈希不算"，否则模型会把两者等同。
2. **把"完成"做成有门禁的状态迁移**：任务带 `writeScopes` 时，标记完成**必须**附 `evidence_paths`；宿主收到后**自己**算哈希、把结果连同任务一起回写。分配了写盘范围却拿不出可核验的产出 ⇒ **拒绝完成**，且"缺证据"与"证据不存在"要有**两个可区分的错误 code**（分不开就没法修）。
   - 反例（别这么做）：让子代理在汇报里**编一段 JSON** 描述它改了什么——那是"自证"，等于把验收权交给被验收方。
3. **宿主算出的哈希要能被下一个人独立复现**：把 `sha256` 写进任务视图，Lead 用**另一条完全独立的路径**（自己的 `read` / `Get-FileHash` / `sha256sum`）再算一次对齐。**两条独立路径给出同一个哈希**才算闭环——**同一条路径算两次不算**。
4. **"一致性"不等于"同一性"**（§4.6 的行尾/哈希案例是同一族陷阱）：多来源 hash 互相一致只证明**传输/读取无损**，不证明它与某个上游 blob 逐字节相同；判"同一个文件"永远要**归一化后逐字节比**，别拿 hash 相等代替。
5. **证据不足时宁可阻塞**：门禁拦下来的"未完成"是**有用**信号；为了推进而放宽门禁，换来的是"看起来完成了"的假绿。

**边界（别把机制当万能）**：

- 哈希只能证明"**这个路径、这个时刻的字节**是这样"，**不能**证明"这个字节是想要的产物"——语义正确性仍要 Lead 读一遍。
- **没有按 agent 的改动归因可用**：workspace 变更事件按顶层会话统计、**跳过子代理会话**，shell 工具不产事件，`FsInfo.version` 是 stat 令牌而非内容哈希（机制与出处见 `dsh-agent-customization` 2.10 第 3 条）⇒ **"验它有没有越界写"做不到**，能做的只有"验它声称的产出是否存在、哈希如此"。
- 门禁只覆盖**走完成接口**的那条路；子代理在自己汇报里说"做完了"仍然只是声明——**验收永远在 Lead 这一侧**。
- 因此"鼓励多派子代理"和"绝对可信"**不矛盾**：把验收做成宿主侧的可复算机制，正是可以大胆派活的前提。

## 9. 台账与写域（团队化协作）

官方这套纪律的**唯一现行出处**是工具包里的**固定策略文本** `team:policy`，逐字可核：

- 四段正文：`const POLICY = \`…` 定义在 **TP:21 / TP:23 / TP:25 / TP:27**（段间空行 = TP:22 / TP:24 / TP:26）。
- 注册点：`register(scoped.systemPrompt.section({ … }))` = **TP:237–241**，其中 `name: "team:policy",` = **TP:238**、`text: POLICY` = **TP:240**。
- 官方自己把它描述成固定文本：`the fixed policy text`（TPR:94）、`One team:policy section on the member scope states the shared coordination rules`（TPR:99）。

**它自己不是约束**——这句**在 README，不在策略文本里**：`Prompt policy is coordination, not confinement — it cannot stop Bash or external processes from writing overlapping files.`（**TPR:146**）⇒ 所以下面每条纪律都配一个**我这一侧的可复算动作**，不能只写进 prompt 就算做了。

**工具 schema 对 Lead 与 teammate 完全相同，角色差异只在执行期**：`All nine Team schemas are identical for Leads and teammates; execution enforces Lead-only operations.`（**TPR:128**）；同一句的挂载说明 `every team member — the Lead and each teammate — gets the same nine tools plus the same coordination policy`（**TPR:28**）。

**本部署没有挂它**（可观测判据，不是官方原文）：两个在用 profile patch 里 `team` **0 命中** —— `C:\Users\admin\.dsh\profiles\web\cordis.patch.yml`（1778 B）、`C:\Users\admin\.dsh\profiles\headless\cordis.patch.yml`（350 B）。⇒ 本节只搬**与载体无关**的那部分；你用的是 `subagent` / `subagent_fork` / 后台 job 时它同样成立。

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

### 9.7 验收判据本身也必须"可独立复现"（被证伪时子代理该报证伪）

**实测教训**：Lead 给取证子代理写的验收判据是"备份文件字节数应在 **15000–23000 B**"——**这个区间是估的，不是实测的**，随后**被证伪**：真值 **12860 B**（该 skill 只被追加一节，那一节本身 **+8982 B** ⇒ 终值 22962 B）。子代理**拒绝为凑尺寸而填充内容**、如实**报了证伪**，处理正确。

⇒ **判据（可复用）**：

1. **验收判据只写"可独立复现的量"**：sha256（且要能被**另一条独立路径**再算一次）、**双向回放**（正向对写手自己实测的 `bytes`/`sha256`，反向把每一步 `edit` 的 old/new 依次回放到重建文本上、看能否复现改后状态）、**真跑命令的退出码 / 输出点名**。
2. **不要用自己估出来的区间当判据**：尺寸带（15000–23000 B）、行数带、"大概 N 处"这类**估值**会把**正确的交付误判为失败**，还会**诱导下一个人为凑数而改动内容**——判据从"验真"退化成"达标"。要带区间就带**实测出来的**区间，并写明它是哪次实测的结果。
3. **判据被证伪时，子代理应当报证伪，而不是迁就判据**：正确处置是停下、给出真值与证据、指明判据错在哪；**为满足判据去增删正文 / 凑字节数是作弊**，比判据本身错更严重。Lead 收到证伪后要**改判据**，不是改交付（重建旧版本的正反两向实测见 `dsh-agent-customization` 2.12）。
4. **改「被逐字注入所有 agent 的常驻文件」（`~/.dsh/AGENTS.md`）时，自校验要做成可复跑的断言脚本**：断言**按条目编号对齐**（一条断言对一个改法），并对**被证伪的旧断言加反向断言**——例：「`与磁盘实际变化对一遍` 必须已不存在」「`本机没有 PS7` 必须已不存在」。
   - 依据（实测）：收紧措辞后旧套断言先报 **3 个 FAIL**（`宿主自己算出的 sha256`→`宿主自算的 sha256`、`带上 -Encoding utf8`→`带 -Encoding utf8`、`必须走 Python 二进制读`→`一律走`）⇒ **只看"FAIL 数 = 0"会把"措辞变了"误判成"内容丢了"**；反向断言的价值是**同时证明"旧病已除"**，而不只是"新句子在"——这就是本节第 1 条「判据要可独立复现」的自用版。
5. **验收判据必须写在「结果本体」上，不能写在「实现细节」或 `exit code` 上**（本轮 F2 / F3 / F5 的共同母题）。反例三则（全部实测）：
   - ① **写在实现细节**：判据写成"必须传 `-YamlModule`，不传等于没验"，而实现改成**候选自动探测**后这句话当场变假 ⇒ **判据应写成输出里的 `YAML_SKIP=0`**。
   - ② **写在 `exit code`**：形状校验器**静默退化**（YAML 未验）时 `EXIT` **仍是 0** ⇒ 只看退出码会**假通过**；要读输出里的 `YAML_SKIP` / `FAIL` / `WARN` 计数。
   - ③ **写在状态名**：后台 job `finished` / 成员 `inactive` 都不代表成功，要读**结果本体**（判据见 §9.4「状态 ≠ 成果」）。
   - 一句话版：**"能不能验过"要能直接从产物上读出来**（哈希 / 逐字节比对 / 计数 / 输出里的关键字段），**不能依赖"某个开关被打开过"或"进程结束了"**。
   - 推论：**写进常驻注入文件的断言，一旦它依赖的实现改变就会变假** ⇒ 判据要么**锚在产物**上，要么**改实现时同步搜一遍引用它的文字**（与上一条 `反向断言` 同族）。

### 9.8 破坏性操作与回滚路径（稳定性；宪法 §9 把这几条落到这里）

- **破坏性操作先确认再执行**：删文件 / 强推 / 改全局配置这类动作，**先说清怎么撤、再动手**；改的是**自己正跑在里面的环境**（本会话的宪法 / skill / preset 行 / patch）时尤其如此——改坏了连取证与回滚都做不了。
- **改之前先想好回滚路径**：副本 + 记 sha256（做法见 §9.3 末）+ 能一句话说清"怎么撤"。**没有回滚路径就别开始**。
- **失败如实报告**：报错原文 + 已尝试方案 + 判断（环境问题还是方案问题）；**不许把"没验证"说成"已完成"**（判据见 §9.4「状态 ≠ 成果」）。

### 9.9 派发前先读目标句：「只读」是标签，目标句才是判据（写域）

**事故（实测）**：Lead 给一条**标注为只读**的复核 lane 下发的目标是「确保两仓都在目标 commit 上、工作树干净」——

**这句话只能靠写来满足**。结果一条 `git checkout` 级别的操作在 `16:45:23` 重写了一棵工作树，并在**同一秒**移动了 `.git/HEAD`，
把**另一条 lane 已完成的 strip 改动整个抹掉**（跨 lane 破坏，两名写手都不知情）。

取证依据（判"同一秒"是**排除法**用的）：被重写的 `requirements.txt` mtime `16:45:23.508944490`、`pyproject.toml` `16:45:23.507944490`、
`.git/HEAD` `16:45:23.667944497`；`git reflog` 里 `checkout: moving from master to FETCH_HEAD`。
**排除法**：`git add -A` + `git write-tree` **既不碰工作树文件、也不碰 `.git/HEAD`** ⇒ 可排除"只是写 index"的嫌疑；
而被怀疑的那条 lane 脚本里**零个破坏性 git 动词** ⇒ **根因是 Lead 自己的派发设计，不是子代理越界。**

**派发前逐字问一句：「这句话能不能只靠读满足？」** 不能 ⇒ 两种改法（二选一，别含糊）：

1. **把目标改写成只读可判的形式**：「**报告** X 的值」/「**报告**工作树是否干净」，而不是「**确保** X」/「**确保**干净」；
2. **或者明确给它写域**——但那就不是只读 lane 了，写域按 §9.2 切，且**必须与其它 lane 的"收尾对齐"类动作排他**。

- **红线动词**：复核类 lane 的目标句里出现「**确保 / 保证 / 修正 / 对齐到 / 清理**」= 该 lane 实际带写，**标签写"只读"不解决问题**。
- **加剧因素**：多条 lane 的写域**名义上互不相交，但"收尾对齐"类目标会跨域**（对齐到某个 commit / 统一格式 / 清理临时产物都是全域动作）
  ⇒ 与 §9.2「写域是纪律，不是锁」同源：**约定拦不住它，只有改目标句才拦得住**。

### 9.10 验收要有 before 基线（负对照），否则"通过"无法与"本来就对"区分（验收）

**实测（装 vllm-ascend 前后各跑同一层 8 项探针，逐项看是否翻转）**：

```text
PLUGIN_EPS            : []                                            → [('ascend','vllm_ascend:register')]
RESOLVED_QUALNAME     : vllm.platforms.interface.UnspecifiedPlatform  → vllm_ascend.platform.NPUPlatform
CURRENT_PLATFORM_TYPE : UnspecifiedPlatform                           → NPUPlatform
ENUM                  : PlatformEnum.UNSPECIFIED                      → PlatformEnum.OOT
DEVICE_NAME           : None                                          → 'npu'
DEVICE_TYPE           : ''                                            → 'npu'
VLLM_TARGET_DEVICE    : <unset>                                       → <unset>（必须保持 unset）
import vllm_ascend    : ModuleNotFoundError                           → 正常
```

⇒ **凡"装完应该变成 X"的验收，动手前先跑一次同样的探针并落盘**，事后**逐项对照**（哪几项翻转、哪几项**必须不变**——
上表最后两项就是负对照）。**没有 before 基线，你无法区分"我的改动生效了"和"它本来就是这样"**；
只有 after 的"8 项全对"与"8 项本来就对"在报告上长得一模一样。

**配套配方 · 承载 shell 对照（证明环境是交付脚本给的，不是残留环境蒙的）**：终审时用
`env -i HOME=/root TERM=xterm bash <脚本>` **清空一切再跑**，并**同时**报出"未 source 时的 `python` 是谁"。
实测：未 source 时 `command -v python` = 共享 conda base 的 python，`source` 交付脚本后才变成目标环境的 python
⇒ 两步一起报，才证明是**交付脚本**把环境给出来的。

### 9.11 A/B 实验要先确认单一变量真的起作用，且失败点就是被测的那一环（实验设计）

**反面教材（实测）**：想验"某个 `compat_lib` 是否修好了 `GLIBCXX_3.4.26` 缺失"，做了一个 dlopen A/B ——
**四个臂全部同样死掉**：该库还需要 CANN 的兄弟库（`libnnopbase.so` / `libexe_graph.so` / `libregister.so`），
**没 `source set_env.sh` 时四个臂都死在更早的地方** ⇒ **A/B 不可区分，实验无效**（看输出会得出"加了 compat 也没用"的假结论）。
只有先 `source set_env.sh` 之后，才拿到**干净判别器**：A（无 compat）→ `version 'GLIBCXX_3.4.26' not found`；B（有 compat）→ `DLOPEN_OK`。

**跑 A/B 前问两句，答不出 ⇒ 实验作废，别下结论**：

1. 两个臂**唯一**的差别，是我要测的那个变量吗？（本例：四臂**同样**缺兄弟库 ⇒ 变量不唯一）
2. **失败点**是不是就是我要测的那一环？（本例：死点比被测环节更早 ⇒ 测的是别的东西）

**同族教训 · 空结果不是结论**：`os.execv` 重入**不会 flush** Python 的 stdout 缓冲（过管道时是块缓冲）⇒ 结果是空输出。
**空输出不是"没问题"的证据**：先证明探针本身能出结果（同族母题 = §9.7「判据必须写在结果本体上」）。

### 9.12 别用会自相矛盾的分母当进度 / 工期判据（进度判据）

**实测**：想判"算子编译到哪了"。候选分母**互相矛盾**——

- 按 **C++ 源文件数**（1631 个）算 ⇒ 约 **82%**；
- 按 **`op_*` 目录数**（128 个，其中只有 **1** 个生成了 `kernel_meta`）算 ⇒ 约 **0.8%**。

而 `.o` 计数（1421）被 `build/binary/ascend910_93/gen/kernel_meta_<Op>_<hash>/` 的**实例**淹没，
**根本不是线性进度信号**。**两个候选分母差两个数量级 ⇒ 两个都不能用。**

**Lead 的处置 = 拒绝给 ETA**，改用**该流程的确定性产物 oracle**：
`csrc/build/cann-ops-transformer-custom_linux-x86_64.run` 存在 ⇒ `--target package` 阶段**确已完成**（该阶段的 CRITICAL 产物）；
再配合"编译器进程数归零（`bisheng` / `opc.py` = 0）"。⇒ 判据锚在**产物 + 归零的计数**上，不锚在"百分比"上（同族：§9.7）。

**配方**：当两个候选分母给出差两个数量级的答案时，**两个都不能用**；去找流程的**确定性产物**
（一个只在成功时出现的文件 / 一个只在结束时归零的进程计数）。

**同族教训 · 自算量必须交叉验证**：`unzip -l` 的列做目录求和会得出 **552 MB**，实际安装的 `_C` 只有 **159 MB**
⇒ 别用 `unzip -l` 的列做求和，用 Python `zipfile` 逐条求和。
另一条：pip 的 `Building editable ... still running...` 是 **spinner**，子进程输出**不流式回传**
⇒ **日志不增长 ≠ 卡住**，要判进度只能看**文件系统产物**。

### 9.13 备份名单从「写域并集」推导，下发前后各 diff 一次（写域）

**时机纪律**（`§9.3` 已定"派活之前就存"，本节点**名单怎么来**）：**备份名单 = 本次已下发的所有 prompt 写域的并集**——
**不是"我先想起来的清单"**。写域是在**写 prompt 的过程中逐步长出来的** ⇒ **备份动作必须放在"最后一条 prompt 定稿之后、派发之前"**。

**Lead 侧事故（实测）**：先写好一份**4 个文件**的备份名单，**之后才**把**第 5 个**文件 `ascend-server-layout` 加进某条 prompt 的写域。结果：

- 第 5 个文件**没有改前备份**（`Test-Path` 为 **False**）；
- 快照源里也没有它（`D:\repos\deepseek-harness` 里搜不到该文件）；
- ⇒ 那份改动**永久失去可差分的前态**，只能退而做**结构核验**（frontmatter 三键完整、标题树完整、无连续重复长行、被要求保留的原句确实还在）——
  **"零丢失"这个结论永远拿不到**，且**漏备造成的缺口是不可逆的**（不是"验得不够"，是"没得可验"）。

**配方（两条，缺一不可）**：

1. **下发前显式列名单**：把各 prompt 的写域**逐条枚举**成路径清单，**别只写目录**——写目录时**不存在的文件不会被点名**，漏的正是第 5 个这种"写域里新加、转眼就忘"的条目。
2. **下发前后各 diff 一次，差集必须为空**。**三条硬要求**：① `$bak` 必须指向**真实写过的落点**（本仓两处实测：`<cwd>\.dsh-run\backups\` 与 `artifacts\backups\`），**不许留一个未核对的前缀当示例**；② **diff 之前先加"glob 匹配到东西"的护栏**；③ 比对按**类名**（`SKILL.md` 取**父目录名**，其它取文件名去扩展名），**别拿 `SKILL.md` 当名字**——备份名是基于**类名**的：

   ```powershell
   $bakDirs = @((Join-Path (Get-Location).Path '.dsh-run\backups'), 'D:\workspace\agent\dsh_base\artifacts\backups')  # 换成你真实写过的落点
   $scope   = @('<写域并集：逐条完整路径>')                                    # 各 prompt 写域并集（逐条路径，不写目录）
   $bakNames = @(); foreach ($d in $bakDirs) { foreach ($o in (Get-ChildItem ($d + '\*.bak') -EA SilentlyContinue)) { $bakNames += $o.Name } }

   # 护栏：glob 没匹配到 ⇒ 这不是"全都没备份"，别下结论（否则 $bak 为空会把每个写域文件都报成漏备）
   if (@($bakNames).Count -eq 0) { Write-Host "GLOB_MATCHED_NOTHING - 别下结论，先修 glob/落点"; return }

   foreach ($f in $scope) {
     $cls = if ($f -like '*\SKILL.md') { Split-Path -Leaf (Split-Path -Parent $f) } else { $f -replace '.*\\','' -replace '\.[^.]+$','' }
     $hit = 0; foreach ($b in $bakNames) { if ($b.StartsWith($cls)) { $hit++ } }
     if ($hit -eq 0) { "LEAK: $f  (class=$cls 无任何 .bak)" }        # 无输出 = 差集为空 = 可以派发
   }
   ```

   - **「`$bak` 为空」与「写域漏备」是两件事**：两者都表现为"有输出"，不加护栏时前者被静默显示成后者（每次假警报 ⇒ 判据失效，比没有配方更坏）。
   - **判据要能区分"glob 没匹配到"与"真的漏备"**：前者走 `GLOB_MATCHED_NOTHING` 分支、后者走 `LEAK:` 分支。
   - **前缀判据的前提**：备份名以**源文件类名**开头（本仓三种命名都满足：`<类名>.<日期>.bak`、`<类名>.POST-EDIT-<日期>.bak`、`<类名>.SKILL.md.pre-<日期>.bak`）。**契约不同就得改判据**，否则会报假漏备。
   - **实测（本机）**：`orchestrating-subagents` hits=2、`pwsh-on-windows` hits=1、`sedimenting-skills` hits=0（真漏备，与事故记录一致）；用 `SKILL.md` 当名字则**全部 hits=0**（假警报）。

**只记字节数 + sha256 不算备份**：那是**回滚判据的下限**，**不是"能差分"的前提**（同族：`§9.7` 禁止拿估量当判据；`§9.8`"没有回滚路径就别开始"）。
**不要指望子代理替你留副本**：本轮实测，子代理在**没有池外写权限**时不会自己留，它明确报告"**未落备份副本，写域只授权这两个文件**"
——**这正是把备份责任放在 Lead 侧的理由**（它只对自己的写域负责，看不见别的 lane 的写域）。

### 9.14 让改文件者做「撤回式闭包」，把"除申报的改动外逐字节未变"变成可复算的等式（范围证明）

**本节点是 `§9.13` 第 2 条那个 diff 步骤的加强版**（分工单一：`§9.13` 管**备份名单怎么从写域并集推导**，本节点管**改完之后怎么证明改动范围**）。

**先看现有 diff 有多弱（本轮实测口径）**：
`Compare-Object -ReferenceObject $bak -DifferenceObject $new | Where-Object { $_.SideIndicator -eq '<=' -and $_.InputObject.Trim().Length -gt 25 }`
—— **`-gt 25` 只证明"没有长行消失"**，看不见 **① 短行的改动**（被长度阈值滤掉）、**② 行重排**、**③ 纯空白 / 行尾改动**、**④ 一行内改一个字符**（整行只是一个元素，"改一处"与"整行重写"在差集里长得一样）⇒ **那是必要条件，不是充分条件。**

**更强的做法 = 撤回式闭包（reverse-apply closure）**——**机理与配方单一归属在 `dsh-skill-authoring` §8 oracle 5，本节点只写编排侧判据**：让**改文件的那个子代理**把它**自己申报的每一处改动按逆序**换回旧文本，重建结果与**改前基线**逐字节比对 ⇒ **能重建出与基线逐字相同的 sha256，就反证"除申报的这几处外全文逐字节未变"**。

**实测（本轮，可直接引用）**：子代理 `sediment-remote-channel` 申报改了 `ascend-env/SKILL.md` 的 **4 处**；按逆序把这 4 处换回旧文本后重建 = **`37745 B` / sha256 `de13e9e1fbd11cdd8c7d22dca527cca5a1b50356b009e939bcbcf514a1b068e4`**，**与改前基线逐字相同**；最终文件 = **`40301 B` / `68c9430428d4f2b0f83be45431ddbeb625faf5cf27fe62cf57b8fbc61ca54815`**，Lead 独立复核：**无 BOM**、`lf=257` 而基线 `lf=250`（**纯增 7 行**）⇒ 它把「我只改了这 4 处」从**散文**变成了**可复算的等式**。

**四条判据**：

1. **强在哪**：diff 证"**没有东西消失**"，闭包证"**除申报的这几处，全文逐字节相等**"——后者是**充分**的（前提：申报清单完整）。
2. **必须按逆序（后 → 前）施加逆变换**：否则**前后相邻 / 内容重叠**的替换会互相错位（换回前一处时，锚点已被它后面那处的新文本污染）⇒ 一步都重建不出来，并被误判成"有未申报改动"。
3. **失败本身就是信号——这是本条最有价值的用途**：**重建不出来 = 有未申报的改动**（少报一处就闭合不了）⇒ Lead 拿到"闭包失败"要**回炉要它补全申报清单**，不许当成"工具不灵"放过。
4. **★ 它是生产者侧自证，不能替代 Lead 的独立核验**：闭包**依赖改文件者的自我申报**（少报一处就重建不出来，但"能重建"这件事本身仍要与磁盘上的最终哈希对上）⇒ Lead **仍必须自己**算**最终文件的 sha256**、并 **grep 申报的新锚点是否真在**（两条命令本轮都实跑过）：

   ```powershell
   $p = 'C:\Users\admin\.dsh\skills\ascend-env\SKILL.md'
   $b = [System.IO.File]::ReadAllBytes($p); "bytes=$($b.Length)"; (Get-FileHash -Algorithm SHA256 $p).Hash.ToLower()
   Select-String -Path $p -SimpleMatch -Pattern '<申报的新锚点原文>' | Select-Object LineNumber, Line
   ```

   **不要把闭包当终审**（同族：`§9.7` 判据要写在结果本体上；`§9.4` 状态 ≠ 成果）。

**它反向加强了 `§9.13` 的备份纪律**：逆变换要用的**旧文本**由 `edit` 发给改文件者的 `old_string` 提供（所以它**有能力**重建），但"**重建得对不对**"只能拿**改前基线的 bytes / sha256** 来判 ⇒ **没有基线记录，闭包无从验收**。**适用面**：任何**申报为"最小改动"**的编辑（改 skill、改配置、改代码）；**不适用**于整体重写、生成式写入（没有离散的 (new, old) 对可逆）。它也**不替代 `§9.13` 的备份**——备份管**回滚**，闭包只管**范围证明**。

### 9.15 审计纪律：受限深度的空结果不证"不存在"；目录名与他人标签不证"是什么"

**两条都属"读错了证据"**：结论本身可能碰巧是对的，但支撑它的东西不成立（同族母题：`§9.7` 判据要写在结果本体上、`§9.11` 空结果不是结论）。

**① 受限深度 `find` 的空结果，不能支撑"某包不存在 / 装不上"**

- 实测：`find /mnt/share/vllm/conda_envs/xmz_0921 -maxdepth 6 -name 'fla_npu*'` → **空**，据此**差点判定**"这台机器上没有这个包（因此装不了）"。
- 真相：目标在第 **7** 层（`…/lib/python3.12/site-packages/fla_npu`）。改 `-maxdepth 8` 后**仍为空**（本例那台机器确实没装，结论碰巧对），但**"空"这个结果当时是不可信的** ⇒ **证据不成立**。
- 修法：在 `site-packages` 下找包**直接列路径**，别用受限深度 `find`：
  ```bash
  ls -d <env>/lib/python3*/site-packages/<name>*      # 判存在
  ```
  或把 `-maxdepth` 放到 **8+**。**不要**拿受限深度的 `find` 空结果去支撑"不存在"。
- 同族（本机侧，正文归 `pwsh-on-windows` 陷阱表「目录"看着空"其实不空」行）：`Get-ChildItem <dir> -File`（**不递归**）对"文件全在子目录"的目录回**空数组且不报错**。⇒ **共性判据：判"没有"之前，必须先证明"找过了、且找的深度够"**。

**② 目录名 / 上级报告 / 别的子代理的标签，都不是"某目录是 X 的产物"的证据**

- 实测：上游子代理报告"`/home/vllm/prune_run/` 是 Kimi-K3 减层 dummy 产物"，实际挖下去是**另一个模型**（Qwen3-30B-A3B）。
- 支撑真相的**硬证据只有文件内写死的东西**：
  - `mk_models.sh:7`、`split_weights.py:53`、`mk_split_model.py:100` 三处**都写死** `SRC=/mnt/weight/Qwen3-30B-A3B`；
  - `evidence_pilot.txt:19` = `Resolved architecture: Qwen3MoeForCausalLM`（**运行时打印**，比任何标签都硬）；
  - `PILOT_REPORT.md:1` 标题自述。
- ⇒ **可复用纪律**：验收"某目录是 X 的产物"这类**定性声明**，必须回到**文件内的硬证据**——脚本里写死的路径 / 源、`Resolved architecture:` 这类运行时打印、配置里写死的模型名。**目录名、上级报告的说法、别的子代理的标签都不算证据**：三者都可任意命名 / 误标，且它们本身就是**待验声明**（`§8`：子代理的汇报是声明，不是证据）。

### 9.16 目标轮次 ≠ 墙钟：长任务要等"barrier 标记"，别空转轮次（等待配方）

**实测事实**：goal round 的推进与远端墙钟**完全脱钩**——两个 round 之间远端只过 **~1 分钟**，而一次 AscendC 编译要 **24 分钟** ⇒ **靠空转轮次等长任务，等不来进度**（轮次照跑、远端没往前）。

- **做法：在 Lead 自己的 turn 里轮询等待 barrier 标记文件**（远端如 `log/S3_DONE`），把"round 数"换成"墙钟时间"——一次 turn 里可以连续探测多次，比"每轮回来重新判断一次"省得多。
- **长命令超过执行器上限会**自动**转后台 job**：别以为它失败了；用 `job_output(<id>, wait:true)` 继续等。等待期间照常推进**不依赖它**的独立步骤，但**别重复起同一个 job**（已受理的任务不重发，同 `§9.4`）。
- **判据要读标记文件本体**：判"这一步完了没有"只认**那个文件存在 + 内容**（`ls -l` / `cat` 标记本身），**不认** `finished` 这类状态名、也不认"上一步说成功"（同 `§9.4` 状态≠成果、`§9.7` 判据要落在结果本体）。
- **为什么不能靠轮次**：轮次是**会话推进**的单位，不是**远端时间**的单位；两者不同步时，"再等一轮"可能只对应远端 1 分钟。

### 9.17 被复验方可能还在编辑时：只审计"快照"，并用 md5 闸门拦下中间态（并发写手）

**实测**：被复验方在 **25 分钟内保存目标文件 4 次**（**23500 → 24842 B**）⇒ 直接审计"它现在的版本"= 审计一个**移动靶**：你验的和它改的**不是同一份**；更糟的是你的推送可能**覆盖它正在写的版本**。

- **固定顺序**：**等待稳定**（连续两次取到同一 md5 / 大小不再涨）→ **取快照**（复制到独立路径）→ **记快照 md5** → **只审计并只运行这份快照**。
- **md5 闸门**：每次推送 / 执行前重新取一次目标文件 md5，与快照 md5 不等就**停**——本轮用这条闸门**拦下 2 次中间态推送**。
- **不要覆盖、也不要删除与自己版本不同的并发产物**：改用**新目录**锁存自己那份（本轮用 `/tmp/fv2_lock/`），对方原文件一并留着 ⇒ 冲突留给双方，不留给运气（同 `§9.13` 备份纪律：池外文件没有自动回滚源）。
- **交付物里写清审计的是哪个 md5 的快照**——否则结论无法与"哪一版"绑定（同 `§9.7` 判据必须可独立复现）。跨平台推送通道细节见 `ascend-env` §5。
