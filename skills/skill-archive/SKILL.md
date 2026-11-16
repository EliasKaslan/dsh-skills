---
name: "skill-archive"
description: "DSH冷备skill索引入口；核实索引、路径和正文再加载，转作者技能归档查找模式。"
whenToUse: "DSH冷备skill索引入口；核实索引、路径和正文再加载，转作者技能归档查找模式。 模型触发仍以description为准。"
---

# skill-archive

## 何时调用

先验证INDEX及目标正文，再加载实际方法；不要凭摘要编造已归档能力。

加载并遵循 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)，模式为 **归档查找**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
