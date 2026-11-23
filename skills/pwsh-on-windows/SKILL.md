---
name: "pwsh-on-windows"
description: "在 Windows 排查 PowerShell 版本、编码/BOM、原生命令参数与退出码、管道和文本计数问题；名为 pwsh 的工具在本机实为 Windows PowerShell 5.1。"
whenToUse: "在 Windows 排查 PowerShell 版本、编码/BOM、原生命令参数与退出码、管道和文本计数问题；名为 pwsh 的工具在本机实为 Windows PowerShell 5.1。 模型触发仍以description为准。"
---

# Windows shell 的可靠执行

先记录 `$PSVersionTable` 的 PSEdition/PSVersion、实际可执行文件和参数模式。本机 2026-11-23 实测只有 **Windows PowerShell 5.1.26100.9711（Desktop）**：`Get-Command pwsh.exe` 命中 0 个，`C:\Program Files\PowerShell` 不存在。工具名叫 `pwsh`，执行的仍是 5.1，语法与编码按 5.1 解释；换一台机器先跑同一条命令再下结论。

- 复杂代码写成工作区脚本再 `-File` 执行，逐层确定 PowerShell、cmd、Python/Node 谁解析引号与 `$`。尽量用结构化参数数组，Core 可用 ProcessStartInfo.ArgumentList；Windows PowerShell 所依赖的 .NET Framework 不能照搬。JSON.stringify 不是 shell quoting。
- 立即保存原生命令退出码（`$LASTEXITCODE`/subprocess.returncode），同时检查预期产物。stderr 有内容不等于失败，目录存在或 git 打印进度不等于成功；记录 tool 包装错误与真实子进程状态的区别。
- 需要原样字节时用二进制读写/重定向接口，不经 Out-String、Get-Content、格式化表格或跨 shell 转手。默认编码和 BOM、行数定义、管道消费方法见 [版本与字节](references/encoding-process.md)。
- 不用 `$PID`、`$HOME` 等自动变量作临时变量；函数名避开内置别名（Alias 优先于 Function，`GC` 就是 `Get-Content`），必要时用 Get-Command 查解析结果。Native stderr 与 PowerShell terminating error 分开处理。
- 文件操作始终使用同一 shell 的 LiteralPath，递归移动/删除前解析绝对路径并验证在指定边界内。不要把 PowerShell 枚举结果拼成 cmd 删除命令。后台辅助进程需要隐藏窗口时显式配置，保留 PID/创建时间用于定向停止。

## 5.1 的硬坑

1. **写文件必须是无 BOM 的 UTF-8**：`Set-Content -Encoding UTF8` 与 `Out-File -Encoding utf8` 首字节都是 `EF BB BF`，会毁掉 skill 的 YAML frontmatter。用 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($false)))`，或 Python 的 `io.open(...,encoding='utf-8',newline='')`。
2. **读文件必须带 `-Encoding utf8`**：不带不报错但静默乱码（实测 `中文行一` → `涓枃琛屼竴`），行数统计失真。
3. **数出现次数别用 Select-String**：`-SimpleMatch -AllMatches` 的 `Matches.Count` 恒为 0（实测 2 次读成 0）→ `[regex]::Matches($t,[regex]::Escape('X')).Count`。
4. **统计别走管道**：`Measure-Object -InputObject @()` 对空数组报 `Count: 1`；`Measure-Object -Line` 跳过空行（4 行读成 3）；`'{0}' -f $null` 输出空白。用 `[IO.File]::ReadAllLines($p).Count`。
5. **执行策略 `Restricted`**（实测）：复杂逻辑写 `.py` 跑，别写 `.ps1`。
6. **没有 PS7 语法**：`? :`、`??`、`-AsByteStream`、`utf8NoBOM` 都属**解析期**错误，整段一行都不执行（实测 `$true ? 1 : 2` 报"意外的标记 `?`"），易被判成通过。
7. **`>` 重定向写 UTF-16LE**：首字节 `FF FE`（实测 `hello` → `FF FE 68 00 65 00 ...`），后续 `yaml.safe_load` 直接 `UnicodeDecodeError`。
8. **HTTP 与 stdin 另有专写法**：响应体、请求体、stdin 都踩编码/注入坑，见 [版本与字节](references/encoding-process.md)。结论存疑时做最小合成 fixture，别拿真实凭据或生产配置做编码实验。

## 落盘与跨 shell 复核

`git show <blob> > file` 落盘即踩第 7 条；本机 `bash` 是 WSL，Windows 路径写 `/mnt/d/...`（写 `/d/...` 得 exit 127）；判断脚本语法前用 `git ls-files --eol` 看行尾。细节见 [版本与字节](references/encoding-process.md)。

## git porcelain 的 ?? 不能用 -like 匹配

统计 `git status --porcelain=v1` 时，`Where-Object { $_ -like '??*' }` 里的 `?` 是通配符（"任意单字符"），修改行也会算成 untracked，命令还正常退出。用字面前缀显式计数：

```powershell
$s = @(git -C $repo status --porcelain=v1)
$untracked = @($s | Where-Object { $_.StartsWith('??') })
$modified = @($s | Where-Object { -not $_.StartsWith('??') })
$untracked.Count
$modified.Count
```

不要根据表格外观判断；先用总数核对 `$modified.Count + $untracked.Count -eq $s.Count`。

## MSIX 应用：Get-Command 为空不等于没装

## MSIX 应用：Get-Command 为空不等于没装

- 商店/MSIX 应用（如 Codex 桌面版）不注册 PATH，命令里只看到 `Codex.exe`：先 `Get-AppxPackage *Codex* | Select-Object InstallLocation`，再拼 `InstallLocation\app\resources\codex.exe` 才是真正的 CLI。
- `& $exe login status` 明明成功却报 `NativeCommandError`：PS 5.1 把原生命令的 stderr 一律当错误流。加 `2>&1` 接收，判定只看 `$LASTEXITCODE`（本次 exit 0 = 登录正常）。

## here-string / -c 会改写反引号与转义：含代码围栏的文件用写文件工具（实测）

在 PowerShell 里用 here-string（`@"..."@`）或 `python -c "..."` 生成含**代码围栏 / 反引号 / 多层引号**的文件时，内容会被改写或直接语法报错：

- 现象 A：要写入 ```` ``` ````（三反引号），结果文件里只剩一个反引号——代码块判定、Markdown 结构全部失效。
- 现象 B：here-string 里写 Python 三引号 `'''`，PowerShell 先行解释，Python 收到的是 `SyntaxError: unterminated triple-quoted string literal`。
- 现象 C：`$t.Replace("...`n...")` 这类双引号里的反引号转义，替换锚点没匹配上就**静默不改**，看起来"脚本跑了"。

修法（按优先级）：

1. 含代码围栏、反引号、多层引号的文件**用文件写工具（write）或 Python 脚本文件生成**，不要经 PowerShell here-string / `-c` 传内容。
2. 必须走 PowerShell 时，用**单引号 here-string**（`@'...'@`）并避免在内容里出现行首 `'@`，或把内容 base64 后再解码写入。
3. 写完**按字节核对**：`[IO.File]::ReadAllText` 或 Python `repr()` 看反引号/反斜杠是否还在；语法检查（`node --check`）通过**不能**证明内容没被改写。

判据：只要文件里有 Markdown 围栏或转义序列，一律当成"非 ASCII 文本资产"处理——生成后读回逐字比对。
