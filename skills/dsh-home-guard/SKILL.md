---
name: "dsh-home-guard"
description: "DSH home守护与恢复入口；检查外置备份、自愈失败、隔离恢复和内容核验，转总纲守护恢复模式。"
whenToUse: "DSH home守护与恢复入口；检查外置备份、自愈失败、隔离恢复和内容核验，转总纲守护恢复模式。 模型触发仍以description为准。"
---

# dsh-home-guard

## 何时调用

先只读查守护状态与当前源码；恢复到独立空目录核验，不删除真实关键文件作测试。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **守护恢复**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
