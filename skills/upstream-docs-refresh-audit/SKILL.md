---
name: upstream-docs-refresh-audit
description: 上游开源仓库 docs 刷新审计（实测 vllm-project/vllm-ascend main）——输入一批中文内部需求或中文转测文档，判 docs/source 是否需要刷新，产出六节结论清单 + 逐条刷新方案：三件前置产物先行、只读 worktree 隔离、代号靠 git log --grep 破解、页名看 nav_titles.py、判存在性搜全仓、findings 落盘 fan-out、分次写盘、`.po` 翻译归责与脚本存在性判据。适用于"这批需求在 docs 里都能检索到吗 / 转测文档声明的能力主线能查到吗 / 这版主线资料要不要刷新 / 出一份资料刷新清单 / 内部代号在仓库里到底叫什么 / 转测文档写的环境变量和启动参数主线到底有没有 / 要不要顺手改 .po 翻译 / 那个脚本到底存不存在"。不适用：要装 vllm 或 vllm-ascend → 用 `vllm-ascend-source-install`；要起服务跑推理 → 用 `ascend-vllm-serve`。
whenToUse: 手里有内部需求或转测文档，要判上游仓库 main 的 docs 缺口并产出刷新清单时用；只是要装或跑 vllm 请转 ascend 系列。模型看不到本节。
---

# 需求资料刷新审计（内部需求 / 转测文档 ↔ 上游仓库 docs）

实测环境：Windows + pwsh + DSH，2026-09-28，vllm-project/vllm-ascend main@`18d0537d9`（第二轮复跑时远端已前进到 `f18d103838b8`，见步骤 1），12 条需求 / 13 个子代理。第二轮（同日下午）外部输入换成 12 份中文转测文档 `D:\workspace\260928_vllm资料确认\转测文档_2026Q3\*.txt`（约 165KB，最大一份 50KB），交付 `vllm-ascend主线资料刷新清单_v2_转测文档校核.md`（336 行）。第三轮（2026-09-28 复跑，基线前进到 `233adfea55c565260345311845811237d726c2f2`）新增三件前置产物（`keywords.md` 162 行 / `codename_map.md` 171 行 / `existence_audit.md` 496 行）、汇总分 3 次写盘协议与 5 处 findings 互相矛盾的复核实证，交付 `vllm-ascend主线资料刷新清单_2026Q3转测校核.md`（317 行，六节）。

## 何时调用

**加载本 skill 当：**

- 一批已完成的中文内部需求（含内部代号），要判定某上游仓库 main 的 docs 是否需要刷新。
- 需要「结论清单 + 逐条刷新方案」这种可交付物，而不是自己直接改文档。
- 定期核查「需求说的能力，用户能不能在单一文档页检索到」。
- 要判 `.po` 中文翻译该不该跟着改，或某脚本存不存在 / 会不会在 PR 上跑（链路与触发条件见步骤 4d）。

**不要用本 skill（转交）：**
- 要装 vllm / vllm-ascend（源码配对安装、算子编译） → 用 `vllm-ascend-source-install`。
- 要起 OpenAI 服务、跑离线推理冒烟、挑卡挑端口或排运行时故障 → 用 `ascend-vllm-serve`。
- 只做论文精读 + 开源声称独立核查 → 用 `arxiv-paper-deep-read-and-claim-verification`。
- 判某模型在昇腾侧的适配程度与未闭合缺口 → 用 `ascend-model-adaptation-recon`。

**前置**：有该仓库的只读副本（detached worktree 或本地 checkout，且 `git status --porcelain` 为 0 行）+ 需求或转测文档原件。 ／ **后继**：按刷新清单决定是否改 docs —— 改文档不在本 skill 范围内。

## 前置检查

代码副本：`D:\workspace\code\vllm-code\vllm-ascend_main`（fork，origin=EliasKaslan/vllm-ascend_k3，upstream=vllm-project/vllm-ascend，detached HEAD）。先摸清状态：

```powershell
git log -1 --format="%H %ad %s"
git branch --show-current
git remote -v
git status --porcelain
```

`git status --porcelain` 必须 **0 行**——这是「git grep 覆盖全部 tracked 文件、无未跟踪文件漏检」的证据，要写进每份 findings。

第二轮（转测文档口径）新增前置项，做完再派子代理：

```powershell
# ① 逐份登记转测文档（行数 + 字节数，判断「缺字段」时按小节核对）
Get-ChildItem "D:\workspace\260928_vllm资料确认\转测文档_2026Q3\*.txt" |
  Select-Object Name, Length, @{n='Lines';e={(Get-Content $_ -Encoding UTF8).Count}}
# ② 转测文档里出现的每个环境变量 / 启动参数，逐个拿去主线 grep
git -C D:\workspace\260928_vllm资料确认\repo_main grep -F -i -c -- <VAR_OR_FLAG>
```
- 验证：本轮 `KV_BF16` 全仓 0 命中（exit 1），实测 165KB / 12 份，最大一份 50KB。
- 实测基线：第一轮 HEAD=`18d0537d9`；第二轮复跑时远端已前进到 `f18d103838b831380d3590df32e0e82d4aa07a9a`（2026-09-28 10:12）；**第三轮再前进到 `233adfea55c565260345311845811237d726c2f2`（2026-09-28 11:41）**。每轮开工先 `git fetch upstream main` + `git -C <repo> rev-parse HEAD` 复核，并 `git checkout --detach <新 sha>` 把只读 worktree 移到新 sha，再复验 `git status --porcelain` = 0 行——不要沿用上一轮写的 sha，子代理抓到过一次「任务里给的 HEAD 与实际不符」。
- 第三轮（转测文档口径）再新增前置项：**开工先产出三件种子文件**（Recon A 关键词抽取 / Recon B 代号映射 / 词存在性普查），它们是 12 个子代理 prompt 的共用输入；做法与范本见 `references/recon-artifacts.md`。同时把 12 份文档逐字指令里的开关抽进 `keywords.md`。

## 步骤

1. **锚定上游基线**（不动用户当前 checkout）：

   ```powershell
   git fetch upstream main
   git log -1 --format="%H%n%ad%n%s" upstream/main
   ```
   - 验证：本轮 = `18d0537d9`（2026-09-28）；看 git 自己输出的 `cc09c4457..18d0537d9 main -> upstream/main` 判成功。

2. **建隔离只读副本**，后续所有 grep 都在它里面跑：

   ```powershell
   git worktree add --detach D:\workspace\260928_vllm资料确认\repo_main upstream/main
   ```
   - 验证：`repo_main` 存在且 `git -C repo_main status --porcelain` 为空。

3. **关键词普查（必须在派子代理之前做）**：用一条 pwsh 循环，对每个关键词分别跑下面两条，统计命中文件数；`docs` 命中 ≤6 的直接把文件名列出来：

   ```powershell
   git grep -F -i -l -- <kw> -- vllm_ascend
   git grep -F -i -l -- <kw> -- docs
   ```
   - 验证（本轮实测）：`moonlight` 全仓 0 命中（**第二轮已破解**，见步骤 3b：映射要从提交正文里找）；`dspark` 实为 `vllm_ascend/models/deepseek_v4/dspark.py`；`A5` 在 docs 里一律写作 `950DT Products` / `950PR&950DT Products`。
   - 这一步把「内部代号 → 仓库真实符号」的映射建立起来，否则子代理会凭猜名检索。

3b. **工作区 0 命中时，改搜提交信息（不要直接判 unclear）**：

   ```powershell
   git -C D:\workspace\260928_vllm资料确认\repo_main log --all -i --grep="<内部代号>" --oneline
   git -C D:\workspace\260928_vllm资料确认\repo_main log -1 --format="%H%n%ad%n%s%n%b" <sha>   # 看提交正文，必要时 -p 看 diff
   ```
   - 验证（本轮实测）：`git grep -F -i moonlight` = 0 命中，但 `log --all -i --grep=moonlight` 命中唯一一提交 `d86021f7b [Bugfix] record cos and sin cache in AscendRotaryEmbedding (#5516)`，正文写 `[Moonlight](https://modelscope.cn/models/moonshotai/Moonlight-16B-A3B-Instruct)` + "(using MLA but without `rope_scaling` in config.json)" → 映射破解为 `moonshotai/Moonlight-16B-A3B-Instruct`，该条结论从 `unclear` 升级为 `yes`。
   - 判读要点：`git log -S/-G` **无匹配时 exit code 仍是 0**，只能数输出行数（`... | Measure-Object -Line`），不能靠退出码判有没有命中。

3c. **第二轮的输入形态：转测文档。** 一批中文 `.txt`（本轮 `转测文档_2026Q3/`，12 份）声明「该需求实际交付并验证了什么」，含公开模型名/权重路径、硬件代际（A3/A5）、精度格式、配套 vllm/torch/torch_npu/CANN 版本、启动参数、性能与精度数值、测试结论。判据随之变为：**转测文档声明已交付的能力 = 已交付事实；要判的是主线 docs 能否让用户检索到它**（不再猜型号/场景）。逐项核对清单见 `references/test-doc-vs-main-checklist.md`。
   - 转测文档**常常缺关键字段**：本轮 12 份里多份「实验环境 / 服务器拉起 / 日志 / 结果」小节标题下正文为空；REQ-01/11/12 全文无 A2/A3/A5/Atlas 字样；REQ-03（moonlight）通篇没有公开模型名。→ 这些空缺必须显式写成 `gaps_or_risks`，**不得臆断**，刷新方案对应列标「待业务确认」。
   - **转测口径可能引用主线不存在的开关**：本轮 REQ-07/REQ-10 的转测命令都 `export VLLM_ASCEND_DSV4_KV_BF16=1`，而 `git grep -F -i KV_BF16` = 0 命中（exit 1）、`git log -S"VLLM_ASCEND_DSV4_KV_BF16" --all --oneline` = 0 提交（exit 0，需数行）；主线等价开关是 `--kv-cache-dtype bfloat16`（`DeepSeek-V4-Flash.md:1196`、`DeepSeek-V4-Pro.md:1524`）。→ 验证子代理必须把转测文档里出现的**每个**环境变量/参数名拿去主线 grep 一遍，找不到就在风险里点名，**文档不得照抄转测命令**。
   - 成对出现时别只判一半：同一份转测文档常同时写该变量与 `--kv-cache-dtype bfloat16`（实测 `【A5】A5支持DS V4 flash高性能推理.txt:75,83`），结论要写「两者并存，主线只认后者」。

4. **先问清 3 个口径再动手**：① 「主线」指哪个 checkout（本地 / 远端 main）；② 「资料」范围（仅 user_guide / docs/source 全部 / 含 README）；③ 交付到哪一步（只出结论 / 结论+刷新方案 / 直接改）。口径②的资料范围必须点全四个权威源：`docs/source/**` + `mkdocs.yml` nav + 中文翻译 `docs/source/locale/zh_CN/LC_MESSAGES/**.po`（**不是** `locale/zh_CN/**.po`——仓库根 `locale\` 不存在，`Test-Path` False；实测 206 个 `.po`、26 个目录，`tutorials/models` 63 个 / `user_guide/feature_guide` 39 个）+ **`docs/hooks/nav_titles.py`（用户可见页名的唯一权威）**。本轮答：upstream/main@`233adfea5`；结论+方案（不改文档）。

   第二轮追加第 ④ 个口径：**交付物是否要「与上一轮的差异」一节**（本轮要）。该节逐条写「上一轮怎么判 / 这一轮为什么改判 / 依据是什么」——只报「等级变动」不够，等级没变但刷新落点被转测文档改写（本轮 12 条里 10 条属此类）也必须逐条写，否则上一轮的作废方案会被当成现行结论。范本见 `vllm-ascend主线资料刷新清单_v2_转测文档校核.md` 第三节（30 行）。

4b. **判「用户用词」不能只看文件名——权威是 `docs/hooks/nav_titles.py`**：用户打开的页名由该文件的 **en/zh 双键**决定，`mkdocs.yml` 的标题与文件名都不是权威。实测：`:134` = `"tutorials/models/GLM5.md": {"en": "GLM-5 & GLM-5.1", "zh": "GLM-5 & GLM-5.1"}`；`:128` GLM-5.2；`:193` `Qwen3.5-397B-A17B`；`:194` `Qwen3.6-35B-A3B`；`:208` `user_guide/feature_guide/batch_invariance.md` → `Batch Invariance` / 批次不变性。

   ```powershell
   git -C D:\workspace\260928_vllm资料确认\repo_main grep -F -n -- "Qwen3.6-35B-A3B" -- docs/hooks/nav_titles.py
   ```
   - **实证（本轮 REQ-10 的关键结论就靠它）**：转测用名 `Qwen3.5-35B-A3B` 在 docs 只命中矩阵一行（`supported_models.md:153`，且在 `Atlas 300I DUO` tab），而用户真正打开的页名是 `Qwen3.6-35B-A3B`（`nav_titles.py:194`）。⚠️ 注意本轮 REQ-09 与 REQ-10 对「A3 可检索」用了不同基准（3.5 无行 / 算在兄弟页 `Qwen3.6-35B-A3B.md:139`），汇总时必须显式消解这类基准不一致。
   - 同理，「转测文档说的型号 / 特性」必须落成 `nav_titles.py` 的键值对再判缺口，否则会把「兄弟页已覆盖」误判成 yes、或把「页名不同」误判成缺页。

4c. **locale `.po` 命名规则 = `docs/source/` 下相对路径去 `.md` 加 `.po`**：`user_guide/feature_guide/lora.md` → `docs/source/locale/zh_CN/LC_MESSAGES/user_guide/feature_guide/lora.po`；`getting_started/installation.md` → `.../getting_started/installation.po`。文件内 `msgid` = 英文原文、`msgstr` = 中文，由 `detect_po_changes.py` 生成（文件头 `"Generated-By: detect_po_changes.py\n"`，少数老文件是 `Babel 2.17/2.18`）。判「译文是否同步」就用这个映射直接 `Select-String -Path <对应 .po>`。

4d. **`.po` 翻译归责的判据是「谁在改 + 有没有门禁」，不是「上游约定」**（本轮纠正两条已被证伪的断言）：

   结论先写：**跳过 `.po` 在本次是合理选择，但理由只能是「机器翻译流水线负责 + 无 CI 门禁」**。

   - **真实链路**（逐环节按磁盘 glob + 读 `on:` 键复核）：
     - `.github/workflows/schedule_doc_translate.yaml` —— `:20-34` 的 `on:` 只有 `schedule`（cron `0 0 */3 * *`）与 `workflow_dispatch`，`:43` 的 `if:` 也只放行 `workflow_dispatch || schedule` ⇒ **没有 `pull_request` 触发**；它是**自建 PR**（`:186-190` 往上游 `vllm-project/vllm-ascend` 提 `auto-pr/doc-translate-*`），不是对别人 PR 的门禁。
     - `.github/workflows/scripts/detect_po_changes.py` —— `:77` 被上面那个 workflow 调用，是 `.po` 的**写入方**。
     - `.github/workflows/scripts/po_translate.py` —— `:106` 被调用；`:202` `base_url="https://api.deepseek.com"`、`:211` `model="deepseek-chat"`、`:104` 凭据 `DEEPSEEK_API_KEY` ⇒ **机翻执行方**。
     - `tools/generate_zh_docs.py` —— 只是 `.po` → `zh.md` 的**消费方**，别把消费方当生成方。
   - **「存在性判据别信脚本名」**：`tools/detect_po_changes.py` **不存在**（全仓 `glob **/detect_po_changes.py` 只回 `repo_main\.github\workflows\scripts\` 与 `pr_work\.github\workflows\scripts\` 两份）。判某脚本存不存在 / 会不会在 PR 上跑，**不要按名字猜路径**：先全仓 glob 定位，再读对应 workflow 的 `on:` 与 `if:`。
   - **「没有 CI 门禁管 `.po`」的验法**：`.github/workflows` 全目录 grep `\.po\b|LC_MESSAGES`（`*.yaml` 与 `*.yml` 各扫一遍），唯一命中是 `schedule_doc_translate.yaml:31` 里 `workflow_dispatch` 的一条 input 描述 ⇒ **没有任何 job 检查 PR 里的 `.po`**。
   - **已证伪断言 ①「改了英文就该顺手改 `.po`」**——上游没有这条约定，人类维护者**确实手改过** `.po`（提交 `0a52fdd` 手工改了 8 个）⇒ 手改不违规，改不改是**成本选择**。
   - **已证伪断言 ②「改了 `.po` 会被下次 cron 覆盖」**——`detect_po_changes.py:415-422` 对**未被触碰**的 `msgid` 直接 `continue`（`:422`），**保留现有 `msgstr`**；只有 `:443-449` 命中「相似但已变更」的段落才走 `new_entry.msgstr = ""`（`:447`）强制重译 ⇒ 与本次改动无关的老 `msgstr` 不会被清掉。
   - **可照抄进交付物的表述**：`.po` 由每 3 天一次的机器翻译 workflow 自建 PR 维护，且**没有任何 CI 门禁**要求 PR 同步 `.po` ⇒ 本次跳过 `.po` 合理；**不要**写成「上游约定不许手改」或「改了会被覆盖」。

5. **Fan-out**（`workflow` 的 `parallel()`）：N 条需求 = N 个**只读**子代理 + 1 个汇总代理。每个子代理用 write 落盘 `findings/REQ-XX.md`（≤60 行六节结构，见 `references/findings-template.md`），只回结构化 JSON：`req_id / mapping / code_status / docs_status / needs_refresh / refresh_plan / confidence / gaps_or_risks`。汇总代理读全部 findings 写最终清单（六节，见 `references/deliverable-template.md`）。本轮 13 个 agent 全部成功，findings 实测每份 43-50 行、恰含 6 个 `## ` 小节。

6. **子代理 prompt 必须写死的 4 条**：仓库绝对路径（`D:\workspace\260928_vllm资料确认\repo_main`）；映射陷阱提醒（如「A5 不是 docs 面向用户的用词，需自行确认实际写法」）；「关键结论必须给 file:line，不要臆断，映射不成立就填 unclear 并列出搜过的关键词」；只读边界（禁止 checkout / commit / push / fetch）。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `upstream-docs-refresh-audit`（正文步骤 6 的 4 条硬约束）与 `pwsh-on-windows`；落盘 findings 的子代理再加本 skill 的 `references/findings-template.md`。加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\upstream-docs-refresh-audit\SKILL.md`、`C:\Users\admin\.dsh\skills\pwsh-on-windows\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。
> 并发成员 ≥2 或子任务 ≥3 时，按 `orchestrating-subagents` §9.1 在本轮 cwd 落 `.dsh-run\<日期>-ledger.md` 台账，收尾清空。

6b. **prompt 里的「已知线索」一律标成待验证假设**：本轮曾在 REQ-06 的 prompt 里写「GLM-5.1 与 GLM-5 合并成一行」，子代理用 file:line 反驳——`supported_models.md:25`（950DT tab）是**独立** `|GLM-5.1|…` 行，`:42`（A2/A3 tab）才是 `GLM-5/5.1` 合并行（已复验）。写 prompt 时加一句：「以下线索是**待验证假设**，以 file:line 证据为准，与线索冲突时用证据反驳」。汇总代理必须复核「主线提示 vs findings」的冲突并写进交付物（本轮写在差异节第 6 条）。

7. **主 Agent 必须自己抽样复验**：一条 pwsh 把 `git grep -F -n -- <kw> -- <path>` 与 `Get-Content -Encoding UTF8 <path> | Select-Object -Skip N -First M` 组合起来，直接看目标行原文。本轮抓到 1 处章节误标、2 处分节归属错。

8. **判「缺行 / 空列」前先定位 tab 骨架（否则会把另一张表里已有的行误判成缺口）**：

   ```powershell
   Select-String -Path D:\workspace\260928_vllm资料确认\repo_main\docs\source\user_guide\support_matrix\supported_models.md `
     -Pattern '^(#{1,4} |=== )' | Select-Object LineNumber, Line
   ```
   - **正则必须是 `'^(#{1,4} |=== )'`**（`===` 前**没有** `\s+`）——8 个 tab 是**顶格**书写的。实测这条回 **19 行**（`supported_models.md` 共 184 行），tab 行在 `:18 :27 :52 :90 :103 :121 :129 :147`。写成 `'^(#{1,4} |\s+=== )'` 只回 11 行 heading、**0 个 `===`**；**若回 0 个 `===` 就说明正则被锚定错、tab 是顶格**，别据此判「本页没有 tab」。
   - 实测骨架（本轮）：`:12 ## Text-Only Language Models` / `:18` `=== "950DT Products"` / `:27` `=== "A2/A3"` / `:52` `=== "Atlas 300I DUO"` / `:115 ## Multimodal Language Models` / `:121` 950DT / `:129` A2/A3 / `:147` Atlas 300I DUO。同一型号在不同 tab 里可能是不同的行（GLM-5.1 的独立行只在 950DT tab `:25`，A2/A3 tab `:42` 是合并行）。
   - **别把 tab 骨架与「行名」混为一谈**：本轮两处实证 —— ① `:25`（950DT tab）是独立 `|GLM-5.1|` 行、Note 列空，`:42`（A2/A3 tab）才是合并 `GLM-5/5.1` 行；② `:153` 行名是 `| Qwen3.5-35B-A3B |`、硬件列 `Atlas 300I DUO`，而 `:139` 是 `Qwen3.6-35B-A3B` / A2/A3 tab、PD 列 ❌ —— REQ-10 说 `:139` PD=❌「与同型号相反」、REQ-11 说 `:153` PD=❌，实为**两行两 tab**，不是矛盾。

9. **汇总协议（第三轮实证，13 个 agent = 12 findings + 1 汇总；现有 skill 只写到「fan-out 产出 findings」，这一段是补的）**：

   1. **分 3 次写盘**（>250 行交付物必须这样，见步骤 12）：`write` 首版（§1 核查口径 + §2 总览结论表）→ `edit` 追加 §3 逐条刷新方案 → `edit` 追加 §4 需业务澄清 + §5 未确认项 + §6 复验锚点。本轮产出 317 行，三次全成功。
   2. **等级只能来自 findings、汇总不得改判**。本轮 12 条 = `yes` 6（REQ-01/02/05/09/10/11）/ `partial` 6（REQ-03/04/06/07/08/12）/ `no` 0 / `unclear` 0。
   3. **「与上一轮的差异」一节只在真有上一轮交付物时才写**。本轮工作区**没有**上一轮产物 ⇒ 不写该节、也不得虚构上一轮结论（第二轮有，范本 `vllm-ascend主线资料刷新清单_v2_转测文档校核.md:34-50`）。开工第一件事就是列工作区，判定这一节到底写不写。
   4. **必须复核 findings 互相矛盾并写明处理**（不能只挑一份采信）。本轮实证 5 处：① `:139` vs `:153` = 两行两 tab（见步骤 8）；② REQ-03 判 GLM-5.2 `max-model-len` 200k「非冲突」 vs REQ-08 判「四源冲突待裁」→ 采 REQ-08 框架（四值并存、以转测 `1024000` 为权威）但采 REQ-03 对 `40960/34816` 的定性（短序列场景值、不入冲突表）；③ 审计表写 `VLLM_ASCEND_DSV4_KV_BF16`「无等价物」 vs findings 写等价物是 `--kv-cache-dtype bfloat16` → 实为**字面等价 vs 功能等价**两种口径，须显式登记；④ REQ-04/REQ-06 描述同一行不同列（BF16 列为空 vs Note 列已有），复验后**同时记录两列状态**；⑤ REQ-09/REQ-10 对「A3 可检索」基准不同（3.5 无行 vs 兄弟页 `Qwen3.6-35B-A3B.md:139`）。
   5. **验收判据：§3「逐条刷新方案」里出现的幽灵开关必须全是禁止性表述**（「不得照抄」/「严禁写」/「不进文档」/「写入即返工」）；同一批词在 §4.1 需业务澄清表里**允许正常正面出现**。本轮实测 §3（`:58-148`）里 `VLLM_ASCEND_DSV4_KV_BF16` 2 处、`--kv-offloading-size` 1、`VLLM_USE_SIMPLE_KV_OFFLOAD` 1、`VLLM_SSM_CONV_STATE_LAYOUT` 1、`VLLM_ENABLE_V1_MULTIPROCESSING` 1、`CUDA_VISIBLE_DEVICES` 2 —— 逐条复验全是禁止性；同批词在 §4.1（`:155-175`）正常出现（`VLLM_ASCEND_DSV4_KV_BF16` 6 次等）。**复验方式 = 对 §3 逐词取上下文判是否禁止性，不要只看词频。**
   6. **主 Agent 亲手复验锚点**（可作 skill 的验收示例）：`supported_models.md:25` / `:42` / `:153` / 文件 184 行；`nav_titles.py:134`；`quant_type.py:32` = `W8A8MXFP = 3  # W and A are MXFP8`；`GLM5.2.md:1036` = `### 5.2 1M Context Configuration`；`feature_guide/rl.md` 367 行且 `git grep -c -i lora` = 0（exit 1）⇒ 「RL 页全文不提 LoRA」缺口成立；`DeepSeek-V4-Flash.md:1196` 与 `DeepSeek-V4-Pro.md:1524` 的 `--kv-cache-dtype bfloat16`；主线 `git grep -F -i KV_BF16` = 0 命中。

10. **判「词是否存在」用 `git -C <repo> grep -F -q -- <词>`（exit 0 存在 / exit 1 不存在），且必须搜全仓**——只搜 `vllm_ascend` 会误判（`max-model-len` 在 `vllm_ascend` exit=1，但代码属性 `max_model_len` 有 51 文件命中）。**误命中与口径三件套**：① `-i A5` 回 190 行含 `Binary file ... matches` 24 行与 CSS `color: #ffa500;` 2 行 → 改 `git grep -I -l -E "\bA5\b"` 回 8 文件；② `-i 35B` 回 69 文件、其中 42 个是 `235B` / `DequantSwigluQuantV35BaseTilingData` → 改 `\b35B\b` 回 27；③ `-F -c` 是**子串**匹配（`GLM-5.2-w4a8` 会因 `w4a8c8` 得 11）→ 精确性要求高的场合改用 `\b` 或 `-w`。**`-l` 回的是文件数不是命中次数。** 本轮实测 236 词：存在 193 / **不存在 43**（env 8 + flag 6 + 类别关键词 29），关键裁决：`--master_addr/--master_port/--node_rank` 主线只有连字符写法 `--master-addr`(8)/`--master-port`(8)/`--node-rank`(10)，`--nproc_per_node` 两种写法都没有；`CUDA_VISIBLE_DEVICES` → 主线是 `ASCEND_RT_VISIBLE_DEVICES`(165 文件)；`--additional_config` 11 文件 vs `--additional-config` 298 文件（**都存在但悬殊**）。完整协议与分组清单见 `references/recon-artifacts.md`。

11. **验收前主 Agent 再亲手复验一遍锚点**（步骤 7 是抽查、这里是交付前终检）：一条 pwsh 把 `git grep -F -n -- <kw> -- <path>` 与 `Get-Content -Encoding UTF8 <path> | Select-Object -Skip N -First M` 组合起来，直接看目标行原文。本轮抓到 1 处章节误标、2 处分节归属错；终检锚点清单见「验收标准」末两条。

12. **长交付物必须分次写盘**：汇总任务产出预期 >250 行时，在汇总子代理 prompt 里明写「write 首版（前 3 节）→ edit 追加第四节 → edit 追加剩余节」的三到四段式。本轮证据：第一轮一次 write 失败（workflow 返回 `synthesis_summary: null`，交付物未生成）；第二轮改分次写盘后成功产出 336 行；**第三轮 3 次全成功（317 行）**。`edit` 失败过一次，报错原文 `Error: old_string was not found`，原因是**被替换串里的全角标点不一致**（把 `，结论只有` 写成 `、结论只有`）→ 修法 = 换更短的唯一尾串重试，不要重写整段。**汇总失败 ≠ 白干**——12 份 findings 已在盘上，直接补派/补跑汇总即可，不要重跑核查。

## 坑与修法

- **通用 PowerShell 陷阱**（编码 / 管道统计 / PS7 语法 / BOM / 只读变量）的完整清单与可抄写法见 skill `pwsh-on-windows`；下面只列与「docs 刷新审计」这一流程相关的。
- pwsh 里 `git fetch upstream main` 报红字 `NativeCommandError` → git 把进度写 stderr，pwsh 包成错误，命令其实成功。→ 判成功看 git 自己输出的 `<旧 sha>..<新 sha> main -> upstream/main`（实测 `f18d10383..233adfea5 main -> upstream/main`），不要被红字误导，也不要据此判失败重跑。
- `Get-Content` 默认编码会把 emoji/`|` 分隔符吞掉 → markdown 表格列错位、**误判某列为空**。→ 复核表格一律带 `-Encoding UTF8`（机制与通用清单见 `pwsh-on-windows`）。
- `git grep -i 35B` 会误命中 `235B` → 加边界或用更具体串。
- 数文件行数别用 `Measure-Object -Line`（会少算，机制见 `pwsh-on-windows`）→ 用 `(Get-Content f -Encoding utf8).Count`。
- 内部代号 ≠ 仓库符号：只搜 `A5` 会误判「资料完全没写」，实际 docs 写 `950DT Products`；`moonlight` 工作区 0 命中时**先搜提交信息**（`git log --all -i --grep`），本轮据此把它从 unclear 改判为 yes。
- `git log -S"<串>" --all --oneline` **无匹配时 exit code 仍为 0** → 看退出码会误以为「有结果」。→ 必须数输出行数；而 `git grep -F -i -- <串>` 无匹配是 exit 1、stderr 为空（是「无此串」，不是报错）。
- 转测文档口径 ≠ 主线口径：`export VLLM_ASCEND_DSV4_KV_BF16=1` 在本轮两份转测文档出现（`【A5】A5支持DS V4 flash高性能推理.txt:75,133,211,270`），但主线 `git grep -F -i KV_BF16` = 0 命中、`log -S` = 0 提交。→ 文档写主线的 `--kv-cache-dtype bfloat16`，该变量列为待业务澄清，**不照抄转测命令**。
- 转测文档缺字段会被当成「无此能力」：本轮多份「实验环境 / 服务器拉起 / 日志 / 结果」小节标题下正文为空，REQ-01/11/12 全文无硬件代际。→ 写成 `gaps_or_risks` + 方案标「待业务确认」，不要用「未提及」倒推「不支持」。
- 转测实测数值可裁决主线内部冲突：本轮 REQ-09 主线并存 `200k`（`supported_models.md:43`）/`1048576`（`GLM5.2.md:1273,1337,1399,1462`）/`198k`（`GLM5.2.md:1654-1661`）/`1024000`（`GLM5.2.md:1055,1104`）四值；转测四机脚本一致 `--max-model-len 1024000` + 压测 `--random-input-len 1000000` → 以转测裁决为权威值，其余三处记为待统一。
- `Measure-Object` 是管道对象统计 → 配合 `.Count` 使用；空集合走管道 `@() | Measure-Object -Sum`（`-InputObject @()` 会报 `Count: 1`，见 `pwsh-on-windows`）。
- 判定依据别选错表：`feature_matrix.md` 是 feature×feature 矩阵，**结构上不适用**于型号×硬件×特性判定；本仓库的判定页是 `support_matrix/supported_models.md` + `tutorials/models/*.md` + `release_notes.md` + `mkdocs.yml` nav + 中文翻译 `docs/source/locale/zh_CN/LC_MESSAGES/**.po`（**不是仓库根 `locale/zh_CN/**.po`——`locale\` 在仓库根不存在，`Test-Path` False；实测 206 个 `.po` / 26 个目录）＋ 用户可见页名 `docs/hooks/nav_titles.py`。
- `supported_models.md` 同一型号在多 tab 里有不同行 → 判「缺行」前先 `Select-String -Path <file> -Pattern '^(#{1,4} |=== )'` 列骨架定位（本轮 REQ-05 就因选错表误判过）。**写成 `'^(#{1,4} |\s+=== )'` 只回 11 行 heading、0 个 `===`（tab 是顶格的）**——回 0 个 `===` 时不要判「本页没有 tab」，是正则错了。
- 判「词是否存在」要搜**全仓**，只看 `vllm_ascend` 会误判：`max-model-len` 在 `vllm_ascend` exit=1，但代码属性 `max_model_len` 有 51 文件命中。`-l` 回的是**文件数不是命中次数**；`-F -c` 是**子串**匹配（`GLM-5.2-w4a8` 会因 `w4a8c8` 得 11）。
- `git grep -i A5` 回 190 行里混着 `Binary file ... matches` 24 行与 CSS `color: #ffa500;` 2 行 → 改 `git grep -I -l -E "\bA5\b"` 回 8 文件。`git grep -i 35B` 回 69 文件里 42 个是 `235B`/`DequantSwigluQuantV35BaseTilingData` → 改 `\b35B\b` 回 27。
- 转测文档是 wiki 导出的 `.txt`，**代码块必然丢失**：本轮 REQ-05（moonlit）/ REQ-07 的「环境变量」「业务启动」小节**正文全空**，一条 env/flag 都抽不到。→ 缺失一律写「缺」、标 `待业务确认`，**不得臆断补全**；抽关键词时也不能因为「这节应该有条命令」就反推。
- 从转测文档抽环境变量的正则别只写 `(?:^|\bexport\s+)(\w+)\s*=`：**抓不到** `env["VLLM_ALLOW_RUNTIME_LORA_UPDATING"] = "1"` 这类写法，必须补扫 `os.getenv|environ|env\[`。
- 用户看到的页名 ≠ 文件名 ≠ `mkdocs.yml` 标题：权威是 `docs/hooks/nav_titles.py` 的 en/zh 双键。本轮转测用名 `Qwen3.5-35B-A3B` 只在矩阵 `supported_models.md:153`（Atlas 300I DUO tab）命中，而用户真打开的页名是 `Qwen3.6-35B-A3B`（`nav_titles.py:194`）——只按文件名判会写错刷新落点。
- `edit` 报 `Error: old_string was not found` 时，先怀疑**全角标点不一致**（实测把 `，结论只有` 写成 `、结论只有` 就复现了）→ 换更短的唯一尾串重试；在长中文段落里一次替换整段很容易踩到。
- **判「某脚本存不存在 / 会不会在 PR 上跑」别信脚本名**：`tools/detect_po_changes.py` **不存在**（真身 `.github/workflows/scripts/detect_po_changes.py`），而确实存在的 `tools/generate_zh_docs.py` 只是**消费方** ⇒ 先全仓 glob、再读对应 workflow 的 `on:`/`if:`。`.po` 归责判据与两条被证伪的断言见步骤 **4d**。

## 不要做什么

- 映射未建立（关键词 0 命中）时不要指定待刷新文件、不要硬猜模型名——**先补搜提交信息**（`log --all -i --grep`、必要时 `-p` 看 diff），仍无命中才判 `unclear` 并在「需业务澄清」节列出搜过的关键词。
- 不要把转测文档里的环境变量/参数名照抄进刷新方案——先逐个主线 grep；找不到的点名进风险，不要写进用户文档。
- 不要在 prompt 里把「已知线索」写成结论（本轮 REQ-06 的 GLM-5.1 线索就是错的）；一律标注「待验证假设，以 file:line 为准」。
- 不要让汇总子代理一次 write 完 >250 行的交付物；也不要因为汇总失败就重跑核查（findings 已在盘上）。
- 不要动用户当前 checkout；子代理一律只读，禁 checkout/commit/push/fetch。
- 不要让子代理把长结论回给主 Agent（12 条会打爆主上下文）——一律落盘 `findings/`，只回 JSON。
- 不要跳过关键词普查直接 fan-out。
- 不要直接改 docs（除非口径 ③ 明确要改）；本轮交付只到「结论 + 刷新方案」。
- 不要修改已交付的清单文件本身。

## 验收标准

- `findings/REQ-*.md` 数量 = 需求条数（本轮 12 份），每份 ≤60 行、含 6 个固定小节、关键结论带 `file:line`。
- 最终清单含六节：核查口径 / 总览结论表 / 逐条刷新方案 / 需业务澄清 / 未确认项 / 复验锚点。范本：`D:\workspace\260928_vllm资料确认\vllm-ascend主线资料刷新清单.md`（274 行）。
- 第二轮（转测文档口径）追加：清单须含**与上一轮的差异**一节，逐条写「上一轮怎么判 / 这一轮为什么改判 / 依据」；范本 `D:\workspace\260928_vllm资料确认\vllm-ascend主线资料刷新清单_v2_转测文档校核.md`（336 行，第三节 :34-50 即差异节）。
- 验收标准：每条需求 `needs_refresh ∈ {yes, partial, no, unclear}`；`unclear` 条目不派发任何刷新任务；转测文档里出现的每个环境变量/参数名都有「主线存在与否」的结论。
- 主 Agent 至少亲手复验 1~2 处 `file:line`（本轮抓到 3 处错误标注）；第二轮抽查了 `supported_models.md:25/:42`（GLM-5.1 独立行 vs 合并行）与 `GLM5.2.md:1055/1273/1654`（1024000/1048576/198k 三值），全部与 findings 一致。
- 交付物行数可核：`(Get-Content <清单> -Encoding UTF8).Count`。
- 第三轮追加的验收（本轮实测通过）：① 工作区内存在三件种子文件（`keywords.md` 162 行 / `codename_map.md` 171 行 / `existence_audit.md` 496 行，三表 50/96/90）；② `needs_refresh` 分布可核：`yes` 6 / `partial` 6 / `no` 0 / `unclear` 0，且与 12 份 findings 逐条一致（**汇总不得改判**）；③ **§3 里出现的每个幽灵开关都是禁止性表述**（本轮 §3 `:58-148` 的 7 处同类词逐条复验全是禁止性，同批词在 §4.1 正常正面出现）；④ 交付物总行数 = `write` 首版 + 2 次 `edit` 追加之和（本轮 317 行，§1 `:6` / §2 `:39` / §3 `:58` / §4 `:149` / §5 `:241` / §6 `:253`）；⑤ 无上一轮交付物时不出现「与上一轮的差异」章节。
- 第三轮主 Agent 亲手复验锚点（全部与 findings 一致）：`supported_models.md:25`（950DT tab 独立 `|GLM-5.1|` 行、Note 空）/`:42`（A2/A3 tab 合并 `GLM-5/5.1` 行）/`:153`（`| Qwen3.5-35B-A3B |`、硬件列 `Atlas 300I DUO`）/文件 184 行；`nav_titles.py:134`；`quantization/quant_type.py:32` = `W8A8MXFP = 3  # W and A are MXFP8`；`GLM5.2.md:1036` = `### 5.2 1M Context Configuration`；`feature_guide/rl.md` 367 行且 `lora` 0 命中（exit 1）；`DeepSeek-V4-Flash.md:1196` / `DeepSeek-V4-Pro.md:1524` 的 `--kv-cache-dtype bfloat16`；主线 `git grep -F -i KV_BF16` = 0 命中。
