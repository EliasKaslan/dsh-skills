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

仓专属事实与坑：[mindspeed-ops.md](references/mindspeed-ops.md)（算子交付件/backport）、[mindspeed-agent.md](references/mindspeed-agent.md)、[lgtm/approve 名单](references/lgtm-approve-permission-source.md)、[复用坑与判据](references/maintenance-log.md)。

沿共享方法执行，但平台固定为本次GitCode实例：先发现连接器schema、账号/权限与仓库MR/PR接口；标签、compile/retry评论及双CI车道按目标仓当前规范核对。门禁绑定当前head SHA，不拿历史评论或最近一次绿代替。不继承旧仓的免确认compile、强推、合并或release权限。

完整方法读取 [github-pr-flow](../github-pr-flow/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。

## GitCode API 自动化：认证、开 PR、发评论、判门禁

本仓当前可用的端点（实测 2026-11，基址 `https://gitcode.com/api/v5`）：

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

返回的 `password` 即令牌（GitCode 是 24 位串），`Authorization: Bearer <token>` 有效。PS 管道给 git 喂 stdin 会注入 BOM 导致 `missing protocol field`，用 Python `subprocess.run(stdin=...)` 或 `Start-Process -RedirectStandardInput`。

**建 PR 的关键点**：fork 源写成 `用户名:分支名`（如 `EliasKaslan:ci/master-2620-pairing`），只给分支名会被当成上游同名分支。建完回读 `title/base.sha/head.sha/files/body`，确认中文正文没变成 `?`、文件清单与本地 diff 一致。

**门禁判读**：
- 触发靠 PR 评论 `compile`（AtlasAccount 回评论 `CI 流水线已启动` + run 链接），标签从 `ci-pipeline-running` 翻成 `ci-pipeline-passed` / 失败态。
- `ci-pipeline-passed` 只说明流水线整体结论，**不能证明 workflow 引用的容器镜像可拉**：曾出现 head 引用的新镜像在 SWR 返回 404 而 PR 仍带绿标（该 PR 只改 ci/ 与 .gitcode/，UT 是否真跑无从证）。凡改 `container.image` 的 PR 必须另行直连 registry 验镜像存在。
- `mergeable_state.reason.merged_by_user_passed` 提示 "do not have PUSH permission" 或 "protected branch, you do not have MERGE permission"，都只反映查询账号无合并权，不是 PR 的阻塞项。

完整字段还包括 `can_merge_check`、`approval_approvers_required_passed`；`stat/needs-squash` 只表示合入时要 squash，**不阻塞合入**（已合入的 #246 就带着它）。

## ascend-robot 自动合入的门禁集合（MindSpeed-Ops 实测 2026-11）

按标签集合对：`approved`+`lgtm`+`ci-pipeline-passed`+`ascend-cla/yes`+`docs-ci-pipeline-success` 齐了才动，末道标签后 7~10s 合入。

- 代码更新会清掉 `ci-pipeline-passed`，须再评论 `compile` 在新 head 重跑；**不必重新 /approve**。
- `labels[].updated_at` 是标签落地时间；标签只是线索，结论绑当前 head SHA 的 run。
- 查 run/job 走 **v8**（v5 无线）：`/api/v8/repos/{o}/{r}/actions/runs[?per_page=100]`、`…/runs/{run_id}`、`…/runs/{run_id}/jobs/{job_id}`。字段/坑见 [v8 API](references/gitcode-actions-v8-api.md)。
- **`Job(<a>_<b>)` 不是 run id**：它是 job 的 `exec_id`。
- 判读：`步骤初始化步骤执行失败`+`start_time=null` = 排队到超时、容器没起来；`步骤run X执行失败` 才是脚本挂。

细节见 [坑与判据](references/maintenance-log.md)。

## 评审意见定点取证：diff_comment 锚点与按 sha 读原文

用于「确认某条评审意见是否成立 / PR 是否还需改」。GitCode 的接口形状与 GitHub 不同：

- 取评审意见：`GET https://gitcode.com/api/v5/repos/{owner}/{repo}/pulls/{n}/comments`（公共仓免鉴权可读），**必须带 `?per_page=100`**：默认只回 20 条，实测 92 条评论只拿到最旧 20 条，一度误判「机器人没反应」。`/pulls/{n}/reviews` 在 GitCode 直接 404，别照 GitHub 心智找 reviews 端点。
- 行内意见是 `comment_type=diff_comment` 的条目：锚点看 `diff_position.start_new_line`/`end_new_line`，闭环状态看 `resolved`（布尔）。`reply[]` 里那句 “changed this line on <sha>” 是平台在强推后**自动生成**的，不等于作者解释、更不等于已修复——必须回读该 sha 的实际 diff。
- 不 clone 也能定点比对：`https://raw.gitcode.com/{owner}/{repo}/raw/{sha}/{仓库内路径}` 可读任意提交的文件，PR base（`base.sha`）、上一版 head、当前 head 都能取；fork 的 head sha 也常能从目标仓按 sha 读到。落到磁盘后做 difflib/unified diff，才能分辨「这行是被修正还是被回退」。
- 判「文档写法有没有原始实现依据」时，以 **PR base 那份实现源码**为准（`GET .../pulls/{n}` 拿 `base.sha` 后按上一条 URL 取文件），找对应变量的真实语句；不要只读 head 的文档，也别拿本地 checkout 的 HEAD 冒充 base（本地可能没有该对象，`git cat-file` 会失败）。

坑：
- 连续调 API 会 `HTTP Error 429: Too Many Requests`：匿名额度挂在平台公共账号上（实测响应体 `Limited account:p_repoRobot`、`Threshold: 10W times per user per hour`，2026-11-23 两个 API 主机同时耗尽），额度用完后重试照样 429、要等小时窗口。一个脚本一次性批量取完（detail/files/comments/commits），别写轮询。
- 平台自动回复挂在评论的 `reply[]` 里而不是新增一条 comment，只按 comments 列表的时间线读会误判成「作者没回应」。

## lgtm/approve 权限名单来源

`/lgtm` 只认 reviewers、`/approve` 只认 committers，按模块分别计数；名单在 `Ascend/community` 的 `MindSpeed/sigs/<仓>/sig-info.yaml`（仓库级 + `entry_configs[].path`）。判「为什么没打上标签」先比对评论人 gitcode-id 是否在该模块名单（大小写敏感，改动约 10min 后生效）。取法与实测见 [references/lgtm-approve-permission-source.md](references/lgtm-approve-permission-source.md)。
