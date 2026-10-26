---
name: gitcode-pr-flow
description: GitCode 上任意昇腾社区仓提 PR（MindSpeed-Ops 与 MindSpeed-Agent 均已完整验证）从个人 fork 到合入全流程——compile 评论触发门禁（任何 head 变化后须补发）、双 CI 判读与标签审计（operate_logs）、PR 冲突诊断（git merge-tree）、GitCode OpenAPI v5 创建/关闭 PR 与批量改 issue、版本分支 backport，以及 pre-commit 概率 FAILED 判平台抖动还是改代码。适用于"向 GitCode 仓提 PR / PR 冲突了要 rebase / 补一下 ci-pipeline-passed / 查 PR 标签是谁打的 / 标签为什么被摘 / 评论 compile 门禁没跑 / 门禁快速失败且没有结果评论 / pre-commit 随机 FAILED / backport 到 26.1.0"。不适用：目标仓在 GitHub 而不是 GitCode → 用 `github-pr-flow`。
whenToUse: 在 GitCode 任意仓（Ascend/MindSpeed-Ops、Ascend/MindSpeed-Agent 等昇腾社区仓）提交/更新/跟进 PR、修冲突或 rebase、补门禁标签、backport 到版本分支，或判 pre-commit FAILED 该不该改代码时使用。模型看不到本节。
---

# GitCode 代码仓提交 PR 全流程

**适用范围**：GitCode 上**任意**仓（当前已完整验证两例：`Ascend/MindSpeed-Ops`、`Ascend/MindSpeed-Agent`）。
贡献模型：**个人 fork → 分支 → 跨仓库 PR → 门禁 → committer 合入**。
URL 规则、OpenAPI v5、评论指令、标签语义、双门禁判读、冲突诊断这些**与具体仓无关**；仓专属事实一律放 `references/`。

## 仓参数化（换仓只改这张表）

| 项 | MindSpeed-Ops | MindSpeed-Agent |
| --- | --- | --- |
| 上游 | `Ascend/MindSpeed-Ops` | `Ascend/MindSpeed-Agent` |
| GitCode 仓 id（compare URL 的 `targetProjectId`） | `9612429`（实测） | **未取证**——换仓时从 compare 页现取，别照抄 |
| openlibing `projectId`（流水线 detail 接口） | `300091`（实测） | `300091`（沿用同一探测脚本，**未独立证实**） |
| 门禁流水线 `pipelineId` | `dc050eb8a847445c8fe635fb50d1f99d`（实测） | `0208644146484af992f1b3996d1a5f72`（取自 PR 评论 `pipelineDetail` 链接，**未复核**） |
| 门禁阶段集 | Antipoison → Only_doc_commit → pre-commit → SCA → `UT_MindSpeed_1~4` | Antipoison → Only_doc_commit → pre-commit → SCA（**无 UT 阶段**） |
| 分支 | `master` + 版本分支 `26.1.0`/`26.2.0` | 只有 `master` |
| 仓专属交付件 | `docs/zh/ops.md` 等（见 `references/mindspeed-ops.md`） | 无 |
| 仓专属事实 | `references/mindspeed-ops.md` | `references/mindspeed-agent.md` |

下文示例里的 `Ascend/MindSpeed-Ops` 一律可替换为 `<owner>/<repo>`；**冲突/门禁诊断类结论对两个仓都成立**。

**用户账号事实（已验证）**：GitCode 用户名 `EliasKaslan`（昵称 xmz），fork 在 `EliasKaslan/<repo>`；**Ascend CLA 已签署**。凭据原则：token/密码**不写入仓库文件、日志或命令历史**；**缓存位置放 skill 目录内或 `~\.dsh\.secrets\` 都合法**（2026-10-08 起鼓励 skill 直接写明凭据文件位置；统一策略见 `github-pr-flow` §0），并优先复用 Windows 凭据管理器（见下文）。

## 何时调用

**加载本 skill 当：**
- 用户要在 **GitCode** 的任意仓（Ascend/MindSpeed-Ops、Ascend/MindSpeed-Agent 或其他昇腾社区仓）提 PR、改 PR、修冲突 / rebase、同步 fork。
- 要评论 `compile` 触发的门禁没跑，或要补 `ci-pipeline-passed` / `docs-ci-pipeline-success` 等标签、跟进门禁状态。
- 门禁**快速失败（约 40~60 秒）且没有 `AtlasAccount` 结果评论** → 先判"是不是合不进去"（§6.4）。
- 要弄清某个 PR 上**标签是谁在什么时刻打/摘的**，或判 `stat/needs-squash`、`docs-ci-pipeline-success`、`ascend-cla/yes` 这类标签的真实含义（含"标签为什么被摘了"）→ 用 §6/§7 的 `operate_logs` 权威接口与 §6.3 判读陷阱。
- 要把 master 的改动回合并到版本分支 `26.1.0` / `26.2.0`（仅 MindSpeed-Ops 有版本分支；backport 判定 + 直推见 `references/mindspeed-ops.md`）。
- `pre-commit` 任务随机 FAILED（message 带 `DEV-CODECI-35002`），要判是平台抖动还是要改代码。

**不要用本 skill（转交）：**
- 目标仓在 **GitHub**（如 vllm-project/vllm-ascend）而不是 GitCode → 用 `github-pr-flow`。
- 要读 / 导出华为 AIDD 扫描报告 → 用 `aidd-report-reader`。
- 要过滑块验证码 → 用 `dingxiang-slider-captcha`。
- 要精读 arXiv 论文并独立核查其开源声称 → 用 `arxiv-paper-deep-read-and-claim-verification`。

**前置**：GitCode 账号 + 个人 fork + Ascend CLA 已签署（未签 ascend-robot 不会打 `ascend-cla/yes`）。 ／ **后继**：建 PR（§3）→ 评论 `compile`（§5）→ 判门禁（§6）→ 合入 / backport（见 `references/mindspeed-ops.md`）。

## 1. 前置条件

1. **GitCode 账号 + fork**：上游仓库页点 Fork；已有 fork 时页面显示"已存在的fork项目"按钮直达。fork 落后时用 fork 仓库页的"**同步源项目**"按钮同步（PR 页出现"落后目标分支 N 个提交"或"存在冲突"时必须先同步/变基）。
2. **CLA 签署**（Ascend 社区统一）：未签署时 ascend-robot 不会给 PR 打 `ascend-cla/yes` 标签。签署入口：https://clasign.osinfra.cn/sign/68cbd4a3dbabc050b436cdd4 （个人/企业/员工 CLA 三种）。用户已签过，无需重复。
3. **本地环境**（改代码时）：
   ```bash
   git clone https://gitcode.com/<user>/MindSpeed-Ops.git   # 或浅克隆上游后加 fork remote
   pip install -e . --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple --no-build-isolation --no-deps
   ```
   pre-commit 检查项（`.pre-commit-config.yaml`）：ruff(check+format)、pylint、bandit、codespell、typos、trailing-whitespace、end-of-file-fixer、check-yaml。提交前先跑 `pre-commit run -a`，能省一轮 CI 往返。

## 2. 分支与 commit 规范

- 分支命名见贤思齐：`fix/xxx`、`docs/xxx`、`feat/xxx`、`feature/xxx`。
- **commit 标题遵循 Conventional Commits**：`feat:` / `fix:` / `docs:` / `test:` / `ci:`（如 `docs: add contribution guide`、`feat(triton): add minimax_m3_indexer`）。模板提示语为 `type(scope): 描述`，常见 type：feat/fix/docs/style/refactor/adaptor/chore/test。
- 合入采用 **Squash 合并**，commit message 由机器人自动生成（`# message auto-generated for no-merge-commit merge: !N ... Created-by/Commit-by/Merged-by`），无需手写 Sign-off（与 GitHub DCO 不同，GitCode Ascend 仓用 CLA 不用 DCO）。
- PowerShell 提交的坑与解法（消息走 stdin、BOM、CRLF）见 `github-pr-flow` skill **§2**，通用。

## 3. 创建 PR（Web UI，已逐步验证）

**关键 URL 认知（最大的坑）**：
- `/pulls/new` 是 **404**（"页面找不到或无权限"）。正确路径是 **`/pull/new`**（pull 单数）。
- 在**上游仓库**的 `/pull/new` 页，源分支下拉只列上游自己的分支（master、26.1.0），选不了 fork 的分支——**跨仓库 PR 必须从自己 fork 的仓库页发起**。
- 流程：进入 `https://gitcode.com/<user>/MindSpeed-Ops` → 顶部 "Pull Requests" 标签 → "新建Pull Request" 按钮 → 源分支=「自己的 fork + 分支」（表单会记住上次用的分支），目标分支=「Ascend/MindSpeed-Ops + master」→ 点"下一步"。
- **直达 compare 页 URL**（可跳过上一步，直接给 Playwright 用）：
  ```
  https://gitcode.com/Ascend/MindSpeed-Ops/pull/compare?originRepo=EliasKaslan/MindSpeed-Ops&targetRepo=Ascend/MindSpeed-Ops&targetProjectId=9612429&originBranch=<你的分支>&targetBranch=master
  ```
  （`targetProjectId=9612429` 是 MindSpeed-Ops 的项目 ID；目标分支可换 `26.1.0`。）

**compare 页表单**（标题、描述均为必填）：
- 标题：预填模板占位符 `feat/fix/docs/style/refactor/adaptor/chore/test(backend): pr describe`——**必须替换掉**，上限 200 字符；暂不想被合入时加 `[WIP]` 前缀（或勾选"设为草稿"）。
- 描述：富文本编辑器（非普通 textarea，自动化时用 Playwright 的 fill 对 contenteditable 或直接改 Vue 状态），预填三段模板（见 §4）。
- 选项：前置 PR（依赖链）、"合并后关闭已关联的 Issue"（默认勾选）、合入时删除源分支、合入时 Squash 提交。
- 侧栏可分配：合并人/审查人/测试人/评审人/Label/里程碑/关联Issue。
- 页面显示"可直接合入"（或"存在冲突"）状态与变更文件 diff。

**GitCode 特性**：PR 描述的**第一个表格**可元编程设置 title/labels/assignees（`| title | labels | assignees |`），见仓库 `.gitcode/PULL_REQUEST_TEMPLATE.md`；事后也可通过"修改 Squash 信息"和编辑描述调整。

## 4. PR 标题与描述模板（.gitcode/PULL_REQUEST_TEMPLATE.md）

```
## What this PR does / why we need it?
（背景与详细改动；bugfix 请附相关 issue）

## Does this PR introduce any user-facing change?
（是否引入用户可见变更；有相关文档则给出路径）

## How was this patch tested?
（如何验证正确性与有效性、使用约束与限制；doc-only 可写 "CI verification only"）
```

**配套要求（CONTRIBUTING.md）**：发起 PR 后**同步创建 issue 并关联该 PR**（issue 标签与 PR 类型对应：`feature`/`bug`/`document`；issue 标题前缀 `[Feature]`/`[Bug]` 等）。在 PR 页"关联Issue"侧栏或 issue 侧栏操作；页面文案叫"合并后关闭已关联的 Issue"。

## 5. 触发门禁：评论 `compile`

PR 创建后代码门禁**不会自动跑**，需在评论区输入：

```
compile
```

仅 **PR 创建者**和白名单成员（wujinyuan1、liuzhexu）的评论有效。其他指令：
- `retry`：重试流水线所有失败子任务
- `retry <任务名>`：仅重试指定失败子任务
- `stop`：停止流水线

维护者评论 `/approve` → 打 `approved` 标签（等价 lgtm + approve）。

**要点**：
- **🔁 标准动作（用户已授权，不要再问）：任何让 head 变化的操作做完后——rebase / 强推 / 追加提交——立刻自动用创建者 token 补发 `compile`，不等用户开口。** 用户已明确要求："做完类似的事情后，你需要自动帮我评论 compile。" 发完回读确认 `ci-pipeline-passed` 就位、且 `AtlasAccount` 结果评论里的 `commitID` 等于当前 head（§7 有现成片段与回读方法）。
- 目标是拿到 `ci-pipeline-passed` 标签；纯文档 PR 也照样要发（只是流水线里除 `Only_doc_commit` 外全是 ⚪ IGNORED）。
- **任何 head 变化（rebase / 强推 / 追加提交）后 `ci-pipeline-passed` 都会消失，必须重发 `compile`**——见 §9。
- 发之前先看评论区：committer 可能已经替你发过，重复发无副作用但没必要。⚠️ 查评论必须带 `?per_page=100`，默认只回 20 条旧评论（见 §10）。
- 无 token 时可用浏览器发；有 token 时直接走 API（§7 有现成片段，实测 60s 内标签就位）。

## 6. 双门禁管线判读（PR 页 Labels + 机器人评论）

**文档门禁（ascend-robot）**，改文档即触发，labels `docs-ci-pipeline-running/success/failed`：
检查项 = markdownlint、link-validity-check、resource-existence-check、tag-closed-check。高频失败：MD051 链接锚点无效（如 README 里 `#版本配套表` 锚点找不到）、图片/资源不存在。通过后评论"✅ 文档门禁通过！"。

**代码门禁（AtlasAccount）**，`compile` 触发，labels `ci-pipeline-running/passed`：
流水线 `PR-pipeline_MindSpeed-Ops#N`，阶段 = 恶意代码检查(Antipoison) → 编码安全与规范检查(Only_doc_commit) → pre-commit → 开源片段检查(SCA) → 开发者测试(UT_MindSpeed_1~4 分片)。**doc-only PR 大部分阶段显示 ⚪ IGNORED 是正常的**（Only_doc_commit 判定纯文档变更后跳过其余）。

**PR 级标签全集（13 个，逐条实测口径）**：`ascend-cla/yes`、`ci-pipeline-passed`、`approved`、`lgtm`、`stat/needs-squash`、`docs-ci-pipeline-success`、`ci-pipeline-failed`、`ascend-cla/no`、`docs-ci-pipeline-running`、`ci-pipeline-running`、`docs-ci-pipeline-failed`、`fix`、`installation`。前 11 个由机器人/门禁驱动；**`fix` / `installation` 是作者手加的普通标签**。⚠️ PR 页 Label 下拉里的几百个标签**绝大多数是 issue/分诊标签库**，不适用于 PR（见 §6.3）。

**打标主体（operate_logs 实证，不是按配置推断）**：`ascend-robot` 负责 `ascend-cla/yes|no`、`docs-ci-pipeline-*`、`stat/needs-squash`、`approved`、`lgtm`；`AtlasAccount` 负责 `ci-pipeline-running|passed|failed`。⚠️ 配置里 `ci-pipeline-passed` 声明为**双 person**（`person: ascend-robot,AtlasAccount`），但**实测 operate_logs 里的打标 actor 是 `AtlasAccount`**——两个事实都要记，别只留一个。

**`approved` / `lgtm` 是 ascend-robot「代打」**：维护者在评论里发 `/approve`、`/lgtm` 后 **5~10 秒**由机器人加上标签，不是维护者本人操作。所以 operate_logs 里看到 actor 是机器人，**不代表"机器人自己批了"**。

**head 变化（rebase / 强推 / 追加提交）后的四类标签处置（判读基线，逐条实测）**：
| 标签 | head 变化后 | 机器人公告原文 / 你要做的事 |
|---|---|---|
| `approved` + `lgtm` | **被摘且不自动恢复** | `### Notice / New code changes of the pull request are detected and remove these labels ***lgtm, approved***. :flushed:` → **必须请原评审人重新 `/lgtm`、`/approve`；这一步只能人工，无法自助补** |
| `ci-pipeline-passed` | 摘掉并**立刻加 `ci-pipeline-running`** | 必须重发 `compile`（§5 标准动作） |
| `stat/needs-squash` | 摘掉后**按新 commit 数重判**（可能又被加回来） | `This pull request has been changed(code update) or closed, so removes the following label(s): stat/needs-squash.` |
| `ascend-cla/yes` | 作者邮箱与已签署地址一致 → **delete + add 秒级回填**（等价重校验） | 不是真正的"丢失"，巡检时不要报成异常（§10）；**但作者邮箱不是已签署地址时会掉成 `ascend-cla/no` 并阻断合入**（§6.6） |

**`stat/needs-squash` 的含义与触发条件（已坐实）**：含义 = **该 PR 含多个 commit，合入时会被压成一个**（本仓 `merge_method: squash`）。触发条件用交叉表验证：**单 commit 的 PR 从不带该标签；多 commit 的 PR 几乎必带（只有极少数反例）**。⚠️ 该标签在 `bot-review-config.yaml`、robot 使用指南、GitCode 帮助中心里**都没有语义声明（0 命中）**——**只有 operate_logs 行为证据，没有配置级声明**。残留不一致：已合入的 PR 里仍有保留该标签的（与"关闭/更新即摘"不完全吻合）→ **不要把"还带这个标签"当成"还没合入"**。

**`docs-ci-pipeline-success` 不能反推"改过文档"**：机器人评论 `✅ 跳过 docs ci 检查，没有需要检查的文档文件` 时**照样打 success**（实测只改 `setup.py` 的 PR 也带该标签）→ 见 §10。

**门禁触发条件**：
- **文档门禁在"推送"和"发评论（含 `compile`）"之后都会重新触发**——但**很慢，别急着下结论**。
- **判读阈值：文档门禁重新出现 `docs-ci-pipeline-running` 需 2~4 分钟**（实测一次 `compile` 评论后约 2 分 40 秒才转 running）。**判定"评论无法重触发文档门禁"之前至少等 3~4 分钟**，或直接看标签 `docs-ci-pipeline-running` 有没有回来——只等 90 秒就下结论是错的。
- `docs-ci-pipeline-success` 会在 push/评论后短暂变回 `docs-ci-pipeline-running`，判定最终状态前先等它 settle。
- **失败原因要读清楚**：`ascend-robot` 会给出原因。若为 **"未能获取文档 CI 配置"**，那是 openlibing 平台侧取配置失败（配置托管在平台，不在仓内文件里），**与你的文档内容无关**；旁证口径：**同一次 push 的代码门禁仍正常 COMPLETED**（两条流水线互相独立）。此时不要去改文档，先按 §9 第 3 条确认自己的 markdown 自查是干净的，**然后重发 `compile` 触发重跑即可**，不必为此多推一次 head。

### 6.1 pre-commit 门禁的概率性失败（平台抖动）与无登录判读

**结论口径**：`ci-pipeline-failed` 但失败项是 `pre-commit` 时，**先在改代码之前**取"同一 commit 的多次运行"证据（或直接发一次 `retry`）——若同一 commit 两次结论相反，即判为**平台概率性失败**，处理方式只有 `retry` 到 `pre-commit` 变 COMPLETED，**不要为此改源码**。反例：`UT_MindSpeed_*` 失败通常是真问题。

**⚠️ 别把"隐晦文案"当抖动直接 retry（2026-10-26 实测纠正）**：`pre-commit` 的真实内容性失败，message 也只有 `步骤pre-commit执行失败，错误信息：点击任务查看详情`——**与抖动同形**，`retry` 和重发 `compile` 各跑一轮都照样红。所以顺序必须是「**先本地复现**，本地复现不出来才判抖动」。真实成因的典型形态：**PR 动了某个文件，pre-commit 就按整文件校验该文件里"既有"的 lint 问题**（本次：`docs/zh/install_guide.md` 有 2 处行尾空格 + 1 处 MD049 `*X*` 强调样式），与你的改动无关却必定红。修法：同一 PR 里顺手修掉，`git commit --amend` 后强推再补 `compile`，PR 描述里说明"顺带修复文件内既有告警"。

**本地复现配方（Windows 实测跑通）**：`python -m venv %TEMP%\pcvenv` + `pip install pre-commit` → 仓库根 `SKIP=gitleaks-offline-scan pre-commit run --files <改动文件...> --show-diff-on-failure`。`trailing-whitespace` / `end-of-file-fixer` 会**就地改文件**（预期行为，改完留着）；`markdownlint` 只在**改动的那个文件**有既有告警时报错，其他文件全绿不代表安全。

**已实证的错误形态（逐字）**：
- 同一 commit 上：首轮 `pre-commit` **FAILED**，message = `步骤pre-commit执行失败，错误信息：{"errorMessage":" 构建任务执行失败!","errorCode":"DEV-CODECI-35002"}`；对**同一 commit** 发 `retry` 后，在**同一 pipelineRunId** 内 `pre-commit` 变 **COMPLETED**。**同 commit、同内容，两次结论相反。**
- 更强的对照组：另一个 PR 在**同一 commit** 上跑了多次流水线，`pre-commit` 呈 **COMPLETED / FAILED 交替** → **与代码内容无关**。
- **`retry` 会被静默丢弃**：2026-10-26 实测，run 已 `FAILED`（`end_time` 已落）之后 6 分钟发 `retry`，`attempt` 仍为 **1**、`CodeCheck_pre_commit` 仍 `FAILED`、机器人**无任何响应评论**。别反复发 `retry` 白等——直接重发 `compile`（起**新的** `workflow_run_id`）更可靠；`compile` 还会顺带重跑文档门禁。

**排除代码原因（可复用）**：
```bash
python -m venv <venv> && <venv>/Scripts/pip install pre-commit      # 独立 venv，别污染主环境
cd <worktree>
SKIP=gitleaks-offline-scan pre-commit run --files <改动文件> --show-diff-on-failure
```
- 实测：改动文件上**全部 hook Passed**（含 pylint / bandit / typos / ruff）；再用一个**未改动**的同类型文件做对照，逐 hook 结果完全一致 → 证明不是改动引入。
- `gitleaks-offline-scan` 本地**必然失败**：仓库**没有**提交 `gitleaks` 二进制，CI 是先 `wget https://pytorch-package.obs.cn-north-4.myhuaweicloud.com/pta-codecheck/gitleaks` 再 `chmod +x`，故用 `SKIP=gitleaks-offline-scan` 排除这个环境性噪音。
- 该二进制（`gitleaks 8.30.1`）在 CI 场景下其实是**空门禁**：`protect` 子命令忽略传入文件名，只对工作区未提交改动跑 `git diff -U0`，干净 checkout 上扫到 0 字节恒过。

**⭐ 更省事的首选：GitCode 自己的 workflow-run 接口（2026-10-26 实测，一步拿到逐任务状态）**。上一条 openlibing 接口要凑 `pipelineRunId`，而 PR 评论只给 GitCode 的 `actions/runs/<32hex>`；直接用那个 id 打：

```
https://web-api.gitcode.com/api/v2/projects/<owner>%2F<repo>/actions/workflow-runs/<runId>
```

返回 `data.stages[].jobs[]`，每个 job 有 `name` / `status`（COMPLETED|FAILED|RUNNING|INIT）/ `message` / `steps[]`（step 也有 `status`，能看出卡在哪一步，如 `run UT rank 3`）。**要点**：① 必须**在页面上下文里 fetch**（PowerShell 直接 GET 返回 **418**，带 PRIVATE-TOKEN 也没用）；② `runId` 从 `AtlasAccount` 的"CI 流水线已启动"评论里抓 `actions/runs/([0-9a-f]{32})`；③ 浏览器是**共享**的，用户可能把标签导航走（本轮就被切到华为下载页导致 `Failed to fetch`）——判读兜底用 **PR 标签**（`ci-pipeline-passed` 出现即通过，无需浏览器），或新开标签再试。

**无登录读任务级状态（openlibing 侧，备选）**：用 Playwright 打开任意 openlibing 页面（如 PR 评论里 `pipelineDetail?...` 的 URL），在**页面上下文**里 `fetch`：
```
https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/pipeline-run/detail?projectId=300091&pipelineId=<pid>&pipelineRunId=<rid>
```
在返回的 `data` 里递归找**同时含 `name|jobName` 与 `status|state`** 的对象，即可拿到每个任务名与状态（`pre-commit` / `SCA` / `Antipoison` / `Only_doc_commit` / `UT_MindSpeed_1..4`）以及失败任务的 `message`（含 `DEV-CODECI-35002`）。
- `pipelineId` 固定 `dc050eb8a847445c8fe635fb50d1f99d`（PR-pipeline_MindSpeed-Ops）；`pipelineRunId` 从 PR 评论抓 `pipelineRunId=([0-9a-f]{32})`。
- **页面本身渲染为空是因为 `get-user-permission` 等接口 401，但上面的 detail 接口返回 200、不需要登录**；step 日志类接口（`/pipeline-run/step/log`、`/log`、`/job/log`）一律 **401**，不要去试。
- **`retry` 不产生新 pipelineRunId**，只在同一 run 内重跑失败任务 → 判断"重试是否生效"必须看**任务状态变化**，不能靠 run id 变化。且**早发的 `retry` 会被忽略**：必须在上一轮流水线已结束之后发（实测早发的被忽略、等上一轮结束后发的生效）。

**相关定义（读源码得到的事实）**：`pre-commit` 任务定义在仓库 `.gitcode/workflows/pr-pipeline-mindspeed-ops.yml` 的 `pre-commit` 任务里（**行号随分支变化，定位按任务名 / 文件名精确匹配，别照抄行号**；容器 `swr.cn-north-4.myhuaweicloud.com/mindspore/mindspore_python3.11:v0.1`，checkout `refs/merge-requests/<pr_id>/merge`，先下载 gitleaks，再 `uses: openlibing/pre-commit-action@v1.0.0`）。该 action 源码 https://gitcode.com/openlibing/pre-commit-action 的 `index.js`：PR 事件且 `ATOMGIT_BASE_REF` 非空 → `--from-ref FETCH_HEAD --to-ref HEAD`（增量，只查改动文件），否则 `--all-files`；失败分 `failureType=install`（钩子安装/环境错误，日志含「钩子安装或环境错误」）与 `failureType=check`（检查告警，日志含「pre-commit 检查发现告警」），**两者都 exit 1**，且 **PR 场景都不产出 SARIF、都不发 PR 评论** → 因此"PR 上没有失败评论"**不能**用来推断失败类型。

**合入**：`master`（protected=true）上贡献者无合并权限——"合并受阻：用户无当前保护分支的合并权限"是**保护分支**上的预期状态；等 CI 全绿 + `approved` 后由 committer 点"Squash 合并"。合入后自动生成 squash commit message 并可自动关闭关联 issue。**注意这条只对保护分支成立**：未保护的版本分支（`26.1.0`/`26.2.0`）EliasKaslan 有 Maintainer 直推权限，回合并走 §12。

### 6.2 门禁标签的权威出处（目标仓内零出处，出处在上游基础设施仓）

- **目标仓 `Ascend/MindSpeed-Ops` 里找不到标签定义**：仓内 `.gitcode/` 只有极少数文件——`PULL_REQUEST_TEMPLATE.md` 只定义 PR 标题前缀（feat/fix/docs/style/refactor/adaptor/chore/test），`.gitcode/workflows/pr-pipeline-mindspeed-ops.yml` **不含任何 label 声明**。**别去改目标仓的 workflow 想改门禁标签，那里没有**。
- 权威出处是昇腾社区基础设施仓 **`Ascend/infrastructure`**（master）。**这两个文件的行号会随分支漂移，定位一律按「文件名 + 键名 / 小节标题」精确匹配，不要照抄行号**：
  - `config/bot-review-config.yaml`：MindSpeed-Ops 块的 `repos` 列表里，`lgtm_need_nums: 2`、`approve_need_nums: 1`、`merge_method: squash`；labels 声明里 `lgtm`/`approved`/`ascend-cla/yes` 的 person = `ascend-robot`，`ci-pipeline-passed` = `ascend-robot,AtlasAccount`。**关键**：`docs-ci-pipeline-success` 在该配置里**只给 `Ascend/community` 声明**，MindSpeed-Ops 块**未声明** → **本仓文档门禁属平台侧托管**（这正是 §6 "未能获取文档 CI 配置" 那类故障的由来）。
  - `docs/robot/robot使用指南.md`：命令→标签总表（`/check-cla`、`/cla cancel`、`compile`、`retry`、`stop`、`/lgtm`、`/approve`、`/check-pr`、`/merge`、`/kind|/priority|/sig`、`/label add|remove`）与 FAQ。两条硬约束：**"非机器人账号添加的标签无效"**（PR 会提示 `The following labels are not ready...`，**手工补标签没用，必须发指令**）；**评论时间早于最新 commit 的 `/lgtm`、`/approve` 无效**（与上面的 head 变化表互为因果）。评论人 gitcode-id 与 `sig-info.yaml` 不一致时需改 `sig-info.yaml`，合入 10 分钟后权限生效。`/check-cla` 行明确：已签 → `ascend-cla/yes`，未签 → `ascend-cla/no`。
- **读基础设施仓的方法（可复用）**：`GET api.gitcode.com/api/v5/repos/Ascend/infrastructure/tree?ref=master&path=docs` → **401**；改**直读 raw**：
  ```powershell
  # 英文路径直读（成功）
  Invoke-WebRequest 'https://raw.gitcode.com/Ascend/infrastructure/raw/master/config/bot-review-config.yaml' -UseBasicParsing
  # 中文文件名必须 URL 编码，否则 404
  Invoke-WebRequest 'https://raw.gitcode.com/Ascend/infrastructure/raw/master/docs/robot/robot%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md' -UseBasicParsing
  ```

### 6.2.1 GitCode 只读清点（`contents/` + raw，替代失效的 tree 接口）

**⚠️ 修正上面的断言**：tree 接口确实 401，但**不是"只能改 raw 直读"**——`contents/` 接口**匿名 200 可用**，返回带 `type`/`size` 的条目，比逐个猜文件名再 raw 探测可靠得多：

```powershell
# 列目录（匿名 200）：返回数组，每项含 type(file|dir) / name / path / size
Invoke-WebRequest 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/contents/docs/zh' -UseBasicParsing   # 200
Invoke-WebRequest 'https://api.gitcode.com/api/v5/repos/Ascend/infrastructure/tree?ref=master&path=docs' -UseBasicParsing  # 401（保留原结论）
```
同批实测匿名 200 的还有 `/branches`、`/issues?state=all&per_page=100`、`/pulls?state=all&per_page=100`；**流程 = 先用 `contents/` 列目录，再用 raw 取内容验证**（raw 路径见上一节，中文名要 URL 编码）。

**坑：只探根目录会误判"某仓没有该文件"**。`SECURITYNOTE.md` 这类文件在本组织**没有"必须在根目录"的统一约定**（实测各仓位置不统一：有的在根目录、有的在 `docs/zh/`、有的没有）→ 根目录 404 **不等于**仓库里没有；必须先把可能目录（`/`、`docs`、`docs/zh`…）用 `contents/` 列一遍。

**坑：浅克隆判祖先会双向都返回 1（误判"两分支已分叉"）**。`git clone --depth=1` 后 `git merge-base --is-ancestor A B` 与 `--is-ancestor B A` **都返回 1**（缺 merge-base 信息）；实测 `26.2.0 → master` 在 `--depth=1` 下 = **1（错）**，`git fetch --deepen=300 origin`（`git rev-parse --is-shallow-repository` 变 `false`）后 = **0（对）**。判祖先关系前先确认不是浅克隆。

**可复制的正确命令序列（原样，实测跑通）**：
```
git ls-remote --heads <url>                    # 先拿真尖端；本地 remote-tracking ref 可能过期
git clone --no-checkout <url> repo && cd repo
git fetch --depth=1 origin master 26.2.0 && git fetch --deepen=300 origin
cmd /c "git grep -n -I -E \"https?://\" origin/master -- . > out.txt 2>&1"   # PS5.1 的 > 会写 UTF-16，别直接用
```

### 6.3 标签体系里的判读陷阱（别被仓里的脏数据带偏）

- 仓库 `GET /labels` 返回的标签里**绝大多数是 issue/分诊标签库**（`triaged`/`resolved`/`rfc`/`feature`…）→ PR 页 Label 下拉里几百个标签**大部分不适用于 PR**。
- **存在近义脏标签**：`c-pipeline-passed`（疑似 `ci-` 错别字）、`ci-pipeline-success`、`torchair`/`torchchair`/`torhchair`、`triage-review`/`triage-reveiw`/`triaaged` → **判定门禁必须精确等值匹配 `ci-pipeline-passed`，不要用 `-like '*pipeline-passed*'`**（否则错别字标签会被算成"通过"）。
- `/labels` 里**有标签名带前导空格**（`" ci-pipeline-passed"`、`" ci-pipeline-success"`、`" ci-pipeline-running"`、`" triage-reveiw"`，前三个还有无空格孪生）→ 比较前先 `.Trim()`。
- `Bug` 与 `bug` 是两条真实记录；PowerShell 的 `Sort-Object -Unique` **默认大小写不敏感**会把它们并成一条 → 去重要加 `-CaseSensitive`。
- 平台脏数据形态：`[Ljava.lang.String;@<hash>`（Java 数组 toString 泄漏）、`label_name`（模板占位）→ 统计口径里剔除或单列。
- 评论 JSON 的作者字段是 **`user.login`**，不是 `username`（用后者只会得到全空）。
- fork 被删除的 PR 其 `head.sha` 会为空（实测）→ 取 sha 前先判空。

### 6.4 快速失败且**没有** `AtlasAccount` 结果评论 ⇒ 先查合入冲突（别先怀疑内容）

**判据（实测）**：正常一轮 `compile` 会在约 1 分钟内贴出 `PR-pipeline_<仓>#N [ commitID：<head> ]` 的结果评论（§7）。
若流水线**在 40~60 秒内**就变 `ci-pipeline-failed`、且**始终没有**这条结果评论，第一嫌疑**不是你的内容**，
而是**这个 PR 合不进去**（与目标分支冲突 / 落后过多）——平台校验的是**合入后的结果**，合不进去就在早期中止，
连阶段表都不发。**此时 `retry` 无用**：实测 `retry` 被接受（HTTP 201）并真的重跑了，40 秒后以同样方式失败。

**两步确认（各一条命令）**：
1. PR 页面（Playwright）搜 `存在冲突` / `落后目标分支 N 个提交`；冲突时面板写「合并受阻 / 代码合入存在冲突」。
2. `git merge-tree --write-tree --name-only HEAD origin/master`（**git ≥ 2.38**，不碰工作区）→ 直接打印冲突文件清单（与 §9 同一套命令，remote 名统一用 `origin`）。

**先补历史再算分叉（浅克隆陷阱）**：浅克隆下 `git merge-base` 报 `fatal: ... no merge base`，
而 `rev-list --count` 会给**看起来合理但完全错误**的 behind/ahead（实测假值 2/2，真值 3/3）。先
`git fetch --unshallow upstream` 再算，否则会得出"没落后"的错误结论。

**证明"不是我的改动"（可复用套路）**：① 对比推送前后 `python ci/guard.py --repo . --json <f>` 的 `summary`——
逐字相同即无新增阻塞（注意**阻塞数非 0 不代表门禁会挂**：实测 master 自身就带阻塞，别的 PR 照样
`ci-pipeline-passed`）；② 在干净 master 工作树上跑同一套检查做基线；③ 看**别的 PR 当天有没有通过**
（有通过 → 不是平台整体故障，是本 PR 特有）。这套三步能逐条否证 guard / 尾随空白 / 换行 / YAML / `<>` 占位符 /
自动格式化等嫌疑，把真因收敛到合入冲突。

**修法**：`git merge origin/master`（`origin` 指目标仓，remote 名不同就替换）→ 解冲突（**两侧都保留**，别丢目标分支新增的契约）→ 提交合并 commit →
**补发 `compile`**（§5 标准动作）。合并后回读 `behind = 0` 与门禁转绿。

### 6.5 文档门禁（docs CI）失败定位与「公网地址」URL 可达性硬规则

**① 取逐行错误原文：只认 PR 评论，别去翻平台 step 日志。** 文档门禁的逐行错误（「第 X 行 + 违规 URL + 性质」）只出现在 `ascend-robot` 的 PR 评论里，靠匿名接口取，**不需要 token**：

```powershell
$w=New-Object Net.WebClient; $w.Headers.Add('User-Agent','ps')
($w.DownloadString('https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls/<n>/comments?per_page=100') | ConvertFrom-Json) |
  Where-Object { $_.user.login -eq 'ascend-robot' } | Sort-Object created_at | Select-Object -Last 1 -ExpandProperty body
```

- 取到的是 `ascend-robot` **最新**一条含 `本次检查出 N 项错误` 表格的评论，**表格里逐行给出「第 X 行 + URL + 性质」**。
- 该 `comments` 接口**匿名 200**（§7 已列），但**默认只回 20 条，必须带 `?per_page=100`**（§7/§10）——否则取到的是旧评论、看到的是上一轮的结论。
- **不要去 openlibing 平台翻 step 日志**：step 日志类接口（`/pipeline-run/step/log`、`/log`、`/job/log`）一律 **401**（§6.1/§10，早试过）。`pipeline-run/detail`（§6.1）虽**匿名 200**，但对**文档门禁那条流水线只到阶段级**——实测只回 `阶段_2 = FAILED`、`Build构建 = FAILED`，**没有行级信息**。→ 定位文档门禁错误**唯一可靠来源是评论**。

**② 标签只给结论、不给原因。** 文档门禁标签是 `docs-ci-pipeline-success` / `docs-ci-pipeline-failed`；**不存在 `docs-ci-pipeline-passed` 这个标签**——`ci-pipeline-passed` 是**代码门禁**（AtlasAccount）的（§6），**两者别混用、别互相反推**。看到 `docs-ci-pipeline-failed` 只知道"失败"，**必须回读评论①**才知道挂了什么。
失败项候选就是 §6 列的四项（`markdownlint` / `link-validity-check` / `resource-existence-check` / `tag-closed-check`）；**实测新增内容最容易挂的是 `link-validity-check`**。

**③ URL 可达性硬规则（写「公网地址声明 / 链接清单」类文档时必须遵守）**

1. 每个写成 `<https://...>` **自动链接**的地址，都必须是**真探针可达**的合法 URI。探针口径：**HEAD 失败退化 GET、带 `User-Agent`、超时 15s、跟随重定向**。
2. **含字面空格的 URL 必然被判失败**——裸中文路径不做百分号编码就会命中这一条。
3. **含 `${...}` / `${{...}}` 模板占位的地址不可作为链接**（会被当字面 URI 抽取校验）。
4. **`.git` 结尾形式不要当自动链接**：`https://<host>/<owner>/<repo>.git` 对**浏览器 UA 返回 418**、对 curl UA 返回 200（同一地址两个结论）→ 写域名即可，别写 `.git` 形式。
5. **本地探针复现不了失败的情况是存在的**：实测对一个被判失败的裸中文 URL，用「截断 URL / HEAD+GET / 4 种 UA」**全部拿到 200**——失败发生在**门禁的 URL 抽取层，而非传输层**。→ **本地探针只能筛候选，定案必须用评论①的原文。**

**④ URL 必须可回溯。** 清单 / 声明类文档里出现的**每个** URL，都必须能在**仓库源文件里逐字 `git grep` 到**；**禁止凭记忆补 URL**。
- 典型错误形态：凭记忆写域名 / owner，`git grep` 对写错的那串**零命中**，直接导致 `link-validity-check` 失败（错的是域名或 owner 段，肉眼很难看出来）。
- 因此**自检脚本要加一条断言：表内每个 URL 都能在目标 ref 的对应文件里逐字找到**（找不到就报错退出，别只做格式检查）。

**⑤ 修完必须重新触发。** head 一变，`compile` 门禁需**重新评论**才跑（§5 标准动作）；文档门禁重新出现 `docs-ci-pipeline-running` 还要再等 **2~4 分钟**（§6 有阈值，别等 90 秒就下结论）。

### 6.6 CLA 门禁与提交身份：以标签为唯一判据，按「提交作者邮箱」复查

**① 判 CLA 只看标签，不要去评论里找文案。** 标签是 `ascend-cla/yes` / `ascend-cla/no`（打标主体见 §6）。
实测在 PR 评论里按 `user.login` 筛**不存在任何 login 含 `cla` 的机器人**——**没有可引用的 CLA 评论文本**，判定依据只有标签本身。想主动查身份状态，robot 指南的指令表里列了 `/check-cla`（§6.2；**未验证**：未实测发过该指令，只从指南读到）。

**② CLA 按「提交作者邮箱」判定，head 一变就复查。** 只要 PR head 变化（新增提交 / amend / rebase / 强推），CLA 就会重新校验：新提交的**作者邮箱**若不是 CLA 已签署的那个地址，标签会从 `yes` **掉回 `no` 并阻断合入**。

**③ 典型错误形态：作者邮箱被写成平台 noreply 地址。** 新提交把 作者=提交者 写成 `<用户名>@users.noreply.gitcode.com`（GitCode 的 **noreply 地址**形态，**别当已签署邮箱**），而同一 PR 里早先通过 CLA 的提交用的是账号真实邮箱 → 新 head 一出即 `ascend-cla/no`；改回真实邮箱即恢复 `yes`。
**共同陷阱**：拿 `git -c user.email=<noreply 地址> ...` 之类方式覆盖身份，或在**没有 local `user.email`** 的仓里想当然。→ **提交前先 `git config --get user.email` 确认，不要覆盖成平台 noreply 地址。**

**④ 修法：只改身份、不改内容（实测序列）。**
```powershell
# 1) 先存档指纹——改完必须逐字不变
git rev-parse 'HEAD^{tree}'
git show -s --format=%B HEAD | git hash-object --stdin
# 2) 作者与提交者都要改（只加 --author 不够）
$env:GIT_COMMITTER_NAME='<Name>'; $env:GIT_COMMITTER_EMAIL='<CLA 已签署邮箱>'
git commit --amend --no-edit --author="<Name> <CLA 已签署邮箱>"
# 3) 断言：tree 与提交信息 hash 不变；再 `git diff --check` 取 exit 0
git show -s --format='%an <%ae> | %cn <%ce>'      # 两处都要核，别只看作者
# 4) 自己的 fork 特性分支
git push --force-with-lease origin HEAD:refs/heads/<branch>
# 5) 上游共享分支：用带期望值的 lease，先 --dry-run 验一次
git push --dry-run --force-with-lease=refs/heads/<br>:<旧sha> upstream HEAD:refs/heads/<br>
```
只加 `--author` 不改提交者**不够**：作者与提交者两处都会被平台读。

**⑤ 改完必须在新 head 上重发 `/compile`，再轮询到三个标签同时齐才算过**：`ascend-cla/yes` + `ci-pipeline-passed` + `docs-ci-pipeline-success`。
**中间态只会出现 `ci-pipeline-running`**——别把"暂时没有 `ci-pipeline-passed`"误判成门禁缺失（§6 有阈值）。实测：发 `compile` → 约 1 分钟起跑 → **约 5~6 分钟**才通过。重发动作本身见 §5 标准动作（任何 head 变化后都要补发）。

**⑥ 要能长期回滚就得自己留对象。** 身份重写会让**旧 sha 变成不可达对象**（只剩 reflog / `gc` 宽限期），想长期可回滚就自建 `refs/backup/...`，或至少记下旧 sha 与期望 lease 值。

**⑦ worktree 相关坑（两项）。**
- `git branch -D` **删不掉被 worktree 检出的分支**，报 `cannot delete branch ... checked out at ...` → 先 `git checkout --detach <新sha>` 再删。
- 改写历史时优先用**空闲的 detached worktree**，别在有未提交改动的主工作树上切分支（worktree 复用口径见 §9）。

## 7. OpenAPI v5 自动化路径（有 token 时优先）

- Base：`https://api.gitcode.com/api/v5`；认证：`Authorization: Bearer <token>`（或 PRIVATE-TOKEN 头 / access_token query）。token 生成：https://gitcode.com/setting/token-classic （勾选 api/pull_requests 等权限）。限速 400 次/分。
- **哪些接口免 token（实测，公开仓）**：`GET /repos/:owner/:repo/branches` 与 `GET /repos/:owner/:repo/pulls?state=all` **不带任何凭据就能读**（可直接用来查 PR 状态/labels/head repo，很适合只读巡检）；但 `GET /repos/:owner/:repo`（仓元信息）**反而强制要求 `private-token` 头**，否则 400 `Orchestration error: Invalid header parameter: private-token, required`。写操作一律要 token。
- **`mergeable` 字段直接可读（实测）**：`GET .../pulls?state=all` / `GET .../pulls/:n` 的 `mergeable`（`true`/`false`）就是"能否合入"的权威判定，匿名可读。**修完冲突后回读这个字段确认 `mergeable: true`，是闭环验证最快的一步**；不用去抓 SPA 页面。
- **token 来源：可直接复用 Windows 凭据管理器里已有的 GitCode 凭据**（不必每次问用户；凭据来自 `git push` 时存下的 classic PAT）：
  ```powershell
  # ⚠️ 必须用 cmd 重定向喂 stdin。PS 管道（含 @("protocol=https","host=gitcode.com","") | git credential fill）
  #    会让 git 报 fatal: refusing to work with credential missing protocol field
  $d = "$env:TEMP\gccred"; New-Item -ItemType Directory -Force -Path $d | Out-Null
  [IO.File]::WriteAllText("$d\in.txt", "protocol=https`nhost=gitcode.com`n`n")
  cmd /c "git credential fill < `"$d\in.txt`" > `"$d\out.txt`" 2>&1"
  $out = [IO.File]::ReadAllText("$d\out.txt")
  $tok = (($out -split "`r?`n") | Where-Object { $_ -match '^password=' }) -replace '^password=',''
  ```
  该 `password` 即 PAT，可直接当 `private-token` 头用。**先校验身份再动手**（避免用错账号发 `compile`——只有创建者/白名单的评论有效）：
  ```powershell
  # GET https://api.gitcode.com/api/v5/user  -Headers @{ 'private-token' = $tok }
  #   → {"login":"EliasKaslan","name":"xmz", ...}        实测 200
  # GET https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops -Headers @{ 'private-token' = $tok }  实测 200
  ```
  **token 不写入仓库文件、日志或命令历史**；缓存位置放 skill 目录内或 `~\.dsh\.secrets\` 均可（2026-10-08 起鼓励 skill 写明凭据文件位置；统一策略见 `github-pr-flow` §0）。
- **用 API 发 `compile` 触发代码门禁（实测有效）**：
  ```powershell
  $payload = @{ body = 'compile' } | ConvertTo-Json -Compress
  $bytes   = [System.Text.Encoding]::UTF8.GetBytes($payload)
  Invoke-WebRequest -Uri "https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/pulls/$n/comments" `
    -Headers @{ 'private-token' = $tok } -UseBasicParsing -Method Post `
    -ContentType 'application/json; charset=utf-8' -Body $bytes      # → 201 Created
  ```
  用创建者 token 发即生效，无需浏览器；实测约 60s 内 `ci-pipeline-passed` 就位，随后 `AtlasAccount` 贴出 `PR-pipeline_MindSpeed-Ops#N [ commitID：<head> ]` 的结果评论（**核对 commitID 是否等于当前 head**，否则是在看旧一轮）。
- **⚠️ 编码坑（写操作必读；通用机制与清单见 `pwsh-on-windows`）**：GitCode 的响应头**不带 `charset`** → PowerShell 按 Latin-1 解码，中文标题/正文全变乱码。只读时只是"显示乱码"，但**写操作会真实损坏数据**：`PATCH /repos/:owner/issues/:number` 的 `title` **必填、必须回传原标题** —— 拿乱码回填会把标题**永久写坏**。GitCode 读写一律显式 UTF-8：
  ```powershell
  function Get-GitCodeJson([string]$Url, [string]$Token) {
      $h = @{}; if ($Token) { $h['PRIVATE-TOKEN'] = $Token }
      $r = Invoke-WebRequest -Uri $Url -Headers $h -UseBasicParsing -Method Get
      # 关键：取原始字节流自己按 UTF-8 解码，绕开 PS 的 Latin-1 误判
      return ([System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json)
  }

  # 写操作同理：body 必须显式转 UTF-8 字节再发，否则中文被写坏
  $json  = @{ repo = 'MindSpeed-Ops'; title = $title; milestone = 849946 } | ConvertTo-Json -Compress
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
  Invoke-WebRequest -Uri "https://api.gitcode.com/api/v5/repos/Ascend/issues/$n" `
      -Headers @{ 'PRIVATE-TOKEN' = $Token } -UseBasicParsing -Method Patch `
      -ContentType 'application/json; charset=utf-8' -Body $bytes
  ```
  写完后**必须逐个回读校验**：`PATCH` 成功响应的 `milestone` 字段是空的（不代表失败），且 `title` 是否被写坏只能靠回读对比改前快照确认。
- **辅助函数别 dot-source**：`. .\helper.ps1` 会被执行策略拦下（本机 `Restricted`，通用清单见 `pwsh-on-windows`）→ 把函数**内联进命令**，无需改策略。
- **函数名别撞内置别名**：`GC` 是 `Get-Content` 的别名、**优先级高于函数**（实测与通用清单见 `pwsh-on-windows`）——用 `Get-GitCodeJson` 之类不冲突的名字。
- **建私仓（Gitee 风格接口，本轮实测一次成功）**：`POST https://api.gitcode.com/api/v5/user/repos`（凭据用 `private-token` 头或 `Authorization: Bearer`），body `{"name":"<repo>","private":true,"auto_init":false}` → **200**（不是 201）。**建仓响应缺 `default_branch`、也缺权限字段** ⇒ 建完必须回读两步才算建好：`GET /repos/:owner/:repo`（拿默认分支）与 `GET /repos/:owner/:repo/collaborators?per_page=200`（确认自己 `access_level=50` / `role_name=Owner`；`total` 会超一页，分页口径同 §10 表末那条）。
- **⚠️ git https 传输层鉴权与 API 头鉴权是两套，别互相推**：传输层**只认** `https://<user>:<token>@gitcode.com/<owner>/<repo>.git`；把 token 当用户名（`https://<token>@gitcode.com/...`）**必失败**，逐字原文 `fatal: could not read Password for 'https://<redacted>@gitcode.com': terminal prompts disabled`（同一形态在另一个机制里也有实测记录 → `dsh-repo-sync` §1/§4）。
- **所有 git 调用都要前置禁用凭据助手**：`git -c credential.helper= ...` + `$env:GIT_TERMINAL_PROMPT='0'`——本机 `credential.helper=wincred` 时打 gitcode.com 会**弹 Git Credential Manager GUI 并挂死**（实测 `ls-remote` 卡满 120 s）。**不要**改用 `GIT_ASKPASS='cmd /c exit 1'` 顶替：实测报 `error: cannot spawn cmd /c exit 1: No such file or directory`。
- **`ls-remote` 的退出码按"有没有匹配的 ref"读，不按成败读**：空仓（无任何 ref）时 `git ls-remote --exit-code <url>` → **exit=2**（无匹配 ref，**不是失败**）；**鉴权失败是 exit=128 + `fatal:`** ⇒ 先看 stderr 有没有 `fatal:`，别只看非零码。
- **判据纪律：负控是判据的一部分**——要拿"空仓 exit=2"当结论，**必须配一个负控**：把 token 截短 1 个字符重跑**同一条**调用，必须复现 **exit=128**；否则无法证明那个 exit=2 不是被吞掉的真失败。
- PR 的 `html_url` 是 `/merge_requests/<n>`（不是 `/pull/<n>`），`number` 与 `iid` 同值。
- 文档：https://docs.gitcode.com/docs/apis/ （Pull Requests 章节）。
- **创建跨仓库 PR**（对 MindSpeed-Ops）：
  ```powershell
  $payload = @{
    title = 'docs: <标题>'
    head  = '<user>:<branch>'        # 跨仓 PR 格式必须是 username:branch
    base  = 'master'
    body  = '<三段模板正文>'
    fork_path = '<user>/MindSpeed-Ops'   # 跨仓 PR 必填
    squash = $true
  } | ConvertTo-Json
  # ⚠️ body 含中文时**必须**传 UTF-8 字节：传字符串会被按 ASCII 编码发出，中文在网线上变成 `??`，**本地不报错**
  #    （与本节开头「编码坑」同一条规则；逐字实测证据见 `pwsh-on-windows`）
  Invoke-RestMethod -Method Post -Uri 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/pulls' `
    -Headers @{Authorization="Bearer $t"} -Body [System.Text.Encoding]::UTF8.GetBytes($payload) `
    -ContentType 'application/json; charset=utf-8'
  ```
  可选参数：labels（逗号分隔）、assignees/testers（逗号分隔 username）、draft、prune_source_branch、squash_commit_message、inner_issue_nums（分号分隔 issue iid，关联 issue）。
- 常用读接口（均已验证文档存在）：`GET /repos/:owner/:repo/pulls?state=all`（支持 author/labels/base 过滤）、`GET .../pulls/:number`、`.../pulls/:number/commits|files|comments`；`POST .../pulls/:number/comments`（评论 body，可用来发 `compile`）；`PATCH .../pulls/:number`（改标题/描述/状态）；`PUT .../pulls/:number/merge`（合并，需权限）。
- **标签审计的权威接口（匿名 200 可读）**——用它可**精确还原"谁在什么时刻打/摘了哪个标签"**，不必靠行为推测：
  ```
  GET https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/pulls/:n/operate_logs?per_page=100
  ```
  逐条返回 `时间 | actor | "add/delete label X"`（actor 即 §6 的打标主体，含 `/label add|remove` 这类手加标签的痕迹）。
- **⚠️ 分页坑（默认 20 条）**：`pulls/:n/operate_logs` 与 `pulls/:n/comments` **默认都只回 20 条，必须显式带 `?per_page=100` 并翻页**。实测单条 PR 的 `operate_logs` 与 `comments` 都能到**百条量级**——**只看默认 20 条会得出完全错误的结论**（§10）。
- **匿名可读接口清单（实测 200）**：`/labels`、`/pulls`、`/pulls/:n`、`/pulls/:n/comments`、`/pulls/:n/operate_logs`、`/pulls/:n/commits`。**不存在/不可用（别试）**：`/issues/:n/events`、`/issues/:n/timeline`、`/pulls/:n/events`、`/issues/:n/labels`、`/issues/:n/notes`、`/pulls/:n/approvers` → **404**；`labels/search` → **405**。
- **纯浏览器兜底**（无 token）：Playwright 登录态已在（浏览器 cookie 复用），直接导航到 §3 的 compare URL，原子化填表单（注：`github-pr-flow` 早先的浏览器兜底与 run_code / wrong-tab 守卫**已从它自己的主流程移除**，其 §8 只剩一个 compare URL 备查，别去那里找那段流程）。GitCode 登录页协议复选框是 vue-devui DCheckbox，**常规点击无效**，解法见 `aidd-report-reader` skill §1（Vue vnode 树注入 onUpdate:modelValue）。

## 8. 新增算子 PR 的附加交付件（MindSpeed-Ops 专属）

**该仓专属内容已移入 `references/mindspeed-ops.md`**（`docs/zh/ops.md` 硬性交付件、UT 精度用例、ATK 测试三件套、
`docs/zh/supported_operators.md` 登记）。**换其它仓时先确认该仓自己的交付件要求**，不要照搬。

## 9. PR 冲突诊断与修正（rebase 到最新 master）

**第一步：分清"跟谁冲突"**。PR 页显示"存在冲突"（API `mergeable: false`）只说明**与目标分支冲突**，不代表两个 PR 互相冲突。用 `git merge-tree`（git ≥ 2.38，**不碰工作区**）一次判定：

```bash
git fetch origin --prune
git merge-tree --write-tree --name-only origin/master <branch>   # exit 0 = 干净；exit 1 = 冲突
git merge-tree --write-tree <branchA> <branchB>                  # exit 0 = 两个 PR 之间无冲突
```
exit 1 时，stdout 里 tree OID 之后的行就是冲突文件清单。

**实测形态**：两个 PR **互不冲突**（改动文件完全不重叠，一个只动 `docs/zh/**`，另一个动 `README.md` + `docs/zh/supported_operators.md`），是**各自**与 master 冲突。

**典型成因：撞上 master 后来的"全局格式整改"提交**。MindSpeed-Ops 已合入的全局约定（写文档前先 `git log --oneline -15 origin/master` 看有没有新的整改提交，能省一整轮返工）：
- `c83994e docs: 移除Markdown文档中中英文及中文与数字之间的空格` —— **新增/修改文档不要在中英文、中文与数字之间加空格**（写 `新增自定义triton算子指南`、`每个AI Core轮流`、`表1`）。这是目前最容易踩的冲突源。
- `dc01505 docs: 扩写README简介并修复算子清单链接` —— 算子清单里指向 `.py` 源码的链接必须改指 Markdown 文档；无对外 API 的内部算子（`chunk_bwd_dh`、`fused_recurrent_bwd`）不进清单。

**典型成因 2：master 已经合入了"同一个 PR 拆出去的另一半"**。原 PR 因体量大被拆成两个：一个只管**格式**（大小写 / 错别字 / 术语），一个只管**语义**（签名 / 公式 / 参数范围）；格式那个先被合入，于是 master 上那条"统一专有名词大小写与文档格式"的提交正是本 PR 自己那一半改动。**结果：本 PR 的语义行与 master 的格式行逐行对撞**（同一行被两边各改一次），冲突块全是这个成因。
- 诊断口径：`git log --oneline <merge-base>..origin/master -- <冲突文件>` 若看到"和本 PR 主题高度相似"的提交（如 `统一专有名词大小写与文档格式`），就是这种情况，**不是**两个 PR 互撞。
- 另一个坑：**拆出去的 PR 合入后，本 PR 的分支基线就永久落后了**，`mergeable: false` 会一直存在，必须 rebase。

**冲突解决口径："以已合入的代码为准" = 取 master 措辞/空格约定，再叠加本 PR 的语义改动**。逐块手工或脚本施加，**绝不要整块选 theirs**——本 PR 那一侧往往携带"基于旧基线的格式"，会**回退掉 master 已经修好的东西**。典型形态：master 已在某行把错误注释改对，而本 PR 那一侧仍是旧注释 + 一个变量名修正；**正确解 = master 的注释 + PR 的变量名**，整块选 theirs 就把 master 的修复打回去了。
- 空间约定细则（`c83994e` 实际规则）：**删掉中文↔拉丁字母/数字之间的空格，但保留中文↔行内代码（反引号）之间的空格**。例：`shape为 (B, T, H)`、`转换为NPU \`torch.int32\``、`按 \`chunk_size\` 分块` 里的空格**都保留**，而 `每个chunk的`、`必须是2的幂次` 无空格。改写冲突行时按这个口径统一。

**rebase 与冲突解决原则**：
```bash
git worktree add <dir> <branch>      # 推荐：每个分支一个 worktree，别在脏工作区里 rebase
cd <dir> && git rebase origin/master
```
冲突时**取 master（rebase 中的 ours/HEAD）一侧**——它带着最新的格式约定与链接修复——再把本 PR 的**语义改动**逐条叠加上去。**不要整块选 theirs**，否则会把 master 的修复回退掉。

**可脚本化**：冲突块结构规整时（同一批行被两边各改一次），写脚本解析 `<<<<<<<`/`=======`/`>>>>>>>`，保留 ours 侧并施加字面替换规则，比手工改十几个冲突块可靠得多。两种写法都跑通过：
- 「逐块规则替换」：把字面替换规则抽成独立数据文件，脚本按冲突块施加，避免手改漏块。
- 「整块映射」：把"每个文件按顺序的冲突块 → 最终文本"写死成 `RESOLUTIONS` 字典，脚本按 `<<<<<<<`…`>>>>>>>` 扫描替换，并**校验块数是否与预期一致**（多一块/少一块直接报错退出），避免静默漏解。

**非交互完成 rebase（Windows 必读）**：`git add -A && git rebase --continue` 会拉起编辑器改 commit message 而**卡住**。用环境变量喂一个空编辑器：
```powershell
$env:GIT_EDITOR='true'; $env:GIT_SEQUENCE_EDITOR='true'   # Git for Windows 的 sh 里 true 可解析
git add -A docs/zh
git rebase --continue        # 自动沿用原 commit message
```
完成后 `git log --oneline -3` 确认新 head 落在 master 之上、且 `git status -sb` 显示 `ahead 1`。

**⚠️ Windows 换行坑（必读）**：该仓检出 `core.autocrlf=true` —— 工作区是 **CRLF**、仓库里存 **LF**。
- 自写脚本必须用 `open(..., newline='')` / 二进制方式读写以保留 CRLF；或分析前先 `raw.replace('\r\n','\n')`。
- 否则"按 `\n` split 再 `line.rstrip()`"会把每行结尾的 `\r` 当成行尾空白，**误报满屏 trailing whitespace**（能产出上千条假告警）。
- 判断"是否引入行尾空白"**以 `git diff --check <base> <branch>` 为准**（exit 0 = 干净），别信自写脚本。

**worktree 坑**：同一分支不能在两处检出（`fatal: 'xxx' is already used by worktree at ...`）。先 `git worktree list` 找已有工作区——用户常把某个 PR 的分支留在自己的任务目录里（如 `260922_catlass清单/repo`），直接复用那个目录。

**验证闭环（缺一不可）**：
1. `git merge-tree` **四种组合全 exit 0**（各自→master、A+B、B+A）——保证将来谁先合入都不再冲突；
2. `git diff --check <base> <branch>` 无空白错误；
3. markdown 自查：表列数一致、表前后空行、文件末尾单换行。⚠️ **仓内 `.markdownlint.yaml` 关了 MD013/MD033/MD040/MD051/MD060，但它不是判据**——文档门禁跑在 openlibing 平台侧、用的是**平台托管配置**（这正是「未能获取文档 CI 配置」那类故障的由来，见 §6），所以**链接锚点（MD051）仍是真实高频失败项**（§6/§10）。**别拿仓内配置推断平台结论。**；
4. **语义零丢失校验（最有力的一条）**：把"原 PR 的 diff"与"rebase 后的 diff"**去掉所有 ASCII 空格**后比较增/删行**多重集合**是否逐文件相等。空格归一化把 master 的空格约定差异抹平，剩下的任何差异都是真实语义丢失。经验信号：rebase 后的 `git diff --stat <master>` 的 `insertions/deletions` 应与原 PR 的 `--stat` **完全一致**。
5. **空格回归校验**：对 `git diff <master>` 的新增行做"中英文 / 中文与数字之间空格"计数（**先把行内代码 span 抠掉**再匹配，否则会把允许的 `按 \`x\` 分块` 误报），期望结果为 **0 条**。
6. `git push --force-with-lease` 后回读 API：`mergeable: true`（§7）；
7. **立即自动补发 `compile`**（§5 标准动作，不必问用户），随后回读 `ci-pipeline-passed` 就位、`AtlasAccount` 结果评论的 `commitID` 等于当前 head；
8. 等 `docs-ci-pipeline-success` 回来。若变 `docs-ci-pipeline-failed`，先看机器人给的原因——**"未能获取文档 CI 配置"是平台瞬时故障，不是你改坏了文档**（见 §6/§10），**重发 `compile` 即可触发重跑**，不必为此多推一次 head。⚠️ 文档门禁重新出现 `running` 要 **2~4 分钟**，别等 90 秒就下"评论刷不动"的结论（§6 有阈值）。

**⚠️ 强推的代价**：rebase 后必须强推，而 ascend-robot 检测到 head 变化会**自动摘掉 `lgtm` + `approved`**（评论：*New code changes of the pull request are detected and remove these labels lgtm, approved*）。实测还发现：**强推后 `ci-pipeline-passed` 也一并消失**。也就是说 **rebase 一次 = 重新走一遍评审 + 代码门禁**。
- **必须做**：强推后**自动补发 `compile`** 把代码门禁拿回来（§5 标准动作，用户已授权，不必问）。实测：强推后补发 `compile`，`ci-pipeline-passed` 随即就位；巡检时核对结果评论里的 `commitID` 是否等于当前 head。
- **只需告知**：`lgtm`/`approved` 无法自助恢复，要在汇报里**明确提醒用户去请原评审人重新 review**。这条别忘说，否则用户以为 PR 已经齐活。
- 汇报时把"已自动补发 compile + 当前标签快照"一并给出，让用户一眼看到还差什么。

### 9.1 内容变了却用 `--amend --no-edit`：提交内容与 message 矛盾（真踩到）

**实测形态**：把"新增英文版 OVERVIEW.md"的改动回退成"不新增"后，用 `git commit --amend --no-edit` 提交 → commit message 仍是 `docs: docker镜像概览补充安全风险说明并新增英文版OVERVIEW.md`，而该提交的实际内容**已经不新增任何英文文件**，message 与 diff 矛盾。

**发现方式（可抄）**：强推后用权威接口回读 PR 操作日志——里面逐字记录 `added 1 commit, force_push=true` 以及该提交标题，与实际 diff 对比即可看出不一致：
```powershell
Get-GitCodeJson 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/pulls/<n>/operate_logs?per_page=100' $tok
```
（`Get-GitCodeJson` 定义见 §7；该接口匿名也可读，见 §7 匿名接口清单。）

**修法（实测序列）**：
```bash
git commit --amend -m "<与新内容一致的新 message>"   # 内容一变就必须显式重写 message，别用 --no-edit
git rev-parse 'HEAD^{tree}'                           # 断言 tree OID 与 amend 前逐字相同 = 只改了 message、没动内容
git push --force-with-lease origin HEAD:refs/heads/<branch>
```
- 实测 amend 前后 tree OID **均为** `a9a7f4dd59490a0ba0be5927051de7ab0c7e5ea3`（判据是"两次相等"，别照抄这个值）；修正后强推日志里的提交标题变为 `298ff362 - docs: docker镜像概览补充安全风险说明`。
- head 又变了 → 按 §5 标准动作**再补发一次 `compile`**。
- **边界**：`--amend --no-edit` 只对"只改身份 / 只改 message、内容一字不动"安全（如 §6.6 ④ 的 CLA 身份修正，tree OID 不变）；**内容一变就必须用 `-m` 显式重写**，否则 message 留在旧内容上。

## 10. 常见坑速查

> 通用 PowerShell 陷阱（编码 / 管道统计 / PS7 语法 / BOM / 只读变量 / 别名冲突）的完整清单与可抄写法见 skill `pwsh-on-windows`；下表只保留**与本仓 PR 流程相关**的后果与修法。

| 现象 | 原因与解法 |
|---|---|
| `/pulls/new` 404 | 正确 URL 是 `/pull/new`（单数）；跨仓 PR 要从 **fork 侧**发起 |
| 上游 /pull/new 选不到自己分支 | 那个表单只列上游分支；去 fork 仓库 → Pull Requests → 新建 |
| web_fetch 抓 GitCode 页面只有导航栏 | SPA 动态加载，blob/pulls 正文抓不到；用 Playwright evaluate 取 `.markdown-body`/body 文本 |
| CI 大部分阶段 IGNORED | doc-only PR 正常现象（Only_doc_commit 判定） |
| docs-ci 挂 MD051/锚点无法访问 | 修复 markdown 锚点链接（中文标题锚点要精确匹配）；link-validity-check 会真访问 |
| code-ci 不跑 | 没评论 `compile`（仅创建者/白名单有效） |
| PR 页"存在冲突"/"落后 N 个提交" | fork 侧"同步源项目"或 rebase 后强推；**先用 `git merge-tree` 分清是跟 master 冲突还是两个 PR 互撞**（§9） |
| 门禁 40~60 秒就 failed 且**没有** `AtlasAccount` 结果评论 | 基本可判"合不进去"（冲突/落后），**`retry` 无用**；按 §6.4 两步确认后 merge master 解冲突再补发 `compile` |
| `mergeable: false` 就以为是两个 PR 互撞 | 多数是**各自**与 master 冲突（撞上 master 后来的全局格式整改提交）；用 `git merge-tree` 分别判定 |
| 想自己点"合入"点不动 | **保护分支（master）**上贡献者无合并权限；等 committer。未保护的版本分支（26.1.0/26.2.0）可直推，见 §12 |
| `fatal: ambiguous argument 'origin/26.2.0': unknown revision` | 该克隆的 fetch refspec 只含 master（`fetch = +refs/heads/master:...`）；用 `git fetch origin '+refs/heads/26.2.0:refs/remotes/origin/26.2.0'` 显式取，用完 `git update-ref -d` 清理（§12.2） |
| 该不该给版本分支回合并，凭 `git diff --stat <版本分支> master` 就动手 | 必须补"严格祖先 + 等价性"两步：`git rev-list --count <版本分支>..master` / `git merge-base`，以及 `git merge-tree --write-tree <版本分支> <已合入 head>` 与 `git rev-parse '<squash>^{tree}'` 的 tree OID 相等（§12.2/12.3） |
| 版本分支回合并后还想去发 `compile` | 直推 FF 后**没有待合入的 PR**，无处可发；只有走 `base=版本分支` 的 PR 才需要 `compile`（§12.4） |
| 权限探测只看 `branches/:name` 的 `can_push` | 只拿到布尔值；要权威等级（10/20/30/40/50）改看 `GET /repos/:owner/:repo/collaborators?per_page=200`（total=100 会分页，**取 200 才够**） |
| token 落到临时文件 | **默认绝不落盘**——`git credential fill` 取（§7）后只留内存变量，传参一律 `-Headers @{ 'private-token' = $tok }`；唯一例外是 §7 那次 `%TEMP%` 中转（用完立刻删、不进 git 工作区），除此之外别写任何临时文件 |
| ascend-cla/yes 消失 | 描述或代码更新后机器人重新校验，已签 CLA 会自动恢复 |
| 强推后 `lgtm`/`approved` 没了 | ascend-robot 检测到 head 变化就摘标签，属预期；去请原评审人重新 approve/lgtm |
| 强推后 `ci-pipeline-passed` 没了 | 同上；**必须重发 `compile`**（§5/§7）——按 §5 标准动作**自动补发，不必问用户**，否则合入时缺门禁标签 |
| 想查"谁在什么时刻打/摘了哪个标签"却靠行为推测 | 有权威接口 `GET .../pulls/:n/operate_logs?per_page=100`（**匿名 200**），逐条返回 `时间 \| actor \| add/delete label X`（§7）；`/label add\|remove`、手加标签的痕迹也在里面 |
| 查 `operate_logs` / `comments` 只看到 20 条，误判"机器人没打标签/没发言" | 两个接口**默认都只回 20 条**；必须 `?per_page=100` 且**翻页**（实测单条 PR 的 `operate_logs` 与 `comments` 都能到**百条量级**，只看 20 条会得出完全错误的结论）（§7） |
| 巡检报"`ascend-cla/yes` 丢了，异常" | 先看它变成了什么：**回填 `ascend-cla/yes` = 正常重校验**；**掉成 `ascend-cla/no` = 新 head 的作者邮箱不是 CLA 已签署地址** → 按 §6.6 只改身份（作者 + 提交者都要改）重推 |
| 用 `-like '*pipeline-passed*'` 判门禁通过 | 仓里有错别字脏标签 `c-pipeline-passed`、`ci-pipeline-success` 等；**必须精确等值匹配 `ci-pipeline-passed`**，否则会把脏标签算成"通过"（§6.3） |
| 标签名比较结果莫名不对 | `/labels` 里 **4 个标签名带前导空格**（`" ci-pipeline-passed"`、`" ci-pipeline-success"`、`" ci-pipeline-running"`、`" triage-reveiw"`，前三个还有无空格孪生）→ 比较前先 `.Trim()`（§6.3） |
| `Sort-Object -Unique` 把 `Bug` 与 `bug` 并成一条 | PS 去重**默认大小写不敏感**，需加 `-CaseSensitive`（§6.3） |
| 看到 PR 带 `docs-ci-pipeline-success` 就以为"改过文档" | 不成立：机器人评论 `✅ 跳过 docs ci 检查，没有需要检查的文档文件` 时**照样打 success**（实测只改 `setup.py` 的 PR 也带该标签）（§6） |
| 看到带 `stat/needs-squash` 就当"还没合入"，或以为它没规则可查 | 含义是"多 commit，合入时压成一个"（本仓 squash）；但它在 `bot-review-config.yaml`/robot 指南/帮助中心 **0 命中**，**只有 operate_logs 行为证据**，且已合入 PR 里也仍有保留该标签的（§6） |
| 想手工给 PR 补一个门禁标签 | **无效**：非机器人账号添加的标签不生效，PR 会提示 `The following labels are not ready...`；只能发指令让机器人打（§6.2） |
| 在目标仓里找标签规则，或改 `.gitcode/` 想改门禁 | 目标仓**零标签声明**（`pr-pipeline-mindspeed-ops.yml` 只有流水线步骤）；权威出处在 `Ascend/infrastructure` 的 `config/bot-review-config.yaml` 与 `docs/robot/robot使用指南.md`（§6.2） |
| `tree?ref=master&path=...` 返回 401 | tree 接口匿名不可用；**改用 `contents/` 匿名列目录（200，见 §6.2.1）**，再直读 raw `https://raw.gitcode.com/<owner>/<repo>/raw/<ref>/<path>`（**中文文件名必须 URL 编码**）。**别只探根目录**——同一文件在不同仓可能位于 `docs/zh/`（§6.2.1） |
| 浅克隆下 `git merge-base --is-ancestor A B` 双向都返回 1 | 缺 merge-base 信息，会被误判成"两分支已分叉"；先 `git fetch --deepen=300 origin`（`git rev-parse --is-shallow-repository` 应变 `false`）再判｜`rev-list --count` 同理会给假 behind/ahead（§6.2.1、§6.4） |
| PS 5.1 报 `Unexpected token '?'` | PowerShell 5.1 **不支持三元 `? :`**；改用 `if/else`，别照抄 C 风格写法 |
| 查 PR 最新评论却只看到很旧的 | `GET .../pulls/:n/comments` **默认只回 20 条**（只看默认 20 条会拿到很旧的评论，误以为机器人没发言）；**必须带 `?per_page=100`** 再 `Sort-Object created_at -Descending` |
| `docs-ci-pipeline-failed`，原因是"未能获取文档 CI 配置" | **平台侧瞬时故障，不是你改坏了文档**（文档门禁配置托管在 openlibing 平台，不在仓内文件里）。实测 rebase 后首轮就可能撞上；旁证：同一次 push 的代码门禁正常 COMPLETED。先确认自己的 markdown 自查（§9 第 3 条）过，**再重发 `compile` 触发重跑**（实测正是这样转绿的），别去改文档 |
| 连发 `compile` 也刷不掉 `docs-ci-pipeline-failed` | **先别下这个结论——很可能只是没等够。** 文档门禁重跑要 **2~4 分钟**才重新出现 `docs-ci-pipeline-running`（§6 阈值）。实测在一条 `compile` 评论后只等 90 秒就误判"评论不能重触发"，实际约 2 分 40 秒后就转 running、随后 ✅ 通过。**`compile` 确实能重触发文档门禁**，无需为此多推一次 head |
| 文档门禁 failed，想知道**是第几行的哪个 URL** 挂了 | 标签只给结论不给原因（**没有 `docs-ci-pipeline-passed`**）；逐行原文（第 X 行 + URL + 性质）只在 `ascend-robot` 评论的「本次检查出 N 项错误」表里，用 `pulls/:n/comments?per_page=100` **匿名**取（§6.5）——**别去翻 openlibing 日志**（step 日志一律 401，`pipeline-run/detail` 只到阶段级） |
| `git rebase --continue` 卡住不动 | 它在等编辑器改 commit message；设 `$env:GIT_EDITOR='true'; $env:GIT_SEQUENCE_EDITOR='true'`（§9） |
| 脚本报"冲突块数量不符" | 好事——说明预期与文件实际不一致（漏解或多解）；`git rebase --abort` 后重新对齐 `RESOLUTIONS`，别硬提交 |
| 解冲突时把 master 的修复改回去了 | 整块选 theirs 的典型后果（典型陷阱：master 已把某处注释改对，本 PR 那侧还是旧注释）；**永远取 master 措辞 + 只叠加本 PR 语义**（§9） |
| 描述改完没生效 | GitCode 描述首行表格控制 title/labels/assignees，检查模板表格别删 |
| 中文标题/正文变 `ãFeatureã`、`ç®å` | GitCode 响应头缺 `charset` → 按 Latin-1 解码（通用规则见 `pwsh-on-windows`）。**写错会永久损坏标题** | 读：`RawContentStream` + `UTF8.GetString`；写：body 转 UTF-8 字节 + `charset=utf-8`（§7 有代码） |
| `PATCH` 返回 200 但响应里 `milestone` 为空 | 正常，该接口响应不回显 milestone；**必须另发 GET 回读确认**，别据此判定失败而重试 |
| 改 issue 里程碑 | `PATCH /repos/:owner/issues/:number`（注意路径只到 owner，`repo` 走 body），body 必填 `repo` + `title` + 目标 `milestone`(里程碑 number，非 title)；里程碑列表见 `GET /repos/:owner/:repo/milestones`（返回 `{value:[...]}`，`state=active` 会 400，用 `state=opened`/不带参数） |
| `. .\helper.ps1` 报 running scripts is disabled | 本机执行策略 `Restricted`（见 `pwsh-on-windows`）；函数内联进命令，别改策略 |
| `git credential fill` 报 `missing protocol field` | PowerShell 管道会先往 stdin 注入 UTF-8 BOM（机制见 `pwsh-on-windows`）；用 `cmd /c "git credential fill < in.txt > out.txt"`（§7） |
| 自写脚本报满屏 trailing whitespace | `core.autocrlf=true` 下工作区是 CRLF，按 `\n` split 后行尾 `\r` 被当成空白；改 `newline=''`/先归一化，判定以 `git diff --check` 为准（§9） |
| `git worktree add` 报 `already used by worktree` | 该分支已在别处检出；`git worktree list` 找到并复用那个目录 |
| `Cannot overwrite variable PID` | `$pid` 是只读自动变量；换个名字（见 `pwsh-on-windows`） |
| code-ci 失败项是 `pre-commit`，message 带 `DEV-CODECI-35002` | **先别改代码**：平台概率性失败（实测同一 commit 两跑可结论相反：FAILED → retry 后 COMPLETED；另一个 PR 在同一 commit 上多跑呈绿红交替）。按 §6.1 本地逐 hook 复现确认干净后，**发 `retry` 到 `pre-commit` COMPLETED**；`retry` 在**同一 pipelineRunId** 内重跑失败任务，且必须在上一轮流水线结束后发（早发被忽略）。`UT_MindSpeed_*` 失败通常是真问题 |
| 想看 openlibing 任务级状态/失败原因，但页面空白 | 页面空是 `get-user-permission` 等接口 401；改用**免登录**的 `pipeline-run/detail` 接口（§6.1，Playwright 在页面上下文 fetch，`data` 里递归找同时含 `name\|jobName` 与 `status\|state` 的对象）。step 日志类接口（`/step/log`、`/log`、`/job/log`）一律 401，别试 |
| 想按"PR 上没有失败评论"推断 pre-commit 失败类型 | **不成立**：该 action 在 PR 场景对 `failureType=install` 与 `failureType=check` **都不产出 SARIF、都不发 PR 评论**（§6.1） |
| 导出的 diff 被 read 工具判为 binary | 本机 PowerShell 的 `>` 写 UTF-16（见 `pwsh-on-windows`）；**改用 `cmd /c "git grep ... > out.txt 2>&1"` 拿原始 UTF-8 字节**（`\| Out-File -Encoding utf8` 仍带 BOM） |
| 内容已改却用 `git commit --amend --no-edit` 提交 | message 会留在旧内容上、与实际 diff 矛盾（实测：提交标题仍写"新增英文版OVERVIEW.md"，而该提交已不新增任何英文文件）；内容一变必须 `git commit --amend -m "<新 message>"`，再用 `git rev-parse 'HEAD^{tree}'` 确认 tree OID 未变，然后 `--force-with-lease` + 补发 `compile`（§9.1） |
| 已直推过的版本分支要回退，想 force-push 抹掉那个直推提交 | **不要改写共享版本分支的历史**：基于它**叠加一个回退提交**再推（实测 `fb09350..05a911c`、exit 0、无需 `--force`）；force-push 会让已 fetch 的人分叉。master 侧未合入的特性分支才可以 `amend` + `--force-with-lease`（强推代价见 §9）；版本分支的既有先例也是叠加修正提交（§12.5） |
| git 报 `fatal: could not read Password for 'https://<redacted>@gitcode.com': terminal prompts disabled` | **鉴权形态错**：git 传输层只认 `https://<user>:<token>@`（把 token 当用户名必失败）；且每次 git 调用都要带 `-c credential.helper=`（否则弹 GCM GUI 挂死）（§7） |
| `git ls-remote --exit-code` 在空仓/无匹配 ref 时回非零 | **exit=2 = 无匹配 ref，不是失败**；鉴权失败是 **exit=128 + `fatal:`**。要把它当结论必须配负控：token 截短 1 字符重跑须复现 exit=128（§7） |
| 要建 GitCode 私仓 | `POST https://api.gitcode.com/api/v5/user/repos`、body 含 `"private":true` → **200**；响应**缺** `default_branch` 与权限字段 ⇒ 必须回读 `/repos/:owner/:repo` 与 `/collaborators?per_page=200`（`access_level=50`）（§7） |

## 11. 浏览器共享注意事项

Playwright 浏览器与用户并行使用（用户常开着 GitHub/AIDD 页面）：开专用标签页（`browser_tabs action:new`）、操作前校验 URL 守卫、绝不关用户标签页；原子化操作用 run_code。详见 `aidd-report-reader` skill §4 与 `github-pr-flow` skill §8。

## 12. 版本分支回合并（backport：master → 26.1.0 / 26.2.0，MindSpeed-Ops 专属）

**该仓专属内容已移入 `references/mindspeed-ops.md`**（版本分支权限探测、三步判定、FF 直推、回退叠加提交（§12.5）与"不会多带东西"的证明）。
GitCode 与 Gerrit 不同：版本分支没有独立合入系统，维护者可直接 push，贡献者侧走 `base=<版本分支>` 的 PR。
**其它仓若无版本分支则本节不适用**（MindSpeed-Agent 只有 `master`）。

## 13. 维护记录

**历史条目已移入 `references/maintenance-log.md`**（含逐次 PR 实测数据点与自我纠错记录；其中的章节号是**当时**的编号）。
