# Sleep / 权重更新的验证边界

先读目标 checkout 的 worker/allocator/loader 与文档。本轮 2026-11-16 获取的 [Ascend sleep 文档](https://github.com/vllm-project/vllm-ascend/blob/main/docs/source/user_guide/feature_guide/sleep_mode.md) 支持以下流程；接口可能变化，不照抄旧行号。

- Level 1 通常 offload 权重，Level 2 丢弃权重且需重新装载；“唤醒成功”不能代表已恢复有效权重。
- Level 2 的文档顺序：wake weights → reload/update 完整权重 → wake kv_cache → 新请求。只 wake weights 就生成可能缺 KV；不要为了显示中间退化而对未装权重的内存执行推理。
- 当前文档示例要求 enable_sleep_mode 和 `weight_nz_mode: 0`；核实本版适用性。HTTP 管理端点需 VLLM_SERVER_DEV_MODE，`/sleep` level 用 query；空体 200 不应 `.json()`。此类接口只在受控本地诊断中按任务启用。

旧材料“dummy 与 reload_weights 互斥”的证据只覆盖某些 loader 缺 get_all_weights；“update_weights 只允许 dummy”也不是通用约束。查看当前 loader、权重传输 engine 和调用状态机，确认参数名（旧版为 weights_path）、所有 rank 完成、派生权重/布局/图状态已更新。

验证分开写：HBM 释放与回升、服务状态、权重/版本载入、相同输入的输出或 raw logprob，以及确实更换 checkpoint 后的变化。A→B→A 或 C 文本恢复本身不能证明每个权重已更新；使用可识别的不同合法 checkpoint/张量指纹和目标观测。更严的逐位目标交给数值一致性 skill。

图模式行为以实际源码和复现为准。eager 成功只覆盖 eager，不把旧 issue “尚未闭合”永久写作现状，也不把地址稳定当作值已恢复。
