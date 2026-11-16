---
name: github-org-delta-watch
description: "GitHub组织与发行差集入口，按既有基线追踪仓库、PR、commit和release变化。"
whenToUse: "已有GitHub组织/仓库基线，需要梳理后续commit、PR、release与观察点变化。"
---

# GitHub 组织与发行差集

按 [研究增量与主题周报](../lora-weekly-report/SKILL.md) 恢复组织/仓库范围、基线日期及完整 commit SHA，分页读取仓库、PR、release 与 compare。pushed_at 只召回线索，内容差异以目标分支与实际 diff 为证；注意 compare 截断和预发布。

分别报告已合入、已发版、准备中和未覆盖项。签名 verified、少量提交或沉寂不能单独判定维护者身份或死仓；不因旧承诺推断下一版必带。保留来源和采样时间，报告生成不自动发信或设置周期。
