---
name: "dsh-agent-preset-verification"
description: "DSH preset/overlay离线验证入口；核对当前loader、组合、配置语义与工具策略，转总纲preset-offline模式。"
whenToUse: "DSH preset/overlay离线验证入口；核对当前loader、组合、配置语义与工具策略，转总纲preset-offline模式。 模型触发仍以description为准。"
disable-model-invocation: true
warm-triggers: "旧式 .agent-presets 目录的离线校验"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dsh-agent-preset-verification

## 何时调用

先验证当前loader与组合入口；保留scanRoot等历史语义，但不据旧目录存在宣称已挂载。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **preset-offline**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
