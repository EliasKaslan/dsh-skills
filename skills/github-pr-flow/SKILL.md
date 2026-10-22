---
name: github-pr-flow
description: 向 GitHub 上游开源仓（如 vllm-project/vllm-ascend）从 fork 提 PR 的全 API 流程（classic PAT）——token 验证与 403/401 判因、DCO 签名提交、REST API 创建/关闭/重开 PR 与回读校验、CI 判读、反向抓既存 PR 做离线终审、rebase/amend 后判上游基线漂移与安全重推。适用于"在 GitHub 仓提个 PR / 关掉或重开 PR / 到 fork 推分支 / token 报 403 说没权限 / DCO 签名校验不过 / commit message 带引号导致提交静默失败 / PR 标题前缀或模板不合规 / CI 挂的 step 是不是我的问题 / 不知道 run_id 怎么拿 / 上游 main 又前进了 / rebase 后重推被拒"。不适用：目标是 GitCode 上的任意仓 → 用 `gitcode-pr-flow`；本机 PowerShell 命令本身的坑 → 用 `pwsh-on-windows`。
whenToUse: 要在 GitHub 上游仓库（尤其 vllm-project/vllm-ascend）提交 / 关闭 / 重开 PR、往 fork 推分支、判断 token 权限，或做 DCO 签名提交时使用。模型看不到本节。
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

**前置**：拿到用户给的 classic PAT，按 §0 的凭据策略缓存（**skill 目录内、`~\.dsh\.secrets\` 两处都合法**）。 ／ **后继**：push 到 fork → API 建 PR → 判读 CI（§6）。

## 0. 凭据

- **凭据策略（2026-10-08 用户反转 2026-09-29 旧规；本 skill 是这条策略的单一出处，其它 skill 只指向这里）**：**允许把凭据文件放在 skill 目录内，而且鼓励每个 skill 直接写明自己用到的凭据文件位置**（如 `ascend-env\credentials.txt`）——2026-09-29 那条"必须放 skill 目录之外 / 绝不放回任何 skill 目录"**已作废**，遇到旧文字按本行纠正。classic PAT（`ghp_` 开头）现位置仍在 **`~\.dsh\.secrets\github-pr-flow.token`**（留着即可，两处都合法）。**仍然禁止**：写进仓内文件、日志、命令历史，或写进 `description`（description 会被会话目录展示）。`.gitignore` 两层保持就位：`~\.dsh\.gitignore` 的 `.secrets/`、`.secrets\.gitignore` 自忽略（`*` + `!.gitignore`）。
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
- **用同一个 classic PAT 建私仓（本轮实测 201）**：`POST https://api.github.com/user/repos`，body `{"name":"<repo>","private":true}` → **201**，一次成功（40 字符的 classic PAT、`x-oauth-scopes` 含 `repo`）。**判令牌能力只看 `x-oauth-scopes` 响应头**（就是上面那条探测命令），**别靠猜前缀**——`ghp_` 前缀不代表带 `repo`，fine-grained（`github_pat_`）在同类调用上会 403（§0）。建完回读 `GET /repos/:owner/:repo` 确认 `private=true` 与 `default_branch`。
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
- **2026-10-08 凭据策略反转（用户决策）**：**取消"凭据文件必须在 skill 目录之外"**——现在**鼓励 skill 直接写明凭据文件位置**，`ascend-env\credentials.txt` 就地保留；PAT 当前位置 `~\.dsh\.secrets\` 保持不动（两处都合法）。禁止项收窄为：不进仓内文件、不进日志/命令历史、不进 `description`。§0 单一出处地位不变，`gitcode-pr-flow` / `dsh-skill-authoring` / `dsh-skill-self-audit` 三处引用已同步改写。
- **2026-10-09 完善**：⑩ 新增 **§12「上游基线漂移与安全重推」**（上游基线漂移的三条判据 / rebase 后用真父提交做范围检查 / LF 不变量落在 blob / 带显式旧 sha 的 `--force-with-lease` / PS 5.1 读 `pulls/<n>/files` 单元素数组塌陷）；⑪ description 削掉两处可省措辞（个人 / 规范调研 / files API 缩进取证、`（含 MindSpeed-Agent）`）并补两条触发句式（「上游 main 又前进了」「rebase 后重推被拒」）。

## 10. 反向流程：抓既存 PR 做离线终审（REST API 取证）

§0–§8 是"提 PR"方向；本节是反方向：**手上只有一个 PR 号（或一串拆分 PR），要把改动、评论、合并态、以及"改动前的代码全文"抓到本地做离线终审**——全程 REST API，不用浏览器；只有 §10.3 读"改动前全文"那一步需要本地 clone。

### 10.1 抓 PR 本体一律走 REST API（HTML 只有导航栏）

- `https://github.com/<owner>/<repo>/pull/<n>` 的 **HTML 抓下来只有导航栏、抓不到正文**（机制与 `arxiv-paper-deep-read-and-claim-verification` 里"GitHub 网页 JS 渲染只剩导航栏"同源）⇒ 正文 / 文件 / 评论一律读 API。
- 7 个产物文件（落同一目录）：

| 产物 | 来源端点 | 说明 |
|---|---|---|
| `pr.json` | `GET /repos/<o>/<r>/pulls/<n>` | 元数据，含 `body`（本地快照可能被截断，见 §10.6） |
| `files.json` | `GET /repos/<o>/<r>/pulls/<n>/files?per_page=100` | **改动清单的唯一事实来源**（见 §10.5） |
| `commits.json` | `GET /repos/<o>/<r>/pulls/<n>/commits` | 防分页截断，见 §10.2 |
| `pr.diff` | `GET /repos/<o>/<r>/pulls/<n>`，头 `Accept: application/vnd.github.v3.diff` | **取原始字节**，不要 JSON 包一层 |
| `comments.json` | `/issues/<n>/comments` + `/pulls/<n>/comments` + `/pulls/<n>/reviews` 三路合并 | 少一路就漏 |
| `linked_issues.json` | 由 `body` 里的 `#<n>` 反查 `/issues/<n>` | `body_excerpt` 同样截断 |
| `notes.md` | 自写 | 结论 + 证据链 |

- **token 定位顺序**（本机实测：env 里没有、`.git-credentials` 里没有、`gh` 未登录，**只有第 2 处可用**；凭据策略见 §0）：

```powershell
$t = $env:GITHUB_TOKEN
if (-not $t) { $f = "$env:USERPROFILE\.dsh\.secrets\github-pr-flow.token"; if (Test-Path -LiteralPath $f) { $t = (Get-Content -LiteralPath $f -Raw -Encoding utf8).Trim() } }
if (-not $t) { $t = (gh auth token) }
```

- 抓取（写盘一律无 BOM，见 §2 坑 2；diff 用 `-OutFile` 拿原始字节）：

```powershell
$h = @{Authorization="Bearer $t"; Accept='application/vnd.github+json'}
Invoke-RestMethod "https://api.github.com/repos/<o>/<r>/pulls/<n>" -Headers $h | ConvertTo-Json -Depth 8 |
  ForEach-Object { [IO.File]::WriteAllText("$out\pr.json", $_, (New-Object System.Text.UTF8Encoding $false)) }
Invoke-WebRequest -Uri "https://api.github.com/repos/<o>/<r>/pulls/<n>" -Headers @{Authorization="Bearer $t"; Accept='application/vnd.github.v3.diff'} -OutFile "$out\pr.diff"
```

### 10.2 抓完必须自校验（防抓错 / 防分页截断）

- **`pr.diff` 实际行数 vs API 的 `additions + deletions`，比值约 1.07**——diff 里除代码行外还有 `diff --git` / `index` / `---` / `+++` / `@@` hunk 头等非代码行。**实测 2057 行 vs 1923 = 1.07**。**差一个数量级 = 抓错了**（例如只拿到 JSON 包装、或只拿到部分文件）。
- `files.json` 条数 **==** `changed_files`。
- `commits.json` 条数 **==** `commits`。

后两条任何一条不等 = 分页截断，抓不完不下结论。

### 10.3 取"改动前"的文件全文：用 `index` 行的前半哈希（比 `merge_sha^` 稳）

`pr.diff` 里每一段都有这样一行：

```
index 7a63adf7b647..f5e47804f0c8 100644
```

`..` **前面**是改动前的 blob 哈希、**后面**是改动后。于是

```powershell
git -C <clone> cat-file -t 7a63adf7b647      # 先确认本地有这个对象，返回 blob
git -C <clone> cat-file -p 7a63adf7b647      # 改动前的完整文件全文
```

**为什么比 `merge_sha^` 稳**：不依赖合并提交有几个父节点——`^1` 在 merge 上取的是第一父，容易取到另一条分支的版本。

### 10.4 缩进类 bug 的定案法：把缩进打成数字

GitHub 网页 diff 的 hunk 只给 **3 行上下文**，**很容易把"这行属于哪个代码块"看错**。必须把缩进打成数字：

```powershell
$L = Get-Content <file> -Encoding UTF8
for($i=$a;$i -lt $b;$i++){ $l=$L[$i]; '{0,4}: [{1,2}] {2}' -f ($i+1), ($l.Length - $l.TrimStart().Length), $l.TrimEnd() }
```

**实测反例（务必照抄记住）**：某 hunk 头是 `@@ -219,7 +225,7 @@`，一行 `self.model.load_weights(weights)` 的缩进从 **12 → 8**。只看上下文，极易得出"这行原来在 per-chunk 循环里、每 chunk reload 一次"。

**真相相反**：`if self.packed:` 在缩进 **8**、`else:` 也在缩进 **8** ⇒ `else:` 的语句体必然是 **12** ⇒ 那行**原本在 `else:`（非打包分支）体内**，改动是把它提到 if/else 之后的**公共尾**。真实 bug 是 **packed 分支从头到尾没调用过 `load_weights`**（权重被整体丢弃、静默无异常），**不是"重复加载"**。

**推论**：缩进宽度**单独不足以定案**——同一个缩进值可能兼容"if 体内 / else 体内 / 更外层循环体内"三种结构，**必须把外层 `if`/`for` 所在行的缩进也读出来**才能定死。

### 10.5 PR body 会过时，`files` API 才是事实

实测某 PR 的 `body` 声称夹带了某文件的修复，但 `files` API 的 11 条里**根本没有那个文件**——改动在 rebase 到主干时被消化成空，`body` 没同步更新。判据：**`body` 说"意图"，`files` API 说"事实"，冲突时以 `files` 为准。**

### 10.6 本地快照 json 里的 `body` 可能被截断

- 实测 `pr.json` 的 `body` 被截到 **2000 字符**；`search/issues` 返回的 `body_excerpt` 也是截断。
- 要全文**必须走 `GET /pulls/<n>`**。
- `linked_issues.json` 的 `body_excerpt` 同样截断。

### 10.7 判"PR 有没有合并"只认 `/pulls/<n>` 的 `merged` 布尔

`search/issues` 返回的 `pull_request.merged_at` **为空 ≠ 未合并**，会误判（实测母 PR 的 `merged=false` 才是真值）。

### 10.8 拆分母 PR 的取证链

1. `GET /search/issues?q=repo:<owner>/<repo> is:pr "split out of #<母PR号>"` 找齐拆分 PR 集合；
2. 逐个用 `GET /pulls/<n>` 判**真实**合并态（§10.7）；
3. 用 `head.ref` 的 `split/prN-*` 命名与 body 里的 "second/third of three" **互证顺序**。

### 10.9 本节的 PS 5.1 / Python 坑（通用陷阱表见 `pwsh-on-windows`）

- `cmd /c "git ... <sha>^1 ..."` 里 **`^` 被 cmd 当转义符吃掉** ⇒ **输出为空且 exit code 0（假通过）**。修法：先 `git rev-parse "<sha>^1"` 把 40 位父 sha 解析出来，再直接用它。
- `git show <sha>:<path>` 直接管道会被 GBK 解码破坏中文 ⇒ 用 `cmd /c "git ... > file"` 落盘再 `read`。
- 含中文 / em-dash 的内容**别用 `python -c` 直接打印到控制台**（PS 5.1 控制台 GBK）⇒ 报 `UnicodeEncodeError: 'gbk' codec can't encode character '\ufeff'`。改成写成 `.py` 文件、结果直接落盘。
- 数行数别用 `(Get-Content $p).Count`（实测少算：1715 vs 真值 2020）⇒ 用 `[IO.File]::ReadAllLines($p).Count` 或 python 二进制读。
- `findstr /s /n /c:"..." vllm\*.py` 递归搜索会**静默返回空** ⇒ 改 `Get-ChildItem -Recurse -Filter *.py | Select-String -Pattern ...`。

## 11. 处理 AI 评审意见（Gemini Code Assist 实测）

拉评论要拉**三个**端点，缺一会漏：

- `GET /repos/{o}/{r}/pulls/{n}/comments` —— inline 行内评论
- `GET /repos/{o}/{r}/pulls/{n}/reviews` —— review 正文
- `GET /repos/{o}/{r}/issues/{n}/comments` —— 时间线评论（bot 的总述常在这里）

回帖用 `POST /repos/{o}/{r}/pulls/{n}/comments/{comment_id}/replies`，body `{"body": "..."}` → 201。

**判一条意见值不值得改之前，先过三道闸（实测三道里两道是假阳性）：**

1. **锚点是否还在**：看该评论的 `commit_id` 是否等于当前 PR head，以及该文件是否还在 `GET /pulls/{n}/files`
   的列表里。评论可能锚在 **rebase 之前**的旧 commit 上——文件早已不在 PR 内，照它改就等于去改一段**已被删除**的文本。
2. **评论挂的位置是否对得上**：inline 评论可能挂在**无关文件**上（实测一条讲"PR 标题格式"的意见，被挂在
   `support_matrix/` 的某个表格行上）。**以 body 内容为准，不要以 `path` 为准**。
3. **仓库内的固定话术要先读配置再判**：vllm-ascend 仓库里有 `.gemini/styleguide.md`，它要求 Gemini **每个 PR 都输出**
   "Suggested PR Title / Suggested PR Summary"，且标题格式为 `[Branch][Module][Action]`、**base 为 main 时 Branch 可省**。
   ⇒ 这类意见**几乎必然每条 PR 都出现**，**不代表当前标题真的不合规**。正确做法是先
   `GET /contents/.gemini/styleguide.md` 读规范，再把自己的标题与之**逐字**比对；**不要照着"建议"去改标题**。
   同理，它给的"建议摘要"可能是**旧 revision** 的内容（文件数、条目都对不上当前 diff），要拿 `files` API 核对。

其余判据同 §10.5：**`files` API 才是事实**，body 会过时。

## 12. 上游基线漂移与安全重推（rebase / amend 之后）

§0–§11 都假设分支还跟得上上游。本节专治「上游 main 又前进了 / 我们 amend 或 rebase 过 / 要重推 fork」这一段——**下面四条判据每条都实测踩过坑，照抄比自创稳**。

### 12.1 判「上游是不是已经自己修好了我们的缺口」不能只看 `base.sha`

`GET /pulls/<n>` 的 `base.sha` 是**建 PR 时**记下的目标分支 sha，之后**不随上游推进而更新** ⇒ 拿它判「我们的缺口还在不在」必错。三条要一起上：

1. **取分支真实父提交**（我们的改动实际落在哪个 commit 上）：`git log -1 --format=%P`（rebase 后它会变，见 §12.2）。
2. **逐路径比对** PR 目标文件在父提交与 `upstream/main` 上的 blob。
3. **只有「我们有改动、而 main 上没有」才算真缺口**——只看 base 与 main 的 diff，会把上游**新提交**误算成我们的缺口。

```powershell
git fetch upstream main                      # ① 每次动手前重取 tip
git log -1 --format="%H %s" upstream/main
git rev-parse HEAD:<path>                    # ② 我们侧该文件的 blob sha
git rev-parse <真父提交>:<path>              #    我们的基线侧
git rev-parse upstream/main:<path>           #    main 侧：与 ② 相等 ⇒ 上游已含该内容
```

- **每次动手前重取 tip，不要复用上一轮的结论**：实测 `git fetch upstream main` 把 tip 从 `d03d385` 推到 `1d5b6c4`（又前进 1 个提交，上一次记下的 sha 当场过期）。
- **比 blob sha，不要比文件的 sha256**：`raw.githubusercontent.com` 下回来的 blob 是 **LF**，而 `core.autocrlf=true` 的 Windows 检出是 **CRLF** ⇒ 同一份内容两份字节，sha256 必然不等。正确口径：
  ```powershell
  curl.exe -sL -o "$env:TEMP\<name>" https://raw.githubusercontent.com/<o>/<r>/main/<path>
  git hash-object "$env:TEMP\<name>"         # 结果拿去和 git rev-parse upstream/main:<path> 比
  ```

### 12.2 rebase 后判「我到底改了哪些文件」必须用**当前实际父提交**

`git diff --name-only <旧 base>..HEAD` 会把**上游新进的提交**一起算进范围；rebase 已经把基准换成新的父提交，旧 base 不再代表你的起点。

```powershell
$p = git log -1 --format=%P        # 真正的父提交
git diff --name-only "$p..HEAD"
```
- 实测：拿**旧 tip** 比回 **11** 个文件（假象）、拿**真父提交**比回 **7** 个文件（真值）——多出来的 4 个全是上游新提交带的文件。**基准写错，范围检查就假报「多改了 4 个文件」。**

### 12.3 「行尾必须是 LF」这条不变量落在 **blob**，不在工作树

- `core.autocrlf=true` 的 Windows 检出**工作树本来就是 CRLF**：`git ls-files --eol` 回 `i/lf w/crlf`，实测工作树 1199 个 CRLF，全部正常。
- 正确验收 = 读**提交进 index 的 blob**：`git show HEAD:<path>` 的字节里 **CR == 0**。
- **照「工作树不许有 CR」去强改，反而引入偏差**——判据写错会把合规检出判成失败，把下游引向「重新规范化整个文件」的返工。这是**「判据写错会误导下游」的实例**，不是格式偏好问题。
- 工作树层面的配套用法见 **§2 坑 3**（改完 `git diff --stat` 确认只有目标行；整文件变更=换行符被动过）——两条一起用，**不要**拿 `git diff` 的整文件变更去否掉上面这条 blob 判据。

### 12.4 amend / rebase 后向 fork 重推的安全形态

```powershell
git -C <w> push https://<token>@github.com/<owner>/<repo>.git HEAD:<branch> --force-with-lease=<branch>:<旧sha>
```
- **必须带显式旧 sha**。只写 `--force-with-lease` 的语义是「远端 ref 与我本地记录一致就放行」——远端被他人更新后本地记录已刷新，它照样通过 ⇒ 那一刻它就是 `--force`，不是保护。带上 `<ref>:<旧sha>` 才是「远端必须仍是我上次看到的那个 sha」。共享分支上的既有配方（含 `--dry-run` 先验一次、`refs/backup/` 长期回滚）见 `gitcode-pr-flow` **§6 ④**。
- 旧 sha 从**上一次 push 之后**取：`git ls-remote <fork-url> refs/heads/<branch>`；**不要**填刚 amend 出来的新 sha。
- **推完两条必核**：`git remote -v` 与 `.git\config` 里**不得出现带 token 的 URL**（token 只走一次性 URL，见 §3）。
- **amend 后核 DCO 没丢**：`git log -1 --format=%B` 里 `Signed-off-by:` 行**必须还在**——`commit --amend` 会重放消息，丢了 DCO 一定挂 CI（§6/§7）。

### 12.5 本节踩到的 `Invoke-RestMethod` / git 坑（通用解码表见 `pwsh-on-windows`）

- **`Invoke-RestMethod` 在 PS 5.1 下把单元素 JSON 数组塌陷成对象**：读 `GET /pulls/<n>/files` 会拿到 `Count == 1` 的**假值**（真实 7 个文件）——这会直接动摇 §10.5「`files` API 才是事实」的可信度；§10.2「`files.json` 条数 == `changed_files`」因为读的是**落盘文件**，不受影响。修法二选一：
  ```powershell
  # ① 走原始字节再自己解析（PS 5.1 下最稳）；UTF8 解码 idiom 的单一出处见 pwsh-on-windows
  #    未验证：本行是按「-UseBasicParsing + RawContentStream + ConvertFrom-Json」三件套口径拼合的，未逐字复跑
  $r = Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/<o>/<r>/pulls/<n>/files?per_page=100" -Headers $h
  $files = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
  # ② 或先判类型再数：单元素时 ConvertFrom-Json 给的是 PSCustomObject，不是数组
  $n = if ($files -is [array]) { $files.Count } else { ($files | Measure-Object).Count }
  ```
- **`git grep --no-filename` 本机 git 不支持**：报错原文 `error: unknown option 'no-filename'` ⇒ 改 `-l`（只回文件名），或去掉该选项。
