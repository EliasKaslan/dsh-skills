---
name: lora-weekly-report
description: "按明确时间窗和基线核查GitHub组织、仓库、LoRA或批次不变性进展并生成增量简报；适用于周报、观察点变化和已合入清单，生成报告不自动发信或创建定时任务。"
whenToUse: "需要GitHub组织或仓库的基线增量、LoRA/批次不变性周报或已合入清单；发信与定时任务另依当前授权。"
---

# 研究增量与主题周报

从已有报告恢复基线日期/commit、观察点与仓库范围。没有基线时明确采用时间窗或建立首个快照；区分滚动7×24小时、自然周与两次采样的差集。用用户时区展示，内部按有时区UTC半开区间 `[start,end)` 过滤，避免相邻周重复。

## 获取与判定

按当前DSH可用GitHub工具或已授权API能力（先检查实际工具schema与权限）读取，一次保存响应和必要字段。跟随分页/Link，处理search上限、incomplete_results、API限流与失败；规模超上限时按时间/仓库细分并去重，不能只取首100。标题/label/路径只是召回策略，说明检索覆盖，不声称零漏报。

PR的merged_at非空且在窗口内才计已合入；closed不等于merged。搜索结果缺精确字段时读PR详情，核查目标分支、merge SHA、实际diff/测试与revert。不把合入称作已发版、实际可用或性能通过。open/draft候选另列，不填进已合入合计。

组织仓库列表先分页；pushed_at用于筛选线索，分支/tag/默认分支SHA和文件变化才支撑内容差异。签名verified只说明签名校验，不证明官方维护者“撒手”或社区贡献性质；几条merge提交、沉寂时间不足以判死仓。

发行差集固定base/head完整SHA，使用commit图和compare覆盖，注意文件/patch截断；releases/latest可能不含预发布，先明确发布类别。升级指南、ADR的implemented和代码存在都是准备进展，不能保证下一版必带；安装包某字节标记存在也不证明功能注册/启用。缺issue跟踪功能不意味着PR必禁用，分别查可见性。

## 工具与输出

[scripts/filter_merged_prs.py](scripts/filter_merged_prs.py) 只读本地采集JSON，做时区、半开窗口、ID去重、merged判定和覆盖提示；不联网、不读PAT、不发信。输入与局限见 [references/report-input.md](references/report-input.md)。

按问题给活跃仓、观察点变化、已合入主题、在途/风险和未覆盖证据，不强制所有报告四节。写背景→实际改动→适用对象/限制，数字只取源证据。LoRA可用 [references/lora.md](references/lora.md) 的既有格式；BI/PD/确定性专项读 [references/bi-digest.md](references/bi-digest.md)。

报告留任务目录；发送邮件、发群或设置周期需要本轮/仍有效的明确用户授权，再使用当前连接与收件人。旧技能中的固定邮箱和“每周自动跑”不产生新授权，发送副本也不证明收件方投递成功。

来源：旧 github-org-delta-watch、lora-weekly-report，及 batch-invariant-weekly-digest 专项材料；2026-11-16审查，历史仓状态/数量不作当前事实。
