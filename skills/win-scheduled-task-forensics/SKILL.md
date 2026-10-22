---
name: win-scheduled-task-forensics
description: Windows 计划任务/持久化项取证与安全退役——谁给我装了每日定时程序、把每日签到任务停掉、这个定时任务是谁加的：五处侦察面（计划任务全量、schtasks 旁证、Run 键、两个启动文件夹、WMI 事件订阅）缺一处就漏；退役顺序固定为 Export-ScheduledTask 留档 → Disable-ScheduledTask（保留定义优于 unregister）→ 复核 State=Disabled 且 Actions 原文未变 → 清进程 → 复核其它任务未被误碰。适用于"找出某个 agent 建的每日定时程序 / 谁给我装了计划任务 / 把每日签到任务停掉 / 这个定时任务是谁加的 / 停用以后怎么恢复 / 雷电签到任务怎么退役"。不适用：本机 pwsh 命令本身的坑 → 用 `pwsh-on-windows`；要拆多路并行子任务 → 用 `orchestrating-subagents`。
whenToUse: 在本机排查/退役 Windows 计划任务与其它自启持久化项（尤其某个 agent 建的每日定时脚本）时用。命令级坑一律见 `pwsh-on-windows`，本 skill 只留指针。模型看不到本节。
---

# Windows 计划任务 / 持久化项取证与安全退役

**本 skill 只写流程与判据**：命令本身的坑（本机 `pwsh` 实为 Windows PowerShell 5.1、BOM/编码、`ExecutablePath` 恒空、非提权停 SYSTEM 服务四条通道、`Export-ScheduledTask` 的 XML 不含 `<Enabled>`）**归属 `pwsh-on-windows` 陷阱表**，本 skill 只留指针、不复述。

## 何时调用

**加载本 skill 当：**
- 要回答"这台机器上有没有某个 agent 偷偷建的每日/定时程序"，并把它**安全停掉**（可恢复，不是删掉）。
- `Get-ScheduledTask` / `schtasks /query` 里出现眼生任务，或用户说"我没装过这个定时任务 / 电脑每天自己弹东西"。
- 已定位到 `run_daily.py` / `run_daily.ps1` 一类脚本，但**手上只有任务名或目录名**、拿不出归属证据。
- 停完要出"其它计划任务未被误碰"的复核结果，或要判断 `LastTaskResult=3` 算不算坏。

**不要用本 skill（转交）：**
- 命令本身的坑（PS 5.1 解析期错误、BOM、`ExecutablePath` / `CommandLine` 恒空的机制、非提权停 SYSTEM 服务的逐字报错、导出 XML 不含 `<Enabled>` 的机制） → 用 `pwsh-on-windows`（陷阱表）。
- 要把取证拆成多路并行子任务、要写子代理契约与验收判据 → 用 `orchestrating-subagents`。

**前置**：Windows + `Get-ScheduledTask`/`schtasks` 可用；**侦察与禁用非提权即可完成**，只有 SYSTEM 服务进程清理要管理员窗口。 ／ **后继**：备份 XML 与退役记录落项目旁 `_task_backup\`；经验沉淀按 `sedimenting-skills`。

## 1. 侦察面（五处，缺一处就会漏）

1. **计划任务全量**，重点是**非 `\Microsoft\`** 的自建/第三方任务；逐条取 `Actions` 的 `Execute`/`Arguments`/`WorkingDirectory` 与 `Triggers`，以及 `Get-ScheduledTaskInfo` 的 `LastRunTime`/`LastTaskResult`：

```powershell
Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  $a = $_.Actions | Select-Object Execute, Arguments, WorkingDirectory
  [pscustomobject]@{ Path = $_.TaskPath; Name = $_.TaskName; State = $_.State
    Actions = (($a | Out-String).Trim()); Triggers = (($_.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ',')
    LastRun = ($_ | Get-ScheduledTaskInfo).LastRunTime; LastResult = ($_ | Get-ScheduledTaskInfo).LastTaskResult }
}
```

2. **`schtasks` 旁证**（与上面互校，能看出 `Get-ScheduledTask` 漏掉的东西）：`schtasks /query /fo LIST /v | Select-String -Pattern '<关键词>'`。
3. **注册表自启**：`HKCU:\Software\Microsoft\Windows\CurrentVersion\Run`、`HKLM:\Software\Microsoft\Windows\CurrentVersion\Run`（**含 `RunOnce`**）。
4. **两个启动文件夹**：`[Environment]::GetFolderPath('Startup')` 与 Common Startup（`[Environment]::GetFolderPath('CommonStartup')`）下的 `.lnk`/脚本。
5. **WMI 持久化 + 服务**：`Get-CimInstance Win32_Service` 的 `PathName`、`Win32_Process` 的 `CommandLine`，以及 `__EventFilter` / `CommandLineEventConsumer`（配对看 `__FilterToConsumerBinding`）。

**判据**：五处都扫过、且**逐条报出命中行**才算侦察完成。"只看了计划任务"不是侦察。

## 2. 定位脚本本体：三处交叉验证（仅凭任务名或目录名不算证据）

1. **脚本自述**——报出`文件:行号`；
2. **运行日志的实际输出**——不是"有个日志文件在这儿"；
3. **`config.json` 的 `task_name` / `time` 与计划任务逐字一致**——字符级相同，差一个字符即不是同一个东西。

三条**同时**成立才叫归属。反例：目录名像、任务名像、`config.json` 的 `task_name` 却对不上 → 归属不成立，继续查。

## 3. 退役顺序（不可颠倒）

1. **先留档**——`Export-ScheduledTask` 导出 XML 到项目旁的 `_task_backup\`，用 .NET 显式**无 BOM** 写入（BOM 会毁掉 XML 的比对基线）：

```powershell
$d = '<项目旁>\_task_backup'; New-Item -ItemType Directory -Force -Path $d | Out-Null
$xml = Export-ScheduledTask -TaskName '<名>' -TaskPath '<路径>'
[IO.File]::WriteAllText("$d\<名>.xml", $xml, (New-Object Text.UTF8Encoding($false)))
```

2. **再禁用**——`Disable-ScheduledTask -TaskName '<名>' -TaskPath '<路径>'`。**保留定义优于 unregister**：随时可 `Enable-ScheduledTask` 恢复。只有对象已被删才用 `Register-ScheduledTask -Xml (Get-Content <xml> -Raw) -TaskName '<名>' -TaskPath '\'` 重建，**重建后必须再补一次 Disable**（机制见 `pwsh-on-windows`）。
3. **复核**：`State=Disabled`，且 `Actions` 的 `Execute`/`Arguments`/`WorkingDirectory` **原文与退役前逐字一致**（禁用不该改定义）。
4. **最后清进程**（见 §4）。
5. **顺手确认其它计划任务未被误碰**——逐个报 `State`，与退役前列表比对。

## 4. 进程清理纪律

- **先走温和通道**：如雷电 `ldconsole.exe quitall`（本轮实测 `exit=0`，**只退实例**、不动服务）。
- **再按"当次实时枚举"的 PID + `ExecutablePath` 双重匹配精确结束**。**不许用旧 PID 快照**——PID 会被复用，拿旧快照杀 = 杀错进程。
- **`ExecutablePath` 拿不到就报告并跳过，不许猜杀**（为什么拿得到、为什么有时为空，见 `pwsh-on-windows`）。

## 5. 提权边界（必须先说清，别当成"进程不存在"）

- **SYSTEM 级服务**（本轮实例 `LDPlayerSvr` → `ldplayerservice.exe`）**非提权停不掉**，必须在管理员窗口执行；四条通道的报错原文与"为什么别反复换命令试" → `pwsh-on-windows` 陷阱表。
- 非提权下该进程 `ExecutablePath` **为空是正常的**，用 `Get-CimInstance Win32_Service -Filter "Name='LDPlayerSvr'"` 的 `PathName` 补证——不要读成"没有这个进程"。
- 收尾时：清不掉的**如实报告"未清理 + 原因 + 需要管理员窗口"**，不要宣称已清。

## 6. 逐字实测案例（本轮实例，可脱敏但保留结构）

| 任务 | 执行体 | 触发 | 作用 |
|---|---|---|---|
| `\LonghuDailySignin` | python 跑 `...\longhu-signin\src\run_daily.py` | Daily 08:05 | 封装雷电模拟器 + adb 驱动 App 签到 |
| `\LonghuDailyCheckin` | powershell 跑 `run_daily.ps1` | Daily 08:30 | 走 HTTP 接口签到 |

- 两者 `LastTaskResult=3` 的**含义是"掉登录态、待人工重登"**，**任务本身正常**——**别把退出码 3 误判成任务损坏**（本机该任务的真实失败形态就是这个 3，不是任务坏了）。
- 每个 agent 建的任务都**跟着一个项目目录**（脚本 + 日志 + `config.json`）⇒ 归属判定的落点就是这三件套（§2），不在任务名上。

## 不要做什么

- **不要** `Unregister-ScheduledTask` 就收工（能禁用就别删；删了要靠 XML 重建，且**重建即启用**）。
- **不要**拿旧 PID 快照杀进程；**不要**在 `ExecutablePath` 为空时猜杀。
- **不要**拿任务名 / 目录名当归属证据（§2 三处缺一不可）。
- **不要**把 `LastTaskResult=3` 当任务损坏。
- **不要**把导出的备份 XML 当"该任务原先是否启用"的证据（机制见 `pwsh-on-windows`）。

## 验收标准

- `(Get-ScheduledTask -TaskName '<名>' -TaskPath '<路径>').State` = `Disabled`，`schtasks /query /tn '<名>'` 显示 `Disabled`。
- `_task_backup\<名>.xml` 存在、与退役前导出内容一致，且**首三字节不是 `239,187,191`**（无 BOM）。
- 逐个报出的其它计划任务 `State` 与退役前一致（未被误碰）。
- 目标进程按 PID + `ExecutablePath` 复核后已消失；SYSTEM 服务若在非提权会话下，输出里必须有一行**显式的未清理报告**，而不是省略。
