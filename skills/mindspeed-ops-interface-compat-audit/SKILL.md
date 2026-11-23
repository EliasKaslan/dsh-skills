---
name: "mindspeed-ops-interface-compat-audit"
description: "MindSpeed-Ops跨仓接口兼容与实际调用核查。适用于\"接口兼容吗 / 周边仓能调用吗 / 导入通过算过吗 / 新增了哪些算子 / 别名绑定对吗\"。不适用：只做版本树差 → 用 `git-tag-diff-audit`。"
whenToUse: "处理MindSpeed-Ops跨仓接口兼容与实际调用核查时加载；模型看不到本节，触发以description为准。"
---

# MindSpeed-Ops跨仓接口兼容与实际调用核查

## 何时调用

**触发**：接口兼容吗 / 周边仓能调用吗 / 导入通过算过吗 / 新增了哪些算子 / 别名绑定对吗。

**转交**：只做版本树差见 [git-tag-diff-audit](../git-tag-diff-audit/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

优先读取共享方法的 [接口与增量](../mindspeed-ops-smoke/references/interfaces.md)。对指定Ops与消费仓SHA逐层核对导出、alias/partial、架构条件、caller参数和真实执行；静态可绑定与调用成功分别报告。算子增量固定时间/版本和四件套含义，不由新增目录名直接判支持。只读源码能完成兼容清单；运行与报告发送按当前任务范围执行。

完整方法读取 [mindspeed-ops-smoke](../mindspeed-ops-smoke/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。
