# MindSpeed-Agent 仓专属事实（实测）

> 上游 `https://gitcode.com/Ascend/MindSpeed-Agent`，默认分支 `master`。
> 平台通用流程（compile / 标签 / 冲突诊断 / OpenAPI）见本体 `SKILL.md`，本文件只记**该仓与 MindSpeed-Ops 不同的部分**。

## 与 MindSpeed-Ops 的差异（实测对照）

| 项 | MindSpeed-Agent | MindSpeed-Ops |
| --- | --- | --- |
| GitCode 仓 id（compare URL 的 `targetProjectId`） | **`10303352`**（实测，`GET /repos/Ascend/MindSpeed-Agent` 的 `id`） | `9612429`（实测） |
| openlibing `projectId` | `300091`（已复核：PR #76 的 `pipelineDetail` 链接逐字等于该值） | `300091`（实测） |
| 门禁流水线 `pipelineId` | `0208644146484af992f1b3996d1a5f72`（已复核，同上链接） | `dc050eb8a847445c8fe635fb50d1f99d`（实测） |
| 门禁阶段集 | Antipoison → Only_doc_commit → pre-commit → SCA | 同上 **+ `UT_MindSpeed_1~4` 分片** |
| 仓内 workflow 文件 | `.gitcode/workflows/ci-guard.yml`（GH-Actions 语法，`runs-on: euleros-2.10.1`，三步 = `ci/guard.py` / engine tests / `pytest ci/test_guard.py`） | `.gitcode/workflows/pr-pipeline-mindspeed-ops.yml` |
| 版本分支 | 无（只有 `master`） | `26.1.0` / `26.2.0` |

## 实测要点（2026-09-29，PR #60）

- **合入结果冲突 ⇒ 门禁快速失败且不发结果评论**：与 master 冲突时，流水线 **40~60 秒内**变 `ci-pipeline-failed`，且**始终不出现** `AtlasAccount` 的阶段表评论；`retry` 被接受后同样以相同方式失败。解决冲突（merge master）后一次 `compile` 即 `ci-pipeline-passed` + `docs-ci-pipeline-success`。
- **正常一轮**：约 1 分钟出结果评论，正文含 `PR-pipeline_MindSpeed-Agent#N [ commitID：<head> ]` 与「代码风格自动修复执行成功（无修复内容）」。**核对 commitID 是否等于当前 head。**
- **`ci/guard.py` 的退出码不是门禁判据**：master 自身 **18 个阻塞 / exit 1**，而该仓 PR 照样拿到 `ci-pipeline-passed`；PR 分支 4 个阻塞时门禁也通过过。仓内 `ci-guard.yml` 里的三步（guard / engine tests / guard self-tests）**不是实际门禁**，实际阶段由平台托管。
- **PR 页面板文案**（判"合不进去"用）：`存在冲突`、`落后目标分支 N 个提交`、「合并受阻 / 代码合入存在冲突」。保护分支上还会显示「合并受阻：用户无当前保护分支的合并权限」——**这是预期状态，不是错误**，等 committer 合入。
- **浅克隆陷阱**：`git merge-base` 报 `fatal: ... no merge base` 时，`git rev-list --count` 仍会给出**看起来正常但错误**的 behind/ahead（实测假 2/2、真 3/3）。先 `git fetch --unshallow upstream` 再算。
- **`stat/needs-squash`** 表示最终 squash 合入，因此分支里带一个合并提交是可接受的；`head` 变化后必须补发 `compile`（§5 标准动作）。
- **仓内校验器**（本地自查用，非门禁）：`catalog/lint_catalog.py`、`ci/guard.py --repo . --json <f>`、`catalog/generator.py`、`pytest ci/test_guard.py ci/test_guard_catalog.py`。跑 `guard.py` 前必须 `PYTHONIOENCODING=utf-8`，否则 GBK 控制台会 `UnicodeEncodeError` 崩成假 exit=2。

## 建 PR 与门禁（2026-10-28 实测，PR #76）

- **建 PR 走 OpenAPI 即可，不必开浏览器**：`POST https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Agent/pulls`，body 字段 `title` / `head=EliasKaslan:<branch>` / `base=master` / `body` / `fork_path=EliasKaslan/MindSpeed-Agent`。**响应 200（不是 201）**，且返回体里 **`html_url` 是空串**——URL 自己拼 `https://gitcode.com/Ascend/MindSpeed-Agent/merge_requests/<number>`。
- **中文 body 必须传 UTF-8 字节**：`-Body [Text.Encoding]::UTF8.GetBytes($json)` + `-ContentType 'application/json; charset=utf-8'`，直接传字符串会把中文写成 `??` 且本地不报错（同 `SKILL.md` §7 编码坑）。
- **建完不用先发 `compile`**：本次创建后 `ci-pipeline-running` 与 `docs-ci-pipeline-running` 立刻出现，`AtlasAccount` 在 1 分钟内贴出 `PR-pipeline_MindSpeed-Agent#191 [ commitID：c2dcec56 ]`（8 位短 sha）。文档门禁 2 分钟先绿，代码流水线 4 分钟全绿。**注意 `compile` 只是 head 变化后的重触发手段**，本仓"建 PR 自动起流水线"这一条未在 head 变化场景复核过。
- **一条只读复核捷径**：`GET /pulls/:n` 的 `labels[]` 同时含 `ci-pipeline-passed` + `docs-ci-pipeline-success` 即全绿；`ascend-cla/yes` 建 PR 时按提交作者邮箱自动打上（作者邮箱必须与 CLA 签署地址一致）。
- **先看有没有同域并行 PR**：本次创建前 `GET /pulls?state=all&per_page=20` 发现 #75 已在改同一个 `batch-invariance-validation` 插件、并已把 `plugin.json`/`marketplace.json` 声明为 `0.2.2`、两个 skill 声明为 `1.1.1`。把新 PR 的版本号**对齐到对方已声明的值**，可避免"合并顺序不同 ⇒ 版本回退 / 版本行冲突"；`marketplace.json` 里同名的 `0.2.x` 不止一处（`veomni-agent` 也是），批量替换会误伤，必须按 `name` 定位。

