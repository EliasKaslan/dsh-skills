---
name: "tilelang-op-generator"
description: "TileLang-Ascend 算子开发：内存同步、独立 golden、性能验证。适用于\"写算子 / 迁到NPU / 修kernel精度 / 尾块越界 / 测性能\"。不适用：环境安装 → 用 ascend-cann-env。"
whenToUse: "处理TileLang-Ascend算子开发及内存同步、独立golden和性能验证时加载；模型看不到本节，触发以description为准。"
---

# TileLang Ascend算子开发

## 何时调用

**触发**：用TileLang写算子 / 算子迁到NPU / 修kernel精度 / 尾块越界吗 / 怎么测性能。

**转交**：环境安装故障见 [ascend-cann-env](../ascend-cann-env/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

先恢复用户公式、shape/stride/dtype、mask/边界、输出与alias/in-place语义、前反向和性能目标。可合理推断的做成明确假设；不能默认所有算子输入[B,N]fp16、输出同形，或为了套模板改用户接口。

固定TileLang-Ascend/TVM/CANN/torch_npu SHA/版本、编译backend和SoC。查当前平台查询/API源码、示例和编译器约束，不能继承910B的UB192KB、L1512KB、L0C128KB、核数、分形或一维grid规则。无设备时可完成设计与可复现工程，交付标未编译/未实跑。

按需读 [设计与lowering](references/design.md) 和 [正确性与性能](references/validation.md)。保留真正kernel、独立golden和可重复测试；Triton同卡baseline在可用且有意义时加入，不要求每个任务再开发一个Triton算子，也不拿两套同错实现互证。

原始测试/compare模板包含 `{op}` 等占位，不是可直接运行的Python模块；旧模板留作历史材料，未经渲染和目标API验证不能执行。旧remote_run.py会清目标目录并使用shell拼接，本skill改为新任务目录显式部署、文件hash核对和已准入设备，不自动删共享路径或操作远端。

来源：DSH tilelang-op-generator及其15份附件，2026-11-16静态审查。当前目标后端API与真实NPU编译/执行需在具体开发任务中核对，旧performance/精度百分比表不作为统一门限。
