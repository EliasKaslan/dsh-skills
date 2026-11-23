---
name: "outlook-mailbox-control"
description: "Outlook邮箱任务入口；以当前DSH邮件MCP schema检索/读附件/草稿/发送并核验证据，转邮件总纲Outlook模式。"
whenToUse: "Outlook邮箱任务入口；以当前DSH邮件MCP schema检索/读附件/草稿/发送并核验证据，转邮件总纲Outlook模式。 模型触发仍以description为准。"
---

# outlook-mailbox-control

## 何时调用

只走 Outlook 当前 MCP：`mcp__outlook__search-tools` → `get-tool-schema` → `execute-tool`；QQ 别名/黄区格式只用于 QQ 发送。

加载并遵循 [qq-mail-control](../qq-mail-control/SKILL.md)，模式为 **Outlook**。只执行该模式的前置、步骤与验收；详细 reference 由该入口给出，工具、权限与认证以本会话实际 schema 与用户授权为准。
