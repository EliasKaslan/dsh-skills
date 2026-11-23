# 旧repo-sync退役边界

原dsh-repo-sync自述2026-11-12退役。2026-11-23复核：旧`D:/repos/deepseek-harness`不存在；`run_daily.cmd`与`sync-dsh-repos.ps1`仍在，但只剩 157/226 字节的退役桩——只打印`DSH_HELPER_RETIRED`并退出 78（.cmd 用`exit /b 78`），不发网络、不读凭据、不碰git；计划任务`DSH-Repo-Sync`、`DSH-Skills-Publish`、`DSH-Skill-Drift`在268条计划任务里均已查不到。不能据旧文档写“脚本已删”，也不能因文件存在重启它。

原PS1（39,975 字节）确实能镜像删除、读取凭据、git fetch/merge/commit/push，还会把认证信息拼入URL；原文与三个计划任务XML留档在`D:/workspace/agent/skill/artifacts/legacy-skill-publish-backup-20261112/`。包括dry-run在内，先审读执行路径再决定是否适合运行；不推荐作为新流程入口。

保留的经验：验证绝对镜像目标确在范围内，排除整个凭据目录（仅*.token漏缓存），结构化字段脱敏后再扫残留，日志不含认证URL，并分别回读每个远端SHA。认证用当前已配置DSH GitHub/GitCode接口或经审查的按进程凭据方式，避免PAT进URL、命令行、FETCH_HEAD或日志。工具具体schema以本会话为准。

新发布器是插件`dsh-plugin-skill-publish`（`D:/workspace/agent/dsh-plugin-skill-publish` 1.0.0，工具`skill_publish` / `skill_publish_status`），与旧repo-sync是不同机制；批量改skills需看[发布事务边界](publisher-transaction.md)，不能恢复旧计划任务代替它。
