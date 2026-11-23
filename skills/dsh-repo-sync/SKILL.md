---
name: "dsh-repo-sync"
description: "退役DSH仓库同步审查入口；定位旧脚本/任务并保留镜像和凭据排除经验，不恢复旧自动发布。"
whenToUse: "被问到 DSH-Repo-Sync / run_daily / sync-dsh-repos 这些旧入口，或旧镜像同步策略是否还该用时。"
disable-model-invocation: true
warm-triggers: "私仓同步 / DSH-Repo-Sync / deepseek-harness / ALERT.md / sync-dsh-repos"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dsh-repo-sync

## 何时调用

此入口不启动旧run_daily或sync-dsh-repos；现发布插件与旧镜像任务分开取证。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **退役同步审查**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。

原run_daily.cmd与sync-dsh-repos.ps1本次同路径退役，调用直接exit78，不执行镜像、读取凭据或git操作。
