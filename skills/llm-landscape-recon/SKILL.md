---
name: llm-landscape-recon
description: 模型对比与速度取证入口：官方来源、effort档、tok/s口径与计费。
whenToUse: "需要比较多家模型的当前能力、上下文、价格与评测，按日期和精确版本取证。"
---

# 模型版图与能力比较

按 [AI 官方来源与模型版图取证](../ai-vendor-official-source-audit/SKILL.md) 核查本次厂商、渠道、精确 model id、版本和采样日期，统一上下文、effort、缓存/批处理与计费单位。官方自报、第三方测评和独立实测分列，第三方榜单解析锚定具体对象与系列。

比较由用户任务、预算、地区与延迟约束决定；同名 effort 不保证同计算预算，名次带候选分母。若问题是渠道是否同模型，再转 [端点身份取证](../model-endpoint-identity-audit/SKILL.md)；若问题是地区与采购资格，转 [跨地区可用性](../overseas-ai-service-cn-availability/SKILL.md)。

## 取数路径与可比口径（2026-11 实跑）

触发信号：用户要"横向对比某几家模型的价格/能力"或"单任务成本多少"。本节只放执行路径与口径纪律，厂商在售型号与具体价格当场取，不写死。

### 官方文档一律加 `.md` 后缀

- OpenAI：`developers.openai.com/api/docs/pricing.md` 给全 Standard/Batch/Flex/Fast/Ultrafast 分档表。不带 `.md` 时是 JS 壳，只抓得到导航。
- Anthropic：`platform.claude.com/docs/en/about-claude/pricing.md` 一次给全模型价格表 + 缓存倍率脚注 + tokenizer 说明。
- Google：`ai.google.dev/gemini-api/docs/*` 已 302 到 `aistudio.google.com/docs/*`，web_fetch 报 `cross-origin redirect to https://aistudio.google.com is not followed automatically`；改抓 `https://aistudio.google.com/docs/<page>.md` 拿干净 Markdown。
- Artificial Analysis：只有 `/leaderboards/models` 的表格能出数（Index / Cost per Task / Time per Task / TTFT / 上下文）。`/leaderboards/coding-agents` 是 404，正确路径 `/agents/coding-agents`，但该页纯 JS 图表并自述 `No publicly available API`，只拿得到"持平 / −N 分"这类相对描述。`/articles/<slug>` 可抓，是拿发布方解读最快的入口。
- `arena.ai` 直连 403（Cloudflare），WebDev/Design Arena 分数只能取其官方社媒或第三方镜像，必须标注非直读并记下多源差异。

## 四条口径纪律

1. **单价表必须配 cost-per-task**。同单价的两个模型单任务成本可差 6 倍，差在思考 token 与输出长度，不在价目表。
2. **跨厂商 harness 不同时，SWE/Terminal/Frontier 分数不可横比**：厂商自报版与第三方实现版要分开记，只有同一 harness（如 AA Coding Agent Index）的分数能并排。某代模型集体停报某个基准时，写"未取到"，不要拿旧代分数顶替。
3. **tokenizer 换代要换算成"同文本成本"**。以厂商 pricing FAQ 当期声明为准（新 tokenizer 同样文本可能多产生约 30% token），报价需按倍数归一化后才可比。
4. **促销价 / 批次价 / 长上下文加价必须单列到期日与触发条件**：长上下文按"整条请求"还是"超出部分"加价差别巨大；隐式缓存与显式缓存的写费、存储费要分别核。

## 缓存对比做法

不要只比命中单价（各家多在输入价的 2.5%–10%，差异有限）。按"1M 前缀复用 N 轮"折算实付：第 1 轮走写缓存价 + N−1 轮走命中价。**写费有无**才是结构性差异，命中率越高越放大。

### 成本核算

用"固定 token 量的场景表"（单页生成 / 多轮 agent / 长上下文 / 批量 5 折）+ 月度混合权重，与第三方的 cost-per-task 并列但不混用：前者反映"你的负载"，后者反映"模型自身效率"。两套口径方向一致处才写进结论。自备脚本，改 token 量即可复算，别手算表格。

## 交付

单价表 / 缓存表 / 单任务成本表三张分开；能力表标清 harness 与日期；最后单独列"未取到"与"多源冲突值"。

## 取样集合、价格带对齐与排名反转

触发信号：用户说"每家取两个型号，详细比对"。本节防的是取样选错导致整篇返工。

### 取样集合听用户的

- "每家 N 个"的**具体型号由用户指定**，别替用户降档。用户点名「旗舰 + 次旗舰」时，不要自行换成「旗舰 + 便宜一档」——换一个型号就要重算全部单价表、场景表、排名和结论，等于整篇重做。
- 用户改口径时只换取样，不要顺带改口径、场景权重或结论方向；改动范围越小，返工越可审。

### 取样后先查价格带对齐

- 三家都是"旗舰 + 主力"不等于价格带对齐。若某家的两个取样都落在高端带，**显式写明**该档位缺口，并把未取样的低价型号放脚注（连它的单任务成本一起，否则读者会误以为换过去能省钱）。
- 价格带不对齐时，横向排名要标"档位不同"，不要给出"某家更贵"这种单句结论。

### 单一场景的排名会反转

- 固定 token 量的单场景表只能说明"这一种负载下谁便宜"；**混合负载（短请求 + 多轮 agent + 长上下文 + 批量 5 折）里，长上下文加价足以反转旗舰排名**。至少同时给「每场景一张表」+「一个混合权重列」，并说明权重是假设。
- 出现反转时要点名是哪个规则造成的（整条请求加价 / 缓存写费 / 促销价到期），否则读者会以为算错了。

## 价目做成数据表

- 把型号 × 输入 / 输出 / 缓存命中 / 写缓存 / 长上下文加价规则写成脚本里的数据表，改一行即可重算全部场景。手算或复制粘贴表格，改口径时必错。

## Codex 推理档位（max / ultra）与本地取证

## Codex 推理档位（max / ultra）与本地取证

问「Codex 里某模型支持哪些档、max / ultra 是什么」时，**先读本机 `~/.codex/models_cache.json`**（客户端按账号下发，比官网/博客准且离线可用），不要靠 `codex --version`（桌面版常不在 PATH）。用 Python `json.load` 逐 model 打印，别把几百 KB 整份读进对话。

取这些字段：`supported_reasoning_levels[].effort` + `description`、`default_reasoning_level`、`service_tiers`、`additional_speed_tiers`、`context_window`、`multi_agent_reasoning_effort`；当前生效值看 `~/.codex/config.toml` 的 `model_reasoning_effort`。

梯度 `low→medium→high→xhigh→max→ultra`：`max` 把同一条推理链推到最深；`ultra` = max + 自动任务委派（真起 subagent，子代理跑 `multi_agent_reasoning_effort`，常见 xhigh）。

- 2026-11-18 本机实测（client 0.169.0）：astra / sol 均 6 档、**默认 `low`**——没手动改档时谈「快/慢」的结论无效；只下发 Fast（`2x speed, increased usage`），Ultrafast（≤4.5×）在网页/Work 端与部分 20x 计划；astra `context_window` 272k、sol 500k，两者 `max_context_window` 872k。
- **tok/s 别照抄**：reasoning token 计入 output token，厂商/网关 tps ≠ 你的出字速度；Codex 无内置 tok/s（statusline 34 项里没有 throughput，社区数字来自 magpie / cc switch 之类反代看板）；网关 p50 是跨 effort、provider、tier 的混合值，不能读成「max 档」。
- 中文社区页 Cloudflare 403 时，`web_fetch(https://r.jina.ai/<URL>)` 能拿正文并保留楼层（nodeseek 对该代理封禁，只能引用搜索索引片段并标注非直读）。

四条口径的原文取证与社区实测表 → `references/throughput-metric-pitfalls.md`
