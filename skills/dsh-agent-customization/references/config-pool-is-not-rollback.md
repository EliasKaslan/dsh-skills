# `config\` 快照池 = 分发源，不是回滚库（原 §2.14 原样拆出）

> 从 `dsh-agent-customization/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

### 2.14 `config\` 快照池是「分发源」不是「回滚库」：一次 `-Apply` = 一次无声的教义回退（实测）

> 编号说明：本节原拟编入 **2.13**，但 2.13 已被上节（registry 行崩塌）占用 ⇒ **顺延为 2.14**。

**它到底是哪一侧的源。** `D:\workspace\agent\dsh_base\config\manifest.json` 是「repo 侧 → live 侧」的映射表：`path` = **仓库侧写入源**，`source` = **live 溯源记录**；而决定"写到哪"的 `Get-DshLivePath`（`tools\sync-to-dsh-home.ps1:84-97`）**只按 `path` 前缀推导、完全不看 `source`**。方向由开关定（`:9-11`）：`-Capture` = live → 快照；`-Apply` = 快照 → live；**不带开关就是 dry-run，只打印不动手**（`:6-7` / `:357`）。两个真读它的消费者：写手 `tools\sync-to-dsh-home.ps1`（`config/skills/* → <live>\skills\*` 的映射在 `:92-95`；池只认 `dsh-*` 目录，`:130`）与比对器 `tools\check-drift.ps1`（`:110` 注释逐字 `snapshot -> live`；`:159-161` 证明 `config/AGENTS.global.md` 与 `<live>\AGENTS.md` 是同一份东西的两侧）⇒ **它是分发源（安装源），不是回滚库。**

**开关的逐字语义与 `-Capture` 的覆盖面（本轮实测 `tools\sync-to-dsh-home.ps1`）。** `:9-10` 逐字 `-Capture   live -> snapshot   (copy live files over the snapshot, then rewrite` + `config\manifest.json so it describes the result)`；`:11` 逐字 `-Apply     snapshot -> live   (back up every target file first, then copy)`；`:6-7` 无开关 = **dry-run**（`:357` 逐字 `DRY RUN -- no switch given, nothing was read from or written to the snapshot/live home.`，`:359` 打印 `-Capture would copy N file(s) live -> snapshot:`）。⇒ 语义有两点必须说全，别只记成"重新 capture"：**① 方向 = 把 live 盖到快照上**；**② 覆盖面 = 逐文件 copy（只写快照侧）+ 整份重写 `config\manifest.json`**。实现即"只写快照侧"：`:232-249` 的 Capture 分支只写 `$c.To`，`:242` 用 `Copy-Item -LiteralPath … -Destination … -Force` ⇒ **字节保真、无重编码**（不会给 skill 文件加 BOM）。

**实锤危害（同一机制、不同时刻；下面每个数字都是时刻值，别背成常量）。** `-Capture` **之前**有两次独立读数：Lead 复核得 `matched=8 drift=8`（**8 条全部 `live-newer`** = 1 个 `AGENTS.md` + 6 条 live `dsh-*` SKILL.md + 1 个脚本 `dsh-skill-authoring\check-skill-frontmatter.ps1`），**exit=2**；我上一轮复跑读到的条数比它少 1（差在那条期间刚被人改过的脚本）——**同一个池、两次读数就能差一条**。当时 dry-run 逐字打印 `-Apply would copy N file(s) snapshot -> live (with backup)`（N = 漂移条数）⇒ **那一刻的任何一次 `-Apply` 都是一次无声回退**。**重新 `-Capture` 之后**实测 `matched=16 drift=0 snapshot-only=0 live-only=0` + 脚本自己的原文 `No drift: the snapshot matches the live DSH home.`，**exit=0**（`:247` 脚本自己就写着 `Run check-drift.ps1 to confirm the result shows no drift.`）⇒ 池此刻已是真快照、`-Apply` 与 live 相等。**但风险只是被判据化，没有被消除**：`AGENTS.md` 是热刷新的、live 随时在动 ⇒ 只要 live 再前进一次，同一条 `-Apply` 就又是一次回退（**本节这次改稿本身就让池落后 1 条**）。

**为什么这叫"教义回退"而不只是"版本回退"（这段历史可当场复核，不必信本节的旧数字）。** 改造前两侧 `AGENTS.md` 的**章节编号完全一致（都 §0–§12）**，语义却相反——快照侧 §2 = 「触发即委派」、§3 = 「可以自己做」；live 侧 §2 = 「生产权在子代理」、§3 = 「审计通道」。**两份改造前原件都还在磁盘上**（只读），可直接逐字复核：`artifacts\backups\orchestration-opt-20261009\001__Users__admin__.dsh__AGENTS.md` 与同目录 `014__workspace__agent__dsh_base__config__AGENTS.global.md`（我本轮已按这两份复核过它们的 `## 0`–`## 12` 标题）。⇒ 那些**按编号引"宪法 §2 / §3"** 的 skill，回退之后会指向**相反语义**，而且**没有任何报错**。**现值**（2026-10-09 改造前实测）：两侧**逐字节相等 = 12,955 B / sha256 `C9AE86A3…`**——改造后本值必然失效，属时刻值；同样是时刻值，会随每次改造再变。

**两个必须一起说的限定（别夸大）**：

1. **这不是自动路径，是"装了子弹没扣扳机"。** `config\_backup` 目录**不存在**（`Test-Path` = False；备份根由 `-Apply` 才创建，`:263`）⇒ 历史上**从未 `-Apply` 过**。全机唯一与 DSH 相关的计划任务是 `DSH-Skill-SelfAudit`，在其 skill **全部文件**里 grep `-Apply|-Capture|sync-to-dsh-home|check-drift` = **0 命中**（本轮实测）⇒ 回退只会由人手动敲。
2. **池自己不会告诉你它旧了。** manifest 的 `bytes` / `sha256` 字段是**死数据、无人校验**——`check-drift.ps1:134-139` 是**现算** `Get-FileHash` 后比对，**从不读 `$e.sha256`**。⇒ **字段过期不产生任何 drift**（本轮就是这样被抓到的：两条失效字段一直躺着，`check-drift` 一声不吭，只有自己现算才看得见）。失效样例（`-Capture` **之前**实测；`-Capture` 会重写 manifest ⇒ 现值已刷新，样例只作形态参考）：`agent.cordis.yml` 记 21867 B / `d1e9f32a` 而磁盘 22980 B / `e8873211`；`preset.yml` 记 360 B / `dad344d4` 而磁盘 553 B / `9b6691f3`。⇒ 判据：**别把"manifest 没报错"当成"快照是新的"**；要判同步只能跑 `check-drift` 或自己现算。

**纪律：方向裁定没做完，任何人不得跑 `-Apply`。** 裁定 = 二选一：① **重新 `-Capture`**（让池重新成为真快照，推荐）或 ② **删池**；`-Capture` 也是写操作（它改的是池、并重写 manifest），同样在裁定之后做。**两个开关一起给 = 直接失败**（`:57-59` 逐字 `FATAL: pick one direction. -Capture and -Apply are mutually exclusive.`，`exit 1`）。

**本轮实测读数（2026-10-09，范例；每个数字都是时刻值）。** `-Capture` **之前**：`check-drift.ps1` 得 `matched=13 drift=3 snapshot-only=0 live-only=0` + **`EXIT=2`**；`sync-to-dsh-home.ps1` **dry-run** 逐字打印 `-Capture would copy 3 file(s) live -> snapshot:`（**恰好 3 个目标，没有附带拉入**）；**先备份再**跑 `-Capture`，**复跑** `check-drift.ps1` 得 `matched=16 drift=0` + 原文 `No drift: the snapshot matches the live DSH home.` + **`EXIT=0`**。**退出码定义：`0` = 无漂移 ／ `2` = 有漂移 ／ `1` = 用法或环境错误。** ⇒ **标准四步法（顺序不能换）**：① `check-drift.ps1` 判方向 → ② `sync-to-dsh-home.ps1` dry-run 先量（确认 copy 集合**恰好等于**漂移条数）→ ③ **先备份再** `-Capture` → ④ 复跑 `check-drift.ps1` 验收 `drift=0 + EXIT=0`。

**执行 + 验收配方（四条命令，顺序不能换）**

```powershell
$R='D:\workspace\agent\dsh_base'
# ① 先定方向：看 live-newer / snapshot-newer（exit=0 无漂移 / exit=2 有漂移）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\check-drift.ps1"
# ② dry-run（不带开关，不动任何文件）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\sync-to-dsh-home.ps1"
# ③ 裁定后真跑（写操作；实现见 sync-to-dsh-home.ps1:232-249）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\sync-to-dsh-home.ps1" -Capture
# ④ 验收：必须以 drift=0 + exit=0 收尾
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\check-drift.ps1"
```

- **验收判据 = 第 ④ 步 `drift=0` 且 `exit=0`**（收尾行 `No drift: the snapshot matches the live DSH home.`）。**别拿"capture 输出说 copy 了 N 个文件"当验收**——它只说明第 ③ 步动过 N 个文件，不说明结果对。
- **前提：动手前先确认所有写手都已停**（`AGENTS.md` 是热刷新的、live 随时在动）⇒ **`drift=0` 是时刻、不是属性**：live 再改一次就得**重跑 `-Capture`**，否则池立刻又落后。**纪律：改完 live 必须 capture**——只改了 live 侧却把漂移留着，等下一次谁跑 `-Apply`，就会**把 live 静默回退成旧快照**（刚改的内容没有任何报错地消失）。
- **坑：dry-run 会把两个方向都列出来，且对"两侧都存在但不同"的文件，两份清单是同一批**（`:196-229` 两个 plan 共用同一条"hash 不等"判据，`:359` / `:363` 分别打印）⇒ **光看清单分不出谁新、也就选不出开关**，方向只能由第 ① 步判。
- **坑：判"manifest 被重写"必须看 `generated_at`，不能看字节数。** `-Capture` **哪怕只 copy 1 个文件也会整份重算 manifest**（`sync-to-dsh-home.ps1:246` 打印 `manifest.json rewritten: 17 entries`），但 manifest 的**字节数可能完全不变**（Lead 实测：重算前后都是 **7,260 B**——只有 `sha256` / `bytes` 字段在换值）⇒ 拿"文件大小没变"当"没重写"会得出**假结论**，让人误以为 capture **静默失败**。同理，manifest 里那条过期的 59027 B 旧记录，在重算前后**都产生不了 drift**（`check-drift.ps1:134-139` 从不读 `$e.sha256`）。**更硬的一条实测**：四轮 `-Capture` 下来 manifest **恒为 7,260 B**，而 `generated_at` **四次各不同**；根因 = `Write-DshManifest` 各字段长度守恒（只有 `bytes` 跨位数时才偶然变）⇒ **字节数对"是否被重写"零信息量**。**并且不要手工改 manifest**：它只是 `-Capture` 的产物——`:244` 每次整份重写（`Write-DshManifest`）、`:246` 打印 `manifest.json rewritten: N entries`；而判漂移**从不读**它的 `sha256` 字段（`check-drift.ps1:134-135` 逐字 `$sh = Get-DshHash $snapPath` / `$lh = Get-DshHash $livePath`，现算后比对）⇒ **手改任何字段都不会影响判漂移的结果**，只会制造一份更不可信的记录。
- **非 `dsh-*` skill 不产生 drift 是设计内过滤、不是漏报**（本轮实测）：`sync-to-dsh-home.ps1:130` 与 `check-drift.ps1:176` 是**逐字同一句** `if ($d.Name -notlike 'dsh-*') { continue }`，后者上游 `:155` 的注释还写明 `deliberately`。⇒ `pwsh-on-windows` / `sedimenting-skills` 本轮被改过，但**既不入池、也不报 `[LIVE-ONLY]`**——这是设计，别当漏报去"修"。**推论（重要）**：改这类 skill（例如 `orchestrating-subagents`、`sedimenting-skills`）时，`check-drift` **不会报警**、快照里也**没有备份** ⇒ 对它们而言 `artifacts\backups\<name>.<日期>.bak` 是**唯一**回滚源；另一个会话正在改的技能也全在这类池外 ⇒ **它们的改动在 `check-drift` 里完全不可见**。
- **`check-drift` 的 `matched` 是动态值，不能进验收判据**（旧文把它定义成"可比文件数"是**错的**，以本轮实测为准更正）：`matched` = **hash 逐条相等的文件数**（`check-drift.ps1:136-137` 只在 `$sh -eq $lh` 时 +1，汇总打印 `:193-194`）⇒ `matched + drift` 才等于可比文件数（本轮 capture 前 `13 + 3 = 16`、capture 后 `16 + 0 = 16`）；只有 `drift=0` 时它才恰好等于"条目数 − `[SKIP]` 数"（17 − 1 = 16）。⇒ **验收只认 `drift=0` 与 `EXIT=0`**；把 `matched=16` 当常数写进判据，条目数一变就会误判。
- **判"池真同步"只能靠三件套**：`file_count` 与实际条数一致（`check-drift.ps1:104-105`；本轮实测 17/17）+ `generated_at` 是本次（本轮实测 `2026-10-09T14:52:01+08:00`）+ **现算 hash** 逐条相符。两个脚本都**不打印、也不写任何 `STALE` 标记**（`check-drift.ps1` 只有 `[SKIP]` `:117` / `[BROKEN]` `:122` / `[SNAP-ONLY]` `:128` / `[DRIFT]` `:147` / `[LIVE-ONLY]` `:186` 五种标签；manifest 里 `(?i)stale` 匹配 0）⇒ **根本不存在"检查有没有 STALE 行"这一步**，别照着一个不存在的前提下结论。
- `config\_backup\` 子树不进 manifest（`:144` / `:163`）。

**池的覆盖边界（池的定义权威 = 现存产物 `D:\workspace\agent\dsh_base\config\manifest.json`：本轮 recapture 后 **17 条 / `file_count=17` / `generated_at=2026-10-09T14:52:01+08:00**；宪法 §9 只讲**备份与回滚纪律**、**已不再定义池**，别再去宪法里找这句话）**：池**覆盖不到真正生效的编排 preset**。池里 preset 那半边指向**已死的** `~/.dsh\.agent-presets`（运行时全部 `.js` 里 `.agent-presets` 出现 0 次，见 `02-mechanics.md` 的 Q3 / Q7）；**真正生效**的是 **`artifacts\presets\orchestrator-bundle\cordis.patch.yml`**（经 `profiles\web\package.json:5` 的 `link:` 挂载 + `profiles\web\cordis.patch.yml:69-73` 的 `selectedDefault: orchestrator` 选中）——**bundle patch 与 profile patch 都不在池内** ⇒ **`-Apply` 无法恢复现网真正生效的编排 preset**，只能恢复一个没人读的目录式旧件。⇒ 「重建 home = 跑一次 `-Apply`」是**错的**。**同一条边界还有第二半**：同步与漂移检测**只认 live `skills\dsh-*`**（`sync-to-dsh-home.ps1:130` 逐字 `shared cross-project library, not ours`）⇒ `orchestrating-subagents` / `pwsh-on-windows` / `sedimenting-skills` 这类**非 `dsh-*` 的 skill 根本不在池内**——改它们**不产生任何 drift**（`check-drift` 永远显示"无漂移"，给的是**假安心**），同时它们也**没有自动回滚源**（改前必须自己留副本）。

**与第 1 节表格的呼应**：`AGENTS.md` 是**热刷新**的（第 1 节表格：改完当轮即收到 `Updated instructions from: ~/.dsh/AGENTS.md …`）⇒ **回退宪法的影响面不只新会话**，而是每个正在跑的会话**下一轮**就开始按旧教义行事。

> 本节行号取自 `tools\sync-to-dsh-home.ps1` / `tools\check-drift.ps1`（本机当前版本）；脚本一改行号就漂，**可迁移的是判据**（方向由字段定、drift 方向定生死、manifest 哈希字段不可信、池覆盖不到生效 preset）。

