# Codex effort 档位的额度烧速（取证法与实测值）

适用于「high/xhigh/max 分别多快吃掉额度」。不适用于「某档支持哪些 effort / max 与 ultra 定义」→ `codex-effort-local.md`。

## 官方口径（2026-11-24 抓取）

- `learn.chatgpt.com/docs/pricing.md` Token rates 表：GPT-6.2 Astra = **200 / 10 / 1,000 credits** 每 1M（input / cached / output）；GPT-6.2 Sol = 50 / 2.5 / 250。**没有按 effort 的倍率，也没有各档 token 预算**；只给速度档（Fast 2x、Ultrafast 6x included usage）与 5h 消息数区间（Astra 6–50）。
- 官方只定性：「Model choice, context, **reasoning**, tool use, retrieval, and caching all affect usage」。
- reasoning token 计入 output，按 output 费率计（`developers.openai.com/api/docs/guides/reasoning.md`）。

## 本机 rollout 取证（能算到 1% 粒度）

数据在 `~/.codex/sessions/**/rollout-*.jsonl`，两类事件够用：

- `event_msg` / `thread_settings_applied`：`thread_settings.{model, reasoning_effort, service_tier}`。**按文件顺序跟踪**（同一 thread 中途会切模型/档位），不要只看首条。
- `event_msg` / `token_count`：`info.last_token_usage`（本轮 in/cached/output/reasoning）+ `rate_limits.primary.used_percent` / `window_minutes`（本机 10080 min 周窗）+ `plan_type`。

做法：流式读 jsonl，只对含 `token_count` / `thread_settings_applied` 的行 `json.loads`（大文件含 base64 图片，逐行全解会爆内存）。按官方费率把每轮折成 credits：`(in − cached)×200 + cached×10 + output×1000`（每 1M），再对相邻两次 `used_percent` 增量求 `credits per +1%`。

## 实测（本机 2026-11-16 → 11-24，周窗，9,154 次 token_count）

- **1% 周额度 ≈ 164 credits**（中位；astra max 171、sol max 164 —— 两模型几乎一致，说明没有按模型/档位的隐藏权重）。
- 每轮 reasoning token（astra）：high 58｜xhigh 90｜max 193；占单轮额度 ~2%/4%/8% → 常规轮只差 +1%/+5%。
- reasoning 尾部（p99）：high 292｜xhigh 939｜max 3,039 → 硬轮单轮额度 ≈ 1 : 1.2 : 1.9。
- 活跃小时烧速（事件间隔按 120s 截断）：354 / 509 / 452 credits/active-h ≈ 2.2 / 3.1 / 2.8 %/h，非单调 → 真实负载里档位不是主导项。
- 主导项是输入：平均 191k input/轮、98.6% 命中缓存，输入仍占 80% 额度。

## 交叉口径（第三方）

- Artificial Analysis 同题 cost-per-task：high $2.07｜xhigh $2.52｜max $4.00 → 1 : 1.22 : 1.93；Axton 实测 ultra ≈ 2.64× high。可辩护区间：xhigh 1.2–1.4×，max 1.9–2.7×。
- 社区「每小时吃周额度」只有单点（Plus + max ≈ 43%/50min），样本不可控，只能当上界。

## 坑

- **2026-11-22 起有计费异常**：openai/codex issue #63138 报「同负载烧快 ≥5×」，跨该日期的数字别混算，结论里写脚注。
- **Fast / Ultrafast 与 effort 是叠乘**（2x / 6x included usage），不要读成档位倍率。
- `used_percent` 是**账号级**的，多会话并行时分段归因会串味；只用「单会话主导」的时段算 `cr/pct`。
- 切档后上下文是否重新计费 **未验证**，不要据此给建议。
- 反代看板（magpie / cc-switch）只按模型/账户统计，**没有公开的按 effort 分档看板**。
