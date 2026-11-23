---
name: "subagent-toolset-precheck"
description: "子代理工具能力预检：按实际schema与只读probe核对网络/命令/落盘。"
whenToUse: "子代理声称无网络、无命令或不能写盘，需要先核对真实能力时。"
disable-model-invocation: true
warm-triggers: "子代理工具受限 / 让它回报函数清单"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# subagent-toolset-precheck

## 何时调用

查实际schema并做最小只读probe；需要网络/命令/写盘时选对应角色，不靠模型自述能力。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **工具能力预检**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
