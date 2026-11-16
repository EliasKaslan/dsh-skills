---
name: "github-pr-flow"
description: "GitHub及GitCode PR交付、评审处置与当前head的CI核验。适用于\"帮我提PR / 更新PR正文 / CI为什么红 / 处理评审意见 / 修PR冲突\"。不适用：仅审版本实质差异 → 用 `git-tag-diff-audit`。"
whenToUse: "处理GitHub及GitCode PR交付、评审处置与当前head的CI核验时加载；模型看不到本节，触发以description为准。"
---

# PR / MR交付与门禁

## 何时调用

**触发**：帮我提PR / 更新PR正文 / CI为什么红 / 处理评审意见 / 修PR冲突。

**转交**：仅审版本实质差异见 [git-tag-diff-audit](../git-tag-diff-audit/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

用当前已配置的DSH连接器或进程级认证处理API，先发现schema与权限，先核对账号、规范远端、base/head和用户请求。旧skill记录的账号、CLA、免确认compile评论、强推/合并权限不构成本次授权；不为探权限向创建端点发试探写请求，也不按token前缀断定能力。

读目标仓AGENTS/CONTRIBUTING、PR模板、提交身份/DCO/CLA、title和lint规范。保护用户未提交改动；分支基线/工作树/暂存区分开检查。修正身份先确认CLA/DCO绑定邮箱，不能为过检查伪造他人身份。commit消息用UTF-8文件，检查实际提交tree、message与diff。

推送使用无凭据远端URL和进程内认证。push超时先查远端ref，避免重复写入；收到失败或权限错误先辨认证/策略/限流/网络。冲突前确认历史深度和merge-base，不用allow-unrelated-histories掩盖浅历史；保留两侧语义，不能整块theirs覆盖已合入修复。仅在本次已允许改写历史时对确切分支使用带期望SHA的lease；不强推共享分支或重指release/tag来“整理版本”。

PR标题/正文描述最终问题、结果行为和相关验证，保留仓库机器人管理字段；范围变化时同步更新。创建/更新后回读base/head/title/body，检查中文/换行、完整分页files和实际diff；hash不同可能因换行clean filters，要比较提交blob或受控规范化结果，不能悄悄抹掉语义差异。

CI按当前head SHA、run/job、配置和所有必需车道核对。PR标签、旧机器人评论与“最近一次绿”不足以证明当前提交通过。GitCode compile/retry、GitHub /e2e 等评论会通知他人并消耗CI资源，只按本次明确授权或适用技能授权发送；写后回读评论及派生run。避免重复触发，重试有截止和停止条件。

失败先读首个失败step及原始日志，对同head基线区分确定回归、既有问题、flaky与基础设施。相同commit有一绿一红只证明不稳定，不直接判平台故障；也不能统一SKIP gitleaks/bandit或把缺工具当通过。取消/skip/no-tests与失败分别记录，按合入策略判断必需证据是否齐。

收齐普通评论、inline review与review总结，逐条确认实际触发条件；机器人建议不是事实。合理修复后补对应回归，误报用源码/实验解释。回复评审或解决线程仍须本次沟通授权。作者不能自批所需审批，不能用标签冒充维护者认可。

交付PR链接、完整head、改动/验证/未覆盖、当前门禁与需要维护者动作。创建PR不自动授权合并、发release、回合并版本分支或给其他人发消息；已授权的交付步骤直接完成，不重复增加确认流程。

来源：DSH github-pr-flow、gitcode-pr-flow及其3份历史reference；2026-11-16去除固定仓权限、凭据URL、平台接口与门禁时延假设。具体API/标签从目标仓当前规范和一手文档读取。
