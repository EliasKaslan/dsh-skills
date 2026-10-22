---
name: dsh-skill-authoring
description: DSH skill 文件本身的写法契约——skill 没被触发或加载不上时先看这条：模型每步只看到目录里的一行「`name` + 半角冒号 + description」（正文与 whenToUse 都不进目录），description 被折成单行、超 500 字符截断为前 497+"..."，旧 invocation 键（camelCase，3 个）会让整个 skill 拒载；含"适用于…/不适用：…→用 `<兄弟skill>`"句式模板、正文 `## 何时调用` 四要素、以及只读校验脚本 check-skill-frontmatter.ps1。适用于"写/改/新建一个 skill 的 frontmatter / 统一 skill 的何时调用与触发词 / 目录里哪个 skill 会被想起来 / skill 没被触发或加载不上 / description 字符数超限 / 校验脚本跑不起来报 Unexpected token"类任务。不适用：判断该不该沉淀、写到哪个根目录 → 用 `sedimenting-skills`。
whenToUse: 要新建或改 SKILL.md 的 frontmatter / description / 「何时调用」段，或要逐条校验一批 skill 的契约合规时使用。模型看不到本节，它只影响人和 API 的阅读。
---

# DSH skill 文件写法契约（frontmatter + 「何时调用」）

本 skill 只管**文件本身怎么写才触发得对**。判断「该不该沉淀 / 写到哪个根」是 `sedimenting-skills` 的事（见其 §1–§2），本 skill 不重复那套流程，只做交叉引用。

## 何时调用

**加载本 skill 当：**
- 要新建 / 改写 / 批量整理 `SKILL.md` 的 `description`、`whenToUse` 或正文「何时调用」段。
- 问「模型到底怎么看到 skill」「改了要不要重启」「为什么加了描述还是不触发」「description 写多长才算超」。
- 要跑契约校验（`TOTAL=.. FAIL=.. WARN=..`），或校验脚本报 `Unexpected token` / `Missing closing '}'`。

**不要用本 skill（转交）：**
- 判断「这个流程该不该沉淀成 skill」「该写 user 级还是 repo 级」→ 用 `sedimenting-skills`。
- 要写的是 skill 里的技术正文（命令、IP、版本、坑）→ 那属于具体领域 skill（`ascend-*`、`dsh-*`、PR 族等），本 skill 只管契约字段，不管内容真假。
- 要定期体检整个 skill 集合（重复正文 / 失效指针 / description 预算）→ 用 `dsh-skill-self-audit`。
- 本机 PowerShell 命令本身的坑（编码 / 计数 / PS7 语法）→ 用 `pwsh-on-windows`。

**前置**：知道目标 skill 的根目录（user 级 = `~/.dsh/skills/<name>/SKILL.md`）；无命令行权限时读不了源码证据，可以只照抄下表。 ／ **后继**：写完用 `skill` 工具按名字加载一次自验，再跑一次校验器。

## 1. frontmatter 契约事实表（读 DSH 加载器源码得到，已复验）

| # | 事实 | 证据 |
|---|---|---|
| F1 | 模型每步看到的 skill 目录**只有一行**：`` - `name`: description `` | `@deepseek-ai/dsh-tool-skill/lib/index.js:293-294` |
| F2 | `description` 被压成**物理单行**（连续空白 → 一个空格），YAML 折行/多行缩进排版无效 | 同上 `:359-361` |
| F3 | `description` 超 **500** 字符截断为 `前497字符 + "..."`（默认值见 `:40`、`:49`、`:57`） | 同上 `:40`,`:49`,`:57`,`:359-361` |
| F4 | **`whenToUse` 不进模型上下文**：对 `dsh-tool-skill/lib/index.js` grep `whenToUse` **零命中**；它只在 `dsh-skill-filesystem` 解析后透传到 session API 的 `SkillEntry` | grep `whenToUse` 该文件 → No matches；透传见 `dsh-api-session-controller/lib/index.js` |
| F5 | 目录重发判据 = `sha256(name + 截断后的 description)` → **只改 whenToUse，模型侧毫无变化** | `dsh-tool-skill/lib/index.js:301-303` |
| F6 | 正文（标题以下）只在 skill **被加载后**才进上下文 → 正文里的「何时调用」**不影响触发**，只影响加载后的转交/前置判断 | `<skill_content>` 渲染 `dsh-skill/lib/index.js:57-81` |
| F7 | `name` 必须匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`；身份**只取 frontmatter 的 `name`**，与目录名解耦（不一致会让你以为改了 A、实际注册的是 B） | `dsh-skill/lib/index.js:17`；解析 `dsh-skill-filesystem/lib/index.js:581-592,664-704` |
| F8 | frontmatter 写旧 camelCase 键（`disableModelInvocation` / `modelInvocable` / `userInvocable`）会**整个 skill 拒载**，不是忽略该字段 | `dsh-skill-filesystem/lib/index.js:842-854` |

**一句话结论：决定「何时调用」的字段只有一个 —— `description`。** `whenToUse` 只留作人 / API 读的一句话导航。

## 2. 写法硬规则

- **R1** `description` ≤ **480** 字符（UTF-16 码元，中文每字计 1），给 500 截断线留余量。**红线 500，超了就是 bug。**
- **R2** `description` 必须**物理单行**；YAML 里用**全角冒号**避免 `: ` 被当键值分隔符。
- **R3** **前 60 字符**内必须出现：领域锚点（机器/IP/平台名）+ 用户最可能说的 1~2 个触发词。截断只砍尾巴，关键触发词必须靠前。
- **R4** 结尾固定两段，缺一不可：
  - `适用于"<触发1> / <触发2> / …"` —— **≥5 条用户口语触发句式**（用户会怎么问，不是 skill 内部术语）。
  - `不适用：<场景> → 用 \`<兄弟skill名>\`` —— 消歧必须指向**确切**的 skill 名（反引号包住）。
- **R5** 实测数字 / 版本 / 报错短语**最多保留 3 个**最有检索价值的，其余删掉换触发句式。
- **R6** `whenToUse` **目标上限 ≤ 150 字符**（**>150 只出 `WHENTOUSE_OVER` 提示性 WARN；>160 才判 `WHENTOUSE_TOO_LONG` 硬 FAIL**）。**150 这个数是规范值，唯一出处 = `D:\workspace\agent\skill\_recon\skill-when-to-call-standard.md` L30 的 R6（"`whenToUse` ≤ **150** 字符"）+ L149 模板标注；校验侧实现 = `check-skill-frontmatter.ps1` L43 `$whenSoftMax = 150`。** 别把 160 当目标——**160 只是该脚本里一个无规范出处的宽松硬失效线（L44 `$whenHardMax = 160` + L232 判 WARN 处硬编码），不是契约**；写到 151~160 就已有 WARN。**在预算内必须显式标注"模型看不到本节"**（否则下次还会有人指望它触发）。两条冲突时**先保长度**：`whenToUse` 是给人看的提醒字段，为塞这句标注而把值顶过 150 是本末倒置——长度是硬约束，标注是预算内的义务。
- **R7** 正文含 `## 何时调用`（模板见 §3），放在标题引言之后、原有 `## N.` 章节之前；**绝不重编号已有 `## N.` 章节**——跨文件引用锚点（如「见 `ascend-cann-env` 坑 5」）依赖编号。
- **R8** 技术正文（命令、路径、版本号、坑与修法）一字不改；批量整理时只允许改 frontmatter 两行 + 新增/替换「何时调用」段。
- **R9** 不读凭据文件内容，也不在 `description` 里写凭据明文。**凭据文件允许放在 skill 目录内**（2026-10-08 用户决策，取代 2026-09-29 的"不该出现在 skill 目录内"：现在**鼓励 skill 直接写明自己用到的凭据文件位置**，`~\.dsh\.secrets\` 与 skill 目录两处都合法，单一出处见 `github-pr-flow` §0）；整理 / 巡检时只登记存在与体积，别读内容。

禁用清单：无区分度开场（「本 skill 用于…」）；在 `description` 里写「详见正文 / 见 SKILL.md」（模型看不到正文）；营销词；纯名词堆砌；把 `whenToUse` 当触发手段；靠换行排版 description；把兄弟 skill 的触发词抄进自己。

## 3. 正文 `## 何时调用` 四要素模板

```markdown
<!-- 段标题：两个井号 + 空格 + 何时调用 -->
## 何时调用

**加载本 skill 当：**
- <信号1：用户原话，或可观测的系统状态 / 报错原文>
- <信号2>

**不要用本 skill（转交）：**
- <场景> → `<确切兄弟skill名>`

**前置**：<没有就做不了的硬条件，或「无」> ／ **后继**：<做完本 skill 接着用哪个>
```

四要素 = **触发信号 / 转交边界 / 前置 / 后继**。触发信号写**可观测**的东西（用户原话、命令输出），不写「需要配置环境时」这类空话。

## 4. 校验器用法（本机没有 PowerShell 7，只有 5.1）

只读校验器就在本目录：`<本 skill 目录>\check-skill-frontmatter.ps1`（默认扫描 `$env:USERPROFILE\.dsh\skills`）。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\dsh-skill-authoring\check-skill-frontmatter.ps1"
```

- **必须带 `-ExecutionPolicy Bypass`**：本机只有 Windows PowerShell 5.1（`Get-ExecutionPolicy` = `Restricted`），**没有 PowerShell 7 的 `pwsh.exe`**（但工具名仍叫 `pwsh`，两者别混，见 `pwsh-on-windows`），`.ps1` 直接跑会被执行策略拦住。
- **裸 `& <脚本>` 在本机会报 `UnauthorizedAccess`——不是脚本坏了**：`& "…\check-skill-frontmatter.ps1"` 抛
  `PSSecurityException: File … cannot be loaded because running scripts is disabled on this system.`
  末尾 `FullyQualifiedErrorId : UnauthorizedAccess`；这是执行策略拦截，**别去改脚本、也别去改全局 ExecutionPolicy**，用上面那条 `-ExecutionPolicy Bypass` 调用即可（harness 里若 `&` 本来就能跑，就别绕）。
- 想扫别的根：加 `-SkillsRoot "<目录>"`。
- **脚本没有 `[CmdletBinding()]`，所以传它没声明的参数不会报错，只会被静默吞掉**：实测 `-File <脚本> -Path <SKILL.md>` **不报** `A parameter cannot be found that matches parameter name 'Path'.`——未声明的命名参数进 `$args` 后无人读，脚本**退化成整目录扫描**，于是你看着"照着路径验了单个文件"，实际验的是全部（对本机产物无害，但**不能拿它当"我只验了那一个文件"的证据**）。⇒ 判据只认**表里该 skill 那一行** + 末行 `TOTAL=`/exit code；要只验单个 skill 就自己在输出里过滤那一行（本机可用 `-SkillsRoot` 指到一个只含该 skill 的目录，或把整表按 skill 名过滤）。
- 输出一张表（列 `skill / status / yaml / desc / when / issues / warns`）+ 一行 `TOTAL=<n>  FAIL=<n>  WARN=<n>  YAML_FAIL=<n>  YAML_SKIP=<n>`；**有 FAIL 时 exit code = 1**（不是命令失败，是校验有违规）。
- 脚本是 **ASCII-only** 的（见坑 1），中文判定词用 `U 0x9002,0x7528,0x4E8E` 这种码点拼出来，改脚本时别往里加中文字面量。
- **两段检查：形状 + YAML round-trip**。round-trip 才是关键那段——它对每个 skill 真调一次 `yaml.parse()`，解析失败直接判 FAIL 并打印错误原文（`YAML_UNPARSEABLE(Nested mappings are not allowed ...)`）。只做形状检查会给**假 OK**（坑 2 的血证）。
- FAIL 项：`NO_SKILL_MD` / `NO_FRONTMATTER` / `YAML_UNPARSEABLE` / `YAML_DESC_NOT_STRING` / `NAME_MISSING` / `NAME_BAD_FORMAT` / `NAME_NE_DIR` / `CAMELCASE_KEY_REJECTS_SKILL` / `DESC_MISSING` / `DESC_OVER_TRUNCATION` / `DESC_NO_APPLIES` / `DESC_NO_DISAMBIG` / `DESC_POINTS_TO_BODY` / `WHENTOUSE_TOO_LONG` / `BODY_NO_WHEN_SECTION`。WARN 项：`DESC_OVER_BUDGET` / `WHENTOUSE_MISSING` / `WHENTOUSE_OVER` / `FRONTMATTER_MULTILINE` / `BODY_HAS_OLD_HEADING` / `DESC_LEN_NE_YAML` / `YAML_NOT_CHECKED`。
- **长度判定值写死在这里**：见上一条「预算数字只此一处」。
- **预算数字只此一处（唯一出处）**：`description` **≤480 = ok**（出处 = 同文件 **R1** 与 `skill-when-to-call-standard.md` §2 预算表"合计 ≤ 480"）；**481–500 出 `DESC_OVER_BUDGET` 警告**（还没被截断，但已无余量）；**>500 判 FAIL `DESC_OVER_TRUNCATION`**（目录里实际只剩前 497 字符 + `...`）。`whenToUse` 的 150 / 160 见 **R6**（本文件内单一归属，此处不重述）。**别的 skill（含 `~/.dsh/AGENTS.md`）只留指针、不重述这些数**——重述一次就多一份将来必然不一致的真相。
- **优雅降级**：找不到 `node` 或 `yaml` 包时，它打一整块 `WARN: YAML round-trip NOT performed (...) / THIS RESULT IS NOT TRUSTWORTHY`，每行 `yaml=SKIP` + `YAML_NOT_CHECKED`，末行再补一句"计数不可信"——**绝不静默跳过**（静默跳过＝再造一个假 OK）。yaml 包默认**已内置候选自动探测**：`$env:DSH_YAML_MODULE` → `~\.dsh\launcher\runtime\node_modules\yaml` → `%LOCALAPPDATA%\npm-cache\_npx\*\node_modules\yaml` → 旧 `~\.dsh\profiles\node_modules\yaml`（兜底），取第一个 `Test-Path` 命中者。**优先显式传 `-YamlModule <路径>`**（更确定，不受探测顺序影响）；显式传入的假路径仍逐字生效，故上面第 2 条负例照旧能强制降级。**所有候选都不存在时会静默退化**（只剩那块 WARN 横幅可辨认）。⇒ **判据 = 输出末行的 `YAML_SKIP=0`，不是 `exit code`**——退化时 exit 照样是 `0`，且 `YAML_SKIP` 计进 **WARN 桶、不计 FAIL**，所以"FAIL=0 且 exit=0"完全可能是没验 round-trip。本机实测可用模块只在 `%LOCALAPPDATA%\npm-cache\_npx\<hash>\node_modules\yaml`（hash 随重装变，**别写死**）；旧文指的 `~\.dsh\launcher\runtime` 在本机**已不存在**，照抄必失败。**看到 `YAML_SKIP=31` 就是没验。**
- **改本校验脚本后必须自测两个分支**（新加的 FAIL 判据本身需要反例——**没被真正触发过的安全网不算安全网**）：
  1. 在 `$env:TEMP` 造一个含**半角 `: `** 的坏 frontmatter → 必须报 `YAML_UNPARSEABLE(...)`；
  2. `-YamlModule` 指向假路径 → 必须打出 `WARN: YAML round-trip NOT performed` 横幅（而不是静默跳过）。
  验法各一条（负例**只造在 `$env:TEMP`**，验完删除并复核，共享的 `skills` 目录内绝不留负例）：
  ```powershell
  $neg = Join-Path $env:TEMP "skillneg"; New-Item -ItemType Directory "$neg\badskill" -Force | Out-Null
  Set-Content "$neg\badskill\SKILL.md" -Encoding UTF8 -Value "---`nname: badskill`ndescription: 坏例 a: b`n---`n# x"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\dsh-skill-authoring\check-skill-frontmatter.ps1" -SkillsRoot $neg
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\dsh-skill-authoring\check-skill-frontmatter.ps1" -SkillsRoot $neg -YamlModule "$env:TEMP\nope-does-not-exist"
  Remove-Item $neg -Recurse -Force
  ```

## 5. 坑与修法

1. **写含中文字面量的 `.ps1` → PS 5.1 按 GBK 解码无 BOM 文件 → 解析器崩**
   现象原文：`Unexpected token 'X' in expression or statement.` / `Missing closing '}' in statement block or type definition.`
   → 原因：脚本首行不是 `param(` 的 ASCII，中文被 GBK 误读成乱码字符，引号与花括号配对被破坏。
   → 修法：脚本**保持纯 ASCII**（中文用 `[char]0x9002` 之类拼）；或存成**带 BOM 的 UTF-8** 并显式指定编码读取。
2. **`description` 里的半角 `: ` 会让**整个 skill 静默消失**（旧说法「值被截到冒号前」是错的）**
   现象原文（本 skill 自己踩过）：`skill file ...\dsh-skill-authoring\SKILL.md ignored: invalid YAML frontmatter: Nested mappings are not allowed in compact mappings at line 2, column 14`
   → 原因：`:` 后跟空格在 YAML 纯量里是嵌套映射指示符，`parse()` 直接抛错；加载器 catch 后**丢弃整条**（`dsh-skill-filesystem/lib/index.js:669-674`，只留一条 `logger.warn`）→ 会话目录里查无此 skill，磁盘上却"看起来完全合规"。**这是「条目不在目录里」的头号真因。**
   → 修法：`description` 里**不要出现半角 `: `**（实测三种致命写法：`:` 后紧跟空格、` ` 在 `:` 前、以及 `:` 收尾，全都被判 `Nested mappings are not allowed in compact mappings`；而 `http://a.b.com` 这种 `:` 后不跟空格的没事）。用**全角冒号 `：`**；确实要说明目录条目的构成时，写成「`name` + 半角冒号 + description」这种**不含 `: ` 的措辞**，不要照抄成 `` `- name: description` `` 或 `` `name: <说明>` `` 这种示例——那正是本 skill 当年自杀的写法。
   → 逃生口（实测可用）：整个值用引号包住就安全——`description: "… a: b …"` / `description: '… a: b …'` 都能解析（引号被 YAML 剥掉，不进 description 长度）。但引号内的引号要转义，常规还是优先全角冒号。
   → 一行验 YAML 能不能解析（**校验器现在会做 YAML round-trip**，跑一次 §4 那条命令即可；要单独手工验就用下面这条）：
     `node -e "const fs=require('fs'),Y=require('C:/Users/admin/AppData/Local/npm-cache/_npx/<hash>/node_modules/yaml'),p=process.argv[1],r=fs.readFileSync(p,'utf8'),s=r.indexOf('\n')+1,e=r.indexOf('\n---\n',s);try{const d=Y.parse(r.slice(s,e));console.log('YAML OK  name='+d.name+'  desc='+d.description.length)}catch(x){console.log('YAML FAIL  '+x.message.split('\n')[0])}" "$env:USERPROFILE\.dsh\skills\<skill>\SKILL.md"`
     实测：坏文件输出 `YAML FAIL  Nested mappings are not allowed in compact mappings at line 2, column 14:`；好文件输出 `YAML OK  name=<dir>  desc=<真实字符数>`（本机 `sedimenting-skills` → `YAML OK  name=sedimenting-skills  desc=452`）。
3. **只改了 `whenToUse`，以为触发词变了**
   → 原因：F4/F5 —— 模型看不到 `whenToUse`，目录重发判据是 `sha256(name + 截断后 description)`。
   → 修法：所有触发词放 `description`；`whenToUse` 改动后不要指望模型行为有任何变化。
4. **`description` 写得漂亮但不触发**
   → 原因：触发词在 500 字符之后被截断（F3），或没写 `适用于"…"` 口语句式（模型匹配的是**用户会说的话**，不是 skill 内部术语）。
   → 修法：把领域锚点和触发词挪到**前 60 字符**；用校验器看 `desc=` 这一列的字符数。
5. **`Get-Content` 量出的 description 长度不是它的字符数（本机默认按 GBK 误读 UTF-8）**
   现象（同一行，本机实测；那一版 description 真实长度 427）：`(Get-Content $f)[2].Length` = **663**；加 `-Encoding utf8` 后 = **440**；再去掉 13 字符前缀 = **427**。
   → 三个数各差在哪：① 行首 `description: ` 前缀占 13 字符，必须截掉；② 不带 `-Encoding utf8` 时，本机（PS 5.1，无 pwsh）按 GBK 解码 UTF-8，一个中文字（3 字节）变成 1.5 个"字符"，长度**虚高约 1.5 倍**——这是"假超限"的最常见来源；③ 校验器内部已用 `-Encoding utf8`，它那一列 `desc=` 可信。
   → 一行量法（剥前缀 + 指定编码 + **只取第一处匹配**，返回真实字符数）：
     `$f="$env:USERPROFILE\.dsh\skills\<skill>\SKILL.md"; $d=((Get-Content $f -Encoding utf8 | Where-Object {$_ -match '^description: '} | Select-Object -First 1) -replace '^description: ',''); $d.Length`
     **`Select-Object -First 1` 不能省**：像本 skill、`sedimenting-skills` 这种**正文里也贴了 frontmatter 模板**的 skill，`^description: ` 会命中两行，取到的就变成"字符串数组的 `.Length`"＝**行数 2**，看上去像"描述只有 2 个字符"的假数字。
   → **免费红线告警**：会话目录里该条目被渲染成**断尾**（正文半句被切／以 `...` 收尾）就等于 description 超 500——渲染侧取的是「前 497 字符 + `...`」（`catalogDescription`，`dsh-tool-skill/lib/index.js:358-361`），不必先跑脚本。
   → **同上，数半角 `: ` 也踩前缀**：在**整行**上数 `': '`（或匹配 `^description:.*(: )`）恒得 1，那 1 个就是 `description: ` 前缀自身 → 必须先剥掉 `^description: ` 再数，否则会对**每一个健康 skill** 报假失败（实测：`vllm-ascend-e2e-ci-wiring` 描述体内 `': '` = 0、全角 `：` = 1，YAML round-trip `desc=453` 通过）。

6. **批量改 skill 的补丁脚本「跑两次」会把追加的内容落两遍**
   现象：同一补丁脚本第二次运行后，被追加的那段文字在正文里**连续出现两次**（2026-09-29 实测：`github-pr-flow` 的「转交清单」与「维护记录」各多出一份**逐字相同**的长行）。
   → 原因：幂等判据写成「`old` 不存在、`new` 存在 → 跳过」。当 `new` 把 `old` 当**子串**包含时（最常见的"原文 + 追加一段"型补丁），跑完第一次后 `old` 依然存在（它就是 `new` 的前缀），判据失效、第二次又追加一遍——**而且它不报错**。
   → 修法：幂等判据**只查 `new`**（`if new in text → skip`）；补丁要么没应用、要么已应用，`new` 出现即视为已应用。
   → 自证：改完按行扫「连续重复且 >60 字符的行」（`line == prev and len(line) > 60`），有输出就是被落了两次。

## 6. 不要做什么

- **不要**重编号已有 `## N.` 章节（R7）；**不要**顺手改技术正文（R8）——批量整理会和备份 diff 对不上。
- **不要**指望 `whenToUse` 或正文「何时调用」影响触发（F4/F6）。
- **不要**为了塞更多坑原文而挤掉 `适用于"…"` 段（R5）。
- **不要**把本 skill 当成沉淀流程说明用——判定与落盘位置看 `sedimenting-skills`。

## 7. 验收标准

1. **判存在看磁盘**（`<skills根>/<name>/SKILL.md` 真在不在）＋ **判可用看会话目录**（它在不在系统提示那份 skill 目录里），**两条一起才是验收**——会话目录不是存在性 oracle。
   **校验器判据 = 输出里的 `YAML_SKIP=0`，不是 `exit code`**：优先显式传 `-YamlModule`（更确定）；不传时脚本默认已内置候选自动探测，**探测不到才静默退化**——退化时 exit 仍为 `0`，只有末行 `YAML_SKIP` 变正。
   `status=ok`、`FAIL=0`、`skill` 工具能按名字加载，都只是辅助证据，**都不能替代「磁盘上有它」＋「目录里能看见它」**。没出现时**先跑本校验器**（见 §4）：看 `yaml` 列是不是 `FAIL`、`issues` 里有没有 `YAML_UNPARSEABLE(...)`；若 `yaml=SKIP`，说明 round-trip 压根没跑，**那次结果不可信**，先修好 node / yaml 再下判断。
2. **改已有** SKILL.md → 会话 skill 目录下一步就刷新（first-party `write`/`edit` 让 provider 失效，**无需重启**），且 description 就是刚写的那一行。
3. 用 `skill` 工具按名字加载一次，正文可读、frontmatter 没写坏。
4. 目录没出现 → 依次查：**frontmatter 能否 YAML 解析**（坑 2，最容易漏、也最常见的真因）、目录名是否 kebab-case、是否在扫描根的一层内、`name` 是否与目录名一致（F7）、是否误写了 camelCase 旧键（F8）。
5. **「不在目录里」≠「磁盘上没有」——收录的唯一门槛是 frontmatter 能否解析成功**
   - **已被证伪的旧断言**：本 skill 曾据 2026-09-28 的观测，把「新建 `dsh-skill-authoring` 后连续 3 次目录重发（均由其它 skill 的 description 变更触发）都不含该条目」判为「**新建目录会延迟收录，只有新建目录有这个问题，需要重开会话**」——**该推断是错的**。真因是它自己 description 里有一个半角 `: `（见坑 2），YAML 解析抛错 → 加载器丢弃整条；而当时校验器报 `ok`（不做 YAML round-trip），所以"磁盘上 frontmatter 完全合规"这个前提本身就是假的。**与"新建目录 / 要重开会话"无关。**
   - **同轮反证（磁盘时间戳：`dsh-agent-customization` 2026-09-28 15:51:37 落盘，与上面那次观测**同一天**）**：新建该目录后**当轮**它就进了会话目录（两次 write 各触发一次重发），`skill("<name>")` 按名加载正文完整；同一天把本 skill 的 frontmatter 修好，目录在**下一步**的重发里就收录了本条目。→ 旧记录里那"3 次重发都不含该条目"**不是新建目录的锅**，差别只在文件能不能解析。**改 frontmatter 与新建目录都是下一步生效，无需重开会话。**
   - **存在性判据**：要判某 skill 在不在，看磁盘（`Get-ChildItem <skills根> -Directory`），**别拿会话目录当存在性 oracle**；跨引用（正文里写「→ 用 X」那种）同理——目录里没有 `X` 只说明 `X` 现在解析/加载不了，不说明 `X` 没写过。
   - **补充：会话目录 ⊇ 磁盘目录，两边不是一一对应。** 反向陷阱——把系统提示里的会话清单（`available_skills`）与该根下的目录**各数一遍**（`@(Get-ChildItem <skills根> -Directory).Count`），**会话侧可能更多**（本机实测多出的那条是 `diagnose-windows-sandbox-acl`，它在该根下 `Test-Path` 为 `False`）⇒ 它来自**另一个 skill 根**，别把多出来的名字误判成"磁盘上新出现了一个 skill"，也别拿着它去这个根里找；「判存在看磁盘、判可用看目录」仍然成立，但先要问清**是哪个根**。

6. **唯一可执行判据（与宪法 §8 一致，双向引用此条）**：
   - **判存在看磁盘**：`Test-Path <root>\<name>\SKILL.md`；**判可用看目录**：系统提示里那份会话 skill 目录有没有这条。
   - **会话目录 ⊇ 磁盘目录，两边不是一一对应；而且没有任何单一目录能解释目录条数**：目录条数由「**多根** + **进程内注册**」共同决定，**不是**"某个目录下有几个 SKILL.md"。本机实测五个真根（2026-10-09）：

     | 根 | 条数 | 性质 |
     |---|---|---|
     | `~\.dsh\skills` | **现场数**（2026-10-22 为 35，会随新增/合并变动，**别写死**） | 用户可改（唯一该写的根） |
     | `@deepseek-ai\dsh-agent-preset\skills` | **4** | 包内，**不进**目录 |
     | `@deepseek-ai\dsh-sandbox-windows-acl\assets` | **1** | 包内，**进**目录 |
     | `@deepseek-ai\dsh-skill-office\assets` | **3** | 包内，**不进**目录 |
     | `config\skills`（快照池） | **6** | 池，不是会话根 |

     ⇒ **文件根 N（现场数）+ 1 个注册型 provider + 包内 office 族 7 条 = 目录条数**（2026-10-22 实测 N=35 ⇒ 目录 43 条；**别把 N 写死**）。目录里第 32 条 `diagnose-windows-sandbox-acl` **不是文件系统根**，而是 `dsh-sandbox-windows-acl` 包内**进程内注册**的：`…\dsh-sandbox-windows-acl\lib\types-*.js` 的 `registerAclDiagnosisSkill`（L1090）→ `ctx.skills.registerProvider(...)`（L1138）；该包 `README.md:78` 亦写明"Registration ... contributes it when a skill registry is available"，L171"One extra catalog entry on Windows"。**⇒ 数磁盘文件永远对不上目录条数，别拿"目录 32 条"去反推"磁盘有 32 个 skill"。** 包内只读根**只做引用链检查、不出修改建议**（改了会被包升级覆盖）。
   - **校验器判据 = 输出末行 `YAML_SKIP=0`，不是 `exit code`**（退化时 exit 仍为 `0`，那次结果 NOT TRUSTWORTHY，见 §4）。**优先显式传 `-YamlModule`**；不传时默认已内置候选自动探测，**探测不到才静默退化**——别把判据挂在"默认值/探测顺序"这类实现细节上，要挂在结果本体上。
   - 三重独立 oracle 各答一问，别互相替代：**磁盘**答"写没写"、**会话目录**答"加载得了吗"、**校验器**答"frontmatter 能不能解析且合规吗"。
   - **三者的共同点（本轮主线）：全都读「结果本体」**——磁盘路径、目录里的那条目、末行的计数；**没有一个读「状态名 / 退出码 / 上一步说成功」**。本轮两次假 OK（skill 被加载器静默丢弃、YAML round-trip 压根没跑）**都长着成功的脸**（`status=ok`、`FAIL=0`、`exit=0`）——凡是"没报错"就下结论的地方，先问一句"我读的是产物的本体，还是它的状态名"。

## 8. oracle 族（2–5）：证明「只改了允许改的地方」

批量改 skill 时，「技术正文零改动」既不能靠眼看，也不能靠行对齐 diff——在文件中间插入一段会让其后每一行都错位，`Compare-Object -SyncWindow 0` 能把几百行全报成 diff，得出**看起来像被大改**的假结论。正确做法是**先剥掉两侧的「允许改动区」，再整块比较**：

1. 改前整目录备份：`Copy-Item "$env:USERPROFILE\.dsh\skills" <备份目录> -Recurse -Force`
2. 备份后**记下每个将被改的文件的 sha256**（改前一次、改后一次），并写进交付/报告——这是"我只改了该改的"的第二个独立 oracle。副本落点遵循宪法 §9：`D:\workspace\agent\dsh_base\artifacts\backups\<name>.<日期>.bak`（整树改动用目录）；快照池的定义见 `D:\workspace\agent\dsh_base\config\manifest.json`，**池外文件没有自动回滚源**，必须自己存。
3. 剥掉 frontmatter；再从旧正文删除 `## 触发条件` 段、从新正文删除 `## 何时调用` 段（删到下一个 `## ` 之前）
4. 把两侧**各自 join 成一个字符串，用 `-ceq` 整块比较**——相等才算零改动
5. 只有不相等时，才用 `Compare-Object` 去**定位**具体行，不要用它下结论

`diff-skills.ps1` 就是这套流程（本目录内，参数 `-Backup <备份目录>`），逐 skill 打印 `exact=True/False`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<本目录>\diff-skills.ps1" -Backup "<备份目录>"
```

预期所有行 `exact=True`。`exact=False` 只允许出现在两类文件上：**被明确授权重构过**的文件、以及**有外部并发写入者**的文件。

### 并发写入者（真实风险）
2026-09-28 实测：同一批文件里有一个 SKILL.md 被**另一个会话**整体改写（+79/−38 行，引用了当天新建的目录），此时对它做「备份 diff」会把**别人的改动**算成你的。→ 动多个 skill 之前先确认没有别的写入者；发现可疑改动时，**先停下并去问用户**，不要回滚、也不要"顺手修正"。

**oracle 2 · 行多重集比对（与本节上面那套「剥掉允许改动区再整块比较」是两种手段，别当成重复）**：`diff-skills.ps1` 那套要先剥掉授权改动区、再整块 `-ceq`，回答的是"**授权区之外是否一字未动**"；行多重集比对**不剥任何区**，把改前副本与当前文件各切成行做 `Counter(旧行) - Counter(新行)`，回答的是"**到底哪几行没了、各几次**"，再反向看新增。它的**不可替代性在于不受"插入导致的行位移"干扰**（那正是 `Compare-Object -SyncWindow 0` 把几百行全报成 diff 的原因），且能一眼判断**移除的行是不是全部落在预期例外里**。本轮实测口径（可照抄）：12 个文件合计 `removed=8 / added=57`，8 行移除逐条落在 3 类预期例外内（3 个 `whenToUse` 行替换 / 1 个有序列表编号 `2/3/4→3/4/5` 共 3 行 / 2 行表格行内追加）⇒ **零意外删改**。

**oracle 3 · 标题树未受损**：改完**重列一次 `^##` 标题树**并与改前对比——`edit` 的锚点会跨界吞掉标题，让正文变成孤儿段（本轮实犯）。标题树变了就是结构被破坏，必须补回。

实测事故原文：给本 skill `## 7` 追加第 7 条时，替换锚点**把 `## 8. 第二个 oracle：证明「只改了允许改的地方」` 标题行一并吃掉**，§8 正文成了无标题孤儿段。**`status=ok`、`FAIL=0`、白名单 diff、上面的行多重集比对全都不会报**——它们只看内容与形状，不看章节树；只有把 `^## ` 标题逐行列出来对比才看得见。

```powershell
# 改前存一份，改后重列并对比：标题顺序/条数任一变化 = 结构被破坏
Get-Content <SKILL.md> -Encoding utf8 | Where-Object {$_ -match '^## '} | Set-Content "$env:TEMP\titles.before"
Get-Content <SKILL.md> -Encoding utf8 | Where-Object {$_ -match '^## '} | Set-Content "$env:TEMP\titles.after"
Compare-Object (Get-Content "$env:TEMP\titles.before") (Get-Content "$env:TEMP\titles.after")
```

**为什么它不能省**：R7 明令"绝不重编号已有 `## N.` 章节"（跨文件锚点依赖编号），而**吞掉一个标题比改错编号更严重**——编号错了引用还能命中别处，标题没了整节在结构化阅读里消失，且所有形状校验都仍然 `ok`。

**oracle 4 · frontmatter 边界取"前两条 `---`"**：判 frontmatter 是否合法**不能对全文数 `^---$`**——正文里的 frontmatter 模板代码块会让计数虚高（实测 `sedimenting-skills` 全文 **4** 条 `---`，但 frontmatter 只有**第 1–5 行**、三键各一；虚高的两条来自正文 §4 贴的 frontmatter 模板围栏）⇒ **只取第 1 条与第 2 条 `---` 之间的区间**做 `name` / `description` / `whenToUse` 的存在性与唯一性判定。按全文计数会**同时**报出 `dash=4 name=2 desc=2 when=2` 这种"三键重复"假硬伤（Lead 终审实犯一次、本写手也犯过一次）。

```powershell
# 正解：找到第一、第二条 --- 的行号，只看这个区间
$lines = Get-Content <SKILL.md> -Encoding utf8
$i1 = -1; $i2 = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i].TrimEnd("`r") -eq '---') { if ($i1 -lt 0) { $i1 = $i } elseif ($i2 -lt 0) { $i2 = $i; break } }
}
$fm = $lines[1..($i2 - 1)]   # 只在这个区间里数三键
```

**oracle 5 · 撤回式校验（reverse-apply closure）：不给备份也能反证"除申报的改动外逐字节未变"**——`edit` 的 old_string 唯一匹配只证明**改对了地方**，不证明**别处一行没动**；`difflib` 只给"非 equal 区域"，归属仍需人眼判。做法：把本次写入的新文本**按相反顺序**逐段替换回旧文本（每步断言 `t.count(new) == 1`），再比对重建结果的 **bytes + sha256** 是否严丝合缝等于改前基线；相等 ⇒ 反证"除申报的改动外逐字节未变"。

```python
t = open(target, 'rb').read().decode('utf-8')
for new, old in reversed(edits):        # edits = 本次写入的 (new, old) 对，按写入顺序
    assert t.count(new) == 1, new[:40]  # 锚点不唯一 = 申报有误，先停下
    t = t.replace(new, old)
assert t.encode('utf-8') == baseline    # baseline = 改前那个文件的原字节
```

实测（两个互不相识的子代理各自独立用出）：5 个子 persona 逆替换 → 逐字节重建基线 `22,301 B`；`dsh-agent-customization\SKILL.md` 6 段逆替换 → 重建 `74,252 B / sha256 018138E177BA0C744ADE8926F48A46F15BA4A8A6A3F863220F9B0ADAC054C760`，Lead 另用 difflib 独立复核（7 个非 equal 区域全落在预期区间、frontmatter 未变）⇒ 两条独立路径互证。

**与上面三个 oracle 的关系：更强的补充，不是替代**——① 三者都要**先有改前副本**（本节第 1 步），本手法**不需要备份**（旧文本由申报的 `edit` 反推），"改完才发现没备份"时它是唯一可用的范围证明；② 三者给的是"哪几行没了 / 标题树没变 / frontmatter 没被吞"这类**局部或形状**结论，本手法给的是**逐字节闭合反证**，天然免疫插入造成的行位移；③ 备份仍要做——它管**回滚**，本手法管**范围证明**。**适用范围不限于 skill 文件**：任何**无版本控制的共享文件**（patch / yml / 配置 / 池外的 `SKILL.md`）都成立，只要你列得出本次写入的 (new, old) 对。

> 出处：本 skill 的规范素材来自 `D:\workspace\agent\skill\_recon\skill-when-to-call-standard.md`（F1–F8 / R1–R9 / 消歧矩阵），两个校验脚本原件为同目录 `check-skill-frontmatter.ps1` 与 `diff-skills.ps1`（本目录是复制件，均可独立运行）。
