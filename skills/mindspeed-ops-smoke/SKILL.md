---
name: "mindspeed-ops-smoke"
description: "MindSpeed-Ops接口兼容、wheel验收及UT和ATK冒烟。适用于\"跑Ops冒烟 / ATK精度怎么判 / UT全绿了吗 / wheel能用吗 / 跨仓接口兼容吗\"。不适用：基础CANN环境故障 → 用 `ascend-cann-env`。"
whenToUse: "处理MindSpeed-Ops接口兼容、wheel验收及UT和ATK冒烟时加载；模型看不到本节，触发以description为准。"
---

# MindSpeed Ops工程验证

## 何时调用

**触发**：跑Ops冒烟 / ATK精度怎么判 / UT全绿了吗 / wheel能用吗 / 跨仓接口兼容吗。

**转交**：基础CANN环境故障见 [ascend-cann-env](../ascend-cann-env/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

固定Ops与消费仓完整SHA、目标SoC/架构、CANN/torch_npu/Triton、Python ABI和验证任务。沿用用户选择的发布分支或实验栈，不因旧案例默认master、26.2.0、A3/A5或某个镜像。基础环境与资源准入用现有ascend-cann-env/ascend-server-layout。

按任务读取：[接口与增量](references/interfaces.md)、[wheel和构建](references/build.md)、[UT/ATK和CI](references/smoke.md)。三个能力互相提供证据但不能代替：源码能import不证明wheel能用，wheel能安装不证明目标算子执行，CI绿不证明发布配套上的精度。

包名/版本串、镜像tag、SOC_VERSION和HAS标志都不是源码/产物来源的充分证据。记录模块__file__、metadata、源码/二进制hash、实际加载库、目标分支与设备派发。防止旧wheel遮住源码或源码目录遮住待验wheel。

静态检查、导入、编译、执行、数值、性能分别给结论；未知接口/缺依赖/目标平台未实现/资源错误/有效数值差异分开登记。没有NPU或构建权限时继续完成源码/包结构核对和最小复现准备，明确未执行范围，不将历史PASS继承到新SHA。

来源：DSH mindspeed-ops-interface-compat-audit、mindspeed-ops-smoke、mindspeed-ops-whl-build，2026-11-16整理。旧固定机器、邮箱、自动发信、版本组合及门禁状态未继承；旧“半覆盖Triton版本对比”流程剔除。
