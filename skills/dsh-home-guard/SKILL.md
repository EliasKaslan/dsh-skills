---
name: dsh-home-guard
description: 保护 ~/.dsh 不被误删：分钟快照 + 外置裸库 + 哨兵自愈。适用于"防止 agent 删 .dsh / .dsh 被清空了怎么救 / 会话日志丢了 / 想装看门狗 / 恢复后会话变少"。
whenToUse: 模型看不到本节。用户抱怨 .dsh 被删 / 要保护 / 会话丢了 / 要装看门狗时加载；改 DSH 分层与 skill 契约不在此。
---

# DSH home 保护：让 `~/.dsh` 删了也能长回来

**核心结论**：在"agent 要完全权限、用户不审批"的前提下，**防删是做不到的**——任何工具都能被同权限的 agent 一起 `RM` 掉，而 ACL 拒绝位能被 `icacls` 自解。能做的是把"删除"变成**分钟级可逆的事件**：不拦截，只保证还原。所以本机制的**判据不是"删不掉"，而是"删掉后 N 分钟内内容逐字节回来"**。

## 何时调用

**加载本 skill 当：**
- 用户说"agent 把我 `.dsh` 删了 / 保护一下我 C 盘的 .dsh / 装个看门狗 / 会话日志丢了能救吗"，或你要在 `~/.dsh` 之外落一套快照 + 自愈。
- 已经装了 `dsh_guard.py`，要调阈值、加 `keep` 白名单、上/撤 ACL 减速带、从金库恢复。
- 看到 `D:\dsh-vault\logs\incidents\` 里出现新证据文件。

**不要用本 skill（转交）：**
- 改 `AGENTS.md` / skills / preset / `cordis.patch.yml` 的生效与回滚规则 → `dsh-agent-customization`。
- 恢复 `~/.dsh` 后会话列表变少、`session.vN` 与 header 版本段对不上、多帧 zstd 怎么读写 → `dsh-agent-customization`（"恢复 DSH home"一节，单一归属在那里，本 skill 不复制）。
- 新建/改写 SKILL.md 的 frontmatter → `dsh-skill-authoring`。

**前置**：`git` + `python`（本机 Python 3.12 带 `yaml` / `zstandard`），且**看门狗代码与备份数据都不能放在 `~/.dsh` 里**。 ／ **后继**：装完跑一次 `selftest.py` 事故演练，再按第 5 节验证"真删了能回来"。

## 1. 四层机制与它们各自的失效面

| 层 | 做法 | 挡住什么 | 挡不住什么 |
|---|---|---|---|
| **L1 分钟级 git 快照** | `~/.dsh` 是 git worktree，每 2 分钟 `add -A` + commit，push 到 `D:\dsh-vault\dsh-config.git`（裸库） | 配置类（AGENTS.md / skills / presets / profiles / storages）任意删改，最坏丢 2 分钟 | `.git` 在 `.dsh` 里，整棵树被删时历史一起没 → 靠裸库 |
| **L2 目录快照** | 每 30 分钟 `robocopy /E` `sessions/` `attachments/` `storages/` 到 `D:\dsh-vault\snapshots\<ts>\`，保留 24 份（12 小时）；另存一份受跟踪配置到 `<ts>\config\`，凭据到 `vault\secrets\<ts>\` | 会话日志这种二进制大户（不适合进 git） | 最坏丢 30 分钟 |
| **L3 自愈** | 哨兵（AGENTS.md / 根 patch / `skills` / `.agent-presets`）+ 阈值（≥8 个受跟踪文件消失）+ sessions 文件数掉到 60% 以下 → 自动 checkout / 从裸库克隆 | 真实事故形态（`rm -rf ~/.dsh`） | 有人故意慢慢删（每小时 1 个） |
| **L4 ACL 减速带**（默认关） | 根目录 deny `DELETE`，关键项 deny `(OI)(CI)(DE,DC)` | 手滑 `rm -rf` / `Remove-Item -Recurse` 当场报错，抢时间 | agent 有 `WRITE_DAC`，一条 `icacls /remove:d` 就能解；**原子保存的编辑器会存盘失败** |

**为什么不在 DSH 里做拦截**：拦在 `write`/`pwsh` 工具层需要解析任意命令字符串（`python -c "shutil.rmtree(...)"`、`git clean -xfd`、`robocopy /MIR` 都绕得过），既不可靠，又把"无审批"变成"有条件通过"。**权限不动，保障换到事后。**

## 2. 文件布局（代码与数据都在 `.dsh` 之外）

```
D:\workspace\agent\dsh-guard\
  dsh_guard.py        主工具（init/run/snapshot/bulk/heal/restore/verify/status/log/keep/lock/selfcheck）
  selftest.py         事故演练：只在 D:\dsh-guard-lab 里真删文件
D:\dsh-vault\
  dsh-config.git\     ~/.dsh 配置的裸库（push 目标，HEAD 已指向 main）
  snapshots\<ts>\     sessions / attachments / storages 目录快照（轮转 24 份）
  logs\guard.log      事件流（含 ALERT），>4MB 轮转
  logs\incidents\     每次事故的证据 JSON（删了什么、判据、当时 sessions 计数）
  state.json          阈值/间隔/keep 白名单/恢复历史/临时解锁截止时间
```

**这条是血证级的**：本机原有的 `DSH-Repo-Sync`（已 Disabled）与 `DSH-Skills-Publish` 两个计划任务，`/tr` 都指向 `C:\Users\admin\.dsh\skills\<name>\run_daily.cmd`——**那两个脚本今天都不存在了**。看门狗把脚本放在被保护目录里，`.dsh` 一没，看门狗自己也没了（`dsh_guard.py` 的任务结果仍是 0，因为任务连脚本都没找到）。⇒ **代码、备份、日志、状态，一律不许住在被保护的目录里。**

## 3. 命令表（全部无交互，可进计划任务）

```powershell
python D:\workspace\agent\dsh-guard\dsh_guard.py init --bulk   # 一次性：建仓 + 裸库 + 首份目录快照
python D:\workspace\agent\dsh-guard\dsh_guard.py run           # 计划任务入口：heal → snapshot → bulk → relock
python D:\workspace\agent\dsh-guard\dsh_guard.py status        # 看 last_run / commits / 快照份数 / keep 数
python D:\workspace\agent\dsh-guard\dsh_guard.py log -n 30     # 看 ALERT 与 notice
python D:\workspace\agent\dsh-guard\dsh_guard.py heal --dry-run
python D:\workspace\agent\dsh-guard\dsh_guard.py restore --dest D:\dsh-restore   # 克隆+补 sessions+校验
python D:\workspace\agent\dsh-guard\dsh_guard.py verify --dir <目录>
python D:\workspace\agent\dsh-guard\dsh_guard.py keep skills\foo   # 这个删除是故意的，别还原
python D:\workspace\agent\dsh-guard\dsh_guard.py lock | unlock --unlock-for 10
```

计划任务（**不要带 `-AtLogOn`**，见坑 4）：

```powershell
$act = New-ScheduledTaskAction -Execute "<pythonw.exe 全路径>" `
         -Argument '"D:\workspace\agent\dsh-guard\dsh_guard.py" run' `
         -WorkingDirectory 'D:\workspace\agent\dsh-guard'
$trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
         -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
         -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
Register-ScheduledTask -TaskName 'DSH-Guard' -Action $act -Trigger $trg -Settings $set -Force
```

用 `pythonw.exe` 而不是 `python.exe`：否则每 2 分钟闪一次黑框。代价是没有 stdout，**所以日志必须自己写文件**（`guard.log`）。

## 4. 四个必须踩过的坑

1. **自愈必须在 commit 之前跑**（本机制最容易写错的一处）
   `run` 若先 `git add -A; commit` 再 `heal`，删除会**先被提交进历史**，`git diff HEAD --diff-filter=D` 立刻变空 → 自愈看不见，删掉的内容**永久变成"已提交的事实"**。顺序只能是 `heal → snapshot`。
2. **裸库的 HEAD 不指向 `main`，clone 出来是空工作树**
   `git init --bare` 默认分支可能是 `master`，而 push 用的是 `refs/heads/main` → `git clone` 只打一行 `warning: remote HEAD refers to nonexistent ref, unable to checkout`，**退出码 0、目录为空**。建库后立刻 `git --git-dir <bare> symbolic-ref HEAD refs/heads/main`，并在 clone 后补一次 `rev-parse --verify HEAD` 兜底。
3. **会话日志的 header `version` 是整数 `4`，文件名写的是 `v4`**
   直接比 `"v4" != 4` 会把**全部**日志判成不一致（实测 264/264 假报警）。归一化：`str(v).strip().lstrip("vV")`，文件名无版本段时按 `"0"` 比。整段的读写配方仍归 `dsh-agent-customization`。
4. **`Register-ScheduledTask` 带 `-AtLogOn` 会 `Access is denied`**（登录触发器需要管理员）
   原文：`Register-ScheduledTask : Access is denied.` + `HRESULT 0x80070005`。改用纯时间重复触发器（`-Once` + `-RepetitionInterval`），配 `-StartWhenAvailable` 让关机错过的轮次开机补跑。

补充踩点：`robocopy` 的**退出码 1 是成功**（有文件被复制），判失败要用 `rc >= 8`；模拟 `rm -rf` 的测试脚本必须给只读的 git 对象 `chmod`，否则 `shutil.rmtree` 先崩在 `.git\objects\xx`（`PermissionError: [WinError 5] 拒绝访问`），而真实 `Remove-Item -Force` 是会清只读位的——**测试假失败会让你误判安全网坏了**。

## 5. 上线与验收（按顺序，缺一步不算装好）

1. `init --bulk` → `status` 里 `commits>=1`、裸库存在、`bulk snapshots>=1`。
2. **真删一次再让它长回来**（本机实测路径）：记下 `AGENTS.md` 的 sha256 → 删掉 → `heal` → 比对 sha256 相同。**没被真删触发过的"自动还原"不算安全网。**
3. 用 `Start-ScheduledTask` 触发计划任务（不是手跑脚本），确认 `LastTaskResult=0` 且 `state.json` 的 `last_run` 前进。
4. `selftest.py` 全过（它会在 `D:\dsh-guard-lab` 里真删：单文件、哨兵、sessions 批量、整棵树、ACL 锁）。**演练目录以外的路径一律不许被测试脚本碰到**，脚本开头要断言 `LAB` 前缀。
5. `verify --dir %USERPROFILE%\.dsh` 结论 PASS。

## 6. 事故后的恢复顺序

1. **先退出 DSH**（`.dsh` 在用，边跑边换会撞 `storages/workspace.json` 的"内存旧版写回磁盘"）。
2. `restore --dest <新目录>`：从裸库克隆 → 用最新目录快照补 `sessions/attachments/storages` → 跑 `verify`。**PASS 才继续。**
3. 旧的 `.dsh` 改名留档，新目录改名成 `.dsh`。
4. 起 DSH，核对会话列表条数；变少就按 `dsh-agent-customization` 的版本段规则逐条修，别重命名了事（一条坏日志会让整个 listing 500）。

## 7. 不要做什么

- 不要把 `dsh_guard.py` / 备份 / 日志放进 `~/.dsh`——**它们会跟着一起死**（本机已有两个这样的死任务）。
- 不要指望 ACL 层"防住" agent：它是减速带，只争取时间；默认关，因为会让 `Ctrl+S` 类原子保存报拒绝访问。
- 不要在 `run` 里把顺序写成 `snapshot → heal`（见坑 1）。
- 不要为了"更安全"把 `heal_threshold` 调到 1~2：正常删两个 skill 文件就会被复活，来回拉锯；**单文件删除就该放行**。
- 不要用"端口/进程还在"证明看门狗在跑，要看 `state.json` 的 `last_run` 和 `LastTaskResult`。
- 不要在没有 `keep` 白名单的情况下批量删受跟踪文件（会触发还原），也别用 `--force` 绕过它。

## 8. 2026-11 加固后的实况与两条硬规则

装好之后这套东西长这样（`status` 能逐行看到）：凭据副本 `vault\secrets\<ts>\`（`.secrets/`、`.credentials.yaml`、`.anonymous-user-id`，保留 5 份）；二次副本 `C:\ProgramData\dsh-guard\`（裸库镜像 + 脚本自身 + `RESTORE.md` + 每周全量 zip，`archives\` 保留 2 份）；计划任务 `DSH-Guard-Health` 每 10 分钟查停摆，**连续两次**异常才在桌面写 `!!DSH-GUARD-STOPPED.txt`（睡一觉不会误报，恢复正常自动删除）；`status` 多了 `heal_fail_streak` / `pending_deletes` / `bulk_paused` / `secrets backup` / `mirror`。

**规则 1：自愈失败绝不能被下一步固化。** 旧版 `run` = `heal → snapshot`，heal 分批 `git checkout` 里有一批失败只记一条 log、仍返回 ok，紧接着的 `snapshot` 就是 `git add -A` 无条件提交 → **缺失被钉成"删除提交"**，之后 `git diff --diff-filter=D` 恒空，自愈彻底失明（2026-11-05 实测空转 23 轮 / 46 分钟）。现在的强制行为：heal 不干净时只提交新增/修改，把 `git diff --cached --diff-filter=D` 的路径从暂存区撤下（`git reset -q HEAD -- <paths>`），删除永远留在工作树、HEAD 里还在。**任何看门狗改到"落库/提交"这一步，都要先断言后置条件（HEAD 里每个路径都在工作树 + 哨兵齐全）。**

**规则 2：判据不能只看"工作树 vs HEAD 的差异"。** 删除一旦进了 HEAD，差异信号就归零；必须有一条**完全绕开 HEAD** 的恢复来源，并且判据要认"曾经存在过"。具体两条：① 哨兵只在 `HEAD:<path>` 或 `git log --all -- <path>` 命中时才算"缺失"（否则一个该版本没有的 `profiles/desktop/cordis.patch.yml` 会让 heal 永远失败）；② 已提交的删除用"最新 config 快照清单 vs 工作树"来发现，canary 目录下的缺失一律算事故。**救不回来时必须升级成 `error`/`ALERT` + `HEAL-FAILED.txt`，不能只打一行中性 notice。**

补充：`--home` / `--vault` 曾被顶层与子解析器双重定义（`parents=[common]` 两处都在），argparse 会用子解析器默认值覆盖 → **指定了也照样操作真实 home**。写法是子解析器用 `default=argparse.SUPPRESS`。这个 bug 的代价是"隔离演练实际打在线上"，装完先验一次 `status` 里的 home/vault 是不是你传的路径。

## 验收标准

1. `status` 能一眼给出：`last_run` 在 2 分钟内、`commits` 增长、`bulk snapshots` 有份数、`keep_deleted` 数目。
2. **真删过 AGENTS.md 并看到内容一致地回来**（第 5 节第 2 条）。注意判"一致"要**归一化行尾**：本机 `git config --system core.autocrlf` 出厂是 `true`，而仓库本地是 `false`，恢复时若走临时 clone（克隆出来的 `.git` 不带本地配置）会把 LF 写成 CRLF；给每次 git 调用都注入 `-c core.autocrlf=false -c core.eol=lf` 后，恢复文件与 `git cat-file -p <rev>:<path>` 逐字节一致。
3. 计划任务用 `Start-ScheduledTask` 触发过，`LastTaskResult=0`。
4. `restore` 出来的目录 `verify` 为 PASS；`logs\incidents\` 里有对应证据 JSON。
5. 装完后 `~/.dsh` 里只多了 `.git` 与 `.gitignore`（`dsh-runtimes/`、`plugins/*/node_modules/`、`.secrets/`、`sessions/`、`attachments/` 都该被 ignore）。
