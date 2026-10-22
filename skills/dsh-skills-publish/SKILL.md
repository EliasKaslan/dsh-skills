---
name: dsh-skills-publish
description: 把本机 ~/.dsh/skills 的全部 skill 每天凌晨 2 点发布到 GitCode 公开仓 EliasKaslan/dsh-skills——脚本 publish-dsh-skills.ps1 先快照再扫活密钥，然后提交 main 并让当日 YYYY-MM-DD 分支与 main 指向同一 commit；计划任务 DSH-Skills-Publish，退出码 0/3/4/5/6/7/8，状态落 .skill-publish\state.json 与 ALERT.md。适用于"把 skill 发到 GitCode / 建个公开 skill 仓 / 每天自动同步 skill / 今天的日期分支建了吗 / main 和日期分支不一致 / 发布脚本报错 / 手动跑一次 skill 发布 / 停掉每日发布任务"。不适用：DSH 配置与私仓同步 → 用 `dsh-repo-sync`。
whenToUse: 发布 skill 到公开仓、排查每日同步失败、改发布范围或计划任务时用。模型看不到本节。
---

# dsh-skills-publish：本机 skill → GitCode 公开仓（每日 02:00）

把 `~\.dsh\skills` 整棵树快照到一个**公开**仓库（`https://gitcode.com/EliasKaslan/dsh-skills`）：
每天凌晨 2:00 建/更新一个以日期命名的分支，并让 `main` 与它指向**同一个 commit**（内容逐字节一致）。
公开仓任何人都能 clone，但只有仓库所有者能推送。

## 何时调用

**加载本 skill 当：**
- 用户说「**把 skill 发到 GitCode**」「建个公开的 skill 仓」「让所有人都能下载我的 skill」。
- 用户问「**今天的日期分支建了吗**」「main 和日期分支是不是一致」「昨天同步成功了吗」。
- `D:\repos\dsh-skills\` 或 `.skill-publish\ALERT.md` 出现异常；计划任务 `DSH-Skills-Publish` 报错。
- 要改发布范围（排除项）、换仓、换令牌文件、暂停/恢复每日发布。

**不要用本 skill（转交）：**
- 同步 DSH 配置 / preset 到**私有**镜像仓（GitHub + GitCode 双推）→ 用 `dsh-repo-sync`。
- 向 GitCode 社区仓提 PR / 判门禁标签 → 用 `gitcode-pr-flow`。
- 本机 PowerShell 的编码 / 计数 / PS7 语法坑 → 用 `pwsh-on-windows`。
- skill frontmatter 与 description 怎么写 → 用 `dsh-skill-authoring`。

**前置**：`D:\key\gitcode_访问令牌_xmz_agent用.txt` 里的 GitCode classic PAT 有 `repo` 写权限；目标仓已建好（公开、`main` 为默认分支、协作者只有本人）。 ／ **后继**：真跑一次，读 `state.json` 与远端 `ls-remote` 双确认。

## 1. 机制与绝对路径

| 项 | 值 |
| --- | --- |
| 发布脚本 | `C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1` |
| 每日入口（ASCII） | `C:\Users\admin\.dsh\skills\dsh-skills-publish\run_daily.cmd` |
| 本地配置（**不发布**） | `C:\Users\admin\.dsh\.skill-publish\publish.config.json` |
| 运行状态（**不发布**） | `C:\Users\admin\.dsh\.skill-publish\state.json` |
| 日志（按月） | `C:\Users\admin\.dsh\.skill-publish\logs\publish-YYYY-MM.log` |
| 告警（**只在失败时存在**） | `C:\Users\admin\.dsh\.skill-publish\ALERT.md` |
| 工作副本（镜像仓） | `D:\repos\dsh-skills` |
| 远端 | `https://gitcode.com/EliasKaslan/dsh-skills.git` |
| 计划任务 | `DSH-Skills-Publish`（每天 02:00） |

执行顺序（脚本内固定）：

1. **快照**——`robocopy <skills> <work_repo>\skills /MIR`，排除 `.git` / `node_modules` / `__pycache__` / `.venv`，按文件名排除 `credentials.txt`、`*.key`、`*.pem`、`*.p12`、`*.pfx`、`*.token`、`.env*` 等。`/MIR` 会删除目标侧多余文件，所以目标只能是镜像仓的 `skills` 子目录。**`/MIR` 也意味着源侧一次瞬时缺失就会从公开仓删掉内容**，因此脚本带缩水护栏：快照为 0 个 skill，或比上次 `state.json` 的 `skill_count` 掉超过一半（且上次 ≥10）时 **exit 5 拒绝发布**；确属大清理时加 `-AllowBigShrink`。
2. **生成**——每次重写 `README.md`（skill 清单表）、`index.json`（机器可读清单）、`.gitattributes`（`* -text`，禁止 CRLF 归一化）。三者都是**确定性**的：内容不变就逐字节不变，不会为了"跑过"产生空提交。
3. **密钥扫描**——把 `token_file` 与 `extra_secret_files` 里的每个字符串读进内存（**不落盘、不打印**），在快照树上做字面量匹配；另扫 `ghp_` / `github_pat_` / `-----BEGIN ... PRIVATE KEY-----` / `AKIA` 四类模式。命中即 **exit 4**，绝不推送。
4. **提交与推送**——`main` 与 `<YYYY-MM-DD>` 各推一次，refspec 是 `HEAD:refs/heads/<branch>`。**clone 走公开 URL，令牌只出现在推送的内联 URL 里**（`<user>:<token>@`，GitCode 只认这种形态）；脚本每次启动都会检查 `remote.origin.url`，一旦发现带凭据就 `set-url` 洗掉，令牌永不进 `.git/config`。
5. **验收**——`git ls-remote` 回读两个 ref，断言 `main` == 当日分支 == 本地 HEAD，否则 exit 7。

## 2. 可直接复制的命令

```powershell
# 安全预演（只写 %TEMP%，不碰镜像仓、不起 git）
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\admin\.dsh\skills\dsh-skills-publish\publish-dsh-skills.ps1" -DryRun

# 真跑（正常路径）
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

# 看远端两个 ref 是否同一 sha（把 <token> 换成真实令牌再跑，别把输出贴出去）
git -c credential.helper= ls-remote "https://EliasKaslan:<token>@gitcode.com/EliasKaslan/dsh-skills.git" refs/heads/main refs/heads/2026-10-22

# 立即触发一次计划任务（最便宜的真实凭据与权限验证）
schtasks /Run /TN "DSH-Skills-Publish"
```

注册 / 恢复计划任务（本 skill 不代注册，由人决定）：

```powershell
$act = New-ScheduledTaskAction -Execute 'C:\Users\admin\.dsh\skills\dsh-skills-publish\run_daily.cmd'
$trg = New-ScheduledTaskTrigger -Daily -At '02:00'
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$prn = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'DSH-Skills-Publish' -Action $act -Trigger $trg -Settings $set -Principal $prn -Force
```

## 3. 退出码与判读

| 码 | 含义 | 先看哪里 |
| --- | --- | --- |
| 0 | 推送成功，或 `NO_CHANGE`（内容没变，两个 ref 已在同一 commit） | `state.json` 的 `changed` / `main_remote_sha` |
| 3 | 环境或配置错误：缺 `source_dir` / `token_file`、工作副本不是 git 仓、分支名非法 | 日志里的 `not found` / `not a git repository` |
| 4 | 密钥扫描命中：快照里出现活令牌字面量或私钥块 | 日志里的 `SECRET HIT:`（只给文件与模式，不给值） |
| 5 | 快照或提交失败：`robocopy rc>=8`、`git add/commit` 非 0，或 skill 数异常缩水被护栏拦下 | 日志里的 `robocopy rc=` / `git commit failed` / `refusing to publish` |
| 6 | 推送失败：鉴权、网络、non-fast-forward | 日志里的 `push ... failed`（输出已脱敏） |
| 7 | 推送后复核不一致：两个 ref 缺一个，或 sha 不相等 | 日志里的 `ref mismatch:` |
| 8 | 未预期异常 | 日志里的 `unexpected:` |

**判完成只认产物，不看计划任务的 `Last Result`**：`state.json` 的 `exit_code` + 当月日志尾部 + `ALERT.md` 是否存在（存在 = 上次失败，成功时脚本会删掉它）。

## 4. 验收口径（三条独立证据）

1. **远端同一 sha**：`ls-remote` 里 `refs/heads/main` 与 `refs/heads/<今天>` 相等，且等于 `state.json` 的 `head_sha`。
2. **匿名可读**：URL 不带 token、`-c credential.helper=`、`GIT_TERMINAL_PROMPT=0` 下 `git clone --depth 1` 成功，且 `skills/<某 skill>/SKILL.md` 在克隆里存在。
   实测计数：clone 下来的 skill 目录数应等于 `state.json` 的 `skill_count`（本轮实测 **35**，会随 skill 增删变化），且克隆里 `credentials.txt` 命中数为 **0**。
3. **匿名不可写**：同样的匿名 URL 做 `git push --dry-run` 必须失败——本机实测是 `fatal: could not read Username for 'https://gitcode.com': terminal prompts disabled`（exit 128）。
   **别把 403 之外的形态当通过** —— 超时、连接失败都不算负控成立；再叠加一条平台侧证据：`GET /repos/:owner/:repo/collaborators` 只有本人一个 `access_level=50` 的 Owner。

## 5. 排障

- **exit 6 + `Authentication failed` / 403**：先核 `publish.config.json` 的 `token_file` 路径与令牌是否过期；GitCode 传输层只认 `https://<user>:<token>@`，把 token 当用户名必失败（`could not read Password`）。
- **exit 6 + `non-fast-forward` / `rejected`**：远端有本地没有的提交（例如网页端直接改过）。本脚本**不自动强推**；先 `git -C D:\repos\dsh-skills fetch` 看清差异，人工对齐后再跑。
- **exit 4**：说明 skill 目录里出现了真实凭据。把该文件加进 `/XF` 排除清单（脚本里的 robocopy 行）或从 skill 正文里删掉明文，再跑一次 `-DryRun` 复核。
- **exit 5 + `refusing to publish`**：源目录 `~\.dsh\skills` 那一刻只剩不到一半 skill（常见于另一个进程正在合并 / 重建 skill 目录）。等源树稳定后重跑；若确是有意大清理，加 `-AllowBigShrink`。
- **日期分支名撞车 / 补跑历史**：`-DateStamp 2026-10-21` 会把某个历史日期分支快进到当前内容，**不是**重建当时的内容——要真历史只能靠每天按时跑。
- **同日多次运行**：内容变了就追加提交，当日分支随之前进；内容没变则 `NO_CHANGE`，两个 ref 原地不动。
- **手动删远端日期分支**：`git -C D:\repos\dsh-skills push <authUrl> --delete <YYYY-MM-DD>`；删完 `main` 不受影响。
- **每日任务没跑**：`Get-ScheduledTask DSH-Skills-Publish` 看 `State`；`Last Result` 不能当判据。机器 02:00 关机时靠 `-StartWhenAvailable` 在下次可用时补跑；`Interactive` 登录类型要求该用户已登录。
- **想立刻回滚内容**：日期分支是历史快照，`git -C D:\repos\dsh-skills reset --hard <旧 sha>` 后再 `-NoPush` 检查，然后真跑覆盖 `main`（**只在自己的镜像仓里操作**，不要在远端改写 `main` 历史）。
- **隐私提醒**：仓库是公开的，skill 正文里的本机路径（`D:\key\...`、内网 IP）会一起公开。要收口就先改 skill 正文，再跑发布。

## 6. 边界（不要做什么）

- **不要**把 `credentials.txt`、`.secrets`、`*.token` 从排除清单里拿掉；公开仓一旦推上去，历史里删不干净。
- **不要**为了"每天都有提交"而加空提交：内容没变时 `NO_CHANGE` 是正确结果，日期分支照样建。
- **不要**把令牌写进 `publish.config.json`、`.git/config` 或任何入库文件——配置里只放**令牌文件路径**。
- **不要**手工改 `D:\repos\dsh-skills\skills\**`：下次 `/MIR` 会覆盖；改动来源只有 `~\.dsh\skills`。
- **不要**在远端对 `main` 做 `--force` 推送；日期分支是追加式的，`main` 应始终是它的超集。
