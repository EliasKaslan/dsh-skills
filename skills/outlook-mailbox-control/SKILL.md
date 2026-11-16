---
name: "outlook-mailbox-control"
description: "Outlook邮箱任务入口；以当前DSH邮件MCP schema检索/读附件/草稿/发送并核验证据，转邮件总纲Outlook模式。"
whenToUse: "Outlook邮箱任务入口；以当前DSH邮件MCP schema检索/读附件/草稿/发送并核验证据，转邮件总纲Outlook模式。 模型触发仍以description为准。"
---

# outlook-mailbox-control

## 何时调用

只选Outlook当前MCP/schema/账号路径，使用其草稿/附件/分页/发送判据；QQ别名格式只适用相应QQ发送。

加载并遵循 [qq-mail-control](../qq-mail-control/SKILL.md)，模式为 **Outlook**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
