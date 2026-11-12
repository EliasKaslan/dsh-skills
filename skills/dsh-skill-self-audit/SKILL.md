---
name: dsh-skill-self-audit
description: skill 集合定时自检：YAML、交叉引用、重复正文、目录预算。适用于"自检我的 skill / 有没有该合并的重复 / 哪些 skill 触发不了 / skill 目录多久没动"。
whenToUse: 定期（默认每天一次）对整个 DSH skill 集合做加法与减法的自检流程；含闸门判据、机械体检、处置分级、回滚路径与计划任务。模型看不到本节。
---

# DSH skill 集合每日自检

对 `C:\Users\admin\.dsh\skills` 这**一整个目录**（不是单个 skill）做体检与维护。单个 skill 的写法契约见 `dsh-skill-authoring`，某条经验该不该沉淀见 `sedimenting-skills`；本 skill 只管「定期把整个集合过一遍」。

## 何时调用

- **触发信号**：用户说"自检我的 skill""每天检查一下 skill""skill 有没有重复该合并的""删掉过时的 skill 经验""哪个 skill 触发不了"；或距离上次自检已过一天；或会话里出现了 skill 目录的批量异常（某条目突然消失、描述断尾）。
- **转交边界**：单条经验该不该沉淀 / 融合还是新建 → 用 `sedimenting-skills`；只改一个 skill 的 frontmatter 或 description → 用 `dsh-skill-authoring`（跑它的 `check-skill-frontmatter.ps1`）；要查 DSH 非交互入口、skill 发现根与热重载真相 → 用 `dsh-agent-customization`。
- **前置**：能读 `C:\Users\admin\.dsh\skills`；机器上 Windows 计划任务服务可用；已知本机 Python 3.12 在 `C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe`。／ **后继**：体检出的处置清单落到 `D:\workspace\agent\skills-audit\reports\`，结构性改动交用户确认后再动。

## 0. 闸门（先判能不能跑，再决定做什么）

**用户定的规则**：skill 目录最后一次变更后**满 1 小时**没有新变动，才允许自检。另有「距上次自检 ≥20h」，把计划任务的每小时轮询收敛成"每天至多一次"。

```powershell
& "C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe" `
  "C:\Users\admin\.dsh\skills\dsh-skill-self-audit\scripts\skill_audit_gate.py"
```

- 退出码 `0`=PASS、`10`=SKIP_QUIET（树太新）、`11`=SKIP_INTERVAL（刚审计过）、`12`=SKIP_CONFLICT（指纹不符）。
- 判据**必须遍历文件取 mtime**：`Set-Content`/`edit` 原地改内容**不更新目录 mtime**。实测 `github-pr-flow` 目录 mtime 停在 09-28 11:42:37，而其 `SKILL.md` 当天被改写两次。
- SKIP 时**什么都不做**（不改任何文件），只记一行日志。**静默窗口是硬闸门，不许为了"今天必须跑"而绕过。**

## 0.5 先读跨轮待办（BACKLOG.md）

`D:\workspace\agent\skills-audit\BACKLOG.md` 是**跨轮的持久记忆**：上一轮判为"结构性、需用户确认"而没做的项，以及"被并发写手跳过"的项，都记在那里。无人值守的一轮开始时**先读它**，能自动做掉的做掉，做完把条目移进报告并从 BACKLOG 删除；仍不能做的更新状态而不是重复记录。**没有这个文件，每天一轮的审计就永远只会重新发现同一批问题。**

## 1. 机械体检（只读，一条命令）

```powershell
& "C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe" `
  "C:\Users\admin\.dsh\skills\dsh-skill-self-audit\scripts\skill_audit_scan.py"
```

stdout 只有一行 ASCII：`SCAN ok files=<n> fail=<n> warn=<n> dangling=<n> asym=<n> dup_pairs=<n> report=<path>`；完整报告在 `D:\workspace\agent\skills-audit\reports\scan-<时间戳>.json|.md`。

它做七件事：A 转调 `dsh-skill-authoring\check-skill-frontmatter.ps1`（**含 YAML round-trip**，抓 `TOTAL/FAIL/WARN` 原文）、B description 预算清单（真实字符数、距 480 余量、触发句式条数）、C 交叉引用三分（`dangling` 指向不存在的 skill / `asymmetric` 单向引用 / `orphan` 孤立）、D 正文重复块（排样板行后两两比对）、E 体量清单、F 树指纹与"最后一次变更"、G 跑前跑后指纹自证。每项都有 `status`，拿不到写 `not_taken`，**不允许把"没取到"当 0 或 ok**。

### 1.1 目录预算（2026-11-12 起，单独一条只读命令）

```powershell
$env:PYTHONIOENCODING='utf-8'
& "C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe" `
  "C:\Users\admin\.dsh\skills\dsh-skill-self-audit\scripts\skill_budget.py"
```

判据（与插件 `dsh-plugin-sediment` 的写入闸一致）：**hot ≤ 40 条、目录行合计 ≤ 7000 字符、单条 description ≤ 120 字符**；
退出码 0 = 预算内、1 = 超预算。它同时报告 warm 条数，并可用 `--write-index` 重建 `skills-archive/INDEX.json`。
超预算时的处置顺序：先合并同主题 → 再把低频/过期条目加 `disable-model-invocation: true` 降为冷备 → 最后才考虑删。
（B 项里的"距 480 余量"是旧口径，仅作历史参考；新口径以 120 为准。）

## 2. 语义体检（委派子代理，这是"加法/减法"的判断部分）

机械项只能发现形状问题；"缺什么经验、哪些经验过时、description 能不能被想起来"必须由子代理读 description 与正文后判断。派发时把下面三问写进 prompt，并要求它**只读**：

1. **加**：本次会话 / 最近报告里有没有"该沉淀却没落盘"的经验？（判据与三段决策见 `sedimenting-skills`）
2. **减**：有没有被证伪的旧断言、跨 skill 重复的正文（同一经验写了两份）、明显过时的一次性数字？
3. **可发现性**：每个 `description` 的前 60 字符有没有领域锚点 + 用户口语触发词；`适用于"…"` 是否 ≥5 条；`不适用：…→ 用 \`X\`` 指向的 `X` 是否真能加载。

## 3. 处置分级（用户已授权：小改自动，结构性先报）

| 类别 | 例子 | 动作 |
|---|---|---|
| **自动改** | description 超 480 的截尾、补触发句式、补/修 `不适用 → 用 X` 指针、修 YAML 致命错误（半角 `: `）、补 `## 何时调用` 段 | 直接落盘，逐条记进报告 |
| **只报告** | 合并两个 skill、删除 skill、新建 skill、重写技术正文、改 `name`/目录名、**改本 skill 自己的正文** | 写进报告等用户确认，**无人值守时绝不自动做** |

改前必须整目录备份到 `D:\workspace\agent\skills-audit\backup-<时间戳>\`；改完用 `dsh-skill-authoring` 目录里的 `diff-skills.ps1 -Backup <备份>` 证明"技术正文零改动"（逐 skill 打 `exact=True`）。

**并发写手纪律**（实测存在：另一个 DSH 会话会在同一批文件上工作）：动某个文件前先 `read`，写后**立即重读**；两次读之间内容/大小/时间戳变了 = 有并发写入者 → **跳过该文件、绝不覆盖、绝不留回滚**，把它记进报告"被跳过（并发）"一节。

## 4. 落盘与自验证（写完必须做）

1. 会话 skill 目录里**出现**该条目——**这是唯一验收判据**；形状表全 ok 也不能替代它。
2. 再跑一次 §1 的扫描，`FAIL` 必须归零；`dsh-skill-self-audit` 自己不该出现在 FAIL 里。
3. 用 `skill` 工具按名字加载一次，确认正文可读、frontmatter 没写坏。
4. 报告写 `D:\workspace\agent\skills-audit\reports\audit-<日期>.md`，含：闸门判定、机械数据、自动改动逐条、待确认清单、**回滚命令**。
5. 最后一行**必须**是 `AUDIT-STATUS: ok|warn|fail items=<n> changed=<n> proposed=<n>`——计划任务靠这行判定成败，缺了它就算失败。

## 5. 无人值守怎么跑（已落地并实测）

Windows 计划任务 `DSH-Skill-SelfAudit`（每小时 :05）→ `run_daily.cmd` → `skill_audit_daily.py` → 闸门 → `dsh --profile headless`。自查/重装：

```powershell
schtasks /Query /TN "DSH-Skill-SelfAudit" /FO LIST /V
schtasks /Create /TN "DSH-Skill-SelfAudit" /SC HOURLY /MO 1 /ST 00:05 /F `
  /TR "C:\Users\admin\.dsh\skills\dsh-skill-self-audit\scripts\run_daily.cmd"
schtasks /Run /TN "DSH-Skill-SelfAudit"       # 立即触发一次（跑闸门，最便宜的真实验证）
schtasks /Delete /TN "DSH-Skill-SelfAudit" /F # 回滚：撤销定时
```

- 为什么不用 DSH 自己的机制：DSH **没有 cron / 调度器**；goal 续跑是 **idle/turn 结束驱动、无时间闸门**，做不到"每天一次"。
- 日志：`D:\workspace\agent\skills-audit\logs\runner.log`（每次一行）；单次 headless 的 stdout/stderr 各存一个文件；连续 2 次失败会写 `ALERT-needs-attention.txt`。
- 手工验证用的逃生口（**计划任务里绝不设置**，设了会绕过用户的静默规则）：`SKILL_AUDIT_FORCE=1`、`SKILL_AUDIT_STATE=<临时 state>`、`SKILL_AUDIT_TASK=<ASCII 任务串>`。三个都在 runner.log 里显式告警。

## 坑与修法

1. **`dsh --profile headless` 的 stderr 不是失败判据**
   实测 stderr 里全是 `GitHub MCP Server running on stdio` + 一堆 `npm notice New major version of npm available!`。→ 只认 **exit code + stdout 的最后一行 `AUDIT-STATUS:`**；exit=0 但没有该行 = 判 `fail`（"跑完了但什么也没干"必须能被抓到）。
2. **`.cmd` 只能是 ASCII**
   `cmd.exe` 用 OEM 代码页（本机 GBK）读 `.cmd`，中文会被拆坏。→ 壳里只写路径与调用，全部逻辑放 `.py`；Python 侧 stdout 也保持 ASCII（`UnicodeEncodeError` 会让计划任务静默失败）。
3. **PowerShell 的 `>` 重定向写 UTF-16LE**
   现象原文：`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte`。→ 用 `Start-Process -RedirectStandardOutput`（runner 就是这么做），或让 Python 自己 `io.open(..., encoding='utf-8', newline='')` 落盘。
4. **退出码 0 不代表 frontmatter 健康**
   `description` 里一个半角 `: ` 会让整条 skill 被静默丢弃（只留 `logger.warn: skill file ... ignored: invalid YAML frontmatter: Nested mappings are not allowed`），**headless 退出码仍是 0**。→ 自检必须自己解析 frontmatter / 跑校验器的 YAML round-trip。
5. **审计器自己会污染被审计的树**
   `daily.py` 里 `import skill_audit_gate` 让 CPython 在 skill 树内生成了 `scripts\__pycache__\skill_audit_gate.cpython-312.pyc`（实测出现，已删）；`python -m py_compile` 同样会用 `__pycache__\*.pyc` 污染脚本目录——而那个目录正是被审计对象，等于自己抬自己的判据。
   → 修法：在**任何同级 import 之前**加 `sys.dont_write_bytecode = True`，并在 `.cmd` 里另加 `set PYTHONDONTWRITEBYTECODE=1`（双保险）；检查语法就直接跑脚本，不要用 `py_compile`。改完必须复验：跑一次后 `Get-ChildItem <skills根> -Recurse -Filter *.pyc` 计数必须为 0。
6. **交叉引用抽取别用宽窗口**
   用「反引号前 16 字符含 用/见」去抽，会把 commit 号 `10d23bf5`、CI 标签 `approved`、YAML 键 `null`、工具名 `grep` 全算成兄弟 skill，得出 `dangling=52` 的假结论。→ 只认显式指针句式（`→ 用 \`x\`` / `见 \`x\`` / `转交 \`x\``）或 token 本身是已存在的 skill 目录。
7. **正文重复检测必须先排除样板行**
   `## 何时调用`、`**加载本 skill 当：**`、代码围栏这类行人人都有，不排除会报出 200+ 对假重复。→ 要求"块内 ≥2 行是真实内容"才算，其余降为信息。
8. **隔离 DSH_HOME 下 headless 必失败**
   新建的隔离 home 没有 `settings.yaml` / `.credentials.yaml` → 回落到没有 key 的 provider。→ 要真跑就指向真实 `DSH_HOME`（本机 `C:\Users\admin\.dsh`），或先复制这两个文件。
9. **没有 `--model` 这类 flag**
   `dsh-cmdline` 没开 `allowUnknownOption`，`--model` 会直接报未知选项。→ 换模型只能改 `settings.yaml` 的 `agent-default-model`，或启动时 `--patch` 覆盖那一行。
10. **树里存在明文机密**
    `ascend-env\credentials.txt` 就在被审计的目录里。（`github-pr-flow` 的 token 已于 2026-09-29 迁出到 `~\.dsh\.secrets\`——**skill 目录里本不该再有凭据文件**，体检时若发现应报出来，见 `github-pr-flow` §0。）→ 自检只登记"存在与体积"，**不要把内容抄进报告**。

## 不要做什么

- 不要在静默窗口未满时"顺手跑一下"——那正是用户要避免的场景。
- 不要为了改一个 description 就去重排整个 frontmatter；不要把 `## N.` 章节重编号（跨文件锚点会断）。
- 不要用 `D:\workspace\agent\skill\`（工作区）里的同名 skill 目录当真相——实测那里的 `vllm-ascend-source-install\SKILL.md` 是 09-21 的陈旧暂存，live 版本在 `C:\Users\admin\.dsh\skills`（09-28、体量 2.86×）。
- 发现别人的改动时**不要回滚、也不要顺手修正**，先停下问用户。

## 验收标准

1. `schtasks /Query /TN "DSH-Skill-SelfAudit"` 显示 `Ready`，`schtasks /Run` 后 `runner.log` 新增一行且 `Last Result: 0`。
2. 闸门在树刚被改过时**确实**返回 `SKIP_QUIET`（exit 10）且不启动 headless。
3. `skill_audit_scan.py` 跑完 `scan-*.json` 里 `G.unchanged=True`（跑前跑后指纹相同），且 `D:\workspace\agent\.dsh\skills` 树里没有多出任何文件。
4. 报告末行是 `AUDIT-STATUS: ...`；`FAIL` 归零；会话 skill 目录里能看到 `dsh-skill-self-audit`。
