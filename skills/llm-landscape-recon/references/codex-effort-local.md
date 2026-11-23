# Codex 推理档位（max / ultra）与本地取证

问「Codex 里某模型支持哪些档、max / ultra 是什么」时，**先读本机 `~/.codex/models_cache.json`**（客户端按账号下发，比官网/博客准且离线可用），不要靠 `codex --version`（桌面版常不在 PATH）。用 Python `json.load` 逐 model 打印，别把几百 KB 整份读进对话。

取这些字段：`supported_reasoning_levels[].effort` + `description`、`default_reasoning_level`、`service_tiers`、`additional_speed_tiers`、`context_window`、`multi_agent_reasoning_effort`；当前生效值看 `~/.codex/config.toml` 的 `model_reasoning_effort`。

梯度 `low→medium→high→xhigh→max→ultra`：`max` 把同一条推理链推到最深；`ultra` = max + 自动任务委派（真起 subagent，子代理跑 `multi_agent_reasoning_effort`，常见 xhigh）。

- 2026-11-18 本机实测（client 0.169.0）：astra / sol 均 6 档、**默认 `low`**——没手动改档时谈「快/慢」的结论无效；只下发 Fast（`2x speed, increased usage`），Ultrafast（≤4.5×）在网页/Work 端与部分 20x 计划；astra `context_window` 272k、sol 500k，两者 `max_context_window` 872k。2026-11-23 用 client 0.171.0 的缓存复核，上述档位、默认档与窗口值未变（`gpt-6.2-sol` / `gpt-6.2-astra` / `gpt-6.1-*` 均 6 档且 `default_reasoning_level=low`）。
- **tok/s 别照抄**：reasoning token 计入 output token，厂商/网关 tps ≠ 你的出字速度；Codex 无内置 tok/s（statusline 34 项里没有 throughput，社区数字来自 magpie / cc switch 之类反代看板）；网关 p50 是跨 effort、provider、tier 的混合值，不能读成「max 档」。
- 中文社区页 Cloudflare 403 时，`web_fetch(https://r.jina.ai/<URL>)` 能拿正文并保留楼层（nodeseek 对该代理封禁，只能引用搜索索引片段并标注非直读）。

四条口径的原文取证与社区实测表 → `throughput-metric-pitfalls.md`。
