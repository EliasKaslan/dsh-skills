---
name: "batch-invariant-weekly-digest"
description: "BI批次不变性周报与窗口内已合入PR清单。适用于\"跑BI周报 / 不变性有什么进展 / 这周合了哪些PR / 周报改成列表 / 查确定性进展\"。不适用：模型数值验收 → 用 `batch-invariance-acceptance`。"
whenToUse: "处理BI批次不变性周报与窗口内已合入PR清单时加载；模型看不到本节，触发以description为准。"
---

# BI批次不变性周报与窗口内已合入PR清单

## 何时调用

**触发**：跑BI周报 / 不变性有什么进展 / 这周合了哪些PR / 周报改成列表 / 查确定性进展。

**转交**：模型数值验收见 [batch-invariance-acceptance](../batch-invariance-acceptance/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

先按共享周报方法恢复仓库范围、基线和用户时区，读取其中BI专项参考。BI/PD/确定性标签、路径、作者性能声称用于召回和证据分级，不能替代完整分页与PR详情。精确merged_at按UTC半开窗口过滤并按仓库/PR去重；报告列覆盖限制。生成报告不自动发邮件或创建周期任务。

完整方法读取 [lora-weekly-report](../lora-weekly-report/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。

## 取数覆盖与训推一致性分诊

**GraphQL `search` 的硬上限是每次查询 1000 条结果，不是"每页 100 条"**：两周窗口下单仓 merged 可达 1200+ 条，翻到第 10 页就静默停住，尾部 PR 全丢。做法是按 3~5 天切子窗口分别取，按 PR 号去重；写完先断言 `fetched == issueCount`，相等才敢说"该仓无相关合入"。

**分诊三档，正文命中最不可信**：label（vLLM 的 `batch-invariance`）> 标题命中 > 正文命中。正文里 `0-diff`、`on policy`、`bitwise` 会命中 PR 模板、测试输出和别的语义（如"on policy"出现在无关句子里），必须回标题或 changed-files 复核，否则会把一堆无关 PR 拉进表。

**训推一致性（training-inference consistency）不是靠关键词就能捞全，按载体找**：
- vLLM：`[RL]` / `Model Loader` / `Weight Transfer` 系列，关键判据是 `VLLM_RELOAD_MODE`、`direct reload`、"重载后与冷启动逐位相同"；
- vLLM-Ascend：`RLHF` + IPC/HCCL 权重搬运 e2e、Weight Checker；
- SGLang：`sglang-miles` 前缀与 `weight-sync` / `weight-update`，多为"权重同步后派生缓存/分块更新丢半"这类静默错；
- FlashInfer：`training-forward surface` / `stateless call`（trainer 前向复用推理类），以及"把训练 kernel 移出库"这种 scope 切分提交。

**条目 >30 条时按仓拆给子代理**：每个子代理只拿该仓的 jsonl 路径 + 指定 PR 号清单，产出 `rows_<repo>.json`（number / title / time / background / what / impact / evidence 七个字段，每格 ≤85 字），主 agent 只做排序、定加粗与拼装——这样回执能压到 20 行以内，也避免一次性把 50 条正文读进主编排上下文。

**时间窗边界**：用户说"截止到 X 日晚"时，取 X 日 23:59（用户时区）换成 UTC 半开区间上界；越界 PR 单独列 dropped 并写原因，别悄悄丢。
