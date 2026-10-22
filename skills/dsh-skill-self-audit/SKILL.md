---
name: dsh-skill-self-audit
description: DSH skill 集合的每日无人值守自检——静默满 1 小时且距上次自检 ≥20h 才跑；Windows 计划任务 DSH-Skill-SelfAudit 每小时轮询、headless 真跑；体检含 YAML round-trip、交叉引用 dangling/asym、正文重复、description 预算；小改自动、结构性改动只出清单；待办跨轮记在 BACKLOG.md。适用于"自检我的 skill / 每天检查一下 skill / skill 有没有该合并的重复 / 删掉过时的 skill 经验 / 哪个 skill 触发不了 / skill 目录多久没动了 / 定时体检 skill 集合"。不适用：判断某条经验该不该沉淀、写到哪个根 → 用 `sedimenting-skills`；只改 frontmatter 与 description 的写法契约 → 用 `dsh-skill-authoring`；要 DSH 非交互入口与 skill 发现真相 → 用 `dsh-agent-customization`。
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

stdout 只有一行 ASCII：`SCAN ok files=<n> fail=<n> warn=<n> dangling=<n> asym=<n> dup_pairs=<n> report=<path>`；完整报告在 `D:\workspace\agent\skills-audit\reports\scan-<时间戳>.json|.md`。**文件名只精确到分钟**——同一分钟内跑两次会**互相覆盖**，所以要比对两次运行的结果（例如正路 vs 故障注入）必须用 `--out-dir` 各写一个目录，否则第二次会把第一次的报告盖掉、你以为两次结果一样。

它做七件事：A 转调 `dsh-skill-authoring\check-skill-frontmatter.ps1`（**含 YAML round-trip**——脚本先探测可用的 yaml 模块再传 `-YamlModule`；探测不到时那一项**绝不记 ok**、降级为 `warn` 并在理由里写明「结果不可信」，抓 `TOTAL/FAIL/WARN/YAML_SKIP` 原文）、B description 预算清单（真实字符数、距 480 余量、触发句式条数）、C 交叉引用三分（`dangling` 指向不存在的 skill / `asymmetric` 单向引用 / `orphan` 孤立）、D 正文重复块（排样板行后两两比对）、E 体量清单、F 树指纹与"最后一次变更"、G 跑前跑后指纹自证。每项都有 `status`，拿不到写 `not_taken`，**不允许把"没取到"当 0 或 ok**。

- **A 项的要害是 `YAML_SKIP`，不是 `FAIL`/`WARN`**：脚本此前拼命令时**不带 `-YamlModule`**，而状态判定**只读 `FAIL`/`WARN`、从不单独判读 `YAML_SKIP`** ⇒ 当校验器那个默认 yaml 路径失效之后，31 行 round-trip **静默全变成 SKIP**，A 项却只报一句笼统的 `checker reports WARN=31`，**从字面上看不出"这一项其实压根没跑"**。存档实证：`scan-2026-09-30-*` 还是 `YAML_SKIP=0`，到 `scan-2026-10-09-*` 已是 `YAML_SKIP=31` 而状态**始终是 `warn`**——**它一次都没报过 ok，也正因如此更没人发现**。这才是「`description` 里一个半角冒号加空格让整条 skill 静默消失」这个头号真因长期没被抓到的原因。已修：按候选顺序探测 yaml 包目录（`launcher\runtime` → home 相对 → 动态 glob `npm-cache\_npx\*\node_modules\yaml` 取最新 → 校验器默认兜底），可 `--yaml-module <路径>` 覆盖；修后 `YAML_SKIP=0`、31 行全部 `yaml=ok`。
- **判据**：`YAML_SKIP>0`（或该项 `status` 为 `warn`/`not_taken`）时**不得当 ok**，`YAML_SKIP=0` 才算真验过。探测不到模块时它会落到 `warn` 而**不是** `fail`（校验器同时给出 `WARN=31`，先命中了 WARN 分支）——`warn` 与 `not_taken` 进同一 `warn` 桶、脚本退出码恒 0，"这项没取到"不该让无人值守任务误判成"有违规"。**优雅降级横幅原文与可用模块考点 → 见 `dsh-skill-authoring` §4。**
- **改了 `scripts\` 下的东西仍要冷启动+故障双验收**：①直跑脚本看正路（应 `A.status=ok`、`YAML_SKIP=0`、摘要 `warn=0`）；②**人为制造故障**跑 `--yaml-module <不存在的路径>`，应看到 `A.status` 变 `warn`、理由含「结果不可信」、摘要 `warn` **+1** 而 `fail` **不变**（这一条是"没被真正触发过的安全网不算安全网"）；③在**隔离环境**真跑一次 `run_daily.cmd`（静默闸门未满时它会 `SKIP`，正好是一次安全的冷启动烟测）——**热重载成功 ≠ 冷启动成功**。

## 2. 语义体检（委派子代理，这是"加法/减法"的判断部分）

机械项只能发现形状问题；"缺什么经验、哪些经验过时、description 能不能被想起来"必须由子代理读 description 与正文后判断。派发时把下面四问写进 prompt，并要求它**只读**：

1. **加**：本次会话 / 最近报告里有没有"该沉淀却没落盘"的经验？（判据与三段决策见 `sedimenting-skills`）
2. **减**：有没有被证伪的旧断言、跨 skill 重复的正文（同一经验写了两份）、明显过时的一次性数字？
3. **可发现性**：每个 `description` 的前 60 字符有没有领域锚点 + 用户口语触发词；`适用于"…"` 是否 ≥5 条；`不适用：…→ 用 \`X\`` 指向的 `X` 是否真能加载。
4. **宪法 ↔ skill 一致性巡检**（本轮评审的沉淀方法，可复用）：上一条只看 skill 之间；这一条看**宪法与 skill 之间**。四项，全部**只读**：
   - **① 完好性（判据是可机判的集合关系，不是写死的数字）**：`~/.dsh/AGENTS.md` 的 `^## \d` 编号必须**无重号**，且 **被外部引用的编号集合 ⊆ 现存编号集合**——**别把节数写死成"=N"，更别写字符总数**（本机没有 tokenizer，字符数随每次编辑漂移，属不可复算指标）。**现值（改写当时实测，属时刻值）：12 个 `## ` 标题，编号 §0–§10 + §12。** §11 缺号是**预期的、不是漏了一节**：`## 11.` 那一整节被有意删除，删后**不重排编号**（重排会打断所有按号引用，例如「→ 见宪法 §12」）⇒ **谁看到"少了一节"都不要补一个 §11 回来**。判据写成三句**可重算**的话（③ 是永久判据，①② 是时刻值、改宪法后按下面命令重算）：①`^## ` 计数 = 12；②编号集合 = {0..10} ∪ {12}；③每条「宪法 §N」引用的 N 落在该集合内（**引用 §11 才是断链**——那一节真的没了）。**为什么不用固定数**：写死的数每改一次宪法就失效一次，一失效就会**把正确的现状报成违规**（假警报），或反过来掩盖真重号。
     `python -c "import io,re;t=io.open(r'C:\Users\admin\.dsh\AGENTS.md',encoding='utf-8').read();print(len(re.findall(r'(?m)^## ',t)),sorted(int(m) for m in re.findall(r'(?m)^## (\d+)\.',t)))"` → 实测输出 `12 [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12]`
   - **② 引用链语义核对（最关键）**：扫**全部** `SKILL.md` 里的「宪法 §N」/「`AGENTS.md` §N」引用，**逐个确认该节语义与引用方的描述一致**。
     **行号/编号命中 ≠ 语义未变**——本次实锤：结论池内旧宪法的 **§2/§3 与现盘语义相反**（旧 §2 是"触发即委派"、现 §2 是"生产权在子代理"），编号一字不差，语义翻了。
     ⇒ 判据只能是**读该节正文并与引用方的说法逐句对**，不是 grep 命中。
   - **③ 重复正文**：同一断言在**宪法与 skill 正文各有一份** = 制造两份真相 ⇒ 宪法侧应降级为**指针**（单一归属）。
     典型：description 预算数字（唯一出处应只有 `dsh-skill-authoring` §4）、回执行数契约（唯一出处应只有宪法 §5）。
   - **④ 被证伪断言**：拿实测证据扫技能里的**强断言**——「本机没有 X」「唯一判据是 Y」「只有 1 个 Z」这类。本次抓到多条（如"本机没有 pwsh"、"唯一验收判据＝会话目录可见"）。
   - **⑤ 必须带上"根"的概念（本问最大的判据缺口）**：判据**不能默认只有一个 skill 根**。会话目录条数由「**多根** + **进程内注册型 provider**」共同决定（本机实测 5 个根 + 1 个注册 provider = 目录 32 条，详见 `dsh-skill-authoring` §7 第 7 条）⇒ 巡检要**按根枚举**，并对每个根标注性质：
     - **可写根**（`~\.dsh\skills`）：可出修改建议。
     - **包内只读根**（`launcher\runtime\node_modules\@deepseek-ai\*\…`）：**只做引用链检查、绝不出修改建议**——改了会被包升级覆盖，等于白改。
     - **注册型 provider**（如 `dsh-sandbox-windows-acl` 的 `registerAclDiagnosisSkill`）：**没有对应目录可改**，发现它的 description 有问题只能**报给包 owner**，不是本库能修的事。
     **根不明确时，一切"这个 skill 该改/该删"的结论都不成立**（可能它根本不在你写的那个根里）。
   - **⑥ 每条 finding 必须带 `@sha256@时刻`（防"移动靶"）**：本轮真发生——审计工作窗口内 `dsh-agent-customization` 被改了 **≥2 次**，它报出的**行号当场失效**，下一个人按行号去找会**扑空**。⇒ 每条发现必须写成 **`文件 @<sha256 前 8 位> @<发现时刻>` + 原文片段**（行号只能作辅助，因为行号是移动靶）。**没有 sha256 的 finding = 无法复核的 finding**，按 §3 分级时直接降级为"待重新取证"。
   - **落点与判据**：本节**只读**；产出的不一致清单写进 `BACKLOG.md`，并按 §3 分级处置——**小改自动、结构性改动只报清单**。
     **不要**为这条巡检新建 skill：它是本节的第 4 问，不是新主题（新建 = 白付一份目录税，见 `sedimenting-skills` §5.5）。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `dsh-skill-self-audit`（读本节三问）、`sedimenting-skills`（三段决策与归属判定）、`dsh-skill-authoring`（frontmatter 与 description 契约）。加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\dsh-skill-self-audit\SKILL.md`、`C:\Users\admin\.dsh\skills\sedimenting-skills\SKILL.md`、`C:\Users\admin\.dsh\skills\dsh-skill-authoring\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。

## 3. 处置分级（用户已授权：小改自动，结构性先报）

| 类别 | 例子 | 动作 |
|---|---|---|
| **自动改** | description 超 480 的截尾、补触发句式、补/修 `不适用 → 用 X` 指针、修 YAML 致命错误（半角 `: `）、补 `## 何时调用` 段 | 直接落盘，逐条记进报告 |
| **只报告** | 合并两个 skill、删除 skill、新建 skill、重写技术正文、改 `name`/目录名、**改本 skill 自己的正文** | 写进报告等用户确认，**无人值守时绝不自动做** |

改前必须整目录备份到 `D:\workspace\agent\skills-audit\backup-<时间戳>\`；改完用 `dsh-skill-authoring` 目录里的 `diff-skills.ps1 -Backup <备份>` 证明"技术正文零改动"（逐 skill 打 `exact=True`）。

**并发写手纪律**（实测存在：另一个 DSH 会话会在同一批文件上工作）：动某个文件前先 `read`，写后**立即重读**；两次读之间内容/大小/时间戳变了 = 有并发写入者 → **跳过该文件、绝不覆盖、绝不留回滚**，把它记进报告"被跳过（并发）"一节。

## 4. 落盘与自验证（写完必须做）

1. 会话 skill 目录里**出现**该条目——**这是「改完能被用上」的验收判据**；形状表全 ok 也不能替代它。（**判存在另看磁盘**：磁盘有它 + 目录里有它，两条一起才算过，见 `dsh-skill-authoring` §7。）
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
10. **凭据文件：允许存在，且必须"登记 + 校验指针有效"（2026-10-08 规则反转）**
    `ascend-env\credentials.txt` 这类凭据文件**允许放在 skill 目录内**，而且**鼓励每个 skill 直接写明自己用到的凭据文件位置**（用户 2026-10-08 决策，**取代** 2026-09-29 的"必须放 `~\.dsh\.secrets\`、skill 目录里发现就报出来"）。→ 体检改做三件事：①**登记**每个凭据文件的路径与体积；②**校验被引用的凭据文件真实存在**——skill 正文点名了 `<skill>\credentials.txt` 却在树里找不到，等于会话会照着扑空的假指针，**按 FAIL 报**；③**绝不把内容抄进报告或日志**。`~\.dsh\.secrets\`（`github-pr-flow` 的 token）与 skill 目录内部两处都合法，单一出处见 `github-pr-flow` §0。

## 不要做什么

- 不要在静默窗口未满时"顺手跑一下"——那正是用户要避免的场景。
- 不要为了改一个 description 就去重排整个 frontmatter；不要把 `## N.` 章节重编号（跨文件锚点会断）。
- 不要用 `D:\workspace\agent\skill\`（工作区）里的同名 skill 目录当真相——实测那里的 `vllm-ascend-source-install\SKILL.md` 是 09-21 的陈旧暂存，live 版本在 `C:\Users\admin\.dsh\skills`（09-28、体量 2.86×）。
- 发现别人的改动时**不要回滚、也不要顺手修正**，先停下问用户。

## 验收标准

1. `schtasks /Query /TN "DSH-Skill-SelfAudit"` 显示 `Ready`，`schtasks /Run` 后 `runner.log` 新增一行（**判完成只认产物**：`runner.log` 新行 + 报告末行 `AUDIT-STATUS: ...`）。⚠️ **`Last Result` 不是判据**——本机实测该字段有**恒 0** 的先例（本轮复核），拿它当验收会把真失败读成成功；计划任务的注册形态、`-ExecutionPolicy Bypass` 为何承重、失败要留 ALERT 供 agent 接手 → 见 `dsh-repo-sync` §3「计划任务的硬规则」。
2. 闸门在树刚被改过时**确实**返回 `SKIP_QUIET`（exit 10）且不启动 headless。
3. `skill_audit_scan.py` 跑完 `scan-*.json` 里 `G.unchanged=True`（跑前跑后指纹相同），且 `C:\Users\admin\.dsh\skills` 树里没有多出任何文件。
4. 报告末行是 `AUDIT-STATUS: ...`；`FAIL` 归零；会话 skill 目录里能看到 `dsh-skill-self-audit`。
