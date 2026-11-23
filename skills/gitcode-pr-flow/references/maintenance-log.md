# 维护记录：可复用的坑与判据

> 2026-11-23 体检：原 18KB 流水账（各次 PR 的具体 head、标签时间线、临时脚本与 worktree 路径）已压缩为本文件，只保留仍可复用的判据、错误原文与操作口径。
> 下文 `.gitcode/`、`ci/`、`catalog/` 等**仓内路径**均指远端仓库内的文件，不是本机路径。
> 历史条目只记当时事实，**不构成当前或后续任务授权**；`compile` / `retry` 等写操作按本轮用户明确授权执行。

## 门禁时间线与 retry 语义（实测）

- 自动合入时序：MindSpeed-Ops 近 20 个已合入 PR 都在末道标签落地后 7~10s 内被 `ascend-robot` 合入（例：#246 `/approve` 15:19:52 → 15:20:14 合入）。
- `compile` 会**同时**重跑文档门禁，且慢：实测发出后 2 分 40 秒文档门禁才转 `running`，随后通过。**判定「没触发」前至少等 3~4 分钟**——曾据 90 秒窗口把正确结论误判成错误。
- `retry` **不产生新 pipelineRunId**（同一 run 内重跑失败任务）→ 判断重试是否生效只能看任务状态变化；且**早发的 `retry` 会被忽略**（必须等上一轮流水线结束后再发：实测 10:51:40 发的无效、10:57:49 发的生效）。
- `docs-ci-pipeline-failed` 报「未能获取文档 CI 配置」属 openlibing 瞬时故障，与文档内容无关（同轮代码门禁照常 COMPLETED），别去改文档。
- head 变化（rebase / 强推 / 追加提交）后绿标会消失，通常要补发 `compile`；但它是写操作，**按本轮用户明确授权执行**，历史上的长期授权不自动延续（`lgtm` / `approved` 无法自助恢复，汇报里要提醒用户请原评审人重评）。
- 触发评论 `compile` 走 `POST .../pulls/:n/comments`（body 就是 `compile`）→ 201，创建者 token 即生效；无需浏览器。

## pre-commit 概率性失败：先证平台抖动，再改代码

- 判据是「同一 commit 多跑结果不一致」：PR #187 `fb141cb2` 首轮 `pre-commit` **FAILED**（`{"errorMessage":" 构建任务执行失败!","errorCode":"DEV-CODECI-35002"}`，5m11s），同 commit `retry` 后**同一 pipelineRunId** 内变 COMPLETED；更强对照是 PR #110 同一 commit 六跑 = 4 绿 2 红（`22c55f9c`/`e73f2d8f`/`c9c1867a`/`a7a4aa41` COMPLETED，`72e39b8f`/`ebc16c5c` FAILED）。
- 处置口径：`pre-commit` 失败 + 本地逐 hook 复现干净 → 判平台概率性失败，**只 retry、不改源码**；`UT_MindSpeed_*` 失败通常是真问题。
- 本地复现：独立 venv `pip install pre-commit` → `SKIP=gitleaks-offline-scan pre-commit run --files <改动文件> --show-diff-on-failure`（实测 `setup.py` 13 个 hook 全 Passed：pylint 4.0.5 / bandit 1.9.4 / typos 1.32.0 / ruff 0.14.14），再用**未改动**文件做对照。
- `gitleaks-offline-scan` 本地**必失败**（仓内没有提交二进制，CI 先 `wget .../pta-codecheck/gitleaks` 再 `chmod +x`），故须 `SKIP`；它在 CI 场景是**空门禁**——`protect` 忽略传入文件名、只对工作区未提交改动跑 `git diff -U0`，干净 checkout 恒过。
- 「PR 上没有失败评论」不能推断失败类型：action 的失败分 `failureType=install` / `failureType=check`，**两者都 exit 1**，PR 场景**都不产 SARIF、都不发 PR 评论**。
- step 级日志接口（`/pipeline-run/step/log`、`/log`、`/job/log`）一律 **401**，不要再试。

## 无登录读 openlibing 任务级状态

1. 从 PR 评论抓 `pipelineRunId=([0-9a-f]{32})`；MindSpeed-Ops 代码门禁 `pipelineId` 固定 `dc050eb8a847445c8fe635fb50d1f99d`。
2. Playwright 打开任意 openlibing 页面，在**页面上下文** `fetch`：`https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/pipeline-run/detail?projectId=300091&pipelineId=<pid>&pipelineRunId=<rid>`。
3. 在响应 `data` 里递归找同时含 `name`/`jobName` 与 `status`/`state` 的对象 → 每任务名与状态（`pre-commit`/`SCA`/`Antipoison`/`Only_doc_commit`/`UT_MindSpeed_1..4`）及失败任务的 `message` 同法取。
4. 页面渲染为空通常是 `get-user-permission` 等接口 401，而该 detail 接口 **200 免登录**。

## 冲突诊断与解决口径

- 先判冲突对象：`git merge-tree --write-tree [--name-only]`（git ≥2.38，不碰工作区）一次判「与 master 冲突」还是「两个 PR 互撞」。实测 #183/#181 **互不冲突**，是各自与 master 的同批提交（去中英文空格、修算子清单链接）撞上——**PR 显示冲突时先别假设是 PR 之间冲突**。
- 另一类成因：master 已合入「同一个 PR 拆出去的另一半」（格式半 vs 语义半），语义行与格式行逐行对撞。
- 解决口径：「以已合入的代码为准」= **取 master 措辞/空格约定 + 叠加本 PR 语义**，绝不整块选 theirs（反例：`rmsnorm_without_weight.md` 里 PR 侧会把 master 已修好的注释退回旧文）。
- 空格约定：实测规则是「删中文↔拉丁/数字空格，**保留中文↔行内代码（反引号）空格**」（`shape为 (B, T, H)` 保留、``按 `chunk_size` 分块`` 保留；`每个chunk的` 不保留）。
- 校验手段（不依赖一次性脚本）：① **语义零丢失**——原 PR diff 与 rebase 后 diff **去空格后逐文件比对增/删行多重集合**（实测 13 文件 +44/-40 完全一致）；② **空格回归**——新增行的中英文空格计数须为 0，计数前先抠掉行内代码 span。
- 写解析脚本前先看 `core.autocrlf`：`=true` 时工作区 CRLF，按 `\n` split 会误报满屏 trailing whitespace（实测 3105 条假告警）；判空白违规用 `git diff --check`。
- `git rebase --continue` 会卡编辑器 → 给 `GIT_EDITOR` 一个 true 类命令。

## 强推与改写历史的边界

- 强推 PR 特性分支的代价：`lgtm` / `approved` 被 `ascend-robot` 自动摘除，须原评审人重评；`ci-pipeline-passed` 也会消失，补发 `compile` 即可。**动手前先告知用户**。
- 已直推过的**共享版本分支不要 force-push**：改为叠加一个回退提交（纯 FF）；分支被别人推进会自然报 non-fast-forward，天然安全。
- 直推 FF 后**没有待合入的 PR，不需要发 `compile`**；只有走 PR 路线才需要那套动作。

## 接口与工具链坑（错误原文级）

- `git credential fill` 用 PS 管道喂 stdin 必报 `missing protocol field`（BOM 注入）→ 用 `cmd /c` 重定向、Python `subprocess.run(stdin=...)` 或 `Start-Process -RedirectStandardInput`。取出的 `password` 即可用令牌，只留内存，**别写临时文件**（曾写进 `%TEMP%`）。
- PS `Invoke-RestMethod` 按 Latin-1 解 UTF-8 响应 → 中文乱码；`PATCH issue` 的 `title` 必填，乱码回填会**永久写坏标题**。读写都显式 UTF-8：读 `[Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())`，写 `-Body ([Text.Encoding]::UTF8.GetBytes($json))`。
- `PATCH /repos/:owner/issues/:number`：`repo`/`title` 必填，`milestone` 传 number；响应不回显 milestone，须回读校验。`GET .../milestones` 的 `state` 参数按实际返回核对。
- 仓元信息接口强制 `private-token` 头，而 branches / pulls / comments 可匿名读。
- 匿名读的额度挂在平台公共账号上：响应体 `Limited account:p_repoRobot`、`Threshold: 10W times per user per hour`，耗尽后 429 重试无效、要等小时窗口。

## 被实测否证的旧结论（留作反面教材）

- 「`docs/zh/ops.md` 是死路径、该删」——2026-11-23 复核 `https://raw.gitcode.com/Ascend/MindSpeed-Ops/raw/master/docs/zh/ops.md` 与 `docs/zh/supported_operators.md` 均 **HTTP 200**，路径真实存在。教训：**判仓内路径真伪只能问远端或真克隆**；本地 `D:\workspace\MindSpeed-Ops` 不是 git 仓库（无 `.git`，是存放产物的容器目录），拿它当依据会得出完全错误的结论。
- 校验器判据过严：「全树不得出现旧名」会误伤刚追加的历史变更条目 → 改为「旧名只允许出现在本文件」。
- 门禁是异步状态：别用 90 秒的观察窗口下结论（见「门禁时间线与 retry 语义」）。
