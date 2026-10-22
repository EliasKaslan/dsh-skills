---
name: pwsh-on-windows
description: 本机命令行（pwsh 实为 Windows PowerShell 5.1，非 PS7）——默认按 GBK 解码、写 BOM、PS7 语法是解析期错误，一整套静默坏结果：中文乱码、行数/CR 数少算或暴增、skill frontmatter 被 BOM 毁掉、整段脚本一行不执行（Out-String/Measure-Object -Line/Set-Content 各有一坑）。适用于"中文乱码 / 行数或 CR 数对不上 / .ps1 或 npx 被执行策略拦 / 计数总是 0 / 目录看着空其实不空 / PS7 语法报错 / python 传 JSON 报 Expecting value / icacls 后报 WinError 5 / 重定向输出被判 binary / ssh 内联命令里引号内管道被吃掉 / node -e 引号被剥掉 / diff 整文件全异"。不适用：远端 Linux → 用 `ascend-env`；skill frontmatter 契约 → 用 `dsh-skill-authoring`。
whenToUse: 本机用 pwsh 工具跑命令、读写文件、统计行数/字符/CR、发 HTTP 或写脚本（尤其涉中文、换行、编码、引号、PS7 语法）时使用；**给 node/python 内联传含双引号的脚本或 JSON 时必读**（裸 `-e`/`-c` 的引号会被剥掉）。模型看不到本节。
---

# 本机 PowerShell 正确用法（工具名 `pwsh`，实为 Windows PowerShell 5.1）

## 何时调用

**加载本 skill 当：**
- 命令要读写文件，或统计行数 / CR 数 / 出现次数，而数字**看着不对或明显偏小**时；或 `Get-ChildItem` 的**输出为空**、你正要据此判"目录是空的 / 没有那些文件"时（`-File` 不递归 + 1985 假 mtime，见陷阱表"目录看着空其实不空"行）。
- 要发 HTTP 请求（尤其**写操作**会把中文写进远端）时。
- `.ps1` 被执行策略拦下、脚本报 `Unexpected token`、或整段脚本"什么都没干"时。
- 拿不准某个写法在本机能不能用——`pwsh` 工具**跑的是 Windows PowerShell 5.1**（**注意：错的是"工具解析到的不是 PS7"，不是"本机没有 PS7 二进制"**，见下方"一句话结论"与"环境事实"表），网上抄来的写法很多属**解析期**错误。
- 要给原生程序（`node` / `python`）**内联**传含双引号的脚本或 JSON 时（裸 `-e` / `-c` 的引号会被剥掉，甚至只造成**静默错结果**；`node` 唯一可靠的单行形态见陷阱表「`node --% -e`」行）。

**不要用本 skill（转交）：** 见文末「何时不用本 skill」。任务本体是下面这些时，直接去对应 skill：
- 要向 GitCode 社区仓提 / 修 PR（门禁、标签、backport） → 用 `gitcode-pr-flow`。
- 向 GitHub 上游仓提 PR（token / DCO / CI 判读） → 用 `github-pr-flow`。
- 上游仓库 docs 刷新审计（内部需求 vs docs 缺口） → 用 `upstream-docs-refresh-audit`。
- 新增 / 移动 vllm-ascend e2e 用例进 CI → 用 `vllm-ascend-e2e-ci-wiring`。
- AI 厂商官方信息源的真伪 / 覆盖面判定（含用 HF API 字段判"是否已发布"） → 用 `ai-vendor-official-source-audit`（它只把本 skill 的"`Select-String -SimpleMatch` 的 `Matches.Count` 恒为 0"当指针引用，该坑的归属与写法仍在本 skill — 见上表）。
- 韩国（济州）官方一手信息源抓取（本机直连通道只是工具，站点点位与端点配方在那边） → 用 `korea-official-source-research`。
- 接管 Outlook.com 邮箱（M365 MCP discovery、设备码登录） → 用 `outlook-mailbox-control`。

**前置**：无（本 skill 只描述本机既有事实）。 ／ **后继**：修完命令回到原任务；若这个坑是在改 skill 的过程中踩的，收尾按 `sedimenting-skills`。

## 环境事实（2026-09-29 实测，决定了下文所有结论）

| 项 | 实测值 |
| --- | --- |
| `$PSVersionTable.PSEdition` / `PSVersion` | `Desktop` / **`5.1.26100.9444`** |
| `Get-Command pwsh`（PATH 上有没有 PS7） | **`False`** —— 工具名叫 `pwsh`，跑的其实是 `powershell.exe` |
| `Get-ExecutionPolicy` | `Restricted`（`.ps1` 直接跑会被拦） |
| `[Console]::OutputEncoding` / `$OutputEncoding` / `chcp` | `utf-8` / `utf-8` / `65001`（**输出的**码页是 UTF-8） |
| `[Text.Encoding]::Default` | **`gb2312`**（ANSI 码页 936）——**这才是 `Get-Content` 读文件的默认编码**。它与输出码页不一致，是本页绝大多数坑的根因 |
| `Get-ExecutionPolicy -List` / `git config core.autocrlf` | 5 个作用域全 `Undefined` → 有效策略 `Restricted` / `true` |
| `powershell.exe` | `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` |

**一句话结论**：`pwsh` 工具**实测解析到 Windows PowerShell 5.1**（`Desktop 5.1.26100.9444`）——**别把这条读成"本机没有 PS7"**：树里**确实有** PS7 二进制 `D:\workspace\agent\dsh_base\.dsh-run\ps7\7.6.6\pwsh.exe`（**存在且可直跑，回 `7.6.6`**，`PSEdition=Core`），只是**工具不使用它**（`Get-Command pwsh` 在 **PATH 上**为 `False`，见上表）⇒ 任何 PS7 才有的写法要么报"参数不存在"，要么（三元那种）是**解析期**错误、让整段脚本**一行都不执行**。任何涉及中文、换行、字节的操作都必须**显式指定编码**。

## 铁律（写命令前先过一遍）

1. **读写文件、数行数、数 CR、做文本处理 → 一律交给 Python**，别用 PowerShell 的文本 cmdlet。Python 必须带 `$env:PYTHONIOENCODING='utf-8'`，并用 `io.open(path, encoding='utf-8', newline='')`。
2. **写脚本写 `.py`，不写 `.ps1`**，**给 Python 传复杂字符串也一律写 `.py` 文件、不要内联**（执行策略 `Restricted`；要跑现成 `.ps1` 得 `powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1`，别改全局策略）。**内联 `python -c "…"` 的静默杀手**：PS 5.1 双引号串里**反引号是转义符** ⇒ 模式里被反引号包住的引用会被**吞掉**，报 `SyntaxError: '[' was never closed` 一类解析错，或**静默给 0 计数**（本轮两个子代理先后踩到）；确要内联就改走 stdin：`$c=@'…'@; $c | python -`。
3. **中文优先放进文件再用 Python 读**（不依赖外层调用链的编码）——注意实测：本机 `chcp=65001`，**命令串里带中文其实不乱码**（`echo '中文'` 原始字节 `E4 B8 AD E6 96 87 0D 0A`）。真正会乱的是**非 UTF-8 保存的 `.bat`/`.cmd`**（GB2312 存的 `.bat` → `����`）。所以「放文件」是稳妥偏好，不是「命令串必坏」。
4. **读文件带 `-Encoding utf8`**（不带就是 ANSI/GBK），但它**只保证内容不乱码、不保证行数对**（实测仍少算，见陷阱表）；**写文件用 `UTF8Encoding($false)`**，绝不用 `Set-Content -Encoding utf8`（它写 BOM）。**要把程序输出重定向到文件，整条命令交给 `cmd /c "... > f 2>&1"`**——PS 自己的 `>` 写 UTF-16（带 NUL），下游会把产物判成 binary。
5. **判"存在/没有/数量"要显式计数**（`.Count` / `-ExpandProperty`），**不要肉眼看表格**——表格的空白表头容易被误读成"没有结果"，也别用过滤后的空结果推断"不存在"。**判"目录是否为空 / 里面有没有文件"必须带 `-Recurse`**：`Get-ChildItem <dir> -File`（`-File` 只过滤类型、**不改变递归深度**）对"文件都在子目录里"的目录会给出**空数组且不报错**；再叠加打包产物常见的**假 mtime**（文件写成 1985，真值只在目录 mtime 上），"看目录时间"也会失灵。正确写法见陷阱表"目录看着空其实不空"行。
6. **别用 PS7 语法**：三元 `? :`、`??`、`-AsByteStream`、`-Encoding utf8NoBOM`、`Format-Hex -Count`。
7. **`try/catch` 只抓终止错误**，判失败要配 `-ErrorAction Stop`；`try` 是语句不是表达式，只能用 `$(try{}catch{})`。

## 陷阱表（逐条为本机实测，含错误原文）

| 现象 | 机制 | 实测证据（原文/数字） | 正确写法 |
| --- | --- | --- | --- |
| 读 UTF-8（无 BOM）文件中文乱码——**并会被误判成"文件被写坏了"** | `Get-Content` 默认按 **ANSI/GBK** 解码 | 前端元数据显示为 `涓?Ascend/MindSpeed-Ops 浠?..` | `Get-Content $f -Encoding utf8`。**判"文件坏没坏"必须走字节**，别信终端里那串乱码：`[Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($f))`（或先 `-Encoding utf8` 重读）。本轮实测：**完全正确**的 UTF-8 无 BOM 文件，正确内容 `## 何时调用` 被显示成 `## 浣曟椂璋冪敤`，加 `-Encoding utf8` 即正确 ⇒ 乱码是**显示层**的，不是文件损坏；而 `-Encoding utf8` 只保证不乱码、**不保证行数对**（见上一行） |
| **行数少算 / 行错位**（最危险，无任何报错；**带 `-Encoding utf8` 也会**） | ① GBK 是双字节编码，**把多字节 UTF-8 序列的尾字节当引导字节**，于是把 `0x0A` 当尾字节吞掉 → 多行并成一行；② 即使 `-Encoding utf8` 仍会数错（实测真实 **250** 行的 md 文件给 **249**，且 `Select-Object -Last 8` 漏行/整段错位；该文件含 `\|` 表格行与 `├──` 树形行，疑与多字节边界相关，机制未定论） | 逐字节取证：文件里 `0x0A` 共 **458** 个，UTF-8 解码后 LF 字符 **458** 个，**GB2312 解码后只剩 289 个**；故 `.Count` = **290** 而真实 = **458**（同一文件在会话中被改写过，前一版实测 289 vs 456，结论不变）。我据此误测的"空行 23"同样是假值 | **数行数一律交给 Python 二进制读并自己解码切分**：`open(path,'rb').read().decode('utf-8').split('\n')`（跑 Python 带 `PYTHONIOENCODING=utf-8`）；PowerShell 的 `-Encoding utf8` 只用于**看内容**。`[IO.File]::ReadAllLines($f).Length` 未验证：没做过 250 行用例对照，别当行数判据 |
| `Measure-Object -Line` 也不等于行数 | 它**跳过空行** | 受控文件（8 文本 + 2 空行，共 10 行）→ **8**；456 行文件（84 空行）→ **372** = 456 − 84 | 数行数用 `.Count`；一定要用它就先 `-Raw` 压成单字符串（实测受控文件给 **10**） |
| 管道后 CR 数暴增，"每个文件都有 CR" | `Out-String` 对**数组**输入**逐行插 CRLF** | 5 个元素 → **5** 个 CR；同样内容 `-join LF` → **0** | 判 LF/CR 用二进制读或 `git ls-files --eol`，**绝不用管道统计** |
| 写出的文件被 read 工具判为 binary | **PowerShell 的 `>`** 写 UTF-16；`cmd /c echo` **不**写 UTF-16（因 `chcp=65001` 写 UTF-8 无 BOM） | `"中文" > f` → `FF FE 2D 4E 87 65 0D 00 0A 00`（UTF-16LE+BOM）；`cmd /c "echo 中文 > f"` → `E4 B8 AD E6 96 87 20 0D 0A`（UTF-8 无 BOM）。**实测踩到**：`git grep ... > out.txt`（PS5.1 直接重定向）后再用 read 工具读 `out.txt` → **判为 binary file**（UTF-16 带 NUL）；改用 `cmd /c "git grep ... > out.txt 2>&1"` 拿到原始字节即可正常读 | 二进制写才可控；**要重定向原生程序输出时把整条命令交给 `cmd /c`**（跨进程，绕开 PS 的 `>`）；要自己落盘文本就用 Python `io.open(p,'w',encoding='utf-8',newline='')`（**无 BOM、LF 可控**）；`\| Out-File -Encoding utf8` **仍带 BOM**（`EF BB BF`） |
| **写出的文件带 BOM，前端元数据解析失败** | PS 5.1 的 `-Encoding utf8` = UTF-8 **with BOM** | `Set-Content -Encoding utf8` → 首 3 字节 `239 187 191`（`EF BB BF`） | `[IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding $false))` → 实测首字节无 BOM |
| `.ps1` 不能跑；**`npx` 也一样**（被解析成 `npx.ps1`，同一根因，不是 npx 装坏了） | 执行策略 `Restricted`；PATH 上叫 `npx` 命中的是 `C:\Program Files\nodejs\npx.ps1` | 逐字原文：`... cannot be loaded because running scripts is disabled on this system`；跑 `npx` 时：`npx : File C:\Program Files\nodejs\npx.ps1 cannot be loaded because running scripts is disabled on this system.` | **调 node 生态工具改用 `npx.cmd`**（绕过 `.ps1` 解析），实测可抄写法（markdownlint，exit 0）：`cmd /c "cd /d <workdir> && npx.cmd --no-install markdownlint-cli@0.47.0 --config .markdownlint.yaml <file1> <file2>"`；**`.ps1` 一律首选改写成 `.py`**；不改任何持久设置的两种：`Get-Content x.ps1 -Raw \| powershell -NoProfile -Command -`（实测输出 `hi`）、`powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1`（仅本进程开关，实测输出 `hi`） |
| PS7 三元 `? :` | 5.1 无此语法，且属**解析期**错误 → **整段脚本一行都不执行**，`try/catch` **抓不到** | `Unexpected token '?' in expression or statement`；`$x = $null ?? 'b'` → `Unexpected token '??' in expression or statement` | 用 `if/else` |
| `-AsByteStream` | PS7 专有 | `A parameter cannot be found that matches parameter name 'AsByteStream'.` | 5.1 用 `-Encoding Byte` |
| `-Encoding utf8NoBOM` | PS7 专有 | `Cannot convert value "utf8NoBOM" to type "FileSystemCmdletProviderEncoding" ... Specify one of: Unknown, String, Unicode, Byte, BigEndianUnicode, UTF8, UTF7, UTF32, Ascii, Default, Oem, BigEndianUTF32` | 用 `UTF8Encoding($false)` |
| `Format-Hex -Count` | PS7 专有 | `A parameter cannot be found that matches parameter name 'Count'.` | 5.1 用 `[IO.File]::ReadAllBytes($p)[0..3]` |
| `try/catch` 明明出错却不进 catch | 只抓**终止**错误，非终止错误只写 stderr | `Get-Item <不存在>`：不加 Stop → `NOT-CAUGHT`；加 Stop → `CAUGHT` | `-ErrorAction Stop` |
| `try` 当表达式用 | `try` 是**语句**不是表达式 | `The term 'try' is not recognized as the name of a cmdlet, function, script file, or operable program.` | 放进 `$(try{}catch{})` 子表达式 |
| `Invoke-RestMethod` 读中文 JSON 乱码 | **仅当响应头缺 `charset` 时**才按 Latin-1 解码（不是"永远"） | 回环对照：`Content-Type: application/json` → `.desc` = `[ä¸ææè¿°]`；同内容加 `; charset=utf-8` → `[中文描述]`。实测 `api.github.com`（带 charset）**正常无乱码**。`Invoke-WebRequest` 的 `.Content` 同样中招 | 永远可靠：`[Text.Encoding]::UTF8.GetString($w.RawContentStream.ToArray()) \| ConvertFrom-Json` |
| 变量赋值报只读 | `$pid` 等是**只读自动变量** | `Cannot overwrite variable PID` | 换名（如 `$procId`） |
| 函数名叫 `GC` 后没调用到自己的函数 | **命令解析优先级 Alias > Function**：`GC` 是 `Get-Content` 的内置别名，先被匹配 | `Get-Content : Cannot process command because of one or more missing mandatory parameters: Path.`（`FullyQualifiedErrorId` = `MissingMandatoryParameter`）。带参数时才会出现 `Cannot find drive. A drive with the name 'https' does not exist`（取决于调用形式）。`Get-Command GC` 只回 Alias，**`-All` 才同时看到 Alias 与 Function** | 函数名避开内置别名（先 `Get-Command <name> -All`）；或显式 `& (Get-Command -CommandType Function GC)` |
| `"a\"b"` 这类转义 | PS 的转义符是**反引号 `` ` ``**，不是 `\"` | `Unexpected token ...` | 内层用单引号，或用 `` `" ``；复杂内容写文件 |
| **函数取名撞内置别名 → 整段脚本零执行 + 误导性参数错误** | 同上一行机制（Alias > Function），但报错**完全看不出是别名撞名**：别名 `RV` = `Remove-Variable`，你那段的参数被喂给了 `Remove-Variable` | 逐字原文：`RV : Cannot find a variable with the name '.pre-commit-config.yaml'. [Remove-Variable]`（一个**扫描/清点脚本**因为这一行什么都没跑，错误信息却指向一个文件名） | 函数名/变量名避开内置别名：先 `Get-Command <name> -All` 确认只回你自己的 Function；已踩到时改名（`RV` → `Get-RvList` 之类） |
| **目录"看着空"其实不空**（`-File` 不递归 + 1985 假 mtime） | `Get-ChildItem` **默认不递归**，`-File` 只过滤类型、**不改变递归深度** ⇒ 文件全在子目录时它回**空数组且不报错**；再叠加打包/解包产物里文件 mtime 被写成 **1985**（真值只在目录 mtime 上）⇒ "看目录时间"也失灵 | 实测 `D:\workspace\agent\dsh_base\artifacts\staged`：`@(Get-ChildItem $d -File -Force).Count` = **0**（本轮据此**误判**成"空目录"）；`@(Get-ChildItem $d -Recurse -File -Force).Count` = **50**、`(… \| Measure-Object Length -Sum).Sum` = **361865**；不带 `-File` 只列出 `a` / `b` 两个子目录（mtime `9/30/2026 2:34:24 PM`），而文件 mtime 一律 `10/26/1985 4:15:00 PM` | 判空/计数一律 `(Get-ChildItem <dir> -Recurse -File -Force).Count`（要连隐藏项一起数）；**目录 mtime 与文件 mtime 都可能骗人，只认显式计数**；父目录"看起来新"不代表里面有文件 |
| `Select-String -SimpleMatch -AllMatches` 数出现次数恒为 0 | `-SimpleMatch` 下 `Matches` 集合**恒空**（不是 null 而是空 `Match[]`） | 44 行全回 `0`；去掉 `-SimpleMatch` 同样写法得 `1,4,1,...` 共 **52**；`[regex]::Matches($t,'GitCode').Count` = **25**（真值）——`Select-String` 默认还**大小写不敏感**，会多算一倍 | 数次数：`[regex]::Matches($t,[regex]::Escape('X')).Count`；数行数：`(Select-String -Pattern 'X' -SimpleMatch -CaseSensitive).Count` |
| **发 JSON 时中文变成 `??`**（写操作会永久落库坏数据） | `-Body` 传**字符串**时按 ASCII/ISO-8859-1 编码 | 回环抓包：`-Body <string>` → `CL=16 HEX=7B 22 61 22 3A 22 3F 3F 22 ...`（中文→`??`）；`-Body <utf8 bytes>` → `CL=20 ... E4 B8 AD E6 96 87 ...`。**本地不报任何错** | `-Body ([Text.Encoding]::UTF8.GetBytes($json))` + `-ContentType 'application/json; charset=utf-8'` |
| 给原生程序喂 stdin 失败（如 `git credential fill`） | PowerShell 向原生子进程写 stdin 时**先注入 UTF-8 BOM** | 子进程 stdin 原始字节 = `EF BB BF 0D 0A` → git 报 `warning: invalid credential line:` / `fatal: unable to read credential from stdin`；用管道送同一份正确内容还会 `fatal: refusing to work with credential missing protocol field` | `Start-Process git -ArgumentList 'credential','fill' -RedirectStandardInput $req -RedirectStandardOutput $out -NoNewWindow -Wait`（实测 stdin 被正确解析） |
| **用 `icacls` 收紧 ACL 后，后续的 `os.replace()` / `MoveFileEx` 替换目标必然失败** | ACL 里的 **(R,W) 不含 DELETE 权限**，而替换一个文件需要**目标本身**的 DELETE 权限；写入（新建临时文件）当场不会报错，**下一次覆盖同一文件才炸** | 逐字原文：`PermissionError: [WinError 5] 拒绝访问。: '...\fake.token.json.tmp' -> '...\fake.token.json'`（第二次 `save_cache()` 起必现） | 收紧时给 **(F)**：`icacls <path> /inheritance:r /grant:r "$user:(F)"`；或对"替换"做成**自修复重试**（替换失败先补 `(F)` 再重试）。附带一坑：`"$env:USERNAME:(R,W)"` 报 `Invalid parameter "(R,W)"`（PS 把 `$env:USERNAME:` 当作用域变量名取空）→ 用 `($env:USERNAME + ':(F)')` 拼接 |
| **把 JSON 内联成命令行参数传给 python/node → 引号被 shell 剥掉，解析必炸** | PS 传原生命令参数会**剥掉内嵌引号**；`--args '{"top":3}'` 到子进程手里已不成 JSON。**与上面 stdin 那条是不同机制**（那条是 BOM 注入），但同属"跨进程传值必被外壳改写" | 逐字原文：`json.decoder.JSONDecodeError: Expecting value: line 1 column 2`；同一根因另一次表现为 `NameError: name 'Bad' is not defined`（`python -c @'...'@` 传多行代码）；还有 `error: unrecognized arguments: top\:3,\filter\:\hasAttachments eq true\}`（引号被剥 + 反斜杠被注入）；**内联 `python -c` 带韩文/引号/多行必炸**，另见逐字原文 `The string is missing the terminator: '.`、`Missing type name after '['.`、`SyntaxError: unterminated string literal`、`SyntaxError: invalid syntax`（`python -c @'...'@` 里写字面双引号时） | 三选一，**别内联**：① 复杂值一律写成 **`.py` / `.json` 文件**再跑（首选）；② 用 `@file` 形态读参数（实测 `--args @args.json`）；③ 传 **base64**（实测 `--pkg-args-b64`）。给原生程序喂 stdin 见上一行。**唯一的单行内联例外是给 `node` 传 `-e` 脚本，写法见下一行** |
| **裸 `-e` 给 `node` 传含双引号的 JS → 引号被剥掉、JS 被悄悄改写**（与上一行同一族：跨进程传值被外壳改写；本条给出**唯一可靠的单行内联例外**） | PS 5.1 拼原生命令行时**不转义内嵌的 `"`**，且 **PS 侧无论用单引号还是反引号转义都无效** ⇒ 子进程拿到手的 JS 已被改写；`--%` 让 PS **停止解析**该行、把余下内容按**字面量**整段交给原生程序，内嵌引号改由 node 自己的 argv 解析（所以**仍需写成 `\"`**）。**`--%` 之后不能跨物理行**——那是**解析期**错误 ⇒ **整段脚本一行都不执行** | node v24.18.0 实测，**同一句** `console.log("hi")` 四组：① 裸 `node -e 'console.log("hi")'` → node 实际收到 `console.log(hi)` → `ReferenceError: hi is not defined`，`exit=1`；② 裸 `-e` 改用 PS 反引号转义内层引号（写法 `` `" ``）→ **同样**被剥成 `console.log(hi)`、`exit=1`；③ `node --% -e "console.log(\"hi\")"` → 输出 `hi`、`exit=0`；④ `node --% -e "console.log(JSON.stringify('a\"b'))"` → 输出 `"a\"b"`、`exit=0`。跨行组：`node --% -e "const a = 1` + 次行 `console.log(a)"` → 逐字原文 `The string is missing the terminator: ".`（`ParserError` / `TerminatorExpectedAtEndOfString`，**整段脚本零执行**） | 单行内联只认 **`node --% -e "<JS；内层双引号写成 \" >"`**，且 **JS 必须压成一行**；多行 / 复杂 JS 仍写 `.mjs` 文件再跑（上一行的"别内联"判据不变）。**别只看有没有报错**：①② 是 `ReferenceError`（还看得见），引号被剥也可能表现为**输出内容悄悄变了** |
| 计数显示 0（或空），其实是取值失败 | `'{0}' -f $null` 输出**空白**而非 `0`；`Measure-Object -InputObject` 同时往 **stderr** 写非终止错误，只看 stdout 看不到 | `'{0} 次' -f $null` → `[ 次]`（len=2）；`(Measure-Object -InputObject @() -Sum).Sum` → `$null`；**且 `Measure-Object -InputObject @()` 对空数组报 `Count: 1`**，而管道写法 `@() \| Measure-Object -Sum` 报 `Count=0 Sum=0` | 空集合一律走管道：`@() \| Measure-Object -Sum`；输出前判空 `if ($null -eq $s) { 'N/A' }`；判失败加 `-ErrorAction Stop` |
| 内联 `-Command` 的双引号被父进程先展开 | 父 shell 先把 `$true` 展开成 `True`，子进程拿到 `if (True) { 'a' }` | `True : The term 'True' is not recognized as the name of a cmdlet, function, script file, or operable program.`（**不是** `Missing closing '}'`——那个在本机常见调用路径下未复现） | 父进程用**单引号** `powershell -Command 'if ($true) { ''a'' }'`（实测输出 `a`），或先把命令串存进变量再传 |
| `@" ... "@` 把 `$` 展开 | 双引号 here-string 同时展开 `$foo` 与 `$(1+1)` | `@"..."@` → `foo=BAR calc=2`；`@'...'@` → `foo=$foo calc=$(1+1)`（原样保留） | 要字面量用**单引号 here-string** `@'...'@`；含 `$` 的代码一律写文件 |
| `$pid` 等只读变量的错**能**被 try/catch 抓到 | 与 `Get-Item 不存在` 那类非终止错误不同，它抛的是终止错误 | `Cannot overwrite variable PID because it is read-only or constant.`；`(Get-Variable PID).Options` = `Constant, AllScope` | 换名 `$procId` |
| **`[IO.File]::WriteAllBytes($out, $r.Content)` 抛错，并把整份文件正文喷进异常消息** | `Invoke-WebRequest` 的 `.Content` 是**字符串**，不是 `byte[]`；PS 报"不能转换"时会把**待转换的那个值逐字打进消息** ⇒ 一行异常吃掉几万字符上下文 | 逐字原文（开头即文件正文）：`Cannot convert value "# SPDX-License-Identifier..." to type "System.Byte[]"` | 要落盘一律 **`Invoke-WebRequest -Uri $u -OutFile $path -UseBasicParsing`**（不经 `.Content`）；确实要字节就用 `-OutFile` 或 `[IO.File]::WriteAllBytes($p, [IO.File]::ReadAllBytes($tmp))` |
| **PS 5.1 的 `>` 重定向写的是 UTF-16LE** | 与"PS7 才有 BOM 问题"的直觉相反：5.1 的 `>` 直接写 UTF-16LE + BOM | 实测落盘首 4 字节 = `255,254,13,0`（`FF FE 0D 00`）⇒ 下游按 UTF-8 读全是乱码/被判 binary | 要 UTF-8 无 BOM 就**改用 Python 写文件**（`io.open(p,'w',encoding='utf-8',newline='')`），或把整条命令交给 `cmd /c "... > f 2>&1"`（见上表"写出的文件被 read 工具判为 binary"行） |
| **PS 5.1 函数体内 `Invoke-Expression ... \| Out-File` 之后 `$LASTEXITCODE` 为空** | 管道进 `Out-File` 后 `$LASTEXITCODE` 不再被填（本轮实测：生成的证据文件里每条都是 `EXIT=` 空值） | 本轮逐字现象：证据文件每行 `EXIT=`（值缺失），而进程其实正常退出 | **判退出码改用 Python**：`subprocess.run(...).returncode`，把它自己写进产物（本轮 `gen_evidence.py` 就是这么做的）；别在管道尾巴上读 `$LASTEXITCODE` |
| **`Start-Process -PassThru`（不带 `-Wait`）读回的 `.ExitCode` 恒为 `$null`，`[int]$null` = 0 ⇒ 所有失败被读成成功** | 不等待时进程尚未退出、`.ExitCode` 无值；PowerShell 把 `$null` 转 `[int]` 得 **0**，于是 `if ($p.ExitCode -ne 0)` 永不触发 | 本机实测（PS 5.1）：`$p = Start-Process cmd.exe -ArgumentList '/c','exit','3' -PassThru -NoNewWindow` → `$p.ExitCode` 为 `$null`（`isNull=True`）、`[int]$null` = **0**；**全程不报任何错**（失败被当成成功，与本表"`$LASTEXITCODE` 为空"同族） | 取子进程退出码**只用裸 .NET**（实测 rc=0 / rc=3 均正确）：`$psi = New-Object System.Diagnostics.ProcessStartInfo`；`$psi.FileName='cmd.exe'; $psi.Arguments='/c exit 3'; $psi.UseShellExecute=$false; $psi.RedirectStandardOutput=$true; $psi.RedirectStandardError=$true`；`$pr = New-Object System.Diagnostics.Process; $pr.StartInfo=$psi; [void]$pr.Start(); $out=$pr.StandardOutput.ReadToEnd(); [void]$pr.WaitForExit(15000); $pr.ExitCode`。**判据 = 显式 `WaitForExit(ms)` 之后再读 `.ExitCode`**；不要用 `Start-Process` 的 PassThru 对象读退出码（带 `-Wait` 时它才有值——**别赌这个差异**） |
| **函数里的诊断字符串被调用方的 `$x = f` 静默吞掉 ⇒ 屏幕上一条都不剩，看着像"审计跑完了、什么都没发现"** | `return $x` **不是"返回一个值"**，而是"**把 `$x` 写进 success 输出流并停止**"；函数体内此前发出的**每一个未被消费的对象**（包括每行裸字符串 `"…"`）**都已经在同一个 success 流里** ⇒ 调用方一赋值就把「诊断 + 返回值」整体捕获进变量，**一个字都不落屏**（同族：静默坏结果——与 `Measure-Object -Line` 少算行数、`Out-String` 插 CRLF、`Start-Process` 的 `.ExitCode` 恒 `$null` 同源） | 逐字现象（本轮 Lead 亲踩，代价 = **重跑一整轮审计**）：`function Audit($new,$bak,$label){ …若干行 "  bytes=…" 诊断…; return $ns }`，调用 `$n1 = Audit $new $bak 'install'` → 函数里**所有**诊断一条都没打印，屏幕上只剩函数外那两行 | 诊断一律走 **`Write-Host`**（写 host / information 流，**不进 success 流** ⇒ 不会被 `$x = f` 捕获）；或干脆**不返回值**（改用 `$script:` / `$global:` 传出）；或 `Out-Host` 显式落屏。**通用判据：审计脚本自己也要被验——屏幕"什么都没打印"不等于"没有异常"，先确认诊断真的落到了屏幕上再下结论** |
| **`setsid nohup … &` 经 ssh 执行时通道不返回**（工具显示 `[still running…] moved to background job`），看着像卡死 | 远端进程脱离了 ssh 的会话，但**ssh 通道要等它才关**；而**远端输出其实已经落盘了** | 本轮实测：命令一直"在跑"，而目标日志文件里内容已经齐了 | **不要重跑**（重跑会起第二个进程、覆盖产物）：另开**一条** ssh 探活即可（`ssh -n <host> "cat /remote/x.log; pgrep -f '[x]' | wc -l"`）。要前台等就加 `timeout`；本机侧的后台 job 语义见 `ascend-env` §5 |
| **从 Windows 传大文件到远端：base64 内联进 ssh 命令行 → 撞 Windows 命令行长度上限** | 单条命令行过长，`ssh.exe` 直接被拒绝执行 | 逐字原文 `Program 'ssh.exe' failed to run: The filename or extension is too long`；实测 **25KB / 34KB 的 base64 串就炸** | 改走 `scp`；**远端目标目录要先 `mkdir -p`**，否则报 `scp: dest open "<dir>/<file>": No such file or directory`。或把 base64 **分块**传（实测 **6000 字符/块**可用）。ssh 与远端目录硬规则见 `ascend-env` §5 |
| **`ssh` 内联命令里的反斜杠转义与引号内管道会被剥掉** | pwsh → `ssh.exe` → 远端 shell **多层解析**：内层反斜杠转义先被吃掉；引号被剥后，引号内的 `\|` 在远端变成**真管道** | 逐字原文：想跑 `tr "\r" "\n"`，远端实际执行成 `tr "r" "n"`（表现为日志显示层的 r→n 假性损坏，日志本体无损）；`grep -E "F4:00\|95:00"` 的引号被剥 → 远端报 `bash: 95:00: command not found` | 远端命令**避免反斜杠转义、避免引号内管道**：多模式 grep 用 `-e A -e B`；复杂脚本**先落盘再执行**（本地写 `.py`/`.sh` → `scp` → `ssh -n <host> "bash /remote/x.sh"`）。远端 ssh 硬规则另见 `ascend-env` §5 |
| **`ssh -n root@host '... "pattern" ...'`：单引号内的双引号被本机 PS 重新转义成 `\"`，远端 bash 收到的是字面引号** | PS 5.1 拼原生命令行时把内层 `"` 写成 `\"` 再交给 `ssh.exe`，远端 shell 解转义后拿到**字面引号** ⇒ `grep`/`pgrep`/`awk` 的模式**静默零匹配**（看着像"什么都没找到"，其实压根没匹配上）；语法错误还会被 `2>$null` 一起吞掉。**与上一行是不同机制**（上一行是反斜杠转义被吃 + 引号内管道被剥） | 逐字症状 `bash: -c: line 0: syntax error near unexpected token '('`；本轮实测**复发 6 次**，并**两次据此误判"进程已经死了"**（真相是模式没匹配上） | 内联 ssh **只做无引号的简单命令**（`cat <path>`、`bash /tmp/x.sh`、`md5sum <path>`）；**凡需要模式匹配的一律 base64 推送 `.sh` 再执行**（见 `ascend-env` §5）。另：**ssh 里永远不要丢 stderr（不要 `2>$null`）**——那会丢掉唯一能解释"进程为什么立刻退出"的 traceback |
| **`pwsh` 工具收到的"一条命令串"本身就是信道：引号 / 反斜杠 / 数组字面量在传输与解析中被吃掉或合并 ⇒ 同一表达式"时对时错"** | 工具收到的是**一整条命令串**（不是一次 argv 调用），其中的引号、反斜杠、`@(...)` 数组字面量在**传输 + PS 解析**两段里都可能被改写：数组**塌成单字符串**、`\` **被吞**、同一写法**这次对下次错**。**根因在信道，不在被解析的表达式** | 逐字报告（一个子代理花 **16 次试探**后给出的**错误结论**）："同一个表达式**时而正确时而不对**"，表现为**数组字面量塌成单字符串**、**反斜杠被吞**，并据此怀疑 `Split-Path -Leaf` / `Split-Path -Parent` "**行为不稳**"。决定性实测（同一条命令串里跑、逐字记录）：`run1/run2/run3` 的 `-Leaf` 均为 `'SKILL.md'`、`-Parent` 均为 `'C:\Users\admin\.dsh\skills\orchestrating-subagents'`（**三次逐字相同且全对**）；`literal array count = 3`、`foreach-built array count = 3`（`$acc=@(); foreach($x in @('a','b','c')){ $acc += $x }`）、`derived class names = orchestrating-subagents, pwsh-on-windows` ⇒ **表达式没问题，信道有问题** | ① **判据必须确定性、不能看单次输出**：同一表达式**连跑 3 次**并**逐字比对**（三次相同才算数）；② 要更强就**把逻辑落成独立 `.ps1` 文件**再跑 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <path>`（独立脚本里 `Split-Path -Leaf/-Parent`、数组字面量都是标准写法），或改走 **base64 通道**；③ **结构性推论**：同一表达式在独立 `.ps1` 文件里正确、在同一条**命令串**里时对时错 ⇒ **结论写成"这是信道敏感的写法、改用 `.ps1` / base64 通道"**，**不是**"某 cmdlet 行为不稳"——后者是**错误且会被写进文档**的结论；④ 别为它去"修表达式"：那正是 16 次试探白耗的路径 |
| **本机 CRLF vs 远端/仓库 LF：直接 `diff` 变成"整文件重写"** | 行尾不同 → 每一行都被判为改动 | 实测同一个 yaml 报 **320 行全异** | 比对前统一行尾：`tr -d '\r' < local.txt > /tmp/a && diff /tmp/a remote.txt`，或 `diff --strip-trailing-cr local remote` |
| **`awk '/\r$/'` 判行尾不可靠** | `\r` 在不同 awk 实现/输入处理下匹配行为不稳定 | 同一个 CRLF 文件，一次数出 **161 行**、另一次数出 **0 行** | 按字节数：`open(p,'rb').read().count(b'\r\n')`（写法见下节） |
| **`git rev-parse HEAD^{tree}` 的 `{tree}` 被 PowerShell 吃掉** | PS 把 `{tree}` 当**脚本块（script block）字面量**解析并展开，git 收到的是 `-encodedCommand dAByAGUAZQA=` | 逐字原文：`fatal: ambiguous argument 'dAByAGUAZQA=': unknown revision or path not in the working tree.` | **给整个 revision 加引号**：`git rev-parse 'HEAD^{tree}'`；同理 `git rev-parse 'HEAD:docker'` 这类含 `^{}` / `:` 的表达式一律加引号 |
| **原生程序（git 等）的进度信息走 stderr，被包成 `NativeCommandError`，看着像报错但并不是失败** | PS 5.1 把原生命令写到 **stderr** 的普通输出记成错误记录（`CategoryInfo : NotSpecified`）；**stderr 有内容 ≠ 退出码非 0** | 逐字原文：`git : remote: Start Git Hooks Checking [PASSED] ...` + `CategoryInfo : NotSpecified` + `FullyQualifiedErrorId : NativeCommandError`；实测此处 `git push` 的 `$LASTEXITCODE` = **0**，且远端确实建了分支；`git worktree add` 的 `Preparing worktree…` 同理 | **判据只看 `$LASTEXITCODE`**，不要按 stderr 文本判失败；必要时把 `2>&1` 的输出与退出码**分开**看（`git push; $LASTEXITCODE`），不要用 `$Error` / `$?` 下结论 |
| **端口枚举看不到监听（`Get-NetTCPConnection` / `netstat` 结果恒为空）** | 本机端口枚举被屏蔽——**不是**"真的没监听" | 逐字输出、20 个 node 进程对照与自建 loopback 监听器的对照实验 → 见 `dsh-isolated-web-host` 坑「整机端口枚举是盲的」（本条只留指针，正文归它） | 判就绪 / 判清理的完整写法（HTTP 探针 + 落盘 pid）→ 见 `dsh-isolated-web-host` |
| **`System.Net.WebClient` 不显式设编码 → 抓韩文/中文页乱码** | `WebClient` 按响应头缺省/系统默认码页解码，**不等同于 UTF-8**（与上面 `Get-Content` 那条不同机制，是网络层解码） | 实测抓韩国官方站（如 `bus.jeju.go.kr`）韩文乱码 | 取回前设 `$w.Encoding = [Text.Encoding]::UTF8`；或取字节后自己 `[Text.Encoding]::UTF8.GetString()` |
| **用 `DownloadString` 取二进制（zip / xlsx）→ 解析器读不出中央目录** | 二进制被当文本解码再拼回字符串，字节被改写 | 逐字原文：`Offset to Central Directory cannot be held in an Int64`（对 `DownloadString` 拿到的 zip 字节做解析时） | 先用 `DownloadData` 拿字节，再 `[IO.File]::WriteAllBytes($p, $bytes)`；**别用 `DownloadString`** |
| **函数名取 `R` → 撞内置别名 `Invoke-History`，静默走错**（机制同 `GC` / `RV` 两行：Alias > Function） | `R` 是 `Invoke-History` 的内置别名 | 逐字原文：`Cannot locate the history for command line ...` | 改名；先 `Get-Command <name> -All` 确认只回自己的 Function |
| **写盘时报孤立代理字符** | 抓下来的页面含**孤立 surrogate**（如 `\ud83c`），UTF-8 编码器拒绝编码 | 逐字原文：`UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83c' ... surrogates not allowed` | 写盘用 `open(p,'w',encoding='utf-8',errors='replace')`，或在反转义阶段就丢弃孤立代理项 |
| **BOM 让 DSH 的 profile 清单解析直接崩** | `profiles\<name>\package.json` 被写成 UTF-8 **with BOM** 后，DSH `readProfileManifest` 里的 `JSON.parse` 在第一个字符就失败 | 逐字原文：`SyntaxError: Unexpected token ''`（引号里那个不可见字符就是 BOM）；现象是"这个 profile 起不来"，而文件内容肉眼看**完全正常** | 写 JSON / YAML 清单用 **`-Encoding ascii`**（这类清单本来就是 ASCII）或 `UTF8Encoding($false)`；**改完立刻验首字节**：`Get-Content <f> -Encoding byte -TotalCount 3` 应是 `123`（`{`），不是 `239,187,191` |
| **本机 python「包装脚本」把远端 UTF-8 输出打到控制台 → `UnicodeEncodeError: 'gbk' codec` 崩在 `sys.stdout.write`**（远端命令**已经成功**） | 本机控制台编码是 **GBK**，而远端输出里有 UTF-8 符号（`✓` / `→` / 中文）；崩溃点在本机**打印**这一步，与远端无关 ⇒ **误判成"远端命令失败/没数据"** | 逐字原文（`rsh.py run "bash /tmp/x.sh"` 时）：<br>`UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 6111: illegal multibyte sequence`<br>栈顶是**本机**脚本的 `sys.stdout.write(out)`，远端 rc 明明是 0 | 在包装脚本入口把输出流改成 UTF-8 且**永不因编码失败而中断**：<br>`for s in (sys.stdout, sys.stderr):`<br>`    try: s.reconfigure(encoding="utf-8", errors="replace")`<br>`    except Exception: pass`<br>判据：**凡"取回远端输出"的包装脚本，第一件事就是 reconfigure**；否则一次成功的数据读取会以"脚本崩溃"的形式报出来（同表"空被读成没有"一族：**崩溃被读成失败**） |
| **`$env:$k` 这种"变量名也当变量"的写法是解析期错误** | PS 把 `$env:` 当**驱动器（drive）引用**，后面再拼变量名直接语法错 | 逐字原文：`InvalidVariableReferenceWithDrive` / `变量引用无效。':' 后面的字符不是有效的变量名字符` | 遍历环境变量名时别拼 `$env:$k`：用 `Get-Item "env:$k" -ErrorAction SilentlyContinue`（取对象属性），或 `[Environment]::GetEnvironmentVariable($k)`。**同一根因的另一种触发（2026-10-08 实测）**：**双引号串里变量后紧跟冒号**一样炸——`"reverse anchor hit $n: " + …` → 同一条 `ParserError: InvalidVariableReferenceWithDrive`，而且它属**解析期**错误、**整段脚本一行都不执行**（等于假通过：本次差点把"没跑"当"跑过了"）→ 写成 `"… ${n}: …"`。**第三种触发（2026-10-09 实测，与 `$env:$k` 同一条解析规则）**：变量后面紧跟一段字母开头文本 + 冒号，PS 把 **`$<变量名>https:` 整个当成驱动器限定变量**（`$env:PATH` 那种形状）⇒ 逐字原文：<br>`At line:9 char:9`<br>`+   $u = "$phttps://github.com/$path"`<br>`+         ~~~~~~~~`<br>`Variable reference is not valid. ':' was not followed by a valid variable name character. Consider using ${} to delimit the name.`<br>`    + FullyQualifiedErrorId : InvalidVariableReferenceWithDrive`<br>→ 修法：写成 **`"${var}https://…"`**（或 `"$($var)https://…"`）。**它属解析期错误 ⇒ 整个脚本零执行**，现场表现是"什么都没输出"，极易被误判成"命令没报错 / 环境本来就这样" |
| **`$host` 是只读自动变量，赋值直接抛错** | `$host` 是 PS 内置的 `InternalHost` 对象，不是普通变量 | 逐字原文：`无法覆盖变量 Host，因为该变量为只读变量或常量` | 自己的变量别叫 `$host`（改名 `$xHost` / `$target`）。**更要命的是连带效应**：赋值一失败，后续 `$host.Substring(...)` 之类会在**另一个对象**上执行，得出**看起来像结论**的假结果（本次实测：拿 `$host` 存文件路径，导致整个哈希对比结论作废）⇒ **关键校验里的路径 / 哈希变量要用不可能撞名的名字** |
| **`(名字 = 值)` 写进子表达式 → 被当命令执行** | `( ... )` 里 `名字 = 值` **不是赋值语句**，PS 按**命令**解析，于是去 PATH 里找一个叫 `SHA256` 的命令 | 逐字原文（`(SHA256 = (Get-FileHash $p -Algorithm SHA256).Hash)`）：`无法将"SHA256"项识别为 cmdlet、函数、脚本文件或可运行程序的名称。请检查名称的拼写，如果包括路径，请确保路径正确，然后再试一次。` + `[exit code: 1]` | 赋值写成**独立语句** `$x = ...`；要在**一行**里取值就用字符串拼接 `"SHA256=" + (Get-FileHash $p -Algorithm SHA256).Hash` |
| **多帧拼接 zstd（如 DSH 会话日志 `session.v4.jsonl.zstd`）用单帧 API 解 → 只回第一帧、静默少数据**（**不报错**，所以你不会去查它） | 这类文件是**多个 zstd 帧首尾拼接**（每帧以 magic `28 B5 2F FD` 开头），单帧 API **解完第一帧就返回**、不提示还有后续帧 | Node v24.18.0 实测：**174,301 B 的文件 `zstdDecompressSync` 只回 289 B**（`createZstdDecompress` 流式同 289 B）；按 magic 切帧后 **79 帧 / 927,790 B**。**判据：解出字节数 << 文件大小就是踩了这个坑**（289 vs 174,301） | 按 magic `28 B5 2F FD` **切帧逐帧解再拼**（最后一帧可能被写入过程截断 ⇒ 单帧异常要容忍跳过），或用 Python `zstandard` 的 **`stream_reader`**（**别用 `d.decompress(b)`**）；**逐字可抄命令与取证配方 → `dsh-agent-customization` §2.12** |
| **双引号 here-string `@"…"@` 里喂 python 代码 → 内层 `\"` 被当成字符串终止符，解析期就崩（一行都不执行，等于假通过）** | **PS 的转义符是反引号，不是 `\"`**（同表"`\"a\\\"b\"` 这类转义"行）⇒ here-string 里 `print("a\"b")` 的 `\"` 被当作**字符串结束**，后面的内容成了裸词；**属解析期错误**，`try/catch` 抓不到、**整段脚本一行都不执行** ⇒ 「没报错」与「跑过了」在这里不是一回事 | 逐字原文（子代理实测报告）：`The string is missing the terminator: ".` ／ `Missing type name after '['.` | **把双引号 here-string 换成单引号 here-string 再管道喂 stdin**（本轮亲测可用）：<br>`$code = @'`<br>`print("a\"b")`<br>`'@`<br>`$code \| python -X utf8 -`<br>⚠️ **`@'` 之后必须立刻换行**（`@'…'@` 中间那行是内容、第一行不能有任何字符），否则 here-string 本身起不来。**不要**把它当"UTF-8 编码问题"——是**引号终止符**问题，改编码无用。**附带**：PS 5.1 对原生命令的 stderr 会报 `NativeCommandError` 且 `exit=1`（同表"原生程序的进度信息走 stderr"行），但 **stdout 完整** ⇒ 用 `2>&1 \| Out-String` 收全，**别据此判命令失败**（判据看 stdout 内容 / Python 侧自己写的退出码） |
| **非提权会话里 `Win32_Process.ExecutablePath` 恒为空 ⇒ 拿它判「进程不存在 / 路径取不到」必错**（同族：静默坏结果——"空"被读成"没有"） | SYSTEM 级服务进程（实例 `ldplayerservice.exe`）的进程句柄在非提权下**拿不到查询权限**，CIM 只回**空串**且**不报错**；`CommandLine` 也常为空 ⇒ 旁证换到**服务侧**才有值 | 本机实测（非提权）：`Get-CimInstance Win32_Process`（按该进程名过滤）→ `ExecutablePath` 为空、`CommandLine` 为空；改查 `Get-CimInstance Win32_Service \| Select-Object Name,State,PathName,ProcessId` → `Name=LDPlayerSvr state=Running PathName=D:\tools\leidian\LDPlayer14\ldplayerservice.exe PID=7284` | 判"某进程在不在 / 它的 exe 在哪"**先问服务侧**：`Get-CimInstance Win32_Service \| Select-Object Name,State,PathName,ProcessId`；只看进程名与 PID 时用 `Get-CimInstance Win32_Process \| Select-Object Name,ProcessId`（`ExecutablePath` 列直接别读）。**空 `ExecutablePath` / 空 `CommandLine` 都不是"进程不存在"或"路径拿不到"的证据** |
| **非提权下 `Stop-Service` / `Stop-Process` / `taskkill /F` / `sc.exe` 全都动不了 SYSTEM 服务，且四条通道报错形态各不相同 ⇐ 最危险的误读是把"杀不掉"当成"进程已经不存在"** | 目标进程属 SYSTEM、当前会话非提权 ⇒ 打开进程 / 服务句柄被拒（`ERROR_ACCESS_DENIED`），四条通道各自包装成不同措辞（PS cmdlet / SC / taskkill 各一套），**没有一条会真的把进程停掉** | 本机逐字原文：`Stop-Service -Name LDPlayerSvr -Force` → `Cannot open LDPlayerSvr service on computer '.'`；`sc.exe` 侧 → `[SC] OpenService FAILED 5: Access is denied.`；`taskkill /F /PID 7284` → `ERROR: The process with PID 7284 could not be terminated. Reason: Access is denied.`；`Stop-Process` 对同一 PID 同样失败（同一权限根因，本轮只逐字留存了上面三条）。**旁证**：失败之后该服务仍 `State=Running`、PID 7284 仍在 | 这类清理**必须**在**提权窗口**里做（管理员终端 / `Start-Process powershell -Verb RunAs`），非提权下**别反复换命令试**（四条通道全被同一条权限规则挡住）；**判"是否真的还在"只看 `Win32_Service` 的 `State` / `Get-Process -Id <pid>`**，不要用"命令失败"或"报 access denied"当证据 |
| **`Export-ScheduledTask` 导出的 XML 里 `不含 <Enabled>` 节点 ⇒ 备份判不出该任务原先是否启用；`Register-ScheduledTask -Xml` 重建会默认启用** | 导出/序列化只走**任务定义（definition）**，而 `Enabled` 是任务对象上的**独立属性**、**不在 definition 里**；重新注册时缺这一属性即取默认值 `true` | 本机实测：同一任务 `Export-ScheduledTask` 输出 **42 行**，与当时的 live XML **唯一差异就是 live 多一行** `<Enabled>false</Enabled>`（即导出侧`不含 <Enabled>`） | ① **不要拿备份 XML 判"该任务原先是否启用"**（会误判成"本来就是启用的"）；② 用 `Register-ScheduledTask -Xml (...)` 重建后**必须再补一次 `Disable-ScheduledTask`**，否则**重建即启用**（默认 `Enabled=true`）；③ 想证明"备份确实是在禁用前导出的"，可行做法 = **diff 备份 XML 与当时的 live XML**，看差异是否**恰好只有那一行** |
| **函数内对父作用域数组做 `$out += ...` → 静默丢失（结果数组为空，且不报错）** | PS 5.1 的 `+=` 是"读 + 写"两步：函数体内**先读到父作用域的副本**，赋值时在当前（函数）作用域**新建同名局部变量** ⇒ 父作用域的 `$out` 从头到尾没被写入。**全程不报错** | 实测现象：函数内对父作用域 `$out` 逐条 `+=` 后，调用方拿到的 `$out` 是空的——整段输出变成空白，**最坏情况会被当成"没找到"**（假否定，与本表"静默坏结果"同族） | 用 **`$script:out`** 显式写父作用域；或改用 `New-Object System.Collections.ArrayList` 配 `$null = $script:out.Add(...)`。**与上面的"数组字面量"那条不冲突**：那行的 `$acc += $x` 在**同一作用域**里跑（实测 count=3 正确），本条只在**函数体跨作用域**时发生 |
| **`ConvertFrom-Json` 解析 react 页里嵌入的 JSON → 报 `Invalid JSON primitive: .`** | 页面嵌入的不是规范 JSON（JS 对象字面量 / 含未转义字符）⇒ 整体反序列化在**第一个非法基元**处就断，拿不到任何字段 | 逐字原文：`Invalid JSON primitive: .` | 改用**正则 / 手工转义扫描**逐字段取值（把 `.` 这类字符按需转义后再取），**别指望整体反序列化**；分块截取时同样按字段名定位，不要一次性 `ConvertFrom-Json` 整段页面 |

## 可抄的正确写法

```powershell
# 读：显式 utf8（行数/内容都对）
$lines = Get-Content $f -Encoding utf8          # 只用于看内容：.Count 仍会少算（实测真实 250 行→249），数行数走 Python
$raw   = Get-Content $f -Encoding utf8 -Raw     # 单字符串，保留原始换行

# 写：无 BOM、LF 可控
[IO.File]::WriteAllText($p, $text, (New-Object System.Text.UTF8Encoding $false))   # 首字节无 BOM（实测）
# 抓网页/二进制落盘：一律 Invoke-WebRequest -OutFile（别用 [IO.File]::WriteAllBytes）
Invoke-WebRequest -Uri $u -OutFile $out -UseBasicParsing
# 要把程序输出落盘：整条交给 cmd（PS 的 `>` 写 UTF-16 带 NUL，下游判 binary）
cmd /c "git grep -n pattern > out.txt 2>&1"

# 给 node 内联传含双引号的 JS：--% 之后是字面量，必须压成单行（裸 -e 会被剥引号）
node --% -e "console.log(JSON.stringify('a\"b'))"   # 实测输出 "a\"b"，exit 0

# 要喂多行代码给 python（含 \" 的也安全）：一律用【单引号】here-string 管道进 stdin
# （双引号 @"…"@ 里内层 \" 会被当成字符串终止符 → 解析期错误、整段脚本一行不执行）
$code = @'
print("a\"b")
'@
$code | python -X utf8 -        # 本轮实测可用；@' 之后必须立刻换行

# 数 CR / 判换行（不要用管道）
$bytes = [IO.File]::ReadAllBytes($p)
'CR count = ' + ([regex]::Matches([Text.Encoding]::UTF8.GetString($bytes), [string][char]13)).Count

# 带超时与终止错误的失败判定
$r = $(try { Get-Item 'C:\nope' -ErrorAction Stop; 'OK' } catch { 'FAIL: ' + $_.Exception.GetType().Name })
```

**首选替代**：以上任意一项都有更稳的 Python 版本，能用 Python 就用 Python：

```bash
python -c "import io,sys; sys.stdout.reconfigure(encoding='utf-8'); t=io.open(r'<path>',encoding='utf-8',newline='').read(); print('lines=',t.count(chr(10)),'CR=',t.count(chr(13)))"
```

## 最容易造成"静默错误结果"的四条

1. **用 `Get-Content` 数行数/空行（带不带 `-Encoding utf8` 都不行）** —— 不带不报错但给 289 而不是 456；**带了仍会少算**（实测真实 250 行的 md 文件给 **249**，且 `Select-Object -Last 8` 会漏行/整段错位），任何基于它的推论都会错（我在真实任务里据此得出了错误的空行数 23）→ 数行数交给 Python 二进制读（写法见陷阱表"行数少算 / 行错位"行）。
2. **用管道 `| Out-String` / `| Measure-Object -Line` 做统计** —— 前者把 LF 变成 CRLF，后者跳过空行，两者都会让"审计全绿/全红"的结论失真。
3. **用 PS7 语法** —— 三元那种是解析期错误，整段脚本**一行都不执行**；若这段脚本是你"验完就以为通过"的检查，会得到**假通过**。
4. **用单帧 zstd API 解「多帧拼接」的日志类文件** —— 只回第一帧且**不报错**，据此会得出"文件里没有 X"这类**假否定**结论（曾据此误判"日志里没有 toolFilter 事件"）→ 修法见陷阱表"多帧拼接 zstd"行。

## 何时不用本 skill

- 操作**远端 Linux**（ssh 到昇腾机器）→ 用 `ascend-env`。
- 写 / 改 DSH skill 的 frontmatter 与 description 契约 → 用 `dsh-skill-authoring`。
