# 旧BI工具状态

四个原路径保留为明确失效入口，均输出BLOCKED_LEGACY_TOOL_RETIRED并退出2，不加载torch、vLLM、动态库或设备，也不写结果文件。完整方法与知识案例由 [主入口](../SKILL.md) 承载。

- `bi_equivalence.py`：confirmed-defective。空结果、zip截断、数值equal冒充逐位；float32重建与零轮次边界不满足验收证据契约。
- `bi_matrix.py`：confirmed-defective。PASS日志可覆盖进程失败；NOT_RUN与未知枚举可被阶段汇总忽略，不能完整对账场景与rank。
- `bi_ops_triage.py`：confirmed-defective。空CSV集合仍PASS；旧白名单/比例/芯片默认及排序规范化不能证明模型数值一致。
- `bi_preflight.py`：superseded。仅元数据与名称/首个动态库探测不能完成当前框架/硬件语义准入，旧固定映射不作当前能力判据。

历史源码保存在修改前备份；不是可供自动fallback执行的备选实现。需恢复原功能时按当前API实现完整性校验，并先用缺请求、缺rank、空数据、未知状态及异常退出负控验证判词。旧预检的导入/注册/动态库线索仍可用于人工调查，不能当模型验收。
