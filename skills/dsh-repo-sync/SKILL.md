---
name: dsh-repo-sync
description: 我的 DSH 私仓同步——现在同步一次、昨天同步没成功、私仓内容少了或不对、ALERT.md 出现了、计划任务 DSH-Repo-Sync 报错：脚本 sync-dsh-repos.ps1 把 ~/.dsh 与编排 preset 用 robocopy 快照进私仓镜像，明文 PAT 脱敏成 redacted，退出码即结论（0 成功 / 非 0 见码表）。适用于"私仓天天收到 workflow 失败邮件 / 手动同步我的私仓 / 现在同步一次 / 同步坏了怎么办 / ALERT.md 出现了 / 昨天同步没成功 / 私仓内容少了或不对 / 计划任务 DSH-Repo-Sync 报错 / 想改同步的排除项 / 把私仓公开"。不适用：向 GitHub 上游仓提 PR → 用 `github-pr-flow`；向 GitCode 社区仓提 PR → 用 `gitcode-pr-flow`；计划任务注册与退役取证 → 用 `win-scheduled-task-forensics`。
whenToUse: 要手动跑一次 ~/.dsh 到私仓的同步、排查同步失败（ALERT/退出码/日志）、或改同步排除项与计划任务时使用。模型看不到本节，触发只靠 description。
---

# dsh-repo-sync：DSH 配置 → 我的私仓（GitHub / GitCode）

一个**确定性**同步：本机的 DSH 配置（`~/.dsh`）与生效中的编排 preset bundle，双向快照进本机镜像仓
`D:\repos\deepseek-harness`，再从那里推到两个私仓远端。**没有 shell 里的手工 git 步骤**——
一切走一个脚本，退出码就是结论。

## 何时调用

**加载本 skill 当：**
- 用户说「**手动同步我的私仓**」「现在同步一次」「把 ~/.dsh 推到我的仓库」「同步状态怎么样」。
- 用户说「**同步坏了怎么办**」「昨天/今早的同步没成功」「私仓里的内容少了 / 不对 / 是旧的」。
- `D:\repos\deepseek-harness\sync\ALERT.md` **存在**（脚本只在失败时写它，成功时删除）。
- 计划任务 `DSH-Repo-Sync` 报错，或你要重新注册它。
- 要改**同步范围**（排除项、preset 源、远端 URL、令牌文件路径）。

**不要用本 skill（转交）：**
- 向 GitHub 上游仓提 PR（DCO / CI 判读） → 用 `github-pr-flow`。
- 向 GitCode 社区仓提 / 修 PR（门禁、标签） → 用 `gitcode-pr-flow`。
- 本机 PowerShell 的编码 / 计数 / PS7 语法坑 → 用 `pwsh-on-windows`。
- skill frontmatter 与 description 怎么写 → 用 `dsh-skill-authoring`。

**前置**：镜像仓 `D:\repos\deepseek-harness` 已 clone（含 `upstream` 远端、分支 `master`）；两个令牌文件存在。 ／ **后继**：修完真跑一次 dry-run，再读 `sync\state.json` 与当月日志确认。

## 1. 机制全景（本 skill 只管这一个机制）

| 项 | 绝对路径 |
| --- | --- |
| 同步脚本 | `C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1` |
| 镜像仓 | `D:\repos\deepseek-harness`（分支 `master`，`core.autocrlf=false`） |
| DSH 快照目标 | `D:\repos\deepseek-harness\dsh-home` |
| preset 快照目标 | `D:\repos\deepseek-harness\dsh-presets\orchestrator-bundle` |
| preset 源 | `D:\workspace\agent\dsh_base\artifacts\presets\orchestrator-bundle` |
| 远端配置 | `D:\repos\deepseek-harness\sync\remotes.json` |
| 运行状态 | `D:\repos\deepseek-harness\sync\state.json` |
| 日志（按月追加） | `D:\repos\deepseek-harness\sync\logs\sync-YYYY-MM.log` |
| 告警 | `D:\repos\deepseek-harness\sync\ALERT.md`（**只在失败时存在**） |
| 排除清单 | `D:\repos\deepseek-harness\sync\EXCLUDED.md` |
| GitHub 令牌文件 | `D:\key\github_PTA.txt` |
| GitCode 令牌文件 | `D:\key\gitcode_访问令牌_xmz_agent用.txt` |
| 计划任务名 | `DSH-Repo-Sync` |

三个**执行阶段**（脚本内顺序固定）：

1. **快照**——`robocopy $DshHome $Snap /MIR /XJ /R:1 /W:1 /NFL /NDL /NP /NJH /NJS /XD sessions node_modules .git .pnpm-store .secrets storages /XF *credentials* *.key *.pem *.token .credentials.yaml *.zstd`；再把 preset 源同法镜像到 `dsh-presets\orchestrator-bundle`（只排除 `node_modules/.git`）。`/MIR` 会**删除目标侧多余文件**，所以目标只允许是上面那两个路径（脚本内有 `Assert-SafeMirrorTarget` 硬校验）。robocopy 退出码 **0..7 视为成功，>=8 才是失败**。
   - `.secrets` 与 `storages` 是**目录级**排除：前者整个目录都是凭据（`github-pr-flow.token`、`ms365\.token-cache.json`、`ms365\.selected-account.json`），后者是会话项目缓存。这样 `*.token` 匹配不到 `.token-cache.json` 的缺口就被关掉了。
   - **根级 `cordis.patch.yml` 单独处理**（故意不用 `/XF cordis.patch.yml`——那会连带删掉 `profiles\*\cordis.patch.yml` 与 preset 里的同名文件，它们无密钥且必须保留）：快照完成后先 `Remove-Item $Snap\cordis.patch.yml`，再写 `$Snap\cordis.patch.redacted.yml`——凡是键名匹配 `(?i)(token|secret|password|api_?key|webhook)` 的值一律替换成 `<redacted>`（只动值、保留键与结构、UTF-8 无 BOM），随后**再扫一遍**：只要还能匹配到真令牌字面量就中止（exit 5），绝不把可疑文件留下。
    - **"快照里没有真令牌"的验收配方（③④ 为本轮新增；①② 就是上面两条）**：③ 验收必须**逐字节扫真实令牌字面量**求 **0 命中**——把令牌值从**令牌文件**读进内存（**永不打印、永不落盘**）后对整个快照目录做字节扫描；**别用"看起来像令牌"的正则代替**，那样既漏真值也制造误报。④ **区分"散文里提到 `ghp_` 前缀"与"真令牌值"**：`git grep` 命中前者（skill 正文里讨论 `ghp_` 这类文字）是**正常噪声**，只有后者才算泄漏。
2. **上游**——`git -C $Mirror fetch --prune upstream master`；有新提交则 `git merge --no-edit upstream/master`；冲突则 `merge --abort` + 写 ALERT + **exit 4**。
3. **提交与推送**——`git add -A`；无变化且无上游变化且非 `-Force` → 打印 `NO_CHANGE`、写 state、**exit 0（不做空提交、不推送）**；否则提交后对两个远端各推一次 `HEAD:master`。

**镜像仓的一次性建法（Windows 上做"字节保真"镜像：三步顺序不可换，实测）**：

```powershell
git clone --no-checkout <远端URL> D:\repos\deepseek-harness    # ① 先不检出
git -C D:\repos\deepseek-harness config core.autocrlf false   # ② 关掉换行改写（必须在 checkout 之前）
git -C D:\repos\deepseek-harness checkout master              # ③ 再检出
```

- **顺序为什么不能换**：先 `checkout` 再关 `autocrlf`，工作副本已被写成 **CRLF**，而远端存的是 **LF** ⇒ `git status` 把**全部文件**报成改动，镜像不再字节保真（随后 `git add -A` 会把整棵树的换行差异当成内容改动提交上去）。
- **为什么必须用仓库级作用域（`--local`，即不带 `--global` / `--system`）**：本机 `core.autocrlf=true` 来自**系统级** `file:D:/tools/Git/etc/gitconfig`，**不是** `~/.gitconfig` ⇒ 只改全局配置管不住它，只有仓库级（默认作用域）能覆盖。一行只读取证（本轮复核）：`git config --show-origin --get-all core.autocrlf` → `file:D:/tools/Git/etc/gitconfig` + `true`。
- 建完自检：`git -C D:\repos\deepseek-harness status --porcelain` 应为空（工作区与 HEAD 逐字节一致）。

**鉴权形态（远端实测）**：`remotes.json` 每个远端带 `auth` 与 `user` 两个字段。`auth=token-as-user` → `https://<token>@<host>/<path>`（GitHub 实测可用）；`auth=user-token` → `https://<user>:<token>@<host>/<path>`（**GitCode 只认这一种**：纯 token 形态实测报 `fatal: could not read Password for 'https://<redacted>@gitcode.com': terminal prompts disabled`）。逐字 schema 见 §6。

**非交互与超时（硬）**：每次 git 调用都是 `git -c credential.helper= ...`（**禁用一切 credential helper**），并在脚本开头设 `GIT_TERMINAL_PROMPT=0`、`GIT_ASKPASS=''`。理由：本机 `credential.helper=wincred` 时打 gitcode.com 会**弹 Git Credential Manager GUI 并挂死 120 s**，计划任务会"挂"而不是"失败"。每个 git 调用还有**硬超时**：push 900 s、其余 120 s；超时即杀进程树并按失败处理（push 超时走 exit 6）。

**令牌安全（硬）**：令牌只从 `remotes.json` 里 `token_file` 指定的文件读，`Trim` 掉空白与 BOM；
**永不打印、永不写进 `.git/config`、永不写进仓库内任何文件**；所有 git 输出先经 `Get-RedactedText`
（令牌替换为 `<redacted>`，另加 `://user@` → `://<redacted>@` 的正则兜底）。推送用内联 URL，
不用 `git remote add`——所以 `.git/config` 里没有令牌。唯一例外：`git fetch <内联 URL>` 会把带令牌的
URL 记进 `.git/FETCH_HEAD`（不在 config 里），脚本在 fetch+merge 之后立刻把它回写成 `<redacted>`。

**DryRun 语义**：镜像到 `%TEMP%\dsh-repo-sync-dryrun\`，**不碰镜像仓、不起任何 git 命令、不写 remotes**；
连 `EXCLUDED.md` 都写在 TEMP 里。它照样读镜像仓判断存在性、照样报数。

**`.gitignore` 幂等**：脚本只**追加缺失的**行（`sync/logs/`、`sync/state.json`、`sync/ALERT.md`、`sync/.lock`），
不重复追加、不删原有行、末尾保持 LF。当前 `sync/remotes.json` 与 `sync/EXCLUDED.md` **不在**忽略名单里，
会被一起提交进私仓——两者都只含路径与字节数，**不含任何令牌值**。

## 2. 退出码表

| 码 | 含义 | 先看哪里 |
| --- | --- | --- |
| 0 | 成功推送，或 `NO_CHANGE`（无变化、不提交不推送） | `state.json` 的 `changed` / `remotes[*].ok` |
| 3 | 环境错误：镜像仓不是 git 仓、`remotes.json` 缺失/坏、或 git 提交身份取不到 | 日志里的 `MIRROR_PRESENT` / `REMOTES_JSON` / `GIT_IDENTITY` 行 |
| 4 | 上游合并冲突（脚本已 `merge --abort`，镜像仓保持干净） | 日志里 `git merge` 的输出 |
| 5 | 快照失败（robocopy rc>=8）、提交失败，**或 cordis 脱敏守卫拦下残留令牌** | 日志里 `robocopy ... rc=` / `git commit rc=` / `redaction guard tripped` 行 |
| 6 | 推送失败（两个远端里至少一个最终没推上去，**含 git 调用超时**） | 日志里 `PUSH[github]` / `PUSH[gitcode]` / `TIMEOUT:` 行 |
| 7 | 远端分叉（fetch 到远端 master 后 merge 冲突，推不上去） | 日志里 `reconcile merge conflict` / `remote diverged` |
| 8 | 未预期异常（脚本 bug 或环境突变） | 日志里 `UNEXPECTED:` 那一行 |

**提交身份**：优先用镜像仓的 **local** `user.name`/`user.email`，没有则用 `git config --global` 的值，
两者都取不到就**不编造**——写 ALERT、**exit 3**。

## 3. 可直接复制的命令

```powershell
# 手动 dry-run（安全：只写 %TEMP%，镜像仓一字不动，不起 git）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1" -DryRun

# 手动真跑
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1"

# 真跑但跳过上游合并（上游远端暂时不可用时）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1" -NoUpstream

# 无变化也强制提交（仅在确实要留一条提交记录时用）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1" -Force

# 看日志（当月最后 40 行）
Get-Content "D:\repos\deepseek-harness\sync\logs\sync-$(Get-Date -Format yyyy-MM).log" -Tail 40

# 看状态（最近一次运行的完整结果）
Get-Content "D:\repos\deepseek-harness\sync\state.json" -Raw

# 看告警（文件不存在 = 最近一次成功）
if (Test-Path "D:\repos\deepseek-harness\sync\ALERT.md") { Get-Content "D:\repos\deepseek-harness\sync\ALERT.md" -Raw } else { "no alert" }

# 看被排除清单
Get-Content "D:\repos\deepseek-harness\sync\EXCLUDED.md"

# 重新注册计划任务（本 skill 不代你注册；注册与否由人决定）
$act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-repo-sync\sync-dsh-repos.ps1"'
Register-ScheduledTask -TaskName 'DSH-Repo-Sync' -Action $act -Trigger (New-ScheduledTaskTrigger -Daily -At 09:00) -Force

# 等价写法：schtasks（形态与 dsh-skill-self-audit §5 已实测的那条同构）；/TR 指向 ASCII-only 的 .cmd
schtasks /Create /TN "DSH-Repo-Sync" /SC DAILY /ST 09:00 /F /TR "C:\Users\admin\.dsh\skills\dsh-repo-sync\run_daily.cmd"
schtasks /Query /TN "DSH-Repo-Sync" /FO LIST /V
schtasks /Run /TN "DSH-Repo-Sync"        # 立即触发一次（跑闸门，最便宜的真实验证）
schtasks /Delete /TN "DSH-Repo-Sync" /F  # 回滚：撤销定时
```

**计划任务的硬规则（实测）**：

- **`.cmd` 必须 ASCII-only 且写绝对路径**：`cmd.exe` 用 OEM 代码页（本机 GBK）读 `.cmd`，中文字面量会被拆坏。本 skill 的入口壳就是 5 行：`run_daily.cmd` = `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<...>\sync-dsh-repos.ps1"` + `exit /b %ERRORLEVEL%`，逻辑全在 `.ps1` 里。
- **`-ExecutionPolicy Bypass` 是承重的，不能省**：本机 `Get-ExecutionPolicy -List` **五个作用域全 `Undefined`**（本轮实测）⇒ 有效策略 `Restricted`，去掉它 `.ps1` 会被直接拦下（`running scripts is disabled on this system`）。
- **`Last Result` 不能当判据**：本机 `DSH-Skill-SelfAudit` 有**恒 0** 的先例 ⇒ 只看 `Last Result: 0` 会把真失败读成成功（`dsh-skill-self-audit` §验收标准已同步修正为"只认产物"）。**判完成只看产物自身**：本 skill = `sync\state.json` 的 `last_run_local` / `exit_code` + 当月日志尾部 + **`sync\ALERT.md` 是否存在**（**存在 = 上次失败**；它只在失败时写、成功时删除）。
- **失败必须留下可供 agent 接手的痕迹**：`ALERT.md`（含失败阶段与退出码）就是这条通道——别把"任务历史里看着成功"当结论。

判读要点：脚本把 `SNAPSHOT_FILES=` / `SNAPSHOT_BYTES=` / `EXCLUDED_ENTRIES=` 打在结尾的 `=== SUMMARY ===` 里；
`state.json` 的字段是 `last_run_local` / `last_run_utc` / `upstream_head` / `local_head` / `snapshot_files` /
`changed` / `remotes{ok,pushed_sha,error}` / `exit_code`。

## 4. 故障处置

**上游冲突（exit 4）**——脚本已自动 `git merge --abort`，镜像仓干净。查：`git -C D:\repos\deepseek-harness status`、
`git -C D:\repos\deepseek-harness log --oneline -5 upstream/master`。修：①若镜像仓的本地提交不要了，就
`git -C D:\repos\deepseek-harness reset --hard upstream/master` 再真跑；②必须保留本地改动，就在镜像仓里手工 merge
解决冲突并提交，然后用 `-NoUpstream` 真跑。

**推送被拒（exit 6）**——先看日志里那条 `PUSH[...]`。区分三种：`non-fast-forward / rejected / fetch first`
= 远端有你没有的提交（脚本已试过 fetch+merge 再推，仍失败才报 6）；`TIMEOUT:` = 该次 git 调用撞到硬超时
（push 900 s），多半是网络或凭据助手在等你输入——**不是网络慢就是有人把 helper 放回来了**；
`Authentication failed / 403 / 401` = 令牌或权限问题（见下一条）。探针（**失败时 git 会把带令牌的 URL 打进
报错里，别把输出粘进聊天/工单**）：

```powershell
# GitHub（token-as-user 形态，实测可用）
$t = (Get-Content 'D:\key\github_PTA.txt' -Raw).Trim()
git -c credential.helper= -C 'D:\repos\deepseek-harness' ls-remote ("https://$t@github.com/EliasKaslan/xmz_dsh.git") HEAD

# GitCode（必须 user-token 形态：用户名 + 令牌作密码；纯 token 形态会报
#   fatal: could not read Password for 'https://<redacted>@gitcode.com': terminal prompts disabled）
$g = (Get-Content 'D:\key\gitcode_访问令牌_xmz_agent用.txt' -Raw).Trim()
git -c credential.helper= -C 'D:\repos\deepseek-harness' ls-remote ("https://EliasKaslan:$g@gitcode.com/EliasKaslan/xmz_dsh.git") HEAD
```

两条探针都必须带 `-c credential.helper=`，否则本机 `credential.helper=wincred` 会**弹 Git Credential Manager
GUI 并挂死**（实测 120 s）。

**远端分叉（exit 7）**——脚本 fetch 回了远端 `master` 但 merge 冲突。说明两个私仓/两台机器互相覆盖。
查：`git -C D:\repos\deepseek-harness log --oneline -10` 与远端 `ls-remote` 的 sha 对比，**先决定以哪边为准**，
再手工处理。**不要靠 force push 蒙过去**（见 §5）。

**令牌失效 / GitCode 报 `could not read Password`**——症状是 exit 6 + 日志含 `Authentication failed` / `403` /
`could not read Password`。后者的真因**通常不是令牌坏了，而是鉴权形态用错**（GitCode 必须 `EliasKaslan:<token>@`，
不能只用 `<token>@`）或某处把 credential helper 放回来了。先核 `remotes.json` 的 `auth` 字段，再重新生成令牌、
**覆盖同一个文件**（脚本只认路径、不认格式）：GitHub 写回 `D:\key\github_PTA.txt`（PAT，需 repo 写权限）；
GitCode 写回 `D:\key\gitcode_访问令牌_xmz_agent用.txt`。两个文件 2026-10-09 实测**都存在**。脚本每次运行都从
文件重读，改完直接真跑即可，不需要重启任何东西。

**根级 `cordis.patch.yml`（含明文 PAT）**——它**不会**进私仓：脚本每次快照后都把它从快照里 `Remove-Item` 掉，
只留值脱敏过的 `cordis.patch.redacted.yml`（键名匹配 `(?i)(token|secret|password|api_?key|webhook)` 的值 → `<redacted>`），
并再扫一遍兜底（残留就 exit 5）。**源文件 `C:\Users\admin\.dsh\cordis.patch.yml` 不动**——它是只读输入。
真要根治，去那个文件里把明文 PAT 换成变量引用；换掉之后快照里就不会再出现它的脱敏副本以外的任何痕迹。

**robocopy 失败（exit 5）**——日志里是 `robocopy dsh-home rc=N` 且 `N>=8`。常见成因：目标文件被占用
（脚本 `/R:1` 只重试 1 次）、路径过长、磁盘满。查 D 盘余量（2026-10-09 实测**剩 665 GB**），然后直接重跑一次；
持续失败就找到占用者再跑。注意 `sessions`（DSH 正在写的会话记录）已被排除，所以占用多半来自 `node_modules`。

**确认"到底同步了什么"**——`state.json` 的 `snapshot_files` 与 `EXCLUDED.md` 一起读。2026-10-09 实测口径：
`~/.dsh` 约 **28,000 个文件 / 7.5 亿字节**，其中**被排除的只有 8 个顶层项**（6 个目录 + 2 个文件），却覆盖了
**99.8% 的体积**：`launcher\runtime\node_modules` 26,621 个/475 MB、`sessions` 约 670 个/264 MB、
`storages` 665 个/12 MB、`profiles\*\node_modules`、`.secrets` 4 个/9 KB，加上 `.credentials.yaml` 与
`skills\ascend-env\credentials.txt`；真正进快照的只有 **80 余个文件 / 约 1.6 MB**
（`AGENTS.md`、`cordis.patch.redacted.yml`、`skills\**`、`launcher` 顶层 8 个文件等）。**这是正常的**——
`~/.dsh` 的体积几乎全在 node_modules 与会话记录上，**不要因为"只有 80 个文件"就以为同步坏了**。
**三个会话记录位置**：`~/.dsh\sessions\`、`~/.dsh\storages\session_projcache\sessions\`、
`~/.dsh\storages\session_projcache.json`——前两个被 `/XD sessions` / `/XD storages` 整块挡掉。

**每天收到 GitHub「workflow run failed」邮件（镜像仓继承了上游 CI，2026-10-13 实测）**——把**官方源码**镜像进私仓，会连带把上游的 `.github/workflows/`（本例 **23 个** workflow）与 `.github/dependabot.yml` 一起搬进来，而私仓的 Actions **默认启用** ⇒ **每次推送都会触发一批必然失败的 run**；GitHub 随后把「workflow run failed」通知发到**触发者账号的 primary 邮箱**（本例实测 `GET /user/emails` → `****@qq.com`，`primary=True, verified=True`），同时在 private 仓**消耗 Actions 分钟数**。本例实测：每天 09:30（UTC+8）推送对齐一批 **4 条 failure**（Sandbox / Release (dsh) / Release (vendor) / E2E (real DeepSeek API)），另有上游 `schedule` 触发的 E2E 每天也 failure。

**取证链（顺序固定，别跳步；`{o}/{r}` = owner/repo）**：

1. `GET /repos/{o}/{r}/actions/permissions` —— 看 `enabled` / `allowed_actions`（这一步就能解释"为什么会有 run"）。
2. `GET /repos/{o}/{r}/actions/runs?per_page=N` —— 把 `created_at` 与**推送时刻**对齐；看 `event=push` / `schedule` / `dynamic`。
3. `GET /repos/{o}/{r}/actions/runs/{run_id}/jobs` —— **关键判据：`steps_count=0` + 启动 2 秒即 failure + `runner_name` 为空 = 这个 job 从未启动**。
4. **失败原文只在 check-run annotation 里**：`GET /repos/{o}/{r}/check-runs/{job_id}/annotations`。

三个坑（都实测，别浪费一轮）：

- **坑 1**：`GET /repos/{o}/{r}/actions/jobs/{job_id}/logs` 对**未启动**的 job 返回 **404** ⇒ **别去拉 job 日志判因**（拉不到不代表没有原因，原因在 annotation 里）。
- **坑 2**：`GET /users/{u}/settings/billing/actions` 已 **410 迁移**（原文 `This endpoint has been moved.`）⇒ 计费不能靠这个端点取证，只能看 annotation 原文。本例 annotation **逐字**：`The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings`。
- **坑 3（推论纪律）**：仅凭镜像里出现 `runs-on: [self-hosted, ...]` 或第三方 runner（如 `blacksmith-8vcpu-ubuntu-2404`）就断言"失败是因为缺 runner"是**错的**——本例真正失败的那批是**被账号计费拦在启动前**（`cancelled` / `queued` 的 `CI master` 才与自建 runner 标签有关）。**先看 steps/annotation，再谈 runner。**

**修法（改设置，不动镜像内容）**：`PUT /repos/{o}/{r}/actions/permissions`，body `{"enabled": false}` → **204**，回读 `enabled=false`。镜像内容**逐字节不变**——这是它相对"把 workflows 从镜像里剔掉"方案的最大优点（后者会与上游 merge 反复冲突）。

- **顺序：先关 Actions、再删 dependabot 分支**——dependabot 的版本更新本身就是 Actions run（`event=dynamic`）⇒ **不先关它会重建分支**。
- 删分支：`DELETE /repos/{o}/{r}/git/refs/heads/<branch>`（**分支名含 `/`**，如 `dependabot/github_actions/actions/cache-6`）；删分支会**自动关闭**引用它的 PR。

**边界**：计费问题本身是**账号级**的、与本仓内容无关——关掉本仓 Actions 只止住**这一仓**的噪声；其它仓若依赖 Actions，须自行处理 Billing & plans。

**GitCode 侧无此问题**：实测 `GET /api/v5/repos/{o}/{r}` 的 **37 个字段无** pipeline/ci/webhook 类字段、`/pipelines` **404 未暴露**、`/hooks` **count=0** ⇒ GitCode 不会产生失败邮件。**别把 GitCode 的 events 当数组直接解**——它是 `{"events":[…]}` 包装对象。

**彻底静音（2026-10-13 补充实测）**：

- **账号级 Actions 关不掉（REST 无端点）**：`PUT` 与 `GET /users/{u}/actions/permissions` 实测**均 404**，错误体逐字 `{"message":"Not Found","documentation_url":"https://docs.github.com/rest","status":"404"}`——注意 `documentation_url` 是**通用 `/rest`**（= 路由不存在），**不是**权限不足（权限不足是 **403**）。文档里的 Actions permissions 端点只有 **repo / org / enterprise** 三级 ⇒ **账号级只能在 UI 关**：`https://github.com/settings/actions` → **Actions permissions** → 选 **Disable actions** → Save（该页四个选项：Allow all / **Disable actions** / Allow `<用户名>` / Allow `<用户名>`, and select non-`<用户名>`）。
- **边界补充（"只用 GitHub 当云仓库、不想付费"这个立场下）**：**仓库级关 Actions 已足够**止住失败邮件与分钟数消耗；**账号级**开关只是防止**以后新建的仓**再误触。关掉这些**不影响**推送 / 拉取 / 存储 / 历史 / 私有可见性。

**Dependabot 的两个独立开关（与 Actions 无关、不花钱，但也是通知邮件来源，容易被忽略）**：

- **告警**：`GET /repos/{o}/{r}/vulnerability-alerts` → **404 = 已关闭**（原文 `{"message":"Vulnerability alerts are disabled.",…}`）、**200/204 = 已启用**；关闭用 `DELETE /repos/{o}/{r}/vulnerability-alerts` → **204**。
- **转 public 后安全告警会不会被自动打开：本例实测"没有"（2026-10-14）**——GitHub 对 public 仓**默认**开启 Dependabot 安全告警，但**该默认值不覆盖一次显式的关闭**：本例私有时主动关掉（404），**转 public 后实测仍为 404**（`GET /repos/EliasKaslan/xmz_dsh/vulnerability-alerts`），`automated-security-fixes` 亦仍为 `{"enabled":false,"paused":false}` ⇒ **别把"转公开 ⇒ 告警被自动打开"写成结论**；转公开后**重读一次**即可判，判据 = `GET /repos/{o}/{r}/vulnerability-alerts` → **200/204 = 已启用、404 = 已关闭**，`GET /repos/{o}/{r}/automated-security-fixes` → `{enabled,paused}`（告警关闭时对它 `DELETE` 返回 **422** 幂等前置条件错误，不是失败）。**同批实测里确实发生的是另一件：转公开后依赖图会重跑**——本例转公开后 dependabot 立刻又动作（那道反证见下一条 `归属澄清`）。
- **自动安全修复**：`GET /repos/{o}/{r}/automated-security-fixes` → 原文 `{"enabled":false,"paused":false}`；**在告警已关闭时**调 `DELETE /repos/{o}/{r}/automated-security-fixes` 会返回 **422**，原文 `{"message":"Vulnerability alerts must be enabled to configure automated security fixes.","documentation_url":"https://docs.github.com/rest/repos/repos#disable-dependabot-security-updates","status":"422"}` —— **这是幂等前置条件不满足（告警没开就没得关），不是失败**，别当故障去排查。

**归属澄清（关键，别混）**：dependabot **版本更新**是 **Actions run**（`event=dynamic`，由仓里 `.github/dependabot.yml` 驱动）——但**"关掉 Actions 即随之停止"已被 2026-10-14 实测证伪**：该仓 `actions/permissions` 仍是 `{"enabled":false,"sha_pinning_required":false}`，`2026-10-14T03:06:08Z` 照样起了 3 条 `event=dynamic` 的 dependabot run（`github_actions in /. - Update #1626029849 | completed | success`、`uv in /python/sdk - Update #1626029825 | completed | failure`、`npm_and_yarn in /. - Update #1626029794 | completed | failure`），紧接着 `2026-10-14T03:08:38Z–03:13:35Z` 新建 **5 个 PR / 5 条分支**（#10–#14，user=`dependabot[bot]`，形如 `build(deps-dev): bump papaparse from 5.5.3 to 5.7.0`）⇒ **依赖更新不受 `actions/permissions.enabled=false` 约束**；想真正停掉只能**去掉 / 中和 `.github/dependabot.yml`**（代价：与上游内容偏离，每次上游更新该文件都要处理冲突），或**接受它继续开 PR**（PR 通知是**另一种**邮件，与 Actions 邮件来源不同）。dependabot **安全告警 / 自动修复**走 GitHub 自己的服务、**与 Actions 无关** ⇒ 要**单独关**。

**反向印证（时刻值，只对 2026-10-13 的私有态成立）**：该仓的 Dependabot 告警与自动修复**当时**本就处于关闭态（上面原文）⇒ 那些失败邮件**只可能来自 Actions 一个来源**。**转公开后这一前提要重测**——本例 2026-10-14 实测告警仍 404（前提未被掀掉），见下一条。

**公开镜像仓：把私仓翻成公开之前必须先扫历史（2026-10-14 实测）**——公开的是**同一个仓库、同一条生命周期**（推送对齐 → 邮件静音 → 可见性），所以处置写在本节，不另立 skill。

- **扫的是历史，不是工作区**：可见性由**历史**决定，工作区干净 ≠ 历史干净。配方 = `git rev-list --objects --all` 取全部对象 → `git cat-file --batch --buffer` **流式**喂 Python 做**字节精确**扫描（本例 **255,989 blobs / 7.0 GB / 37 s**）。
- **扫描器必须带自测**：先**故意植入一个假 token**，用同一套代码证明它命中（本例自测 `HITS=1`）——**没有自测的"0 命中"不算证据**。
- **范围**：上游历史本就公开，重点是自己新增的路径（本例 `git rev-list upstream/master..master` = **10 commits / 84 files**，路径只有 `dsh-home/`、`dsh-presets/`、`sync/`、`.gitignore`）。但**全量 blob 扫描更快也更兜底，优先用它**。
- **红旗判据**：根级 `cordis.patch.yml`（**脱敏前的明文令牌版本**）在**历史中出现次数必须 = 0** 才算过关（本例实测 0）。工作区里它已被换成 `cordis.patch.redacted.yml`，历史里那条才是真泄漏面。
- **翻开关**：GitHub `PATCH /repos/{o}/{r}`，body `{"private": false}` → **200**，回读 `private=false, visibility=public`；GitCode `PATCH https://api.gitcode.com/api/v5/repos/{o}/{r}`（header `private-token`）+ 同一个 body `{"private": false}` → 本例**首次即 200**；**GitCode 的回读判据用 `public` / `private` 字段**——它的响应里 `visibility` 是空的，**别拿它当判据**。
- **验收必须真匿名**：URL 里**不带 token** + `-c credential.helper=` + `GIT_TERMINAL_PROMPT=0` ⇒ `ls-remote` exit=0 **并且** `clone --depth 1` 真拉下来（本例 GitHub 与 GitCode 各 **15,071 文件**，再抽查已知文件存在）；另加一个**完全不带 `Authorization` 头**的 REST `GET /repos/{o}/{r}` 交叉验证。
- **许可前置**：先确认上游本身公开且许可允许再分发（本例上游 `deepseek-ai/deepseek-harness` 匿名可读、**MIT**、`LICENSE` 首行 `MIT License`）。**上游若是专有代码，公开镜像 = 再分发他人代码。**
- **公开前先想清会露出什么（本例实测会露出的，作检查清单）**：令牌文件的**路径**（`sync/remotes.json`、以及 skill 正文里写的 `D:\key\...` 之类）、旧的 `.bak` 备份里残留的**个人邮箱**、`.anonymous-user-id` 的**遥测 UUID**、网关 `baseURL`。**公开后这些进了历史并被索引缓存，翻回私有 ≠ 收回。**
- **转公开会重新引入噪声面**：依赖图会重跑（本例转公开后 dependabot 立刻又动作）；安全告警**是否**被自动开启已有实测答案（本例：**没有**，转公开后仍 404）⇒ 完整事实与判据见本节 Dependabot 段，别在这里重述。
- **四个坑（都实测）**：① `git log -p <tip>` 会展开**整条祖先链**（本例 21k commits，落盘 1.4 GB 还在涨）⇒ 改 blob 级扫描；② `git log -p <多个 sha 拼成单串>` 报 `fatal: failed to stat '<长串>': Filename too long` ⇒ 传数组或改 blob 级；③ `findstr` 有**行长上限会漏** ⇒ 用 Python 字节流；④ 落盘的 `.diff` 被 pwsh 句柄占用会让 `Remove-Item` 失败（`being used by another process`）⇒ 用完即删或全程流式。

**`.github/dependabot.yml` 已从镜像移除，脚本带"仅此一路径"的自愈补丁（2026-10-14 实测 + 真跑模拟）**——这是本 skill 里**唯一**一处**故意与上游不一致**的地方，**不是**"可以随手改上游文件"的通则。

- **为什么删**：Actions 已关（`actions/permissions` = `{"enabled":false,"sha_pinning_required":false}`），dependabot 版本更新**照样**跑（`2026-10-14T03:06:08Z` 起 3 条 `event=dynamic` run，紧接 **5 个 PR / 5 条分支**，原文见本节 Dependabot 段）⇒ 去掉 `.github/dependabot.yml` 是**唯一**能停掉它的办法，代价是与上游偏离该文件。
- **现状证据**：镜像仓 `master` 已删除该文件（commit `fc26a0f73f80599e2de39844a34fdce3e0c5997b`，GitHub 与 GitCode 两端 `master` 均为此值），**匿名**读取该路径 **404**。
- **自愈补丁的边界（窄闸门，唯一例外）**：`sync-dsh-repos.ps1` 在 `git merge --no-edit upstream/master` 失败后，只问一句"**唯一的 unmerged 路径**是不是 `.github/dependabot.yml`"（`git diff --name-only --diff-filter=U`）；**是** ⇒ `git rm --force` 该文件解掉冲突（保住删除）并**交回原有的 `git add -A` + commit** 收尾（最终**恰好一个合并提交**、工作区干净）；**否则**（别的文件冲突、或"该文件 + 别的文件同时冲突"、或 merge 因非冲突原因失败）⇒ **逐字保持**原来的 `merge --abort` + `exit 4`。
- **实测判据（一次性克隆里真跑打过补丁的逻辑）**：`.github/dependabot.yml` 单点 modify/delete 冲突 ⇒ `exit 0`、日志 `SELF-HEAL:`、`log --oneline -1` 是那条 sync 合并提交（2 个 parent）、`Test-Path` = `False`、`status --porcelain` 空；README 冲突 ⇒ `exit 4`；`.github/dependabot.yml` + README 同时冲突 ⇒ 仍 `exit 4`。
- **别推广**：与上游**逐字节一致仍是默认**。下次真要删/改某个上游文件，必须**同时在脚本里加一个同样窄的闸门**、并把"单点冲突自动解、多点冲突照旧中断"写成可复现判据，别"顺手改文件"了事。

## 5. 边界（不要做什么）

- **不要绕过脚本手动 force push**（`git push --force` / `-f`）。脚本的推送形态是 `HEAD:master`，被拒时先
  `fetch` + `merge` 再推，失败还有 ALERT + `state.json` 留痕；force push 会直接抹掉私仓里另一台机器/另一个
  会话的提交，而且**不留任何记录**，事后无法判断丢了什么。真要强推，先 `git log` 对清两边差异并让人确认。
- **不要把 credential helper 放回来**：不要在脚本的 git 调用里去掉 `-c credential.helper=`，也不要设
  `GIT_ASKPASS` 指向某个命令（实测报 `error: cannot spawn cmd / c exit 1: No such file or directory`）。
  一旦 helper 生效，gitcode.com 会弹 GUI 挂死，计划任务变成"卡住"而不是"失败"。
- **不要把令牌写进 `.git/config`**：不要 `git remote add` 带令牌的 URL、不要
  `git config --global url."https://<token>@...".insteadOf`。脚本故意用内联 URL 推送就是为了这个。
- **不要让任何别的路径当 robocopy 目标**：`/MIR` 删除目标侧多余文件，写错目标 = 删数据。
- **不要在镜像仓里手工改 `dsh-home` / `dsh-presets`**：下次 `/MIR` 会覆盖，改动来源只有 `~/.dsh` 与 preset 源。
- **不要删掉 `cordis.patch.redacted.yml` 的生成逻辑**——根级 `cordis.patch.yml` 里是明文 PAT，
  少了这一步它就会被 `git add -A` 收进提交并推到两个私仓。
- **不要指望脚本注册计划任务**：它只跑同步；计划任务 `DSH-Repo-Sync` 由人注册（命令见 §3）。
- **不要把「私仓天天收到 workflow 失败邮件」当成同步坏了**：那是镜像携带的上游 CI 在跑，与脚本退出码无关 ⇒ 处置见 §4 最后一条。
- **不要为了让 CI 不报错而把 `.github/workflows` 从镜像里剔掉**：那是与上游 merge 的长期冲突源；正解是关 Actions（`PUT .../actions/permissions` `{"enabled": false}`，见 §4）。
- **不要在 DryRun 里找推送结果**：DryRun 不起 git、不推送，`remotes` 全 `fail` 是设计如此，不是失败。

## 6. `sync\remotes.json` 逐字 schema

令牌**只以路径形式**出现在这里，文件里不放任何令牌值。`auth=token-as-user` → `https://<token>@<host><path>`；
`auth=user-token` → `https://<user>:<token>@<host><path>`。`branch` 字段目前只作记录，脚本推送 refspec
固定为 `HEAD:master`（与本地、与上游一致）。

```json
{
  "branch": "master",
  "github": { "url": "https://github.com/EliasKaslan/xmz_dsh.git", "token_file": "D:\\key\\github_PTA.txt", "auth": "token-as-user", "user": "" },
  "gitcode": { "url": "https://gitcode.com/EliasKaslan/xmz_dsh.git", "token_file": "D:\\key\\gitcode_访问令牌_xmz_agent用.txt", "auth": "user-token", "user": "EliasKaslan" }
}
```
