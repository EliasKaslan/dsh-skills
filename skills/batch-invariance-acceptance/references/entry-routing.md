| 现象 | 优先区分什么 | 可选材料 |
|---|---|---|
| 同侧相同输入重复也不同 | 状态/RNG、异步错误、实际算子、归约/编译路径 | [运行时与生命周期](references/runtime-and-updates.md) |
| 单独相同、混批/换位置不同 | 调度、packing、通信选择、行数/tiling、上下文游标 | [实验设计](references/validation-design.md)、[算子方法](references/numerical-methods.md) |
| decode 与 prefill 不同 | position/mask、KV 精度和布局、chunk/page 边界、状态更新 | [算子方法](references/numerical-methods.md) |
| 两侧分别稳定，交叉不同 | 参数/模型语义、cast/归约顺序、离散选择、scorer | [算子方法](references/numerical-methods.md) |
| old-logprob 相同，真实训练前向不同 | grad/train 分支、重计算、分片与训练专用算子 | [实验设计](references/validation-design.md) |
| logits 相同，logprob 不同 | 实际 scorer、词表分片归约、温度与处理顺序 | [算子方法](references/numerical-methods.md) |
| 首次相同，更新或 sleep/reload 后不同 | master→导出→接收→派生权重、版本/别名/cache/Graph | [运行时与生命周期](references/runtime-and-updates.md) |
| 新模型含类似结构或症状 | 检索带适用条件的历史案例，再验证本轮假设 | [知识索引](knowledge/index.md) |
