---
name: github-pr-flow
description: GitHub 上游仓提 PR：PAT/DCO/建 PR/CI 判读、AI 评审意见处理与回帖、blocked 逐条判定、force-with-lease 强推
whenToUse: 要在 GitHub 上游仓库（尤其 vllm-project/vllm-ascend）提交 / 关闭 / 重开 PR、往 fork 推分支、判断 token 权限，或做 DCO 签名提交时使用。
---

# GitHub 上游仓库 PR 提交流程（classic PAT 全 API 版）

2026-09-14 全链路实测通过（vllm-ascend PR #16474 创建→CI→关闭；#16479 验证 API 建/关）。**2026-09-22 复核**：#16474、#16479 在 API 里都仍在（均为 `state=closed`、`user=EliasKaslan`，标题 `[Doc][Misc] Fix grammar error in AGENTS.md`），token 与 fork 均有效。

## 何时调用

**加载本 skill 当：**
- 用户要给 **GitHub** 上游仓（如 `vllm-project/vllm-ascend`）提 PR / 关闭 / 重开 PR，或要往个人 fork 推分支。
- 要判断手头 token 能不能用（`ghp_` 还是 `github_pat_`、403 `Resource not accessible by personal access token`、`GET /user` 401）。
- PR 建好后 CI 挂了，要分清是「自己的问题」（DCO / pre-commit / 标题前缀）还是「上游基础设施故障」。

**不要用本 skill（转交）：**
- 目标是 **GitCode** 上的任意仓（Ascend/MindSpeed-Ops、Ascend/MindSpeed-Agent 等）→ 用 `gitcode-pr-flow`。
- 要登录 aidd.huawei.blue 抓或导出扫描报告 → 用 `aidd-report-reader`。
- 想自动化过滑块验证码 → 用 `dingxiang-slider-captcha`。
- 要解决的是**本机 PowerShell 命令本身**的坑（编码 / 计数 / PS7 语法 / 引号）→ 用 `pwsh-on-windows`。
- 要精读 arXiv 论文并核查其开源声称 → 用 `arxiv-paper-deep-read-and-claim-verification`。
- 要外部热度量级证据（HN points / HF likes） → 用 `external-buzz-magnitude-check`。
- 只做组织提交活性增量（基准日之后谁在动） → 用 `github-org-delta-watch`。
- 新增 / 移动 e2e 用例要进 CI 并登记 estimated_times → 用 `vllm-ascend-e2e-ci-wiring`。

**前置**：拿到用户给的 classic PAT，按 §0 的凭据策略缓存（**不得放在 skill 目录内**）。 ／ **后继**：push 到 fork → API 建 PR → 判读 CI（§6）。

## 0. 凭据

- **凭据策略（2026-09-29 用户确认；本 skill 是这条策略的单一出处，其它 skill 只指向这里）**：classic PAT（`ghp_` 开头）**允许在本机缓存，但必须在 skill 目录之外**——现位置 **`~\.dsh\.secrets\github-pr-flow.token`**。**绝不放回任何 skill 目录**（skill 目录会被同步、打包、审计），也不写进仓内文件、日志或命令历史。两层 `.gitignore` 已就位：`~\.dsh\.gitignore` 里的 `.secrets/`，以及 `.secrets\.gitignore` 的自忽略（`*` + `!.gitignore`，该目录被整体复制走也不会误提交）。
- 该 PAT 能完成全部操作：push 到 fork、在上游**创建/关闭/重开 PR**，全程 API，无需浏览器。
- **2026-09-22 复核：token 仍然有效**——`GET /user` 返回 200，`login=EliasKaslan`，长度 40 且 `ghp_` 前缀；scopes 含 `repo`、`workflow`、`gist`、`user`、`read:org` 等，建/关 PR 与 push fork 都够用。
- **fine-grained PAT（`github_pat_` 开头）无法对上游仓库建/关 PR**（一律 403 `Resource not accessible by personal access token`，REST/GraphQL/MCP 全一样）。用户给这种就请换 classic（勾 `public_repo` 即可，勿用全权限 token）。
- 快速探测：`GET /user` 401=token 失效；POST 空 `{}` 到 `/repos/<owner>/<repo>/pulls`，403=无权限、422=有权限。**它零副作用的唯一原因是空 body 过不了校验（422）**——绝不能用真实 payload 去探测，那会留下真实 PR（§4）。
- token 泄漏或过期：请用户重新生成，覆盖 `~\.dsh\.secrets\github-pr-flow.token`。

## 1. 账号事实与侦察

- 用户：GitHub `EliasKaslan`，提交邮箱 `3248569436@qq.com`；fork：`EliasKaslan/vllm-ascend_k3`。**fork 名与上游不同名不影响 API**——head 参数写 `EliasKaslan:<branch>` 会自动解析到该 network 中用户的 fork。（2026-09-22 复核：fork 仍在，`default_branch=main`，最近 push 2026-09-17；`id=78793871`。）
- 验 token 与 scopes：
  ```powershell
  $t = (Get-Content "$env:USERPROFILE\.dsh\.secrets\github-pr-flow.token" -Raw -Encoding utf8).Trim()   # 位置与策略见 §0；token 是纯 ASCII，此处只为与全机读写规则一致
  curl.exe -s -D - -o NUL -H "Authorization: Bearer $t" https://api.github.com/user | Select-String 'x-oauth-scopes|^HTTP'
  ```
- **规范调研（必做，决定 commit/PR 格式）**：读上游 `CONTRIBUTING.md`、`AGENTS.md`、`.github/PULL_REQUEST_TEMPLATE.md`，确认：DCO（要 `Signed-off-by:`）、commit 消息格式、PR 标题前缀、PR 模板段落、lint 要求。

## 2. 克隆与 DCO 提交（PowerShell 三坑）

```powershell
git clone --depth 1 https://github.com/<owner>/<repo>.git
cd <repo>
git config user.name 'EliasKaslan'
git config user.email '3248569436@qq.com'
git config commit.gpgsign false
git checkout -b <branch>
```
**`--depth 1` 的代价**：浅克隆只够「改一行、提 PR」；一旦要判断分支落后/领先多少，浅克隆给出的 ahead/behind **完全错误**（姊妹 skill `gitcode-pr-flow` 已实测）。需要比较历史时先 `git fetch --unshallow`。

**坑 1（引号）**：`git commit -m "内嵌""引号"""` 会被 PowerShell 打散成 pathspec，**提交静默失败**（PowerShell 引号规则见 `pwsh-on-windows`）。**解法：消息写文件再 `-F`**：
```powershell
$msg = "docs: <summary>`n`n<body 措辞避开引号>"
$f = Join-Path $env:TEMP 'commitmsg.txt'
[IO.File]::WriteAllText($f, $msg, (New-Object System.Text.UTF8Encoding $false))   # 关键：无 BOM
git commit -s -F $f                # -s 自动加 DCO Signed-off-by
```
**坑 2（BOM）——两个反直觉点，均已逐字节实测**：
- **管道喂 stdin 也会写进 BOM**：`$msg | git commit -s -F -` 看似干净，实测 PS 向原生子进程 stdin 注入的字节恰为 `ef bb bf 41 42 43 0d 0a`（BOM + `ABC` + CRLF，用 `git hash-object --stdin` 反推得到）；提交标题原始字节首 3 字节变成 `239 187 191`，标题成了 `'\ufeffdocs: …'`。`Set-Content -Encoding utf8` 同样写 BOM（通用机制见 `pwsh-on-windows`）。
- **自检方法本身会骗你**：PS 读原生程序 stdout 时会**吞掉 BOM**，所以 `(git log -1 --format=%s)[0]` 对**已损坏**的提交照样报 `100`——实测就是「PS 视角 100 / 原始字节 `239 187 191`」。必须按原始字节查：
```powershell
cmd /c "git log -1 --format=%s > %TEMP%\subj.txt"      # 用 cmd 落字节（PS 的 `>` 会写成 UTF-16）
[IO.File]::ReadAllBytes("$env:TEMP\subj.txt")[0..2]    # 期望 100 111 99（'doc'）；239 187 191 即 BOM
```
上面的「写文件 + `-F`」已实测通过：无 BOM、首字节 `100 111 99`、LF 换行、中文完整、DCO 签名正常。
**坑 3（换行符）**：Windows `autocrlf=true` 下改完必须 `git diff --stat` 确认只有目标行（如 1 file/1 insertion/1 deletion），整文件变更=换行符被动了。

## 3. 推送 fork（一次性 URL，token 不落盘）

```powershell
git push "https://x-access-token:$t@github.com/<user>/<fork>.git" <branch>
# stderr 里 git 进度输出被 PowerShell 标红是正常现象
```

## 4. API 创建 PR（实测 201）

```powershell
$h = @{Authorization="Bearer $t"; Accept='application/vnd.github+json'}
$payload = @{
  title = '[Doc][Misc] <标题>'
  head  = 'EliasKaslan:<branch>'        # 不同名 fork 也自动解析
  base  = 'main'
  body  = "<PR 模板正文，`n 换行>"
} | ConvertTo-Json
# ⚠️ 标题/正文含中文时**必须**传 UTF-8 字节：`-Body` 传字符串会按 ASCII 编码发出，
#    中文在网线上变成 `??`，**本地不报错**（逐字实测 hex `7B2261223A223F3F…`；通用规则见 `pwsh-on-windows`）
$pr = Invoke-RestMethod -Method Post -Uri 'https://api.github.com/repos/<owner>/<repo>/pulls' -Headers $h `
  -Body ([Text.Encoding]::UTF8.GetBytes($payload)) -ContentType 'application/json; charset=utf-8'
$pr.number; $pr.html_url

# 写操作后**必须回读校验**——这是唯一能发现中文被写成 `??` 的方法：
$chk = Invoke-RestMethod "https://api.github.com/repos/<owner>/<repo>/pulls/$($pr.number)" -Headers $h
'回读标题 = ' + $chk.title      # 与预期标题逐字比对，出现 ?? 即已被写坏
```
注意：同 head:base 已有**关闭状态**的 PR 时不报错、会新建一个 PR——不要用创建来做"探测"，会留下真实 PR。

## 5. API 关闭 / 重开

```powershell
Invoke-RestMethod -Method Patch -Uri 'https://api.github.com/repos/<owner>/<repo>/pulls/<n>' -Headers $h -Body '{"state":"closed"}' -ContentType 'application/json; charset=utf-8'   # 纯 ASCII body，无编码风险；closed 换 open 即重开
```
**改标题 / 描述也走同一个 PATCH**（PR 建好后补描述、或标题前缀被 CI 拦下要改）——正文含中文时**必须**走 UTF-8 字节，规则与回读校验同 §4：
```powershell
$p = @{ title = '[Doc][Misc] <新标题>'; body = "<新正文，`n 换行>" } | ConvertTo-Json
Invoke-RestMethod -Method Patch -Uri 'https://api.github.com/repos/<owner>/<repo>/pulls/<n>' -Headers $h `
  -Body ([Text.Encoding]::UTF8.GetBytes($p)) -ContentType 'application/json; charset=utf-8'
```

## 6. CI 判读：自己的问题 vs 基础设施故障

```powershell
# ① 按 head sha 列出该提交触发的 runs —— 这就是 <run_id> 的来源
#    （匿名实测 200：total_count=12，回 workflow_runs[].id / .name / .status）
Invoke-RestMethod "https://api.github.com/repos/<owner>/<repo>/actions/runs?head_sha=<sha>&per_page=20" -Headers @{Accept='application/vnd.github+json'}
# ② 逐项检查结论（匿名实测 200；GitHub 响应头带 charset=utf-8，故读侧不会乱码，写侧才要防）
Invoke-RestMethod "https://api.github.com/repos/<owner>/<repo>/commits/<sha>/check-runs" -Headers @{Accept='application/vnd.github+json'}
# ③ 用 ① 里的 workflow_runs[].id 作为 <run_id> 定位失败 step
Invoke-RestMethod "https://api.github.com/repos/<owner>/<repo>/actions/runs/<run_id>/jobs?per_page=100"
```

- **DCO / pre-commit 挂** = 自己的问题（签名缺失/邮箱不匹配/格式/拼写/PR 标题前缀）。
- **测试 job 挂在 Install/Setup 环境步骤** = 疑似基础设施故障；验证：拉同 workflow 最近 runs（`/actions/workflows/<id>/runs?per_page=15`），同时段别人的 PR 挂**同一个 step** 即坐实，与本次改动无关。
- `mergeable: true` + `mergeable_state: unstable` 通常只是 CI 未全绿。

## 7. vllm-ascend 规范速查

- PR 标题前缀：`[Doc]` `[BugFix]` `[CI]` `[Test]` `[Kernel]` `[Misc]`…（可组合 `[Doc][Misc]`）
- commit：Conventional Commits（`docs:`/`fix:`/`feat:`…）+ **必须** `git commit -s`（DCO）
- PR 正文三段式：`What this PR does / why we need it?` / `Does this PR introduce _any_ user-facing change?` / `How was this patch tested?`（doc-only 可写 "CI verification only"；bot 会自动追加 `- vLLM main:` 版本行，勿删）
- pre-commit 含 typos、markdownlint、PR 标题校验；找文档改动点优先扫语法错误（"will triggers" 类），typos CI 已把拼写错误防干净
- 必须从 fork 发 PR；fork 作者无 CI 重跑权限，需空提交重触发或请维护者重跑

## 8. 备注

浏览器兜底方案（Playwright 登录 + compare 页填表）仅在用户只提供 fine-grained PAT 时才需要，已从主流程移除；如需恢复参考 git 历史或重走：`https://github.com/<owner>/<repo>/compare/main...<user>:<fork>:<branch>?expand=1`。

## 9. 维护记录

- **2026-09-22 复核（DSH skill 巡检）**：`token.txt`（当时还在 skill 目录下，见下方 2026-09-29 迁移）内 classic PAT 有效（`GET /user` 200 / `EliasKaslan` / scopes 含 `repo`）；fork `EliasKaslan/vllm-ascend_k3` 存在；引言引用的 #16474/#16479 仍可查到。判定 skill **仍然有效**，本次仅补注复核时间与实测值，未改动流程。
- 被其他 skill 引用时注意章节号：`gitcode-pr-flow` 的"浏览器兜底"指向本文件 **§8**，GitCode 登录页的 DevUI 复选框解法指向 `aidd-report-reader` **§1**。
- **2026-09-29 完善**：① 修掉 §4 创建 PR 用 `-Body $payload`（字符串）——中文标题/正文会被按 ASCII 发出、在网线上变成 `??` 且**本地不报错**，改为 `UTF8.GetBytes` + `charset=utf-8`，并补**回读校验**；② §6 补 `actions/runs?head_sha=`（匿名实测 200、`total_count=12`）以说明悬空的 `<run_id>` 从哪来；③ §0 与 §4 关于"能否用创建做探测"的张力改为显式交叉引用（零副作用只因空 body 得 422）；④ description 的 GitCode 交叉引用由"仅 MindSpeed-Ops"扩为"任意仓（含 MindSpeed-Agent）"，并补 DCO / 标题前缀 / 引号提交等触发词；⑤ §2 的通用 PowerShell 说明改为指向 `pwsh-on-windows`（单一归属）。
- **2026-09-29 完善（第二轮）**：⑥ 修掉 §2 的 P0——`$msg | git commit -F -` **也会写进 BOM**（实测 stdin 注入字节 `ef bb bf 41 42 43 0d 0a`），且原自检 `(git log -1 --format=%s)[0]` **对已损坏的提交恒报 100（假 OK）**，故删去该自检、改为按原始字节查；解法换成 `[IO.File]::WriteAllText(..., UTF8Encoding $false)` + `git commit -F 文件`（实测通过）；⑦ §5 补「改 PR 标题/描述」的 PATCH（含中文必须走 UTF-8 字节）；⑧ §2 补 `--depth 1` 的 ahead/behind 代价；⑨ 勘误：那组 PR 号在引言而非 §0。
- **2026-09-29 凭据迁移（用户决策：允许缓存 / 移出 skill 目录 / 加 .gitignore）**：`skills\github-pr-flow\token.txt` → **`~\.dsh\.secrets\github-pr-flow.token`**。SHA256 搬运前后一致（41 B 未变），旧路径已删除；新建 `~\.dsh\.gitignore`（`.secrets/`）与 `.secrets\.gitignore`（`*` + `!.gitignore` 自忽略）。§0 已改为凭据策略的单一出处，`gitcode-pr-flow` / `dsh-skill-authoring` / `dsh-skill-self-audit` 改为指向此处。

## PR 卡在 Merging is blocked 或合入冲突时怎么定位与解决

## 何时调用（本节触发）

PR 页面显示 "Merging is blocked"、`mergeable_state` 为 `DIRTY`/`CONFLICTING`、或 rebase 后工作树冒出成片 `AA` 文件时读本节。

## 一、先把 blocked 的成分逐条取出来，再动手

不要凭"哪个 job 红了"猜。权威取数两处：

- GraphQL：`mergeable`、`mergeStateStatus`、`reviewDecision`、`commits(last:1).statusCheckRollup.state`、`reviewThreads(first:60){isResolved}`。
- **Rulesets**（新版仓库用 Rulesets，`GET /repos/<o>/<r>/branches/main/protection` 可能返回空数组，别据此判断"没有保护"）：
  `GET /repos/<o>/<r>/rulesets` → `GET /repos/<o>/<r>/rulesets/<id>`，读
  `required_status_checks`（`required_status_checks[].context`，如 `DCO`、`ci-gate`）与
  `pull_request`（`required_approving_review_count`、`required_review_thread_resolution`、`dismiss_stale_reviews_on_push`）。

实测踩过的误判：同一 head 上 `ci-gate` 可能已有**两条** check-run（旧 failure + 新 success，维护者加标签后重跑），`statusCheckRollup=SUCCESS` 就已满足必需检查；此时真正缺的是 approval。**先枚举规则，再动手。**

## 二、冲突：不要在"多次 `--depth` fetch 拼出来的浅克隆"里 rebase

症状（逐字）：`git status` 刷出成片的 `AA` / `A ` 文件（上千行），rebase 把整棵树当新增文件。

原因：仓是浅克隆、历史由多次不同 `--depth` 的 fetch 拼成，git 取不到 merge base。

修法（实测 5 秒级）：

1. `git rebase --abort` 复原；
2. `git clone --depth 1 --branch main <upstream-url> <新目录>`（只取目标树，无浅历史畸形）；
3. 在新克隆里**按目标文件当前结构重建改动**——评审往返多（七八个提交）时直接压成 1–2 个干净提交，比逐个 `git am` 重放省事且避开冲突密集区；
4. 用显式 lease 强推（见 §3），并在 PR 里说明"旧 head 的 9 个提交已压成 2 个、净 diff 不变"。

重建后必查：`git diff --stat origin/main..HEAD` 的净增删要**与冲突前一致**，否则说明漂移。

## 三、强推：`--force-with-lease` 需要本地有远端引用

没 fetch 过 fork 分支时，`git push --force-with-lease <url> HEAD:<branch>` 会：

```
 ! [rejected]  HEAD -> <branch> (stale info)
```

修法：把期望值写进参数——

```
git push --force-with-lease=refs/heads/<branch>:<远端当前 sha> <url> HEAD:refs/heads/<branch>
```

远端当前 sha 从 `GET /repos/<owner>/<repo>/pulls/<n>` 的 `head.sha` 取。

## 四、fork 作者的权限边界（提前说清，别反复试）

- **不能自 approve**（GitHub 禁止作者批准自己的 PR）。
- `POST /pulls/<n>/requested_reviewers` 对无写权限账号返回 **404**（不是 403）——"请求评审"这个动作本身就要写权限。
- **可以**关闭 review 会话：GraphQL `mutation resolveReviewThread(input:{threadId:$id}) { thread { isResolved } }`（fork 作者身份实测成功），先把已处理的线程全部 resolve 掉。
- 仓库若开 `dismiss_stale_reviews_on_push`：**任何推送都会作废已有 approval**，包括用 "Update branch" 按钮解冲突（它也是往分支写 submit）。所以解冲突前先看 `reviewDecision` 是不是 `APPROVED`，若是，在 PR 里提前说明"approval 会被作废、请重批"，别让审批人莫名其妙。

## 五、收尾

推完重新取一次 §1 的两处数据，确认 `mergeable` 变 `MERGEABLE`、阻塞只剩 approval 这一类；然后发一条 PR 评论写清：冲突根因（哪个上游 PR 挪了哪段代码）、重建方式、净 diff 是否不变、以及"请谁对哪个新 sha 重新 approve"。

## push 卡住不动：先 ls-remote 复核远端，再隔离 credential helper

## `git push` 卡住不返回 ≠ 没推上去：先 ls-remote，再隔离 credential helper

### 现象

`git push` 与 `git push --dry-run` 都能几十分钟不返回、进程零 CPU；同一时刻 `git ls-remote` 秒回；杀掉重试仍然挂。而**远端 `main` 其实已经更新了**。

### 三步定位（每步都很快，能把责任分到网络 / git / 凭据）

1. **远端到底有没有**——这一步才是成败判据，不是命令有没有返回：
   - `git ls-remote <remote> main`
   - `git ls-remote --tags <remote> 'refs/tags/<tag>*'`（tag 要比 `^{}` 那一行才是它指向的提交）
2. **网络与端点**：绕开 git 和凭据助手，直接打 git 的 HTTP 入口：
   - `https://<host>/<owner>/<repo>.git/info/refs?service=git-upload-pack` → 期望 200
   - 同上 `service=git-receive-pack` → 未带凭据时 401 属正常
   两个都秒回 ⇒ 网络与服务器都没问题，问题在本地。
3. **凭据助手**：
   - `git -c credential.helper= push --dry-run <remote> <branch>` —— 若 1 秒内报
     `fatal: could not read Username for 'https://github.com': terminal prompts disabled`，
     说明阻塞点就在 helper（本机是 `wincred`）。
   - 再单独验一次 helper：`"protocol=https`nhost=github.com`n`n" | git credential fill`（加 25 秒超时）
     也会挂 ⇒ 是 helper 本身阻塞，不是 git 也不是网络。

### 结论与处置

- 挂住的位置是**上传完成后的凭据收尾**（`store` / `erase`）：远端已经拿到数据，本地进程却不退出。**不要因为"命令挂了"就反复重推**，先去看远端。
- 缺的可能是**局部**：本次 `main` 到了、tag 没到；单独 `git push <remote> <tag>` 再 verify 就补齐了。
- 想彻底不挂：换 helper（`git config credential.helper manager`），或走 PAT + `GIT_ASKPASS`。**不要把令牌写进 `.git/config`，也不要放进命令行参数**（argv 会进日志与进程列表）。
- 同一台机器上另一个远端（如 GitCode）可能完全正常：helper 是按 host 存条目的，一个坏了不代表网络坏，别据此下"网络不通"的结论。

## 处理 AI 代码评审意见（bot 评审）

## 处理 AI 代码评审意见（bot 评审）

### 先一次把意见收全：三处投放，只查一处会漏

| 端点 | 内容 |
|---|---|
| `GET /repos/{o}/{r}/pulls/{n}/reviews` | 总评。常含"建议的 PR 标题 / 摘要"这类非阻塞项 |
| `GET /repos/{o}/{r}/pulls/{n}/comments` | 逐行 inline 意见。**真正的代码问题通常在这里** |
| `GET /repos/{o}/{r}/issues/{n}/comments` | bot 的变更摘要、社区欢迎语（噪声多） |

同一个 bot 会同时往三处发，**不要用某一个端点的条数判断"只有一条意见"**。

### 判定：是回归，还是既有问题

改之前先把**改动前的代码在同样输入下的行为**读出来。若旧代码走的是同一分支（例：旧守卫 `shape[0] < 65536` 对 0 也成立，同样会把空张量送进算子），这条意见就是**防御性改进**，不是本次引入的回归。

回复里必须写明这一点，否则会被读成"作者引入了 bug"。反过来，如果旧代码确实不会走到，那就是真回归，别说成防御。

### 改法与补测

- 接受意见后，要补**"删掉守卫就红"**的测试：把被保护的调用替换成"一调用就抛异常"的桩，再断言返回的形状 / dtype。只补正向用例挡不住回归。
- 空张量边界直接返回：`x.new_empty(0, x.shape[1], w.shape[-1])`，保持 dtype 与 device，不要手搓 `torch.empty`。
- **非阻塞项（标题 / 摘要措辞）先查仓库现状再决定**：`GET /repos/{o}/{r}/pulls?state=closed&per_page=12` 看最近合入的标题风格。标题已经过了 CI 的标题校验时，纯顺序调整不值得冒险（两种前缀顺序往往都在用）。
- bot 的"建议 PR 摘要"不要照抄：它会把 "A review comment points out ..." 这类自述写进正文，贴进去很怪；只把实质信息并进现有描述。

### 回帖：走线程回复，不要另起评论

```
POST /repos/{o}/{r}/pulls/{n}/comments/{comment_id}/replies
body: {"body": "..."}          # 含中文必须 UTF-8 字节发送
```

201 会返回新评论 id 与 `html_url`。**必须回读校验**：`GET /pulls/{n}/comments`，确认新评论的 `in_reply_to_id` 等于被回复那条的 id，才算挂对了线程。

### 收尾

1. 更新 PR 描述（`PATCH /pulls/{n}`，UTF-8 字节）：把新增的守卫与测试写进 "What this PR does" 与 "How was this patch tested"，测试条数要与实际一致。
2. 用**新 head sha** 重查 `commits/{sha}/check-runs`，确认 pre-commit / DCO 仍绿（改完代码后旧结论作废）。
3. 本地跑不了真测试时（例如无 torch），用桩件把被改函数跑一遍：切片尺寸、行序、边界早返回。**只做 `py_compile` 不算验证**。
