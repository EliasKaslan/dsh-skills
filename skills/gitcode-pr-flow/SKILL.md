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

## ascend-robot 自动合入的门禁集合（MindSpeed-Ops 实测 2026-11）

判定「已有 approve 为什么没合入」时，不要只看 approve，按标签集合逐项对：

- 自动合入由 `ascend-robot` 执行，条件是 `approved` + `lgtm` + `ci-pipeline-passed`（外加 `ascend-cla/yes`、`docs-ci-pipeline-success`）同时存在。它在最后落地的那道门禁之后几乎同刻动手：MindSpeed-Ops 近 20 个已合入 PR 全部在末道标签 +7~10s 内合入（如 #246 `/approve` 15:19:52 → 15:20:14 合入）。
- **代码更新会清掉 `ci-pipeline-passed`**，robot 会在 PR 评论 `### Notification This pull request has been changed(code update) or closed, so removes the following label(s): ci-pipeline-passed.`。此后必须在 PR 评论 `compile` 才会在新的 head 上重跑 UT 流水线（AtlasAccount 回 `CI 流水线已启动` + `actions/runs/{id}` 链接）。典型卡点：先 push、隔天再 approve，approve 时绿标已不在 → 不自动合入；补 `compile` 等绿即可，**不需要重新 /approve**（#135、#234 就是 approve 早于绿标，绿标落地 9 秒内合入）。
- 取证据：`GET /repos/{owner}/{repo}/pulls/{n}` 里 `labels[].updated_at` 就是每枚标签的落地时间。三种 CI 状态可区分：`ci-pipeline-running`（在跑）、`ci-pipeline-passed`（已绿）、两者都没有（当前 head 从未跑过）。
- `stat/needs-squash` 不阻塞合入（已合入的 #246 就带着它）。`mergeable_state.merged_by_user_passed=false` 附 "protected branch, you do not have MERGE permission" 只是查询令牌账号没有合并权，不是 PR 的阻塞项。
- Actions 没有对外的 runs 列表端点：`/repos/{owner}/{repo}/actions/runs`、`/actions/workflows`、`/pulls/{n}/check` 均 404；run id 只能从 PR 评论里 AtlasAccount 的链接取。

## 评审意见定点取证：diff_comment 锚点与按 sha 读原文

用于「确认某条评审意见是否成立 / PR 是否还需改」。GitCode 的接口形状与 GitHub 不同：

- 取评审意见：`GET https://gitcode.com/api/v5/repos/{owner}/{repo}/pulls/{n}/comments`（公共仓免鉴权可读）。`/pulls/{n}/reviews` 在 GitCode 直接 404，别照 GitHub 心智找 reviews 端点。
- 行内意见是 `comment_type=diff_comment` 的条目：锚点看 `diff_position.start_new_line`/`end_new_line`，闭环状态看 `resolved`（布尔）。`reply[]` 里那句 “changed this line on <sha>” 是平台在强推后**自动生成**的，不等于作者解释、更不等于已修复——必须回读该 sha 的实际 diff。
- 不 clone 也能定点比对：`https://raw.gitcode.com/{owner}/{repo}/raw/{sha}/{仓库内路径}` 可读任意提交的文件，PR base（`base.sha`）、上一版 head、当前 head 都能取；fork 的 head sha 也常能从目标仓按 sha 读到。落到磁盘后做 difflib/unified diff，才能分辨「这行是被修正还是被回退」。
- 判「文档写法有没有原始实现依据」时，以 **PR base 那份实现源码**为准（`GET .../pulls/{n}` 拿 `base.sha` 后按上一条 URL 取文件），找对应变量的真实语句；不要只读 head 的文档，也别拿本地 checkout 的 HEAD 冒充 base（本地可能没有该对象，`git cat-file` 会失败）。

坑：
- 短时间连发多次 API 会 `HTTP Error 429: Too Many Requests`，重试也照样 429，冷却需数分钟。一个脚本一次性批量取完（detail/files/comments/commits），需要再看门禁就隔几分钟单次调用，别写轮询。
- 平台自动回复挂在评论的 `reply[]` 里而不是新增一条 comment，只按 comments 列表的时间线读会误判成「作者没回应」。

## lgtm/approve 权限名单来源

`/lgtm` 只认 reviewers、`/approve` 只认 committers，按模块分别计数；名单在 `Ascend/community` 的 `MindSpeed/sigs/<仓>/sig-info.yaml`（仓库级 + `entry_configs[].path`）。判「为什么没打上标签」先比对评论人 gitcode-id 是否在该模块名单（大小写敏感，改动约 10min 后生效）。取法与实测见 [references/lgtm-approve-permission-source.md](references/lgtm-approve-permission-source.md)。
