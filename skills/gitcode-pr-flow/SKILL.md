---
name: "gitcode-pr-flow"
description: "GitCode PR交付、门禁与评审跟进，使用当前配置认证。适用于\"GitCode提PR / 双CI怎么判 / PR冲突了 / 门禁标签缺了 / backport怎么验\"。不适用：仅核实代码是否等价 → 用 `pr-change-equivalence-audit`。"
whenToUse: "处理GitCode PR交付、门禁与评审跟进，使用当前配置认证时加载；模型看不到本节，触发以description为准。"
---

# GitCode PR交付、门禁与评审跟进，使用当前配置认证

## 何时调用

**触发**：GitCode提PR / 双CI怎么判 / PR冲突了 / 门禁标签缺了 / backport怎么验。

**转交**：仅核实代码是否等价见 [pr-change-equivalence-audit](../pr-change-equivalence-audit/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

沿共享交付方法执行，但平台固定为本次GitCode实例：先发现当前连接器schema、账号/权限、仓库MR/PR与Actions接口；标签、compile/retry评论及双CI车道按目标仓当前规范核对。门禁绑定当前head SHA，不拿历史评论或最近一次绿代替。保留原任务已有授权，不能继承旧仓的免确认compile、强推、合并或release权限。

完整方法读取 [github-pr-flow](../github-pr-flow/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。
