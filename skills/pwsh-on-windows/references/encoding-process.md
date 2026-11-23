# 编码、计数与管道

本机（5.1.26100.9711）实测：`Set-Content -Encoding UTF8` 与 `Out-File -Encoding utf8` 首字节均为 `EF BB BF`；`>` 重定向为 UTF-16LE（`hello` → `FF FE 68 00 65 00 6C 00 6C 00 6F 00`）；不带 `-Encoding` 读 UTF-8 中文静默乱码（`中文行一` → `涓枃琛屼竴`），不报错。PowerShell 6+ 文本输出默认 utf8NoBOM，7.4+ 原生命令字节重定向另有改进——这些前提在本机不成立，先确认再套用。明确指定读写编码，比较文件前检查前几字节和实际字节长度。[官方编码说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7.5)

“多少行”先约定：LF 数、分隔后的元素数、逻辑非空行还是物理记录。`a\n\n` 有两个 LF、split 后三个元素；空文件单独定义。Get-Content/Measure-Object -Line、数组 Count 和原始文本方法可能采用不同定义；Out-String 会加入格式化与终止换行。对持续写入文件先做快照，不能把读时竞态当作编码丢行。Select-String -SimpleMatch 的 MatchInfo.Matches 不能当成所有字面命中的计数；需 occurrence 数时使用 escaped regex、明确大小写或直接字节逻辑。

Select-Object -Last 必须消费完整输入才能知道末尾，旧笔记关于它总会提前关闭 pipe 的说法不成立；-First 等操作有时会提前终止上游。对大型输出采用文件或完整消费者，检查原生命令退出状态及截断标识。

`$LASTEXITCODE` 指最近原生命令/脚本的退出码，必须在下一个原生命令前保存；PowerShell cmdlet 的成功另看 `$?`/异常。`ErrorActionPreference` 和 NativeCommandErrorActionPreference 的行为要按版本测试。[自动变量文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables?view=powershell-7.5)

时间用带 offset 的 DateTimeOffset；缺 offset 的文本先说明源时区，不能一律减8小时。压缩日志按格式流式解码，多帧 zstd 不按 magic 字符串切割。文件替换受文件和父目录的删除/创建权限影响，先查具体 ACL/占用，不用放宽整个树 ACL 或全局 execution policy 解决。cmd wrapper 用 ASCII 是兼容性选择，不代表 Unicode 路径永远不可用。

## HTTP 与 stdin

- **读响应体**：用 `[Text.Encoding]::UTF8.GetString($w.RawContentStream.ToArray())`。响应头缺 `charset` 时 `Invoke-RestMethod` 按 Latin-1 解码，中文乱码且不报错。
- **写请求体**：`-Body ([Text.Encoding]::UTF8.GetBytes($json))`。直接传字符串会按默认编码发出，中文变成 `??` 并**永久落库**。
- **喂 stdin**：不要用管道。实测 `'hello' | python -c ...` 收到 `b'hello\r\n'`——PowerShell 会给原生程序追加 CRLF，叠加 BOM 后 git 就报 `unable to read credential from stdin`。要原样喂字节用 `Start-Process -RedirectStandardInput <file>`。

## 落盘字节、WSL 路径与行尾

1. **`git show <blob> > file` 会用 UTF-16LE 写盘**。首字节 `FF FE`，随后 `python yaml.safe_load` 直接报 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte`，`bash -n` 也执行不到。逐字节取 blob 用 Python：`subprocess.run(['git','-C',repo,'cat-file','blob',':'+path], capture_output=True).stdout` 再 `open(...,'wb').write(...)`；纯 PowerShell 用 `[IO.File]::WriteAllText($p,$s,(New-Object Text.UTF8Encoding($false)))`。
2. **本机的 `bash` 是 WSL，不是 Git Bash**。`bash --version` 报 `x86_64-pc-linux-gnu` 时，Windows 盘路径要写 `/mnt/d/...`；写成 `/d/...` 得到 `/bin/bash: /d/workspace/...: No such file or directory`（exit 127），很容易被误读成脚本语法错。
3. **判断脚本语法前先确认行尾**：`git ls-files --eol <file>` 显示 `i/lf w/crlf` 时，工作树是 CRLF 而索引/提交是 LF；直接 `bash -n` 工作树文件会报 `syntax error near unexpected token $'{\r'`。用 `git cat-file blob :<path>` 拿提交版再检查，或转换行尾后再查。

同一目录下的 `git diff` 看不到这些差异（autocrlf 会归一化），所以「diff 干净」不能替代「落盘字节正确」。
