---
name: dsh-skill-authoring
description: skill 契约与跨 harness 分发：触发字段、预算、拒载键、导出到 ChatGPT 的清洗规则。适用于"skill 没被触发 / description 超限 / 想给 ChatGPT 用"
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
- **R6** `whenToUse` ≤ **150** 字符，且**必须显式标注"模型看不到本节"**（否则下次还会有人指望它触发）。
- **R7** 正文含 `## 何时调用`（模板见 §3），放在标题引言之后、原有 `## N.` 章节之前；**绝不重编号已有 `## N.` 章节**——跨文件引用锚点（如「见 `ascend-cann-env` 坑 5」）依赖编号。
- **R8** 技术正文（命令、路径、版本号、坑与修法）一字不改；批量整理时只允许改 frontmatter 两行 + 新增/替换「何时调用」段。
- **R9** 不碰凭据文件，也不在 `description` 里写凭据。**凭据文件不该出现在 skill 目录内**（2026-09-29 策略：缓存放 `~\.dsh\.secrets\` 并 gitignore，单一出处见 `github-pr-flow` §0）；遇到只登记存在与体积，别读内容。

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

## 4. 校验器用法（本机没有 pwsh）

只读校验器就在本目录：`<本 skill 目录>\check-skill-frontmatter.ps1`（默认扫描 `$env:USERPROFILE\.dsh\skills`）。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:USERPROFILE\.dsh\skills\dsh-skill-authoring\check-skill-frontmatter.ps1"
```

- **必须带 `-ExecutionPolicy Bypass`**：本机只有 Windows PowerShell 5.1（实测 `5.1.26100.9444`，`Get-ExecutionPolicy` = `Restricted`），**没有 pwsh**，`.ps1` 直接跑会被执行策略拦住。
- **裸 `& <脚本>` 在本机会报 `UnauthorizedAccess`——不是脚本坏了**：`& "…\check-skill-frontmatter.ps1"` 抛
  `PSSecurityException: File … cannot be loaded because running scripts is disabled on this system.`
  末尾 `FullyQualifiedErrorId : UnauthorizedAccess`；这是执行策略拦截，**别去改脚本、也别去改全局 ExecutionPolicy**，用上面那条 `-ExecutionPolicy Bypass` 调用即可（harness 里若 `&` 本来就能跑，就别绕）。
- 想扫别的根：加 `-SkillsRoot "<目录>"`。
- **脚本没有 `[CmdletBinding()]`，所以传它没声明的参数不会报错，只会被静默吞掉**：实测 `-File <脚本> -Path <SKILL.md>` **不报** `A parameter cannot be found that matches parameter name 'Path'.`——未声明的命名参数进 `$args` 后无人读，脚本**退化成整目录扫描**，于是你看着"照着路径验了单个文件"，实际验的是全部（对本机产物无害，但**不能拿它当"我只验了那一个文件"的证据**）。⇒ 判据只认**表里该 skill 那一行** + 末行 `TOTAL=`/exit code；要只验单个 skill 就自己在输出里过滤那一行（本机可用 `-SkillsRoot` 指到一个只含该 skill 的目录，或把整表按 skill 名过滤）。
- 输出一张表（列 `skill / status / yaml / desc / when / issues / warns`）+ 一行 `TOTAL=<n>  FAIL=<n>  WARN=<n>  YAML_FAIL=<n>  YAML_SKIP=<n>`；**有 FAIL 时 exit code = 1**（不是命令失败，是校验有违规）。
- 脚本是 **ASCII-only** 的（见坑 1），中文判定词用 `U 0x9002,0x7528,0x4E8E` 这种码点拼出来，改脚本时别往里加中文字面量。
- **两段检查：形状 + YAML round-trip**。round-trip 才是关键那段——它对每个 skill 真调一次 `yaml.parse()`，解析失败直接判 FAIL 并打印错误原文（`YAML_UNPARSEABLE(Nested mappings are not allowed ...)`）。只做形状检查会给**假 OK**（坑 2 的血证）。
- FAIL 项：`NO_SKILL_MD` / `NO_FRONTMATTER` / `YAML_UNPARSEABLE` / `YAML_DESC_NOT_STRING` / `NAME_MISSING` / `NAME_BAD_FORMAT` / `NAME_NE_DIR` / `CAMELCASE_KEY_REJECTS_SKILL` / `DESC_MISSING` / `DESC_OVER_TRUNCATION` / `DESC_NO_APPLIES` / `DESC_NO_DISAMBIG` / `DESC_POINTS_TO_BODY` / `WHENTOUSE_TOO_LONG` / `BODY_NO_WHEN_SECTION`。WARN 项：`DESC_OVER_BUDGET` / `WHENTOUSE_MISSING` / `WHENTOUSE_OVER` / `FRONTMATTER_MULTILINE` / `BODY_HAS_OLD_HEADING` / `DESC_LEN_NE_YAML` / `YAML_NOT_CHECKED`。
- **长度判定值写死在这里**：`description` **≤480 = ok**；**481~500 出 `DESC_OVER_BUDGET` 警告**（还没被截断，但已无余量）；**>500 判 FAIL `DESC_OVER_TRUNCATION`**（目录里实际只剩前 497 字符 + `...`）。`whenToUse` >160 判 FAIL、>150 警告。
- **优雅降级**：找不到 `node` 或 `yaml` 包时，它打一整块 `WARN: YAML round-trip NOT performed (...) / THIS RESULT IS NOT TRUSTWORTHY`，每行 `yaml=SKIP` + `YAML_NOT_CHECKED`，末行再补一句"计数不可信"——**绝不静默跳过**（静默跳过＝再造一个假 OK）。yaml 包默认找 `~\.dsh\profiles\node_modules\yaml`，可用 `-YamlModule <路径>` 换。
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
     `node -e "const fs=require('fs'),Y=require('C:/Users/admin/.dsh/profiles/node_modules/yaml'),p=process.argv[1],r=fs.readFileSync(p,'utf8'),s=r.indexOf('\n')+1,e=r.indexOf('\n---\n',s);try{const d=Y.parse(r.slice(s,e));console.log('YAML OK  name='+d.name+'  desc='+d.description.length)}catch(x){console.log('YAML FAIL  '+x.message.split('\n')[0])}" "$env:USERPROFILE\.dsh\skills\<skill>\SKILL.md"`
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

1. **改完 / 新建 skill 后，验收判据只有一条：它出现在本会话的 skill 目录里**（对照系统提示里那份 skill 目录）。表里 `status=ok`、末行 `FAIL=0`、`skill` 工具能按名字加载，都只是辅助证据，**都不能替代「目录里有它」**。没出现时**先跑本校验器**（现在含 YAML round-trip，见 §4）：看 `yaml` 列是不是 `FAIL`、`issues` 里有没有 `YAML_UNPARSEABLE(...)`；若 `yaml=SKIP`，说明 round-trip 压根没跑，**那次结果不可信**，先修好 node / yaml 再下判断。判存在看磁盘、判可用看目录（第 5 条）。
2. **改已有** SKILL.md → 会话 skill 目录下一步就刷新（first-party `write`/`edit` 让 provider 失效，**无需重启**），且 description 就是刚写的那一行。
3. 用 `skill` 工具按名字加载一次，正文可读、frontmatter 没写坏。
4. 目录没出现 → 依次查：**frontmatter 能否 YAML 解析**（坑 2，最容易漏、也最常见的真因）、目录名是否 kebab-case、是否在扫描根的一层内、`name` 是否与目录名一致（F7）、是否误写了 camelCase 旧键（F8）。
5. **「不在目录里」≠「磁盘上没有」——收录的唯一门槛是 frontmatter 能否解析成功**
   - **已被证伪的旧断言**：本 skill 曾据 2026-09-28 的观测，把「新建 `dsh-skill-authoring` 后连续 3 次目录重发（均由其它 skill 的 description 变更触发）都不含该条目」判为「**新建目录会延迟收录，只有新建目录有这个问题，需要重开会话**」——**该推断是错的**。真因是它自己 description 里有一个半角 `: `（见坑 2），YAML 解析抛错 → 加载器丢弃整条；而当时校验器报 `ok`（不做 YAML round-trip），所以"磁盘上 frontmatter 完全合规"这个前提本身就是假的。**与"新建目录 / 要重开会话"无关。**
   - **同轮反证（磁盘时间戳：`dsh-agent-customization` 2026-09-28 15:51:37 落盘，与上面那次观测**同一天**）**：新建该目录后**当轮**它就进了会话目录（两次 write 各触发一次重发），`skill("<name>")` 按名加载正文完整；同一天把本 skill 的 frontmatter 修好，目录在**下一步**的重发里就收录了本条目。→ 旧记录里那"3 次重发都不含该条目"**不是新建目录的锅**，差别只在文件能不能解析。**改 frontmatter 与新建目录都是下一步生效，无需重开会话。**
   - **存在性判据**：要判某 skill 在不在，看磁盘（`Get-ChildItem <skills根> -Directory`），**别拿会话目录当存在性 oracle**；跨引用（正文里写「→ 用 X」那种）同理——目录里没有 `X` 只说明 `X` 现在解析/加载不了，不说明 `X` 没写过。

## 8. 第二个 oracle：证明「只改了允许改的地方」

批量改 skill 时，「技术正文零改动」既不能靠眼看，也不能靠行对齐 diff——在文件中间插入一段会让其后每一行都错位，`Compare-Object -SyncWindow 0` 能把几百行全报成 diff，得出**看起来像被大改**的假结论。正确做法是**先剥掉两侧的「允许改动区」，再整块比较**：

1. 改前整目录备份：`Copy-Item "$env:USERPROFILE\.dsh\skills" <备份目录> -Recurse -Force`
2. 剥掉 frontmatter；再从旧正文删除 `## 触发条件` 段、从新正文删除 `## 何时调用` 段（删到下一个 `## ` 之前）
3. 把两侧**各自 join 成一个字符串，用 `-ceq` 整块比较**——相等才算零改动
4. 只有不相等时，才用 `Compare-Object` 去**定位**具体行，不要用它下结论

`diff-skills.ps1` 就是这套流程（本目录内，参数 `-Backup <备份目录>`），逐 skill 打印 `exact=True/False`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<本目录>\diff-skills.ps1" -Backup "<备份目录>"
```

预期所有行 `exact=True`。`exact=False` 只允许出现在两类文件上：**被明确授权重构过**的文件、以及**有外部并发写入者**的文件。

### 并发写入者（真实风险）
2026-09-28 实测：同一批文件里有一个 SKILL.md 被**另一个会话**整体改写（+79/−38 行，引用了当天新建的目录），此时对它做「备份 diff」会把**别人的改动**算成你的。→ 动多个 skill 之前先确认没有别的写入者；发现可疑改动时，**先停下并去问用户**，不要回滚、也不要"顺手修正"。

> 出处：本 skill 的规范素材来自 `D:\workspace\agent\skill\_recon\skill-when-to-call-standard.md`（F1–F8 / R1–R9 / 消歧矩阵），两个校验脚本原件为同目录 `check-skill-frontmatter.ps1` 与 `diff-skills.ps1`（本目录是复制件，均可独立运行）。

## 9. 目录成本与 hot/warm 两层（2026-11-12 实测）

**目录不是免费的**：`@deepseek-ai/dsh-tool-skill` 在 `agent/pre-step` 里把整个 skill 目录作为一条 **user 消息**注入会话
（source kind = `skill-catalog`），内容是逐条 `- `name`: description`。它按 digest 只在**目录变化时**重发，但一旦进了历史，
后续每个请求都要带着它。本项目实测：58 个 skill、description 平均 411 字符 → 目录行合计 **25,383 字符**（≈8-9k tokens/请求）。

**两层（DSH 原生，不需要改宿主）**：

| 层 | frontmatter | 目录 | 模型可用性 |
|---|---|---|---|
| hot | 普通 | 每条一行，计入每次请求 | `skill` 工具可加载 |
| warm | `disable-model-invocation: true`（+ `warm-triggers` / `warm-reason`） | **不进目录，零成本** | `skill` 工具**拒绝**（`is not available for model invocation`）；用 `read` 读文件即可 |

加载器源码依据：`dsh-skill-filesystem/lib/index.js:863-870`（`parseInvocationPolicy` 读 `disable-model-invocation` / `user-invocable`）、
`dsh-tool-skill/lib/index.js:944`（`snapshot.skills.filter(isModelInvocable)`）、`:875`（非 model-invocable 直接报错）。

**预算（本机插件 `dsh-plugin-sediment` 强制执行）**：热目录 ≤40 条、目录行合计 ≤7000 字符、单条 description ≤120 字符；
超出时 `distill_skill` 拒绝 `new`，提示改用 `merge` 或 `tier=warm`。写 warm 时插件自动更新
`%USERPROFILE%\.dsh\skills-archive\INDEX.json`，`skill-archive` skill 负责按需查表。

**改层的方法**：

```yaml
# hot → warm：在 frontmatter 的 --- 前插三行
disable-model-invocation: true
warm-triggers: "一行触发词，进冷备索引"
warm-reason: "为什么冷备（过期/低频/兴趣）"

# warm → hot：删掉这三行，并把 description 压到 <=120
```

**`catalogDescriptionMaxLength` 不是可靠的止血阀**：它是 `@deepseek-ai/dsh-tool-skill` 的 config（默认 500，超过就截断为前 497 +
`...`），而在 `standard` preset 里 `tool-skill` 是 preset 声明内部的一行，profile patch 按顶层 id 覆盖不到它；要改只能覆盖
`preset-standard` 整段声明（会跟官方升级漂移）。**所以真正的纪律是每条 description 自己写短，而不是靠截断。**

**实测收益**：56 个 skill（2 个已废弃移出）→ 36 hot + 22 warm，目录行合计 25,383 → **4,519** 字符（本地部分，-82%），
热条目平均 description 411 → 125 字符。冷备条目仍可按索引加载，不丢能力。

## 10. 跨 harness 分发（DSH ↔ ChatGPT / Codex）

**结论：不做格式转换，做「标准形态的副本」。** DSH 与 ChatGPT/Codex 都吃 Agent Skills：`<name>/SKILL.md` + 六字段 `name`/`description`/`license`/`compatibility`/`metadata`/`allowed-tools`。差异只在"多出来的键"和"放哪"。

### 10.1 三条硬事实（源码 + 实测）

1. **DSH 原生就读 `~/.agents/skills`**：`agentsHome` 默认 `~/.agents`（`DSH_AGENTS_HOME` 可覆盖），源码注释写明它是"与其他 agent 工具共享"的根（`dsh-home-paths/src/index.ts:21,142-152`）。
2. **重名按 rank 取胜**：`<repo>/.dsh/skills`(100) < `<repo>/.agents/skills`(200) < custom(300) < `~/.dsh/skills`(400) < `~/.agents/skills`(500) < bundled(600)；败者只写一行 `ignored because a higher-priority skill already exists`（`dsh-skill/src/index.ts:567-582,807-811`）。
   ⇒ 真源留 `~/.dsh/skills`、标准副本落 `~/.agents/skills`，**DSH 目录成本一条不涨**（同名被 rank 400 影子覆盖），warm 仍是 warm。
3. **DSH 宽松、别家严格**：DSH 对未知顶层键**静默忽略**；Claude Code 直接拒载，原文 `Unexpected key(s) in SKILL.md frontmatter: argument-hint. Allowed properties are: allowed-tools, compatibility, description, license, metadata, name`。⇒ **不能 symlink 直通，必须剥键**。

### 10.2 导出必须做的三件事

- **剥掉所有非标准顶层键**：`whenToUse`、`disable-model-invocation`、`warm-triggers`、`warm-reason`、`version`、`tags`…；要留私有信息就塞 `metadata:`（它是标准字段）。
- **形状**：`name` 必须**等于父目录名**、kebab、≤64；`description` 折成物理单行、≤1024，按 **200** 保守写（claude.ai 口径）。
- **只导"换 harness 还能用"的**：含 `D:\`、`~/.dsh`、内网/ssh、Ascend/NPU/CANN、凭据的 skill **一律不导**——对方没有那台机器，搬过去只会让模型照旧路径编命令。本机 64 个里 portable 只有 10 个。

### 10.3 一键做法（已跑通，脚本在本机）

```powershell
cd D:\workspace\agent\skill\cross-harness
.\sync-agents-skills.cmd                     # 仅当「要让 Codex 看见」时才跑（默认不跑，等价于 --prune；--check 只查不写）
python .\render_agents_skills.py --dry-run     # 看计划：new/update/same + 被丢弃的键
python .\render_agents_skills.py --prune       # 写 %USERPROFILE%\.agents\skills
python .\render_agents_skills.py --check       # 有漂移 exit 1（可挂计划任务/回合钩子）
python .\render_agents_skills.py --zip-dir .\out\chatgpt-upload   # 要网页/手机时再打 zip
```

脚本按 `.render-manifest.json` 记每个文件的 sha256，`--prune` **只删「自己写过且一字未改」的目录**（`~/.agents/skills` 是共享目录，别人写的不碰）；产物用 DSH 同一套 JS `yaml` 解析验证过（UTF-8 无 BOM、LF、只剩 name+description 两个键）。

### 10.4 边界

- **ChatGPT 网页/移动端**要 workspace Skills（Business/Enterprise/Edu）或 plugin；**桌面 app / Codex CLI / IDE 直接读 `~/.agents/skills`，零上传**。Custom GPT 2026-12-11 退役，别走那条路。
- **反向是免费的**：往 `~/.agents/skills` 丢标准 skill，DSH 不用配置就能用（rank 500）。
- OpenAI 对未知顶层键是否硬拒**未证实**（官方只说"按 Agent Skills 规范校验"）→ 按严格清洗走，不赌。
- 完整方案与全部取证：`D:\workspace\agent\skill\cross-harness\README.md`。

## 11. 跨 harness 副本：默认关，按需开

**上一节讲"能不能共享"，这一节讲"该不该默认共享"——答案是：不该。**

- `~/.agents/skills` 是**共享的用户级目录**：Codex / ChatGPT 桌面 app 把它当自己的 skill 源。一旦把 DSH 的 skill 放进去，影响是**双向**的——你给它的它全收，而且这些条目的 `name`+`description` 会注入它**每一次请求**（吃它的上下文预算），正文还会改变它的行为。**没有"只让 DSH 导出、不让对方接收"的单向模式。**
- 所以「后台常驻同步 / 一次性部署好就一直开着」是错的做法：共享必须 **opt-in**。落地前先明确问用户或自己确认——「另一套 harness 要不要看见这些 skill？」不要因为"技术上能共享"就默认开。
- 开：`.\sync-agents-skills.cmd`（= `render_agents_skills.py --prune`）。关：`rmdir /s /q "%USERPROFILE%\.agents"`。产物全部可再生，删掉不丢东西。
- **删之前先核对**：目录里只能有本流程写的条目（用 `.render-manifest.json` 对一遍），别误删别人或别的工具放的 skill；`~/.agents` 若是这次才建的空壳，连壳一起删才算真正回退。
- 回退时把"默认关"这件事同时写回文档和包装器（`.cmd` 头注释 + 末尾提示改成 `ENABLED … Codex WILL now see these skills`），否则下次双击只会以为是在"刷新"。
- 只把门开给"确实要跨端用"的少数几条方法论 skill；把绑本机的运维 skill（内网、NPU、`~/.dsh`、凭据）一起推进去，等于给另一套 harness 灌无关上下文，比不放更糟。

## 交接给另一个 harness（codex 等）：逐字节底本 + 只读审计 + 更正表

触发信号：用户要把一批知识/skill 交给另一个 harness（codex、ChatGPT 等）做「信息提取 + 沉淀」，或要求「保证材料正确性」。这是本 skill「跨 harness 分发」的**可信底本**支线：先交出可机械校验的原文，再谈清洗与改写。

## 三条硬规则

1. **正文零转述**：材料正文必须是逐字节副本，正确性靠哈希校验，不靠 LLM 复述（复述必然引入漂移）。
2. **两件套**：`MANIFEST.sha256`（兼容 `sha256sum -c`，行格式 `<64hex>  <相对路径>`，两个空格）+ 机械生成的标题树（带行号）才让人能按行跳读原文。
3. **会话专属数字不进材料**：路径、日志、临时 commit 留在报告/`evidence` 里；材料只收「值 + 记录日期 + 出处」。

## 步骤（真跑通过）

1. **Python 写脚本**（不要 `.ps1`，本机执行策略 Restricted）：`shutil.copyfile` → 算源/副本 sha256 并断言相等 → 生成 `MANIFEST.sha256` / `PROVENANCE.md`（源绝对路径、字节、mtime、hash）/ `INDEX.md`。
2. 标题树抽取：逐行匹配 `^(#{1,4})\s+`，遇到 ``` 围栏翻转开关、**围栏内的 `#` 不算标题**；输出「行号 | 级别 | 标题」表格。
3. **独立 verify 脚本**（与 build 分开写，避免自证）：重读 MANIFEST → 重算 hash → `filecmp.cmp(src, dst, shallow=False)` 逐字节比对 → 顺带扫 `credentials.txt`、`*.pyc`、`__pycache__`。
4. **只读审计**：每个子代理 1~2 个 skill，统一五节（时间敏感事实 / 交叉引用是否真存在 / 源文自标「未验证」项 / 矛盾与笔误 / 抽查确认项），每条带 `文件:行号`，返回 ≤40 行，正文落独立 notes 文件。
5. **编排者复核**：把能机械判的结论自己再验一遍（算式、HEAD 探测、grep 行号、实登）。本轮 6 份审计里只有 12 条进了「已复核更正表」，其余在汇总表里明确标「未由我复核」。
6. **交付分层**：`README`（是什么/怎么用）→ `CAVEATS`（时效 + 缺陷 + 更正表）→ `QUICKREF`（速查，每条带出处）→ `INDEX`（机械索引）→ `AUDIT-INDEX`（谁验过什么）。

## 坑

- **源文件会在快照期间被别人改**：本轮 `SKILL.md` 被追加一节（121→144 行）。⇒ 复制后记录 as-of 时间；交付前按 mtime 复检一次，变了就重建，否则清单与源不一致。
- **重跑生成脚本会覆盖手工修正**：`INDEX.md` 里手工改过的错字，重建后被脚本再次写回。⇒ **改生成脚本，不改产物**。
- **PowerShell 5.1 不支持范围数组**：`foreach($r in @(224..232,346..352)){...}` 报「无法将 System.Object[] 类型的值转换为 System.Int32」。⇒ 打行号区间用 Python，别用 PS。
- **源 skill 可能自带明文口令**（本轮某 `SKILL.md:31` 里有 .190 的 root 口令）：`credentials.txt` 可以排除，但正文里的删了就不再逐字节一致。⇒ 保留原文 + 置顶告警 + 建议轮换；给自家散文脱敏时，按凭据文件第 3 列做精确字符串替换（不要用正则猜）。
- **别信子代理"我验过了"**：抽查它给的 `file:line` 是否真存在（本轮 48 条引用逐条 grep 全中，才有资格写进更正表）。
- 更正表里写明「源文说法 → 我的证据 → 沉淀时怎么写」，并保留原值：审计者动过手的地方（HEAD/算术/实登）才是结论，没动过的只能标线索。

## 验收

`sha256sum -c MANIFEST.sha256` 全 OK；独立 verify 0 problem；更正表每条都有可重复命令；文档中不出现会话专属路径与日志；审计结论与「我复核过的」在结构上分开。

未验证：随材料给出的 PowerShell 版逐行校验代码没有在本轮实跑（实跑的是 Python verify）；`sha256sum -c` 依赖 git bash/WSL，未在纯 Windows 上验证。

## 接手另一个 agent 刚改过的 skill：先对账，再只补缺口

触发信号：用户说「我刚让某个 agent 更新了 X（脚本/章节），你把这块加进 skill」「这个改动同步到 skill 里」，或发现 `~/.dsh/skills` 里某个文件被外部进程改过。**默认先假设它可能已经写进去了** —— 直接新开一节是最常见的重复正文来源。

## 对账（先花 2 分钟，别写）

```powershell
git -C $env:USERPROFILE\.dsh log --oneline -4 -- skills/<name>   # 谁在什么时候动了它
git -C $env:USERPROFILE\.dsh show --stat <sha>                   # 改了哪几个文件、+/- 多少行
git -C $env:USERPROFILE\.dsh status --short -- skills/<name>     # 还有没有未提交的
```

`~/.dsh` 有自动快照提交，所以「外部改动」通常就是一个 `auto <日期时间>` 的 commit，能直接看出新增了哪个脚本、正文加在哪几行。再 `Select-String -Pattern '^## '` 看新增章节落在第几节、是不是已经覆盖了用户描述的内容。

## 已经写过了怎么办（本次实际走的路）

1. **逐条比对「用户/脚本说法」与「文档说法」**：脚本里的命名空间清单、判定条件（按路由反查还是写死 ifIndex）、日志路径、幂等语义、跳过分支，一条条核。文档通常缺的正是**脚本内部行为**（日志在哪、没提权会怎样、哪个分支会 SKIP）。
2. **只补缺口，并在两处加指针**：一节正文（`### <脚本自身的行为>` 这类子节，挂在已有 H2 下）+ 工具清单里的一行入口（`## 用脚本操作` 之类）+「何时调用」的一条触发。**不要新开 H2**——同一事实只留一份正文。
3. 用户描述与脚本不一致时以脚本为准（它是真跑的东西），把差异写进正文而不是照抄用户措辞。

## 只读复核"它真的生效了"

改文档前先确认机制在工作，否则会把「照文档写的」当成「已验证」：

```powershell
Get-DnsClientNrptRule | Select Namespace,NameServers
Get-DnsClientServerAddress -AddressFamily IPv4 | ? { $_.ServerAddresses.Count -gt 0 }
curl.exe -s -o NUL -w "http=%{http_code} tls=%{time_appconnect}s`n" --max-time 15 https://<目标>/
```

判据用**返回码 + 握手耗时**这类可对照的量，别用「打开网页看看」。文档里若写了预期值（如 `401`、`tls≈0.26s`），实测撞上才算对齐，撞不上就改文档。

## 改完的校验清单

- `git -C ~/.dsh diff --stat -- skills/<name>`：只有预期文件、行数与预期一致。
- 自己 parse frontmatter：开头 `---` 闭合、`name`/`description`/`whenToUse` 三键在、`description` 单行且 <=120 字符、**文件无 BOM**（`open(p,'rb').read()[:3] == b'\xef\xbb\xbf'` 必须 False）。
- 重复标题：`Select-String -Pattern '^### <新标题>'` 只能命中一次。
- 改动约 2 分钟内会被 `skill_publish` 自动发布，别手工再推。

## 坑

- **`dsh_guard.py verify --dir <skills>` 的 PASS 不能当验证通过**：本轮它对 `~/.dsh/skills` 报 `skill 0 个 | frontmatter 坏 0` 然后 `结论: PASS` —— 它没数到任何 skill，等于什么都没验。frontmatter 自己 parse 一遍。
- 别把「用户说 agent 改过」当成「skill 里还没有」：先 `git log`，否则你会在已有章节旁边再写一遍，两处真相从此不一致。
- 补正文时最容易漏的是**幂等/跳过分支**与**日志位置**——这两样恰恰是下次排障最先要用的。
- 改 `.ps1` 不归这里：脚本编码（BOM）、执行策略、`-Verb RunAs` 参数集等坑走 `pwsh-on-windows`。

## 验收

用户问「加进来了吗」时，能回答三件事：它在 skill 的哪一节（行号）、与脚本逐条对得上、以及只读命令拿到的实测值。
