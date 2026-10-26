---
name: dsh-skills-publish
description: 把本机 ~/.dsh/skills 的全部 skill 每天凌晨 2 点同步发布到 GitCode 与 GitHub 两个公开仓 EliasKaslan/dsh-skills——脚本 publish-dsh-skills.ps1 先快照再扫活密钥，再对每个站点提交 main 并让当日 YYYY-MM-DD 分支与 main 指向同一 commit，每个站点只保留最近 15 个日期分支；计划任务 DSH-Skills-Publish，退出码 0/3/4/5/6/7/8，状态落 .skill-publish\state.json 与 ALERT.md。适用于"把 skill 发到 GitCode / 同步一份到 GitHub / 建个公开 skill 仓 / 每天自动同步 skill / 今天的日期分支建了吗 / main 和日期分支不一致 / 分支太多了怎么清理 / 发布脚本报错 / 手动跑一次 skill 发布 / 停掉每日发布任务 / 换台电脑怎么恢复这个任务"。不适用：DSH 配置与私仓同步 → 用 `dsh-repo-sync`。
whenToUse: 发布 skill 到公开仓、排查每日同步失败、增减镜像站点或计划任务时用。模型看不到本节。
---

# dsh-skills-publish：本机 skill → GitCode + GitHub 公开仓（每日 02:00）

把 `~\.dsh\skills` 整棵树快照后**同一份 commit**推到两个**公开**仓库：

- GitCode `https://gitcode.com/EliasKaslan/dsh-skills`
- GitHub `https://github.com/EliasKaslan/dsh-skills`

每天凌晨 2:00 建/更新一个以日期命名的分支，并让每个站点的 `main` 与它指向**同一个 commit**（内容逐字节一致）。
公开仓任何人都能 clone，但只有仓库所有者能推送。

## 何时调用

**加载本 skill 当：**
- 用户说「**把 skill 发到 GitCode / GitHub**」「建个公开的 skill 仓」「让所有人都能下载我的 skill」。
- 用户问「**今天的日期分支建了吗**」「main 和日期分支是不是一致」「昨天同步成功了吗」「GitHub 上那份同步了吗」。
- `D:\repos\dsh-skills\` 或 `.skill-publish\ALERT.md` 出现异常；计划任务 `DSH-Skills-Publish` 报错。
- 要改发布范围（排除项）、**增减镜像站点**、换仓、换令牌文件、暂停/恢复每日发布。

**不要用本 skill（转交）：**
- 同步 DSH 配置 / preset 到**私有**镜像仓 → 用 `dsh-repo-sync`。
- 向 GitCode / GitHub 社区仓提 PR、判门禁标签 → 用 `gitcode-pr-flow` / `github-pr-flow`。
- 本机 PowerShell 的编码 / 计数 / PS7 语法坑 → 用 `pwsh-on-windows`。
- skill frontmatter 与 description 怎么写 → 用 `dsh-skill-authoring`。

**前置**：两个令牌文件都在、都有对应仓的写权限——GitCode classic PAT（`repo`）与 GitHub classic PAT（`repo`）；两个目标仓已建好（公开、`main` 为默认分支、协作者只有本人）。 ／ **后继**：真跑一次，读 `state.json` 与两个站点的 `ls-remote` 三方确认。

## 1. 机制与绝对路径

| 项 | 值 |
| --- | --- |
| 发布脚本 | `C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1` |
| 每日入口（ASCII） | `C:\Users\admin\.dsh\skills\dsh-skills-publish\run_daily.cmd` |
| 任务注册（自动提权） | `C:\Users\admin\.dsh\skills\dsh-skills-publish\install-task.ps1` |
| 本地配置（**不发布**） | `C:\Users\admin\.dsh\.skill-publish\publish.config.json` |
| 运行状态（**不发布**） | `C:\Users\admin\.dsh\.skill-publish\state.json` |
| 日志（按月） | `C:\Users\admin\.dsh\.skill-publish\logs\publish-YYYY-MM.log` |
| 告警（**只在失败时存在**） | `C:\Users\admin\.dsh\.skill-publish\ALERT.md` |
| 工作副本（镜像仓） | `D:\repos\dsh-skills` |
| GitCode 远端 / 令牌 | `https://gitcode.com/EliasKaslan/dsh-skills.git` ／ `D:\key\gitcode_访问令牌_xmz_agent用.txt` |
| GitHub 远端 / 令牌 | `https://github.com/EliasKaslan/dsh-skills.git` ／ `D:\key\github_PTA.txt` |
| 计划任务 | `DSH-Skills-Publish`（每天 02:00，**S4U + 唤醒定时器**，不要求已登录） |

站点是一个数组：`publish.config.json` 的 `targets[]`，每项含 `id` / `name` / `remote_url` / `user` / `token_file` / `branch_main` / `keep_date_branches`。
**加第三个站点 = 往数组里加一项**，脚本与计划任务都不用改；`targets` 缺失时回退成顶层的单站点老字段。

执行顺序（脚本内固定）：

1. **快照**——`robocopy <skills> <work_repo>\skills /MIR`，排除 `.git` / `node_modules` / `__pycache__` / `.venv`，按文件名排除 `credentials.txt`、`*.key`、`*.pem`、`*.p12`、`*.pfx`、`*.token`、`.env*` 等。`/MIR` 会删除目标侧多余文件，所以目标只能是镜像仓的 `skills` 子目录。**`/MIR` 也意味着源侧一次瞬时缺失就会从公开仓删掉内容**，因此脚本带缩水护栏：快照为 0 个 skill，或比上次 `state.json` 的 `skill_count` 掉超过一半（且上次 ≥10）时 **exit 5 拒绝发布**；确属大清理时加 `-AllowBigShrink`。
2. **生成**——每次重写 `README.md`（skill 清单表 + 站点表）、`index.json`（机器可读清单）、`.gitattributes`（`* -text`）。三者都是**确定性**的：内容不变就逐字节不变，不会为了"跑过"产生空提交。
3. **密钥扫描**——把**每个站点**的 `token_file` 与 `extra_secret_files` 里的每个字符串读进内存（**不落盘、不打印**），在快照树上做字面量匹配；另扫 `ghp_` / `github_pat_` / `-----BEGIN ... PRIVATE KEY-----` / `AKIA` 四类模式。命中即 **exit 4**，绝不推送。
4. **提交**——一次 `git add -A` + 一次 commit；两个站点共用这个 commit（所以两边 sha 天然相同）。
5. **逐站点推送**——对 `targets[]` 里每一项依次：`main` 推一次、`<YYYY-MM-DD>` 推一次，refspec 是 `HEAD:refs/heads/<branch>`。**clone 走公开 URL，令牌只出现在推送的内联 URL 里**（`<user>:<token>@`）；脚本每次启动都会检查 `remote.origin.url`，一旦发现带凭据就 `set-url` 洗掉，令牌永不进 `.git/config`。
6. **逐站点验收**——`git ls-remote` 回读该站点的两个 ref，断言 `main` == 当日分支 == 本地 HEAD，否则 exit 7（报错带 `[站点 id]` 前缀）。
7. **逐站点保留期清理**——再拉一次 `ls-remote --heads`，**只挑名字能被 `date_format` 成功解析的分支**（该站点的 `main` 与任何非日期名分支一律跳过），按日期倒序保留最新 `keep_date_branches` 个（默认 **15**），更早的用一次 `git push <url> --delete b1 b2 …` 批量删除。删除失败只记 WARN + `state.json.targets[].prune_error`，不改变本次同步的成败（下次运行会重试）。

## 2. 可直接复制的命令

```powershell
# 安全预演（只写 %TEMP%，不碰镜像仓、不起 git）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1" -DryRun

# 真跑（正常路径，两个站点都推）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1"

# 只提交不推送（排查用）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1" -NoPush

# 指定日期分支（补跑某天）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1" -DateStamp 2026-10-21

# 确属大规模清理 skill，绕过缩水护栏
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1" -AllowBigShrink

# 读状态 / 告警
Get-Content "C:\Users\admin\.dsh\.skill-publish\state.json" -Raw
if (Test-Path "C:\Users\admin\.dsh\.skill-publish\ALERT.md") { Get-Content "C:\Users\admin\.dsh\.skill-publish\ALERT.md" -Raw } else { "no alert" }

# 两个站点各自的 sha 与清理结果（一屏看完）
(Get-Content "C:\Users\admin\.dsh\.skill-publish\state.json" -Raw | ConvertFrom-Json).targets |
    Select-Object id, main_sha, date_sha, branch_count_after, prune_error

# 匿名看两个站点分支分布（日期分支应 ≤ 15，另加 main）
git -c credential.helper= ls-remote --heads https://gitcode.com/EliasKaslan/dsh-skills.git
git -c credential.helper= ls-remote --heads https://github.com/EliasKaslan/dsh-skills.git

# 立即触发一次计划任务（最便宜的真实凭据与权限验证）
schtasks /Run /TN "DSH-Skills-Publish"
```

注册 / 恢复计划任务（本 skill 不代注册，由人决定）。
**S4U 注册必须提权**：非管理员身份执行 `Set-ScheduledTask -Principal` 会直接 `Access is denied`；本机 `ConsentPromptBehaviorAdmin=0`，`Start-Process -Verb RunAs` 静默提权、不弹 UAC。

```powershell
$act = New-ScheduledTaskAction -Execute 'C:\Users\admin\.dsh\skills\dsh-skills-publish\run_daily.cmd'
$trg = New-ScheduledTaskTrigger -Daily -At '02:00'
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName 'DSH-Skills-Publish' -Action $act -Trigger $trg -Settings $set -Principal $prn -Force
```

改完 principal **必须实跑一次**：S4U 跑在 session 0、不加载用户配置文件，PATH / 令牌文件 / git 都要现场确认。
`schtasks /Run /TN DSH-Skills-Publish` 后读 `state.json` 的 `exit_code` 与日志尾部。

## 3. 退出码与判读

| 码 | 含义 | 先看哪里 |
| --- | --- | --- |
| 0 | 所有站点推送成功，或 `NO_CHANGE`（内容没变，各站点 ref 已在同一 commit） | `state.json` 的 `changed` 与 `targets[].main_sha` |
| 3 | 环境或配置错误：缺 `source_dir`、某站点缺 `remote_url` / `token_file`、工作副本不是 git 仓、分支名非法 | 日志里的 `target <id>` / `not found` / `not a git repository` |
| 4 | 密钥扫描命中：快照里出现活令牌字面量或私钥块 | 日志里的 `SECRET HIT:`（只给文件与模式，不给值） |
| 5 | 快照或提交失败：`robocopy rc>=8`、`git add/commit` 非 0，或 skill 数异常缩水被护栏拦下 | 日志里的 `robocopy rc=` / `git commit failed` / `refusing to publish` |
| 6 | 某站点推送失败：鉴权、网络、non-fast-forward | 日志里的 `[<id>] push ... failed`（输出已脱敏） |
| 7 | 某站点推送后复核不一致：两个 ref 缺一个，或 sha 不相等 | 日志里的 `[<id>] ref mismatch:` |
| 8 | 未预期异常 | 日志里的 `unexpected:` |

**判完成只认产物，不看计划任务的 `Last Result`**：`state.json` 的 `exit_code` + 当月日志尾部 + `ALERT.md` 是否存在（存在 = 上次失败，成功时脚本会删掉它）。
**站点是串行推的**：第一个站点失败就会 `Fail 6` 中断，**后面的站点这次不会推**；修好后重跑是幂等的（已成功的站点会 `Everything up-to-date`）。

## 4. 验收口径（每个站点三条独立证据）

1. **两侧同一 sha**：两个站点 `ls-remote` 里 `refs/heads/main` 与 `refs/heads/<今天>` 相等，且等于 `state.json` 的 `head_sha`，也等于 `targets[].main_sha`。
2. **匿名可读**：URL 不带 token、`-c credential.helper=`、`GIT_TERMINAL_PROMPT=0` 下 `git clone --depth 1` 成功，且 `skills/<某 skill>/SKILL.md` 在克隆里存在。
   实测计数：clone 下来的 skill 目录数应等于 `state.json` 的 `skill_count`（本轮实测 **35**，会随 skill 增删变化），且克隆里 `credentials.txt` 命中数为 **0**。
3. **匿名不可写**：带一个**故意错误**的令牌去 push，必须拿到服务端显式拒绝——GitHub 实测 `remote: Invalid username or token. Password authentication is not supported for Git operations.` + `fatal: Authentication failed`（exit 128）；GitCode 实测匿名 push 停在 `fatal: could not read Username`。
   **别把超时 / 连接失败当负控成立**；再叠加平台侧证据：GitHub `GET /repos/:owner/:repo/collaborators` 只有本人 1 个，GitCode `access_level=50` 的 Owner 也只有本人。

## 5. 排障

- **exit 6 + `Authentication failed` / 403**：先核该站点 `token_file` 路径与令牌是否过期。GitCode 传输层只认 `https://<user>:<token>@`；GitHub 自 2021 起**不再支持密码认证**，令牌必须当密码用，网页端改过密码也可能顺手吊销 classic PAT。
- **exit 6 只提到一个站点**：说明它之前的站点已推成功、它之后的站点没动。修好后直接重跑，已成功的站点是 no-op。
- **exit 6 + `non-fast-forward` / `rejected`**：远端有本地没有的提交（例如网页端直接改过）。本脚本**不自动强推**；先 `git -C D:\repos\dsh-skills fetch` 看清差异，人工对齐后再跑。
- **exit 4**：说明 skill 目录里出现了真实凭据。把该文件加进 `/XF` 排除清单（脚本里的 robocopy 行）或从 skill 正文里删掉明文，再跑一次 `-DryRun` 复核。
- **exit 5 + `refusing to publish`**：源目录 `~\.dsh\skills` 那一刻只剩不到一半 skill（常见于另一个进程正在合并 / 重建 skill 目录）。等源树稳定后重跑；若确是有意大清理，加 `-AllowBigShrink`。
- **某站点日期分支超过 15 个**：先看 `state.json.targets[]` 里该站点的 `prune_error`（删除失败只 WARN，不影响本次同步成败），再手工补删：
  `git -C D:\repos\dsh-skills push <authUrl> --delete 2020-01-01 2020-01-02`。删除只按**日期名**匹配，`main` 和 `feature-x` 这类非日期分支永远不会被脚本碰。
- **日期分支名撞车 / 补跑历史**：`-DateStamp 2026-10-21` 会把某个历史日期分支快进到当前内容，**不是**重建当时的内容——要真历史只能靠每天按时跑。
- **同日多次运行**：内容变了就追加提交，当日分支随之前进；内容没变则 `NO_CHANGE`，各站点 ref 原地不动。
- **手动删某站点日期分支**：`git -C D:\repos\dsh-skills push <authUrl> --delete <YYYY-MM-DD>`；删完 `main` 不受影响。
- **新增站点**：往 `targets[]` 加一项（先手工在平台建好空仓、确认是公开且默认分支 `main`），跑一次即可；第一个 `targets[0]` 还兼任 `work_repo` 的 clone 来源（仓已存在时不 clone）。
- **每日任务没跑**：`Get-ScheduledTask DSH-Skills-Publish` 看 `State`；`Last Result` 不能当判据。任务是 **S4U**（`schtasks /query /v` 显示 `Logon Mode: Interactive/Background`），**不需要任何人登录**；`WakeToRun=True` 且 `powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE` 的 AC 索引为 1 时会自唤醒睡眠机器。**断电 / 关机**仍跑不了，靠 `-StartWhenAvailable` 在下次开机后补跑一次，日期分支名 = 补跑当天。
- **想把任务改回"仅登录时运行"**：同一段注册脚本把 `-LogonType S4U` 换成 `Interactive`（这一步同样要提权）。改完立刻 `schtasks /Run` 验证。
- **空密码账户**：`LimitBlankPasswordUse=1` 时 `-LogonType Password` 存不了凭据，S4U 是唯一既不需要密码、又不需要登录的方式。
- **想立刻回滚内容**：日期分支是历史快照，`git -C D:\repos\dsh-skills reset --hard <旧 sha>` 后再 `-NoPush` 检查，然后真跑覆盖各站点 `main`（**只在自己的镜像仓里操作**，不要在远端改写 `main` 历史）。
- **隐私提醒**：两个仓都是公开的，skill 正文里的本机路径（`D:\key\...`、内网 IP）会一起公开。要收口就先改 skill 正文，再跑发布。

## 6. 换机 / 重装：仓库就是工具链

`skills/dsh-skills-publish/` 里是这个任务的**全部代码**：发布脚本、每日入口、任务注册脚本、README 模板、本手册。
任务注册信息（含 `state.json`、日志）属于本机、不在仓里；换机器用一条命令重建。

仓库里**故意没有**的三样，必须人工补：

| 缺什么 | 为什么不在仓里 | 怎么补 |
| --- | --- | --- |
| 两个令牌文件 | 是活凭据 | 拷到新机器 `D:\key\`，或重新签发后改配置里的路径 |
| `.skill-publish\publish.config.json` | 含本机路径与站点表 | 复制 `publish.config.example.json` 过去，填 `user` / `remote_url` / `token_file` |
| 计划任务 `DSH-Skills-Publish` | 注册在**本机**计划库里 | 跑 `install-task.ps1` 重建（S4U + 唤醒，脚本自己提权） |

新机器落地顺序：

1. 装 Git，且要落在**机器级** PATH（本机是 `D:\tools\Git\cmd`）——S4U 不加载用户 PATH。
2. `git clone https://github.com/EliasKaslan/dsh-skills.git D:\repos\dsh-skills`（GitCode 同）。
3. 把 `D:\repos\dsh-skills\skills\dsh-skills-publish` 复制到 `%USERPROFILE%\.dsh\skills\dsh-skills-publish`。
4. 建 `publish.config.json`（见上表第 2 行），令牌文件就位。
5. 提权跑注册并立刻验证一次：
   `powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\.dsh\skills\dsh-skills-publish\install-task.ps1" -RunNow`
6. 读 `state.json` 的 `exit_code` 与两个站点 `ls-remote`，三处 sha 必须相同。

`install-task.ps1` 的开关：`-At 02:00` 改时间、`-RunNow` 注册后立即跑一次、`-ExportPath <path>` 导出一份任务 XML 留档、`-Uninstall` 注销任务。
导出的 XML 里带本机账户名（`<UserId>`），**不要直接 import 到新机器**（SID / 计算机名不同会失败）——用脚本重建。

整套脚本**不绑定用户名与路径**：`run_daily.cmd` 用 `%~dp0` 定位同目录的发布脚本，`install-task.ps1` 按自身位置生成任务动作路径，所以 skill 文件夹放在任意用户名 / 任意盘符下都能跑；要改的只有 `publish.config.json` 里的 `source_dir` / `work_repo`。

## 7. 边界（不要做什么）

- **不要**把 `credentials.txt`、`.secrets`、`*.token` 从排除清单里拿掉；公开仓一旦推上去，历史里删不干净。
- **不要**为了"每天都有提交"而加空提交：内容没变时 `NO_CHANGE` 是正确结果，日期分支照样建。
- **不要**把令牌写进 `publish.config.json`、`.git/config` 或任何入库文件——配置里只放**令牌文件路径**。
- **不要**把两个站点的 `remote_url` 写成同一个仓（会把内容互推、历史互相覆盖）；每个站点必须是独立的空仓。
- **不要**手工改 `D:\repos\dsh-skills\skills\**`：下次 `/MIR` 会覆盖；改动来源只有 `~\.dsh\skills`。
- **不要**在远端对 `main` 做 `--force` 推送；日期分支是追加式的，`main` 应始终是它的超集。
