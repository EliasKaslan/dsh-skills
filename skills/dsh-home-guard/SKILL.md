---
name: "dsh-home-guard"
description: "DSH home备份与自愈排查：外置守护、失败不固化删除、隔离恢复与hash核验。"
whenToUse: "守护状态异常、怀疑关键文件被删、或要恢复到独立空目录时。"
---

# dsh-home-guard

## 何时调用

先只读查守护状态与当前源码；恢复到独立空目录核验，不删除真实关键文件作测试。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **守护恢复**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
