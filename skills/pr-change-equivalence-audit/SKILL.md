---
name: "pr-change-equivalence-audit"
description: "PR改前改后的接口、数值边界与性能等价性审查。适用于\"PR是等价改写吗 / mask乘法安全吗 / 精度变了吗 / 性能没变化吗 / bugfix有副作用吗\"。不适用：提交PR与跟进门禁 → 用 `github-pr-flow`。"
whenToUse: "处理PR改前改后的接口、数值边界与性能等价性审查时加载；模型看不到本节，触发以description为准。"
disable-model-invocation: true
warm-triggers: "这个 PR 是不是等价改写 / 精度性能没变吧"
warm-reason: "低频审计方法论"
---

# PR改前改后的接口、数值边界与性能等价性审查

## 何时调用

**触发**：PR是等价改写吗 / mask乘法安全吗 / 精度变了吗 / 性能没变化吗 / bugfix有副作用吗。

**转交**：提交PR与跟进门禁见 [github-pr-flow](../github-pr-flow/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

优先使用共享方法的PR等价性章节，固定base/head及完整caller。分别检验接口、数值契约、±0/NaN/Inf/subnormal边界与性能；reference容差通过不等于A=B。where改乘法、cast/融合/归约变化需同输入对照，源码推导、作者自述、独立运行和未验证分列。

完整方法读取 [git-tag-diff-audit](../git-tag-diff-audit/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。
