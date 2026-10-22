# 维护记录（按时间倒序，最新在下）

> 历史条目里的章节号是**当时**的编号；正文迁到 references/ 后不再重排。

## 13. 维护记录

> 注：以下历史条目里的章节号是**当时**的编号。2026-09-23 新增 §9「PR 冲突诊断与修正」后，原 §9/§10/§11 依次后移为 §10/§11/§12；2026-09-24 在 §12 前插入「版本分支回合并」后，原 §12 维护记录改为 §13。

- **2026-09-23 复核（PR #163 rebase 解冲突 + 确立"自动补发 compile"标准动作）**：应"#163 现在存在冲突，帮我解决冲突，以已合入的代码为准"与随后"做完类似的事情后，你需要自动帮我评论 compile"之需。**本次最重要的产出是一条常驻行为约定**：
  1. **🔁 标准动作（写进 §5/§9）**：**任何 head 变化（rebase/强推/追加提交）完成后，自动用创建者 token 补发 `compile`，不等用户开口**——用户 2026-09-23 明确授权。同时保留"只需告知"的部分：`lgtm`/`approved` 无法自助恢复，汇报里必须提醒用户去请原评审人重评。
  2. **新诊断模式（写进 §9 典型成因 2）**：`mergeable: false` 的成因之一是 **master 已合入"同一个 PR 拆出去的另一半"**。原 #163 拆成 #183（格式）+ #163（语义），#183 合入成 `0785b08`，于是 #163 的语义行与 master 的格式行**逐行对撞**（6 文件 8 冲突块）。诊断：`git log --oneline <merge-base>..origin/master -- <冲突文件>` 看有无同主题提交。
  3. **解决口径（写进 §9）**："以已合入的代码为准" = **取 master 措辞/空格约定 + 叠加本 PR 语义**，绝不整块选 theirs。反例实例：`rmsnorm_without_weight.md` 中 PR 侧会把 master 已修好的 `# 执行RMSNorm归一化计算` 退回成 `# 执行加法操作`。
  4. **空格约定细则（写进 §9）**：`c83994e` 的真实规则是"删中文↔拉丁/数字空格，**保留中文↔行内代码（反引号）空格**"（`shape为 (B, T, H)`、`按 \`chunk_size\` 分块` 保留；`每个chunk的` 不保留）。凭此才敢改写冲突行。
  5. **新增两条验证手段（写进 §9 验证闭环 4/5）**：① **语义零丢失校验**——原 PR diff 与 rebase 后 diff **去空格后逐文件比对增/删行多重集合**（`verify_rb163.py`，实测 13 文件 +44/-40 完全一致）；② **空格回归校验**——新增行的中英文空格计数须为 0，匹配前**先抠掉行内代码 span**（`check_spaces_rb163.py`）。
  6. **新坑（写进 §6/§10）**：① `GET .../pulls/:n/comments` **默认只回 20 条**，本次 92 条评论只拿到最旧的 20 条，一度误判"机器人没反应"，**必须 `?per_page=100`**；② `docs-ci-pipeline-failed` 的原因"**未能获取文档 CI 配置**"是 openlibing 平台瞬时故障，与文档内容无关（同轮代码门禁 `PR-pipeline_MindSpeed-Ops#795` 正常 COMPLETED），别去改文档；③ `git rebase --continue` 会卡编辑器，需 `GIT_EDITOR='true'`；④ **一次自我纠错（值得记）**：曾根据"发 `compile` 后等 90 秒没动静"把 §6 的旧结论"发评论也会重新触发文档门禁"判为错误并改写；随后实测证明**原结论是对的，只是慢**——`compile` #2 之后 **2 分 40 秒**文档门禁转 `running`，随即 ✅ 通过。§6 已改成带完整时间线的版本，并写明"**判定'没触发'之前至少等 3~4 分钟**"。**教训：门禁这类异步状态，别用 90 秒的观察窗口下结论。**
  7. 实测数据点：#163 rebase 后 head `375cc69 → 1ebffb2`（相对 master 0 落后/1 领先），`mergeable: true`；**最终标签 `ascend-cla/yes` + `ci-pipeline-passed`（`PR-pipeline_MindSpeed-Ops#795`，后又重跑 `#796`，均在 `1ebffb22` 上 COMPLETED）+ `docs-ci-pipeline-success`**——即"补发 compile + 重跑文档门禁"这套动作能把强推摘掉的标签全部拿回来（`lgtm`/`approved` 除外）。产物 `_pr163split\resolve_rb163.py`、`verify_rb163.py`、`check_spaces_rb163.py`、`check_md_rb163.py`；worktree 在 `_rb163`。
- **2026-09-23 复核（PR 冲突修正 + 补门禁标签任务）**：应"#183 和 #181 有冲突，帮我修正"与"这两个 PR 没有 `ci-pipeline-passed`，帮我搞定"之需，新增 **§9 PR 冲突诊断与修正** 并把经验回灌到 §5/§6/§7/§10：
  1. **诊断方法**：`git merge-tree --write-tree [--name-only]`（git ≥2.38，不碰工作区）一次性判定"与 master 冲突"还是"两个 PR 互撞"。实测 #183/#181 **互不冲突**（文件不重叠），是各自与 master 撞上 `c83994e`（去中英文空格）和 `dc01505`（修算子清单链接）——**结论：PR 显示冲突时先别假设是 PR 之间冲突**。
  2. **解决策略**：rebase 到 `origin/master`，冲突取 master 侧 + 叠加本 PR 语义改动；脚本化解析冲突块（保留 ours + 字面替换）比手改 17 个冲突块可靠。产物：`_pr163split/resolve_conflicts.py`、`rules183.json`、`resolve_readme181.py`。
  3. **两个必踩的坑**：① `core.autocrlf=true` 下工作区 CRLF，自写脚本按 `\n` split 会误报满屏 trailing whitespace（本次 3105 条假告警），判定须用 `git diff --check`；② `git credential fill` 用 PS 管道喂 stdin 必报 `missing protocol field`，须 `cmd /c` 重定向。
  4. **token 复用**：`git credential fill`（`protocol=https`/`host=gitcode.com`）取出的 `password` 就是可用的 classic PAT，`private-token` 头直接生效（`GET /user` → `EliasKaslan`）。补入 §7，附"先校验身份再发 `compile`"的告诫。
  5. **`compile` 走 API**：`POST .../pulls/:n/comments` body `compile` → 201，创建者 token 即生效，约 60s 拿到 `ci-pipeline-passed`；无需浏览器。同时确认 **head 变化后 `ci-pipeline-passed` 会消失、必须重发**（§5/§9）。
  6. **文档门禁会被评论再次触发**（发完 `compile` 后 docs pipeline 又跑一轮，`docs-ci-pipeline-success` 短暂变 `docs-ci-pipeline-running`），判定最终状态前要等它 settle（§6）。
  7. 实测数据点：#183 rebase 后 head `5aeb227`、#181 head `45c44b3`；两个 PR 最终均为 `mergeable: true` + `ascend-cla/yes` + `docs-ci-pipeline-success` + `ci-pipeline-passed`（代码门禁流水线 `PR-pipeline_MindSpeed-Ops#794` 跑在 `5aeb2273` 上 COMPLETED，doc-only 故除 `Only_doc_commit` 外全 IGNORED）。
  8. **强推代价**：rebase 强推后 `lgtm`/`approved` 被 ascend-robot 自动摘除（原评审人 `liu_zhi_xu`/`Xin_811263`/`Ronald1995` 需重新 review）——已在 §9 明确要求"动手前先告知用户"。
- **2026-09-23 复核（issue 里程碑批量调整任务）**：应"检查 feature 标签未完成 issue 并把里程碑改到 MindSpeed 26.3.0"之需，跑通了 issue 读/写全链路，补入 §7 与 §10（当时为 §9）：
  1. **编码坑**：PS `Invoke-RestMethod` 对 GitCode UTF-8 响应按 Latin-1 解码 → 中文乱码；因 `PATCH issue` 的 `title` 必填，乱码回填会**永久写坏标题**。补显式 UTF-8 读写代码片段（§7）。
  2. 补充 `PATCH /repos/:owner/issues/:number` 用法（`repo`/`title` 必填，`milestone` 传 number）、`GET .../milestones` 的 `state` 参数坑、以及"响应不回显 milestone，需回读校验"。
  3. 补 ExecutionPolicy 拦 dot-source、`GC` 与 `Get-Content` 别名冲突两个 PowerShell 坑（§9）。
  4. 实测数据点：MindSpeed-Ops 里程碑 `MindSpeed 26.3.0` = number `849946`（due 2026-12-31）、`MindSpeed 26.2.0` = number `579831`（due 2026-10-20）；`PATCH` 接口对 **fork 拥有者（非 committer）也可写** issue 里程碑（账号 EliasKaslan 实测 24/24 成功）。
- **2026-09-22 复核（DSH skill 巡检）**：`master`/`26.1.0` 分支、`project_id=9612429`、fork、CLA 状态全部与本文一致，流程判定**仍然有效**。本次改动：
  1. §7 补"哪些接口免 token"实测结论（branches/pulls 可匿名读；仓元信息反而强制 `private-token` 头）；
  2. §7/§11 修正指向 `github-pr-flow` 的章节号（原写 §5/§9，实际都在其 §8）；
  3. 文首（"用户账号事实"下方）补 2026-09-22 复核事实与当日合入的 PR #177（可作近期样例）。
- **2026-09-24 复核（版本分支回合并：master → 26.2.0 直推 FF 任务）**：应"检查 26.2.0 是否缺 PR #163 的改动并合入"之需，跑通"判定 → 等价性证明 → FF 直推 → 回读"全链路，新增 **§12 版本分支回合并**（§13 维护记录顺延）并把经验回灌到 §6/§10，**同时更正一条旧结论**：
  1. **⚠️ 更正旧结论（写进 §6/§10）**：原文"贡献者无合并权限（合并受阻：用户无当前保护分支的合并权限）"**只对 master（protected=true）成立**。实测 `GET .../branches/{master,26.1.0,26.2.0}` → master protected=true/can_push=false，26.1.0、26.2.0 protected=false/can_push=true；`GET .../collaborators?per_page=200` → EliasKaslan `access_level=40`/Maintainer/permission=admin。**即用户对上游仓有 Maintainer 权限，未保护的版本分支可直推**（master 部分原样保留）。
  2. **新章节（§12）三步判定"缺不缺这一笔"**：① 显式 fetch 版本分支（本克隆 refspec 只含 master，首轮报 `fatal: ambiguous argument 'origin/26.2.0'`）；② `git merge-base` + 双向 `git rev-list --count` 判分叉（实测 26.2.0 tip `46f76f6` 自身提交 0 个、正是 `1d1239b` 的父提交 → 严格祖先）；③ `git diff --stat origin/26.2.0 origin/master` 正好是 #163 的 13 个 md 文件、`+113/-92`（PR 自身语义子集为 13 文件 `+44/-40`），与 `GET /pulls/163/files` 文件清单一致。
  3. **等价性证明（§12.3，最有力一步）**：`git merge-tree --write-tree origin/26.2.0 da51074` exit 0，第 1 行 tree OID 与 `git rev-parse '1d1239b^{tree}'` **完全相同**（`9a434b8da6fca82275518ec30c3bf8dcc206024f`）→ 合并结果与 master 逐字节一致，不带额外提交。
  4. **合入与验收（§12.4）**：`git push origin refs/remotes/origin/master:refs/heads/26.2.0` → `46f76f6..1d1239b  origin/master -> 26.2.0`、`remote: Start Git Hooks Checking [PASSED]`、exit 0；FF 无需 `--force` 也天然安全（分支被推进会直接 non-fast-forward 失败）。回读：API `branches/26.2.0` → `commit.id=1d1239b4...`、本地 `rev-parse` 两侧 tree 相同、`rev-list --count origin/26.2.0..origin/master` = 0。**直推 FF 后没有待合入 PR，不需要发 `compile`**。
  5. **项目惯例（§12 开头）**：`26.1.0` 上 4 个不在 master 的提交全部是维护者 `liu_zhi_xu` 网页直推的 `update: 更新文件 ...`，**不是 PR 合入**；同时存在面向版本分支的 PR（#162 base=26.1.0，贡献者侧）→ **维护者对未保护版本分支直推是既有做法**。
  6. **未验证的观察（§12 末）**：`26.1.0` 与 master 在那 13 文件上"13 of 13 differ"，但它是已分叉的旧分支（另有 4 个自有提交），**要不要给它也回合 #163 尚未核实**，不能照搬 26.2.0 的结论。
  7. **清理纪律（写进 §12/§10）**：本次为图省事把 PAT 写进过 `$env:TEMP\gctok.txt`（随后已删）——**别写临时文件**；token 只能 `git credential fill` 取、只留内存、绝不落盘。
- **2026-09-25 复核（pre-commit 概率性失败判读 + 无登录读 openlibing 任务状态）**：应"pre-commit 概率性失败、同一 commit 重跑可能变绿"与"无登录读取流水线任务级状态"之需，新增 **§6.1**（并入 §6 双门禁判读）并把经验回灌到 description/§10：
  1. **现象与结论口径（§6.1）**：PR #187（commit `fb141cb2`，只改 `setup.py` 7 行）首轮 `PR-pipeline_MindSpeed-Ops#818` 的 `pre-commit` **FAILED**（`{"errorMessage":" 构建任务执行失败!","errorCode":"DEV-CODECI-35002"}`，5m11s，UTC 02:46:56→02:52:07）；同 commit `retry` 后**同一 pipelineRunId** `13ffcdc93320436a99969e8b0a310b1a` 内变 **COMPLETED**（1m51s，UTC 02:57:53→02:59:44）。更强对照：PR #110（他人）同一 commit `41b421d8` 六跑 = `22c55f9c`/`e73f2d8f`/`c9c1867a`/`a7a4aa41` COMPLETED、`72e39b8f`/`ebc16c5c` FAILED → **与代码内容无关**。判定：改代码之前先取"同 commit 多次运行"或直接 `retry`；`pre-commit` 为失败项且本地逐 hook 复现干净 → 判平台概率性失败，**只 retry，不改源码**（反例：`UT_MindSpeed_*` 失败通常是真问题）。
  2. **排除代码原因的可复用步骤（§6.1）**：独立 venv `pip install pre-commit` → `SKIP=gitleaks-offline-scan pre-commit run --files <改动文件> --show-diff-on-failure` → `setup.py` **13 个 hook 全 Passed**（pylint v4.0.5 / bandit 1.9.4 / typos v1.32.0 / ruff v0.14.14），再用**未改动**的 python 文件做对照逐 hook 结果一致。`gitleaks-offline-scan` 本地必失败（仓内**没有**提交二进制，CI 先 `wget .../pta-codecheck/gitleaks` 再 `chmod +x`），故须 `SKIP`；该二进制 `gitleaks 8.30.1`（sha256 `88f91962aa2f93ac6ab281d553b9e125f5197bbbce38f9f2437f7299c32e5509`）在 CI 场景是**空门禁**（`protect` 忽略传入文件名、只对工作区未提交改动 `git diff -U0`，干净 checkout 恒过）。
  3. **无登录读任务级状态（§6.1，实测可用）**：Playwright 打开任意 openlibing 页面后，在页面上下文 `fetch` `https://www.openlibing.com/gateway/openlibing-cicd/project/pipeline/pipeline-run/detail?projectId=300091&pipelineId=<pid>&pipelineRunId=<rid>` → `data` 里递归找同时含 `name|jobName` 与 `status|state` 的对象即得每任务名与状态（`pre-commit`/`SCA`/`Antipoison`/`Only_doc_commit`/`UT_MindSpeed_1..4`）及失败任务 `message`。**页面渲染为空是 `get-user-permission` 等接口 401，该 detail 接口 200 免登录**；`pipelineId` 固定 `dc050eb8a847445c8fe635fb50d1f99d`，`pipelineRunId` 由评论 `pipelineRunId=([0-9a-f]{32})` 抓取。
  4. **两个反直觉的坑（§6.1）**：① `retry` **不产生新 pipelineRunId**（同一 run 内重跑失败任务）→ 判断"重试是否生效"必须看**任务状态变化**；且**早发的 `retry` 会被忽略**（必须在上一轮流水线已结束后发；实测 10:51:40 发的被忽略、10:57:49 发的生效）。② step 日志类接口（`/pipeline-run/step/log`、`/log`、`/job/log`）一律 **401**，不要再试。
  5. **源码级事实（§6.1）**：`pre-commit` 任务在 `.gitcode/workflows/pr-pipeline-mindspeed-ops.yml:69-95`；action `openlibing/pre-commit-action@v1.0.0` 的 `index.js`：PR 事件且 `ATOMGIT_BASE_REF` 非空 → `--from-ref FETCH_HEAD --to-ref HEAD`（增量），否则 `--all-files`；失败分 `failureType=install` / `failureType=check`，**两者都 exit 1**，**PR 场景都不产出 SARIF、都不发 PR 评论** → **"PR 上没有失败评论"不能推断失败类型**。

## 2026-09-29 泛化改名：gitcode-mindspeed-ops-pr → gitcode-pr-flow

- **动机（有量化依据）**：原 skill 名义上只服务 MindSpeed-Ops，但逐节归属统计显示正文 **64.3% 是 GitCode 平台通用**
  （G 337 行 / O 143 行 / 其他仓 0 行）。拆成 ops+agent 两份会把 337 行通用正文**抄两遍**（重复正文 337 行），
  改名泛化则**重复 0 行**、下沉 143 行 ⇒ 选**改名 + 仓专属下沉 `references/`**。
- **做法**：`name` → `gitcode-pr-flow`；§8（算子 PR 附加交付件）与 §12（版本分支 backport）下沉
  `references/mindspeed-ops.md`；§13 维护记录外移 `references/maintenance-log.md`；
  新增 `references/mindspeed-agent.md`（Agent 侧实测事实）；正文新增「仓参数化」双仓对照表。
  交叉引用同步改名 4 个 skill：`aidd-report-reader`、`arxiv-paper-deep-read-and-claim-verification`、
  `dingxiang-slider-captcha`、`github-pr-flow`（3 处）。
- **顺带修 4 处缺陷**：① **MD051 自相矛盾**——§9 原说仓内 `.markdownlint.yaml` 已关 MD051 ⇒ 锚点"不是风险点"，
  而 §6/§10 把 MD051 当高频失败项 → 和解为「文档门禁跑在平台侧、用平台托管配置，**仓内配置不是判据**」；
  ② §2 指向 `github-pr-flow` 的 **§3** 是错的，讲 PowerShell 三坑的是其 **§2**；
  ③ §6.4 用 `upstream/master` 而 §9 用 `origin/master` → 统一为 `origin/master`，并补「git ≥ 2.38」前提；
  ④ **把未取证的常量降级标注**——原先对照表把 GitCode 仓 id 与 openlibing `projectId` 混成一行，
  且 Agent 侧的 `300091`/`02086441…` 实际**没有被成功取证**（`probe_openlibing.py` 那次探测因需登录而失败），
  现拆成三行并逐格标注「实测 / 未独立证实 / 未复核」。
- **两条被实测否证的外部结论（留作反面教材）**：
  1. 有分析报 `docs/zh/ops.md` 是"死路径"、建议删。对远端核 →
     `https://raw.gitcode.com/Ascend/MindSpeed-Ops/raw/master/docs/zh/ops.md` **HTTP 200**
     （`docs/zh/supported_operators.md` 同样 200）⇒ **该路径真实存在，未做修改**。
     教训：**判仓内路径真伪只能问远端或真克隆**；本地 `D:\workspace\MindSpeed-Ops` **根本不是 git 仓库**
     （是装着 `_pr163split`/`_upstream` 等子目录的容器目录），拿它当依据会得出完全错误的结论。
  2. 校验器自身的判据也可能过严——"全树不得出现旧名"会误伤刚追加的**历史变更条目**，
     现改为「旧名只允许出现在 `maintenance-log.md`」。
- **验证**：18 项校验全绿——§1–§7 与 §9–§11 原文块在新 SKILL.md 中**逐字节保留**（仅已登记的修正除外），
  §8/§12/§13 在 references 内**逐字命中**；frontmatter YAML 可解析、`name` == 目录名、
  `description` 461 字符且物理单行；除历史条目外全树无旧名残留。
  回滚：原文件完整备份于 `_verify\backup\gitcode-mindspeed-ops-pr\SKILL.md`（SHA256 `6292F4B5…`），
  把目录名与 `name` 改回即可。
