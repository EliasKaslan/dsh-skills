---
name: "gitcode-pr-flow"
description: "GitCode PR交付、门禁与评审跟进。适用于\"GitCode提PR / 双CI怎么判 / PR冲突 / 门禁标签 / backport\"。不适用：仅核实代码是否等价 → pr-change-equivalence-audit。"
whenToUse: "处理GitCode PR交付、门禁与评审跟进，使用当前配置认证时加载；模型看不到本节，触发以description为准。"
---

# GitCode PR交付、门禁与评审跟进，使用当前配置认证

## 何时调用

**触发**：GitCode提PR / 双CI怎么判 / PR冲突了 / 门禁标签缺了 / backport怎么验。

**转交**：仅核实代码是否等价见 [pr-change-equivalence-audit](../pr-change-equivalence-audit/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

沿共享交付方法执行，但平台固定为本次GitCode实例：先发现当前连接器schema、账号/权限、仓库MR/PR与Actions接口；标签、compile/retry评论及双CI车道按目标仓当前规范核对。门禁绑定当前head SHA，不拿历史评论或最近一次绿代替。保留原任务已有授权，不能继承旧仓的免确认compile、强推、合并或release权限。

完整方法读取 [github-pr-flow](../github-pr-flow/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。

## GitCode API 自动化：认证、开 PR、发评论、判门禁

本仓当前可用的 GitCode API 端点（实测 2026-11，`https://gitcode.com/api/v5`）：

| 动作 | 端点 | 认证 |
| --- | --- | --- |
| 读 PR 详情/文件/提交 | `GET /repos/{owner}/{repo}/pulls/{n}`、`/files`、`/commits` | 匿名可读 |
| 读 PR 评论 | `GET /repos/{owner}/{repo}/pulls/{n}/comments` | 匿名可读（`/reviews` 端点不通） |
| 开 PR | `POST /repos/{owner}/{repo}/pulls` `{title, head, base, body}` | Bearer |
| 发 PR 评论 | `POST /repos/{owner}/{repo}/pulls/{n}/comments` `{body}` | Bearer |
| 触发门禁 | 上面同一个评论端点，body 发 `compile` | Bearer |

**取令牌**：用本机已存的 git 凭据，不要另建凭据、不要写进 URL。

```bash
git credential fill      # stdin: protocol=https / host=gitcode.com / 空行
```

返回的 `password` 即令牌（GitCode 是 24 位串），`Authorization: Bearer <token>` 有效。从 PowerShell 给 git 喂 stdin 会因 BOM 注入失败，交给 Python `subprocess.run(stdin=io.open(..., 'ascii'))` 或 `Start-Process -RedirectStandardInput` 处理。

**建 PR 的关键点**：fork 源要写成 `用户名:分支名`（如 `EliasKaslan:ci/master-2620-pairing`），只给分支名会被当成上游同名分支。建完必须回读 `title/base.sha/head.sha/head.repo.full_name/files/body`，确认中文正文没有变成 `?`、文件清单与本地 diff 一致。

**门禁判读**：
- 触发靠 PR 评论 `compile`（AtlasAccount 回评论 `CI 流水线已启动` + run 链接），标签从 `ci-pipeline-running` 翻成 `ci-pipeline-passed` / 失败态。
- `ci-pipeline-passed` 只说明流水线整体结论，**不能证明 workflow 里引用的容器镜像可拉**：曾出现 head 引用的新镜像在 SWR 返回 404、而 PR 仍带绿标签（该 PR 只改 ci/ 与 .gitcode/，UT 是否实际执行无从证）。凡改 `container.image` 的 PR，必须另行直连 registry 验证镜像存在，不能拿标签当证据。
- `mergeable_state` 里的 `reason.merged_by_user_passed` 提示 "do not have PUSH permission" 只反映当前账号无合并权，不影响 PR 本身可合并性。

完整字段还包括 `can_merge_check`、`approval_approvers_required_passed`；`stat/needs-squash` 表示合入时要 squash。
