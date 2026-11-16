---
name: "dsh-agent-preset-live-verification"
description: "DSH preset在线验收入口；核对persona、权威工具清单、子代理provider/model与父turn/end，转总纲preset-live模式。"
whenToUse: "DSH preset在线验收入口；核对persona、权威工具清单、子代理provider/model与父turn/end，转总纲preset-live模式。 模型触发仍以description为准。"
disable-model-invocation: true
warm-triggers: "旧式 preset 的在线会话验收 / 会话日志多帧解压"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dsh-agent-preset-live-verification

## 何时调用

离线条件满足后取真实会话证据；旧preset目录已失效时先确认当版overlay机制。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **preset-live**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
