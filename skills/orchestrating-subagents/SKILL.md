---
name: "orchestrating-subagents"
description: "DSH子代理编排入口；明确目标、工具能力、可写边界、产物与验收，转运行时总纲的委派编排模式。"
whenToUse: "DSH子代理编排入口；明确目标、工具能力、可写边界、产物与验收，转运行时总纲的委派编排模式。 模型触发仍以description为准。"
---

# orchestrating-subagents

## 何时调用

以当前DSH schema和宿主指令确定能力/权限，按目标/可写边界/产物/验收派发，不固定工具数量。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **DSH委派编排**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
