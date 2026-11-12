---
name: pwsh-on-windows
description: 本机 pwsh 实为 Windows PowerShell 5.1：GBK 解码、BOM、PS7 语法静默坑。适用于"中文乱码 / 行数或 CR 数不对 / 计数总是 0 / 执行策略拦 / PS7 语法报错"。
whenToUse: 要在本机用 pwsh 工具执行命令、读写文件、统计行数/字符/CR、发 HTTP 请求或写脚本文件，尤其涉及中文、换行符、编码、引号与 PS7 语法时使用。
---

# 本机 PowerShell 正确用法（工具名 `pwsh`，实为 Windows PowerShell 5.1）

## 何时调用

**加载本 skill 当：**
- 命令要读写文件，或统计行数 / CR 数 / 出现次数，而数字**看着不对或明显偏小**时。
- 要发 HTTP 请求（尤其**写操作**会把中文写进远端）时。
- `.ps1` 被执行策略拦下、脚本报 `Unexpected token`、或整段脚本"什么都没干"时。
- 拿不准某个写法在本机能不能用——本机**没有 PS7**，网上抄来的写法很多属**解析期**错误。

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

**一句话结论**：本机**没有 PS7**。任何 PS7 才有的写法要么报"参数不存在"，要么（三元那种）是**解析期**错误、让整段脚本**一行都不执行**。任何涉及中文、换行、字节的操作都必须**显式指定编码**。

## 铁律（写命令前先过一遍）

1. **读写文件、数行数、数 CR、做文本处理 → 一律交给 Python**，别用 PowerShell 的文本 cmdlet。Python 必须带 `$env:PYTHONIOENCODING='utf-8'`，并用 `io.open(path, encoding='utf-8', newline='')`。
2. **写脚本写 `.py`，不写 `.ps1`**，**给 Python 传复杂字符串也一律写 `.py` 文件、不要内联**（执行策略 `Restricted`；要跑现成 `.ps1` 得 `powershell -NoProfile -ExecutionPolicy Bypass -File x.ps1`，别改全局策略）。
3. **中文优先放进文件再用 Python 读**（不依赖外层调用链的编码）——注意实测：本机 `chcp=65001`，**命令串里带中文其实不乱码**（`echo '中文'` 原始字节 `E4 B8 AD E6 96 87 0D 0A`）。真正会乱的是**非 UTF-8 保存的 `.bat`/`.cmd`**（GB2312 存的 `.bat` → `����`）。所以「放文件」是稳妥偏好，不是「命令串必坏」。
4. **读文件带 `-Encoding utf8`**（不带就是 ANSI/GBK），但它**只保证内容不乱码、不保证行数对**（实测仍少算，见陷阱表）；**写文件用 `UTF8Encoding($false)`**，绝不用 `Set-Content -Encoding utf8`（它写 BOM）。**要把程序输出重定向到文件，整条命令交给 `cmd /c "... > f 2>&1"`**——PS 自己的 `>` 写 UTF-16（带 NUL），下游会把产物判成 binary。
5. **判"存在/没有/数量"要显式计数**（`.Count` / `-ExpandProperty`），**不要肉眼看表格**——表格的空白表头容易被误读成"没有结果"，也别用过滤后的空结果推断"不存在"。
6. **别用 PS7 语法**：三元 `? :`、`??`、`-AsByteStream`、`-Encoding utf8NoBOM`、`Format-Hex -Count`。
7. **`try/catch` 只抓终止错误**，判失败要配 `-ErrorAction Stop`；`try` 是语句不是表达式，只能用 `$(try{}catch{})`。

## 陷阱表（逐条为本机实测，含错误原文）

| 现象 | 机制 | 实测证据（原文/数字） | 正确写法 |
| --- | --- | --- | --- |
| 读 UTF-8 文件中文乱码 | `Get-Content` 默认按 **ANSI/GBK** 解码 | 前端元数据显示为 `涓?Ascend/MindSpeed-Ops 浠?..` | `Get-Content $f -Encoding utf8` |
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
| `Select-String -SimpleMatch -AllMatches` 数出现次数恒为 0 | `-SimpleMatch` 下 `Matches` 集合**恒空**（不是 null 而是空 `Match[]`） | 44 行全回 `0`；去掉 `-SimpleMatch` 同样写法得 `1,4,1,...` 共 **52**；`[regex]::Matches($t,'GitCode').Count` = **25**（真值）——`Select-String` 默认还**大小写不敏感**，会多算一倍 | 数次数：`[regex]::Matches($t,[regex]::Escape('X')).Count`；数行数：`(Select-String -Pattern 'X' -SimpleMatch -CaseSensitive).Count` |
| **发 JSON 时中文变成 `??`**（写操作会永久落库坏数据） | `-Body` 传**字符串**时按 ASCII/ISO-8859-1 编码 | 回环抓包：`-Body <string>` → `CL=16 HEX=7B 22 61 22 3A 22 3F 3F 22 ...`（中文→`??`）；`-Body <utf8 bytes>` → `CL=20 ... E4 B8 AD E6 96 87 ...`。**本地不报任何错** | `-Body ([Text.Encoding]::UTF8.GetBytes($json))` + `-ContentType 'application/json; charset=utf-8'` |
| 给原生程序喂 stdin 失败（如 `git credential fill`） | PowerShell 向原生子进程写 stdin 时**先注入 UTF-8 BOM** | 子进程 stdin 原始字节 = `EF BB BF 0D 0A` → git 报 `warning: invalid credential line:` / `fatal: unable to read credential from stdin`；用管道送同一份正确内容还会 `fatal: refusing to work with credential missing protocol field` | `Start-Process git -ArgumentList 'credential','fill' -RedirectStandardInput $req -RedirectStandardOutput $out -NoNewWindow -Wait`（实测 stdin 被正确解析） |
| **用 `icacls` 收紧 ACL 后，后续的 `os.replace()` / `MoveFileEx` 替换目标必然失败** | ACL 里的 **(R,W) 不含 DELETE 权限**，而替换一个文件需要**目标本身**的 DELETE 权限；写入（新建临时文件）当场不会报错，**下一次覆盖同一文件才炸** | 逐字原文：`PermissionError: [WinError 5] 拒绝访问。: '...\fake.token.json.tmp' -> '...\fake.token.json'`（第二次 `save_cache()` 起必现） | 收紧时给 **(F)**：`icacls <path> /inheritance:r /grant:r "$user:(F)"`；或对"替换"做成**自修复重试**（替换失败先补 `(F)` 再重试）。附带一坑：`"$env:USERNAME:(R,W)"` 报 `Invalid parameter "(R,W)"`（PS 把 `$env:USERNAME:` 当作用域变量名取空）→ 用 `($env:USERNAME + ':(F)')` 拼接 |
| **把 JSON 内联成命令行参数传给 python/node → 引号被 shell 剥掉，解析必炸** | PS 传原生命令参数会**剥掉内嵌引号**；`--args '{"top":3}'` 到子进程手里已不成 JSON。**与上面 stdin 那条是不同机制**（那条是 BOM 注入），但同属"跨进程传值必被外壳改写" | 逐字原文：`json.decoder.JSONDecodeError: Expecting value: line 1 column 2`；同一根因另一次表现为 `NameError: name 'Bad' is not defined`（`python -c @'...'@` 传多行代码）；还有 `error: unrecognized arguments: top\:3,\filter\:\hasAttachments eq true\}`（引号被剥 + 反斜杠被注入）；**内联 `python -c` 带韩文/引号/多行必炸**，另见逐字原文 `The string is missing the terminator: '.`、`Missing type name after '['.`、`SyntaxError: unterminated string literal`、`SyntaxError: invalid syntax`（`python -c @'...'@` 里写字面双引号时） | 三选一，**别内联**：① 复杂值一律写成 **`.py` / `.json` 文件**再跑（首选）；② 用 `@file` 形态读参数（实测 `--args @args.json`）；③ 传 **base64**（实测 `--pkg-args-b64`）。给原生程序喂 stdin 见上一行 |
| 计数显示 0（或空），其实是取值失败 | `'{0}' -f $null` 输出**空白**而非 `0`；`Measure-Object -InputObject` 同时往 **stderr** 写非终止错误，只看 stdout 看不到 | `'{0} 次' -f $null` → `[ 次]`（len=2）；`(Measure-Object -InputObject @() -Sum).Sum` → `$null`；**且 `Measure-Object -InputObject @()` 对空数组报 `Count: 1`**，而管道写法 `@() \| Measure-Object -Sum` 报 `Count=0 Sum=0` | 空集合一律走管道：`@() \| Measure-Object -Sum`；输出前判空 `if ($null -eq $s) { 'N/A' }`；判失败加 `-ErrorAction Stop` |
| 内联 `-Command` 的双引号被父进程先展开 | 父 shell 先把 `$true` 展开成 `True`，子进程拿到 `if (True) { 'a' }` | `True : The term 'True' is not recognized as the name of a cmdlet, function, script file, or operable program.`（**不是** `Missing closing '}'`——那个在本机常见调用路径下未复现） | 父进程用**单引号** `powershell -Command 'if ($true) { ''a'' }'`（实测输出 `a`），或先把命令串存进变量再传 |
| `@" ... "@` 把 `$` 展开 | 双引号 here-string 同时展开 `$foo` 与 `$(1+1)` | `@"..."@` → `foo=BAR calc=2`；`@'...'@` → `foo=$foo calc=$(1+1)`（原样保留） | 要字面量用**单引号 here-string** `@'...'@`；含 `$` 的代码一律写文件 |
| `$pid` 等只读变量的错**能**被 try/catch 抓到 | 与 `Get-Item 不存在` 那类非终止错误不同，它抛的是终止错误 | `Cannot overwrite variable PID because it is read-only or constant.`；`(Get-Variable PID).Options` = `Constant, AllScope` | 换名 `$procId` |
| **从 Windows 传大文件到远端：base64 内联进 ssh 命令行 → 撞 Windows 命令行长度上限** | 单条命令行过长，`ssh.exe` 直接被拒绝执行 | 逐字原文 `Program 'ssh.exe' failed to run: The filename or extension is too long`；实测 **25KB / 34KB 的 base64 串就炸** | 改走 `scp`；**远端目标目录要先 `mkdir -p`**，否则报 `scp: dest open "<dir>/<file>": No such file or directory`。或把 base64 **分块**传（实测 **6000 字符/块**可用）。ssh 与远端目录硬规则见 `ascend-env` §5 |
| **`ssh` 内联命令里的反斜杠转义与引号内管道会被剥掉** | pwsh → `ssh.exe` → 远端 shell **多层解析**：内层反斜杠转义先被吃掉；引号被剥后，引号内的 `\|` 在远端变成**真管道** | 逐字原文：想跑 `tr "\r" "\n"`，远端实际执行成 `tr "r" "n"`（表现为日志显示层的 r→n 假性损坏，日志本体无损）；`grep -E "F4:00\|95:00"` 的引号被剥 → 远端报 `bash: 95:00: command not found` | 远端命令**避免反斜杠转义、避免引号内管道**：多模式 grep 用 `-e A -e B`；复杂脚本**先落盘再执行**（本地写 `.py`/`.sh` → `scp` → `ssh -n <host> "bash /remote/x.sh"`）。远端 ssh 硬规则另见 `ascend-env` §5 |
| **本机 CRLF vs 远端/仓库 LF：直接 `diff` 变成"整文件重写"** | 行尾不同 → 每一行都被判为改动 | 实测同一个 yaml 报 **320 行全异** | 比对前统一行尾：`tr -d '\r' < local.txt > /tmp/a && diff /tmp/a remote.txt`，或 `diff --strip-trailing-cr local remote` |
| **`awk '/\r$/'` 判行尾不可靠** | `\r` 在不同 awk 实现/输入处理下匹配行为不稳定 | 同一个 CRLF 文件，一次数出 **161 行**、另一次数出 **0 行** | 按字节数：`open(p,'rb').read().count(b'\r\n')`（写法见下节） |
| **`git rev-parse HEAD^{tree}` 的 `{tree}` 被 PowerShell 吃掉** | PS 把 `{tree}` 当**脚本块（script block）字面量**解析并展开，git 收到的是 `-encodedCommand dAByAGUAZQA=` | 逐字原文：`fatal: ambiguous argument 'dAByAGUAZQA=': unknown revision or path not in the working tree.` | **给整个 revision 加引号**：`git rev-parse 'HEAD^{tree}'`；同理 `git rev-parse 'HEAD:docker'` 这类含 `^{}` / `:` 的表达式一律加引号 |
| **原生程序（git 等）的进度信息走 stderr，被包成 `NativeCommandError`，看着像报错但并不是失败** | PS 5.1 把原生命令写到 **stderr** 的普通输出记成错误记录（`CategoryInfo : NotSpecified`）；**stderr 有内容 ≠ 退出码非 0** | 逐字原文：`git : remote: Start Git Hooks Checking [PASSED] ...` + `CategoryInfo : NotSpecified` + `FullyQualifiedErrorId : NativeCommandError`；实测此处 `git push` 的 `$LASTEXITCODE` = **0**，且远端确实建了分支；`git worktree add` 的 `Preparing worktree…` 同理 | **判据只看 `$LASTEXITCODE`**，不要按 stderr 文本判失败；必要时把 `2>&1` 的输出与退出码**分开**看（`git push; $LASTEXITCODE`），不要用 `$Error` / `$?` 下结论 |
| **端口枚举看不到监听（`Get-NetTCPConnection` / `netstat` 结果恒为空）** | 本机端口枚举被屏蔽——**不是**"真的没监听" | 逐字输出、20 个 node 进程对照与自建 loopback 监听器的对照实验 → 见 `dsh-isolated-web-host` 坑「整机端口枚举是盲的」（本条只留指针，正文归它） | 判就绪 / 判清理的完整写法（HTTP 探针 + 落盘 pid）→ 见 `dsh-isolated-web-host` |
| **`System.Net.WebClient` 不显式设编码 → 抓韩文/中文页乱码** | `WebClient` 按响应头缺省/系统默认码页解码，**不等同于 UTF-8**（与上面 `Get-Content` 那条不同机制，是网络层解码） | 实测抓韩国官方站（如 `bus.jeju.go.kr`）韩文乱码 | 取回前设 `$w.Encoding = [Text.Encoding]::UTF8`；或取字节后自己 `[Text.Encoding]::UTF8.GetString()` |
| **用 `DownloadString` 取二进制（zip / xlsx）→ 解析器读不出中央目录** | 二进制被当文本解码再拼回字符串，字节被改写 | 逐字原文：`Offset to Central Directory cannot be held in an Int64`（对 `DownloadString` 拿到的 zip 字节做解析时） | 先用 `DownloadData` 拿字节，再 `[IO.File]::WriteAllBytes($p, $bytes)`；**别用 `DownloadString`** |
| **函数名取 `R` → 撞内置别名 `Invoke-History`，静默走错**（机制同 `GC` / `RV` 两行：Alias > Function） | `R` 是 `Invoke-History` 的内置别名 | 逐字原文：`Cannot locate the history for command line ...` | 改名；先 `Get-Command <name> -All` 确认只回自己的 Function |
| **写盘时报孤立代理字符** | 抓下来的页面含**孤立 surrogate**（如 `\ud83c`），UTF-8 编码器拒绝编码 | 逐字原文：`UnicodeEncodeError: 'utf-8' codec can't encode character '\ud83c' ... surrogates not allowed` | 写盘用 `open(p,'w',encoding='utf-8',errors='replace')`，或在反转义阶段就丢弃孤立代理项 |

## 可抄的正确写法

```powershell
# 读：显式 utf8（行数/内容都对）
$lines = Get-Content $f -Encoding utf8          # 只用于看内容：.Count 仍会少算（实测真实 250 行→249），数行数走 Python
$raw   = Get-Content $f -Encoding utf8 -Raw     # 单字符串，保留原始换行

# 写：无 BOM、LF 可控
[IO.File]::WriteAllText($p, $text, (New-Object System.Text.UTF8Encoding $false))   # 首字节无 BOM（实测）
# 要把程序输出落盘：整条交给 cmd（PS 的 `>` 写 UTF-16 带 NUL，下游判 binary）
cmd /c "git grep -n pattern > out.txt 2>&1"

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

## 最容易造成"静默错误结果"的三条

1. **用 `Get-Content` 数行数/空行（带不带 `-Encoding utf8` 都不行）** —— 不带不报错但给 289 而不是 456；**带了仍会少算**（实测真实 250 行的 md 文件给 **249**，且 `Select-Object -Last 8` 会漏行/整段错位），任何基于它的推论都会错（我在真实任务里据此得出了错误的空行数 23）→ 数行数交给 Python 二进制读（写法见陷阱表"行数少算 / 行错位"行）。
2. **用管道 `| Out-String` / `| Measure-Object -Line` 做统计** —— 前者把 LF 变成 CRLF，后者跳过空行，两者都会让"审计全绿/全红"的结论失真。
3. **用 PS7 语法** —— 三元那种是解析期错误，整段脚本**一行都不执行**；若这段脚本是你"验完就以为通过"的检查，会得到**假通过**。

## 何时不用本 skill

- 操作**远端 Linux**（ssh 到昇腾机器）→ 用 `ascend-env`。
- 写 / 改 DSH skill 的 frontmatter 与 description 契约 → 用 `dsh-skill-authoring`。

## UTC 日志的时间窗过滤：Parse 默认按本地时间

按"最近 N 分钟"过滤日志，结果恒为空——先别下"没有活动"的结论，很可能是时间戳解析错了。

**坑**：日志是 UTC（行首形如 `2026-11-12T06:44:08.104Z`），而
`[datetime]::Parse('2026-11-12T06:44:08')` **默认按本地时间解析**；
再接 `.ToUniversalTime()` 会再减 8 小时，窗口整体偏移 8 小时，于是"最近 25 分钟"恒为 0 行。

**正确写法**（任选其一）：

```powershell
[datetime]::Parse($s, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
[DateTimeOffset]::Parse($s).UtcDateTime
```

**判据（避免自己骗自己）**：先打印文件最后 3–5 行原文 + `(Get-Item $log).LastWriteTime`，
确认文件确实在写；若文件在更新而时间窗统计为 0 行，就是解析/时区问题，不是"没活动"。
行数、最后写入时间、窗口计数三者要能互相印证，缺一个就可能得出反向结论。

## 内联替换遇到全角标点：整段脚本静默不执行

在 `pwsh -Command` 里用双引号字符串做**文本替换**时，内容里只要出现全角标点（`"` `"` `，` `：`）或反引号，整段脚本会**解析失败、一行都不执行**——
而失败信息常常是一串"缺少 )"的位置提示，看不清真正原因，容易误以为改成功了。

**实测形态**（三次同一类故障）：
- 替换文本里带中文注释与全角引号：`"… 它也是一"步"。"` → `MissingEndParenthesisInMethodCall`，整段未执行；
- here-string 起止符不匹配：以 `@'` 开头却用 `"@` 结尾 → `字符串缺少终止符`；
- 内容含反引号/`$` 时用双引号 here-string → 变量与转义被解释，写出来的文件不是原文。

**规则（按优先级）**
1. **要改文件就写脚本文件**：把替换逻辑写成 `.mjs` / `.py`，再用 `pwsh` 去执行它。
   脚本内容不受 PowerShell 引号规则影响，这也符合本机"文本处理交给 Python/Node"的既有约定。
2. 必须在命令行内联时，文本一律用**单引号 here-string** `@'…'@`，并把起止符写对；
   起止符必须是行首的 `'@`。
3. 不要用双引号 here-string `@"…"@` 承载代码/正则/含 `$`、`` ` `` 的文本。

**自检**：替换类命令跑完后，立刻用 `Select-String` 确认目标串**已存在**（计数 ≥1），
并确认文件 mtime 变了；只看"没有报错"不足以证明写入成功。

## ProcessStartInfo.ArgumentList 在 .NET Framework 上不存在

## `ProcessStartInfo.ArgumentList` 在 .NET Framework 上不存在

本机 pwsh 跑在 .NET Framework 上，`ArgumentList`（.NET Core 2.1+ / PS7 成员）恒为 `$null`，逐个 `Add` 会**每个参数报一次**同样的错，且循环体一次都没执行——脚本看起来跑完了，其实什么都没传：

```
不能对 Null 值表达式调用方法。
所在位置 行:18 字符: 55
+ ...  @('-e', $script, '--') + @()) { $start.ArgumentList.Add($argument) }
+                                      ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : InvalidOperation: (:) []，RuntimeException
    + FullyQualifiedErrorId : InvokeMethodOnNull
```

DSH 文档 `dsh-doc/references/locate-docs.md` 里给的 PowerShell 模板用的就是 `ArgumentList`，直接抄必踩。

改用**单字符串 `Arguments`**，参数自己加引号；多行脚本先落盘成 `.js` / `.py`，传路径而不是塞进 `-e`：

```powershell
$start = [System.Diagnostics.ProcessStartInfo]::new($env:DSH_NODE_EXECUTABLE)
$start.Arguments = '"D:\workspace\tmp\probe.js"'
$start.EnvironmentVariables['ELECTRON_RUN_AS_NODE'] = '1'
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$start.StandardErrorEncoding = [System.Text.Encoding]::UTF8
$process = [System.Diagnostics.Process]::Start($start)
$stderr = $process.StandardError.ReadToEndAsync()
$stdout = $process.StandardOutput.ReadToEnd()
$process.WaitForExit()
[Console]::Out.Write($stdout)
[Console]::Error.Write($stderr.Result)
exit $process.ExitCode
```

同族的 .NET-Core-only 成员：`$start.Environment`（.NET Framework 只有 `EnvironmentVariables` 索引器）。

未验证：其余 PS7-only 成员在本机是解析期报错还是运行期为 `$null`；本次只实测了 `ArgumentList` 这一条，以及 `EnvironmentVariables` 索引器可用。
