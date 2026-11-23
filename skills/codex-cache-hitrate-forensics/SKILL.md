---
name: codex-cache-hitrate-forensics
description: 用 Codex 会话日志复算 prompt cache 命中率；适用于 cached_tokens 下降、新版模型缓存或成本变差的传闻取证
disable-model-invocation: true
warm-triggers: codex 缓存命中率 / cached_tokens 下降 / 6.2 比 6.1 缓存变差
warm-reason: 低频取证类（只在该机型出现缓存/成本变差传闻时才用），不必每轮占目录成本。
---

# Codex prompt cache 命中率本地取证

## 何时调用

- 有人问「codex 里 X 模型缓存命中率是不是比 Y 低」「新版模型变慢了/变贵了」「是不是缓存策略改了」。
- 需要拿证据反驳或证实一个性能/成本传闻，而不是复述社区说法。
- 不适用：纯模型能力对比（转 llm-landscape-recon）；DSH 自身配置问题（转 dsh-agent-customization）。

## 数据源（只读）

- `~/.codex/sessions/**/rollout-*.jsonl`：每行一个 JSON，`type` ∈ session_meta / event_msg / response_item / turn_context / token_usage_record / compacted / world_state。
- 命中率只认 `type=="token_usage_record"` 的 `payload.usage`：`input_tokens`、`cached_input_tokens`、`cache_write_input_tokens`、`output_tokens`、`total_tokens`（每条 = 一次 API response）。
- 模型名不在 usage 里，要按 `payload.turn_id → turn_context.payload.model` 关联（turn_context 每个 step 重复出现，同 turn 无冲突）。
- `~/.codex/models_cache.json` 取模型清单与 `context_window`（决定谁能在 ≥256k 档取样）。
- `logs_2.sqlite` 只当补充：其中 cache 关键词多为 app 自身 `models cache: cache hit ... cache_ttl_secs=300` 与 HTTP 头 `cache-control: private, no-store`，**不是**请求级缓存遥测。

## 口径

- 命中率 = Σcached / Σinput（token 加权）。必须先验证 `cached ⊆ input`（应 0 条 cached>input 且 `total=input+output`）。
- `cache_write_input_tokens` 在本机常恒为 0 → 写侧无计量，只能从读侧反推。
- 命中 token 全部 128 对齐（gcd=128）说明各模型共用同一套前缀分块；粒度不同才是"切块策略变了"的迹象。

## 必剔除的三个混淆（否则一定测出假下降）

1. **换模型**：缓存按模型隔离。thread 内切换模型后的前几个请求命中率会掉到 60–65%，随后回到 97%+。
2. **compaction**：`compacted` 事件替换历史前缀，紧随其后那次请求必然大幅未命中（实测 27–67%）。
3. **thread 冷启**：thread 首个请求几乎全冷，且与"会话是否续接"高度混淆，样本通常只有个位数，不要用它下结论。

还要按 **input 规模档 × thread 内位置** 匹配后再比：命中率随上下文长度单调上升，6.1 可能有 39% 请求在 ≥256k 档而 6.2 某型号 0%（有效窗口只到 ~256k），不匹配就把窗口差异误读成策略差异。

## 统计陷阱

- 同会话请求共享同一前缀，属**伪重复**：token 级两比例 z 检验会给出 z≈−296 这种假显著，不可采信。
- 用**会话级** bootstrap CI / 会话等权中位数；若单条会话占某模型 80%+ 请求，合并值本质是"两条长会话之比"，必须点名。
- 结论落到两个数：命中率差（pp）与**未命中绝对量占比**。命中率 98.9%→97.8% 看着只差 1pp，但未命中占比从 1.07% 翻到 2.00%——"感觉严重变差"通常来自后者。

## 已确认事实：GPT-6.2 的 instructions 改动

官方 [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) 与 [Using GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model)：GPT-6.2 起 Responses API 把顶层 `instructions` **追加在 `input` 之后、落在缓存断点之外，每次请求都按未缓存计费**（即使内容完全相同）；要可缓存必须放进 `input` 第一条 `developer` 消息。同版本还有 "prefix edits"：中途改前缀/换模型会丢 reasoning items。（2026-11-23 复核：latest-model 页原文仍为 `Models starting with GPT-6.2 append top-level instructions after input in the Responses API`。）

所以传闻要分两半看：

- 第三方客户端把系统提示放在 `instructions` → `cached_tokens` 恒为 0，命中率断崖（社区报 6.1 97.4% → 6.2 46.4%）。这是客户端字段位置 + 计费口径，不是模型命中率变差。
- **原生 Codex 不受影响**：可本地自证 `session_meta.payload.base_instructions` 的文本逐字等于 `response_item` 里第一条 `role:"developer"` 消息，且 `session_meta.payload` 没有 `instructions` 键；反证是稳态每请求未命中仅约 1%（若 6.8K 系统提示按未缓存计费，残留不可能是这个量级）。

另有正面事实：6.1/6.2 两代带点号的模型的缓存读折扣是 0.05×（其它模型 0.1×），命中率打平也仍然更便宜。2026-11-23 核 https://developers.openai.com/api/docs/pricing.md ：`gpt-6.2-sol` input $1.00 / cached $0.05，`gpt-6.1-sol`、`gpt-6.1-terra` 同为 0.05×；`gpt-6-astra` 仍是 $5.00 / $0.50 = 0.1×。同页还单列 30m 写（1.25×）与 12h 写（2.5×），别把写费当命中价。

## 复算步骤

1. 全量扫 rollout，按 `response_id` 去重（`~/.codex/sessions` 下同名 thread 会有多份快照），建立 `turn_id→model` 映射，落一份 rows.json。
2. 按模型出 `响应数 / Σinput / Σcached / 命中率`。
3. 按 `规模档 × 位置段`（pos1 / pos2-5 / pos6+）出交叉表做匹配比较。
4. 稳态口径：剔除 thread 前 10 个请求 + 换模型后前 5 个请求，再出表。
5. 会话级 bootstrap 差值 CI；报 pp 差与未命中绝对量。

## 坑

- Windows 下给 python 传参数别用 pwsh heredoc（`python - <<'PY' ... PY` 会得到 `FileNotFoundError: [Errno 2] No such file or directory: '--'`）→ 把脚本写到 `.py` 再 `python path.py`。
- 别把 `codex-auto-review` 混进对比：它是另一条模型路由，命中率天然低（~96%）。
- sqlite 只读打开（`mode=ro`），且有 `-wal` 在写；主文件 mtime 不变就说明没被脚本改过。
