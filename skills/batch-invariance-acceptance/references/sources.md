# 来源与适用边界

整理日期：2026-11-16。本 skill 为根据实际昇腾案例重新归纳的方法集；没有复制两份资料的固定流水线，也不要求安装它们才能使用。

## zero-mismatch-rl

用户指定入口：[Inferact/zero-mismatch-rl/skill](https://github.com/Inferact/zero-mismatch-rl/tree/main/skill)。整理时核对的 main 为 `136aca87d8158adae94b5a272fa4a8a6d5cd6939`，按该版本阅读了方法入口、数值契约和验证章节：

- [方法入口](https://github.com/Inferact/zero-mismatch-rl/blob/136aca87d8158adae94b5a272fa4a8a6d5cd6939/skill/README.md)
- [数值契约](https://github.com/Inferact/zero-mismatch-rl/blob/136aca87d8158adae94b5a272fa4a8a6d5cd6939/skill/numerical-contracts.md)
- [验证与证据](https://github.com/Inferact/zero-mismatch-rl/blob/136aca87d8158adae94b5a272fa4a8a6d5cd6939/skill/validation.md)

借鉴其冻结语义后隔离差异、区分两条训练前向、按更新版本留证据的思想。本文不继承其 C0–C10 门禁、固定 benchmark/审批点、默认训练实现、CUDA 工具或 kernel 语言限制。其 backward 确定性选择也不覆盖本 skill 中 torch_npu level3 的要求。参考资料是设计输入，不自动成为当前任务的操作授权。

## MindSpeed-Agent batch-invariance-validation

用户指定入口：[Ascend/MindSpeed-Agent 插件](https://gitcode.com/Ascend/MindSpeed-Agent/tree/master/plugins/batch-invariance-validation)。网页抓取受限时，整理时通过公开 contents API 核对了 master 上以下文件；blob SHA 表示读取版本，不冒充仓库 commit：

| 参考文件 | blob SHA |
|---|---|
| [插件 AGENTS.md](https://gitcode.com/Ascend/MindSpeed-Agent/blob/master/plugins/batch-invariance-validation/AGENTS.md) | `ce4d4782cd95dca32e589d48923872644d6c8dc2` |
| [environment-admission/AGENT.md](https://gitcode.com/Ascend/MindSpeed-Agent/blob/master/plugins/batch-invariance-validation/agents/environment-admission/AGENT.md) | `90c6abba790c03cbd853a026f884bd9448135386` |
| [phase1-operator-analysis/AGENT.md](https://gitcode.com/Ascend/MindSpeed-Agent/blob/master/plugins/batch-invariance-validation/agents/phase1-operator-analysis/AGENT.md) | `78b0f9b1abae2c0e6a70d739947981c28b8438db` |
| [phase2-functional-validation/AGENT.md](https://gitcode.com/Ascend/MindSpeed-Agent/blob/master/plugins/batch-invariance-validation/agents/phase2-functional-validation/AGENT.md) | `4250f971013b23966c40fb4a5dc8d8c397eb2a02` |

借鉴其分开核验算子包/产物/注册、从真实 profiling 和调度证据定位、修复后回到失败场景的方法。本 skill 不继承其 orchestrator/多 Agent 状态机、固定 TP/BS/长度、万条算子用例、数据集或固定重试次数。

## 本轮实际经验

[DeepSeek V4.1 Flash L4 案例](../knowledge/cases/2026-11-15-dsv41-flash-l4.md) 提供具体昇腾适配经验，保留硬件、版本和验证范围。主文档将它们抽象为可选方法，固定行数、metadata 大小、FP32/BF16 分支、通信选择、scorer block 等数值只保留在案例中。

技术 API、SO ABI、芯片支持和框架实现随版本变化；使用时优先核对本地实际加载源码及产物，必要时查对应版本官方材料。历史链接/结论不替代本轮实测。
