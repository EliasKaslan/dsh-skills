---
name: "dsh-skill-self-audit"
description: "DSH skill集合体检：字段、引用、重复、预算与文件摘要核对，用只读校验器出结论。"
whenToUse: "批量改完skill后跑校验与预算、或需要定期体检整个集合时。"
---

# dsh-skill-self-audit

## 何时调用

审计集合字段、引用、重复与摘要；现有runner顶层/调度副作用先审，不直接启动headless。

加载并遵循 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)，模式为 **周期体检**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。

原scripts/run_daily.cmd和skill_audit_daily.py本次同路径退役，调用直接exit78；扫描/gate/budget资产未一并禁用。
