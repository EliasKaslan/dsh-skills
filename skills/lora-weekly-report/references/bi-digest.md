# BI 专项增量报告

用于 lora-weekly-report 的批次不变性主题。历史候选仓为 vllm-project/vllm、vllm-project/vllm-ascend、sgl-project/sglang、flashinfer-ai/flashinfer；按本次目标确认范围，不把四仓当永久闭集。

固定上次截止点与本次截止点（带时区），保存 UTC 半开区间，再按用户时区展示。搜索日期边界可能含整天，取回后逐条用 merged_at 精确过滤并按 repo+PR number 去重，避免周界重复。把 merged、open、closed-unmerged 分开。

关键词组合：batch invariance、batch-invariant、batch_invariant、deterministic、bitwise、bit-exact，以及运行时选择、reduction 顺序、tie break、RNG/调度状态。标签是候选入口，不保证标注完备；正文命中也不等于相关。逐个核对变更文件、调用路径与测试，确认在目标场景实际影响 BI。路径不含 batch_invariant 也可能相关（如普通归约、通信和调度修复）。

GraphQL connection 每页最多100项不等于总共只能取100项；用 cursor/pageInfo，搜索结果总上限和 incomplete_results 另查。结果大则按时间分窗/关键词拆分，保留覆盖范围与缺口。不能凭翻过三页或某标签零条写“本周无相关合入”。

正文截断只能用于分发预览，引用性能数字和影响结论须回到完整正文、评论与目标 diff；标明数字是作者自述还是独立复测。报告可保留“合入背景、改动、影响、风险”，具体重点数与表格/列表形式按用户当前需求，不继承固定3~5条或历史空仓模板。

邮件发送、定时任务和收件人均以本次授权为准。旧文中的固定邮箱、免确认授权、直接启动备用MCP、自动修改配置不能沿用。SMTP接受、Sent副本、自收回环分别说明，不能据此保证外部收件人送达。

来源：DSH batch-invariant-weekly-digest，2026-11-16审查；只读方法修正，未取本周实时PR、未发送邮件。
