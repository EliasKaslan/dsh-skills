---
name: llm-landscape-recon
description: 核查 OpenAI/Anthropic/Google 最新模型能力：官方定价直取、AA 榜单 JSON 解析、版本口径
whenToUse: 用户问"三家最新模型能力/该选哪个/价格上下文多少"时，走这条取证链。
---

# LLM 厂商最新模型能力核查（OpenAI / Anthropic / Google）

## 何时调用

- 用户要"OpenAI / Claude / Gemini 最新模型能力对比""该选哪个""现在什么价格""上下文多大"。
- 需要给出**可核验**数字（带 URL、带抓取日、区分官方自报与第三方复现），而不是凭记忆回答。
- 不适用：只问某一家的单个 API 参数（直接读该家文档即可）；只问开源模型。

## 三条证据链（缺一条就会被官方宣传带偏）

1. **官方定价页/模型页直取**——价格、上下文、模型 ID 这类硬事实只认官方。
2. **第三方聚合榜原始数据**——Artificial Analysis（AA）是唯一能直接读到结构化分数+价格+延迟的榜。
3. **交叉核对两处锚点**：官方 GPQA / HLE 与 AA 实测的同类分数若吻合（实测差 ≤0.2 个点），说明该模型的其他第三方数字可信；若差很多，先怀疑基准版本不同。

## 三家文档入口（实测可抓性，2026-11）

| 厂商 | 可抓（服务端渲染） | 抓不到 |
|---|---|---|
| OpenAI | `platform.openai.com/docs/pricing`、`/docs/models`（转文本后 16–19K 字符） | `openai.com/index/*`（SPA/403） |
| Anthropic | `docs.anthropic.com/en/docs/about-claude/models/overview`、`/pricing`（15–31K 字符） | 无（文档站全 SSR） |
| Google | `cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/<model>`、`.../pricing`（14K / 110K 字符）；`ai.google.dev/gemini-api/docs/<page>.md`（**加 .md 取纯文本**） | `ai.google.dev/.../docs/<page>`（SPA，转文本只剩 40 字符） |

补充：`ai.google.dev` 会 301 到 `aistudio.google.com/docs/*`，跨域 301 有些抓取器不跟随 → 直接抓 `aistudio.google.com/docs/<page>.md`。
发布日/退役日只看 `aistudio.google.com/docs/deprecations.md`（表格里有 Release date / Shutdown date）。

## AA 榜单原始数据解析（真跑通）

AA 是 Next.js flight payload：**原始 HTML 里引号被转义成 `\"`**。两个不同的数组键，别记混：

- 榜单页 `artificialanalysis.ai/leaderboards/models` → 键是 **`"initialModels":[`**（实测 290 条）。用 `"model":{` 去匹配会得到 0 条（这是本轮第一个坑）。
- 模型页 `artificialanalysis.ai/models/<slug>` → `"model":{` 时有时无，**改用转文本后的正则更稳**（3/3 成功）。

```python
t = open(path, encoding='utf-8', errors='ignore').read().replace('\\"', '"')
dec = json.JSONDecoder()
i = t.find('"initialModels":['); arr, _ = dec.raw_decode(t, t.index('[', i))
```

榜单字段（0–1 或原始值）：`intelligenceIndex`、`scores{gpqa-diamond, humanitys-last-exam, terminalbench-hard, tau2-bench, aime-2025, mmmu-pro}`、`contextWindowTokens`、`price1mInputTokens/OutputTokens`、`cacheHitPrice`、`outputSpeed`、`timeToFirstToken`、`isReasoning`。

模型页要抓的三句（正则/关键词窗口即可）：
`Intelligence # n / 80  NN`、`$X Cost per Intelligence Index task`、`at Y minutes per Intelligence Index task`。
这三个数才是"贵不贵、慢不慢"的决策依据——单价会骗人（输出啰嗦的模型单价低但每任务更贵）。

## 版本与口径纪律（最容易翻车的地方）

- AA 指数带版本号：`Intelligence Index v5`。**v5.0 改组过指标**（移除 GDPval-AA/SciCode/AA-LCR/HLE，CritPt 换 v2，AIME 2025 不再计入），v4 与 v5 分数**不可比**。
- 同一 v5 内部也会回流重评（发布日分数 → 数周后重评分数会变）。**所有 AA 数字必须写"某日抓取 + 版本号"**，否则不可引用。
- 模型页自带排名是最可靠的（`# 1 / 80`），不要用"我按 index 排序数出来的名次"。

## 基准换代：别去找 SWE-bench Verified

2026 年三家官方材料里 **SWE-bench Verified / MMMU / AIME 基本都不再报**，换成 Terminal-Bench 4.0、DeepSWE、FrontierSWE、FrontierCode、ARC-AGI-3 等。含义：

- 结论里必须写清"该榜是官方自跑、第三方复跑、还是自建子集不可比"（Anthropic 的 SWE-bench Pro 属于第三种，官方自己声明不可与公开榜比较）。
- 同一模型换榜可差几十点，单引一个 SWE 分几乎无意义；至少给两个不同 harness 的结果。
- Terminal-Bench 有 2.0 / 4.0 等多个版本，**版本号必须写进结论**，否则两个榜会给出相反排序。

## 坑（均带原文）

- `lmarena.ai` → `HTTPError: HTTP Error 403: Forbidden`；`swebench.com` / `tbench.ai` → 纯 JS，转文本 <200 字符。这三个别重试，直接换源并在结论里标"未取到"。
- 别用 `web_fetch` 抓 >8KB 页面：会整页回灌。落盘 + 关键词窗口切片（见 skill `orchestrating-subagents` 的"大页面不进上下文"）。
- 笔记文件名不要叫 `claude.md` / `gemini.md` 之外的 `CLAUDE.md`：NTFS 大小写不敏感，`claude.md` 就是 `CLAUDE.md`，会被 DSH 当 workspace 指令注入；而且 `Remove-Item CLAUDE.md` 会把 `claude.md` **本体一起删掉**（本轮实际发生，靠子代理重建才恢复）。用 `claude-models.md` 这类明确名字。
- 促销价：Google 的 Gemini 4 Carbon/Argon 在 2026-11-30 前是 `$2/$10`、之后 `$4/$20`（官方定价页写明 through/starting）。**AA 显示的是促销价**，成本模型必须两个价都算。

## 产物落盘

- 主报告：结论表 + 逐家规格表 + 官方自报/第三方复现分离 + 迁移坑 + 退役期 + 待核实清单。
- 机器可复核数据留 `aa_leaderboard.tsv`（一行一模型），原始 HTML 留 `raw/`，让读者能自己重算。

## 未验证

- AA 的 `intelligenceIndexIsEstimated` 字段网页 payload 里没有（属付费 API），无法区分"实测分"与"估算分"。
- 各家的"有效上下文长度"至今无官方数字，只能定性引用 context rot。

## effort 档位是隐藏比较维度（同名模型排序会翻转）

## effort 档位是隐藏比较维度（同名模型排序会翻转）

2026-11 实测：同一张 AA 榜单里，一个模型会按 effort 出现 **5 行**（Low/Medium/High/Xhigh/Max，显示名带 `(Max)` 这类后缀，默认档还标 `Default Fallback`）。不锚定档位，"A 和 B 谁强"可以得出相反答案：

| Claude 5.5 同一 v5.0.1 口径 | Low | Medium | High | Xhigh | Max |
|---|---|---|---|---|---|
| Sonnet 5.5 | 25.65 | 30.82 | **41.52**（默认） | 49.92 | 54.54 |
| Haiku 5.5 | 18.62 | **24.60**（默认） | 29.87 | 34.64 | 36.48 |

- Sonnet(Low) 25.65 **低于** Haiku(Max) 36.48 —— 拿"小模型拉满 vs 大模型摆烂"就能反转排序。
- 正确问法是先固定两件事：**同 effort 档**（要规划就都取 Max，要落地就都取默认档），再比 intelligenceIndex。
- 默认档要看官方文档的 `Default effort` 行（Sonnet 5.5=high、Haiku 5.5=medium、Opus 5.5=medium、Fable 5.2=high），不能假设各家都是 high。

## 名次的分母不统一

模型详情页给的 `Intelligence # n / N` 里 N 是**按族**给的（实测 Sonnet 5.5 `#13/80`、Haiku 5.5 `#1/36`、Opus 5.5 `#5/80`）。`#1/36` 不代表进前 10 —— 跨分母不能比名次；要全局名次就自己按 payload 里所有有指数的条目降序排一次（本轮 113 条）。

## 口径补充（Anthropic 4.6 代之后）

- **dateless ID 就是快照**：`claude-sonnet-5-5` / `claude-haiku-5-5` 没有 `-2026xxxx` 后缀，也没有 alias（官方 `model-ids-and-versions`：For the 4.6 generation and later, the dateless ID is the canonical model ID… maps to a single, fixed model snapshot）。别去搜"带日期的快照名"。
- **Haiku 5.5 起按 prompt 长度分档定价**：input `$0.10/MTok`（≤100,000 tokens）、`$0.50`（>100K）；output `$0.50` / `$2.50`。抓 pricing 时必须把两档都记下，只记小数会低估长上下文成本。
- 引用 Anthropic 公告里的 GDPval-AA / AA-Briefcase 时注意：那是**AA 第三方复跑**，且两家页面自相矛盾（Sonnet 自己的公告 1844/1811，Haiku 公告的参照列 1840/1824）→ 结论里标出，别当单一权威。
- 旧版本（Sonnet 5、Sonnet 4.6、Haiku 4.5）在 AA `initialModels` 里**没有**，只在 `releases`（无指数）→ 跨代对照只能引官方自报基准。

## OpenAI effort 档位与文档站迁移（2026-11 实测）

## OpenAI effort 档位与文档站迁移（2026-11 实测）

### 文档站已迁走（正文表格里 platform.openai.com 的旧入口作废）
- 抓 `platform.openai.com/docs/...` 报 `Error: cross-origin redirect to https://developers.openai.com is not followed automatically; retry against that URL directly`。
- 新入口：`developers.openai.com/api/docs/<page>`，**URL 末尾加 `.md`** 直接拿到 `content-type: text/markdown` 原文，比 HTML 转文本省一个数量级。
- 官方模型清单只有 `gpt-6.1-sol` / `gpt-6.1-terra`，**没有裸 `gpt-6.1`**（`/api/docs/models/gpt-6.1.md` → HTTP 404，可作反证）。第三方聚合（ageval 之类）会把 effort 写成含 `none`，与官方冲突时以官方模型页为准。

### GPT-6.1 Sol 的档位事实
- `reasoning.effort` = `low` / `medium`(默认) / `high` / `xhigh` / `max`；**不支持 `none`、`minimal`**；从 GPT-6 Sol 迁来要把 `none` 改成 `low`。
- **价格不随档位变**：$2/$10（≤272K input），只有 reasoning token 量变，而 reasoning token 按输出计价；`effort != none` 时必须去掉 `temperature`/`top_p`/`top_logprobs`；`text.verbosity` 是正交轴。
- 三套命名别混：API `low..max`；Work·Codex `Light(=low)/Medium/High/Extra High/Max/Ultra`；Chat `Instant/Medium/High/Extra High/Pro`。Sol 不在普通 ChatGPT 对话，只在 Work/Codex（那里默认 500K 上下文且无长上下溢价）。

### AA 的分档数据怎么读
- 同族按 effort 出 5 行（`GPT-6.1 Sol (Max)` 这种）。`Default Fallback` 只打在 Anthropic 行上，**OpenAI 行不带** → 默认档只能查官方文档，别从 AA 猜。
- v5.0.1 实测 Sol：ii 34.80 / 46.35（默认）/ 50.33 / 52.46 / 54.61；首字等待 3.0 / 4.8 / 32.9 / 68.6 / 167.4 s。**medium 已拿 max 的 85%，首字快 35 倍**；边际收益断点在 medium 之后（medium→high 只 +4 分却慢 7 倍）。
- 详情页 `Cost per Intelligence Index task` 是**一模型一个数**（实际取 Max 行），不能用来算逐档成本差；逐档成本只能按 reasoning token 量估（第三方小样本：194 / 539 / 1213 tok，high/low≈1.8×）。
- 对 reasoning 模型，TTFT ≈「想完才吐第一个字」，比 index 更能决定日常体感，选档结论要带它。
