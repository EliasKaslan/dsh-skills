---
name: "batch-invariant-weekly-digest"
description: "BI批次不变性周报与窗口内已合入PR清单。适用于\"跑BI周报 / 不变性有什么进展 / 这周合了哪些PR / 周报改成列表 / 查确定性进展\"。不适用：模型数值验收 → 用 `batch-invariance-acceptance`。"
whenToUse: "处理BI批次不变性周报与窗口内已合入PR清单时加载；模型看不到本节，触发以description为准。"
---

# BI批次不变性周报与窗口内已合入PR清单

## 何时调用

**触发**：跑BI周报 / 不变性有什么进展 / 这周合了哪些PR / 周报改成列表 / 查确定性进展。

**转交**：模型数值验收见 [batch-invariance-acceptance](../batch-invariance-acceptance/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

先按共享周报方法恢复仓库范围、基线和用户时区，读取其中BI专项参考。BI/PD/确定性标签、路径、作者性能声称用于召回和证据分级，不能替代完整分页与PR详情。精确merged_at按UTC半开窗口过滤并按仓库/PR去重；报告列覆盖限制。生成报告不自动发邮件或创建周期任务。

完整方法读取 [lora-weekly-report](../lora-weekly-report/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。
