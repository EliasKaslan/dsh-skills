# 旧repo-sync退役边界

原dsh-repo-sync自述2026-11-12退役，旧D:/repos/deepseek-harness不存在，但run_daily.cmd和sync-dsh-repos.ps1仍有文件。不能据旧文档写“脚本已删”，也不能因文件存在重启它。

旧PS1能镜像删除、读取凭据、git fetch/merge/commit/push，还会把认证信息拼入URL；包括dry-run在内，先审读执行路径再决定是否适合运行。此次没有执行旧同步，原辅助脚本待明确退役或修复，不推荐作为新流程入口。

保留的经验：验证绝对镜像目标确在范围内，排除整个凭据目录（仅*.token漏缓存），结构化字段脱敏后再扫残留，日志不含认证URL，并分别回读每个远端SHA。认证用当前已配置DSH GitHub/GitCode接口或经审查的按进程凭据方式，避免PAT进URL、命令行、FETCH_HEAD或日志。工具具体schema以本会话为准。

新发布器dsh-plugin-skill-publish与旧repo-sync是不同机制；批量改skills需看publisher-transaction.md，不能恢复旧计划任务代替它。
