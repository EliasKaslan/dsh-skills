# 编码、计数与管道

Windows PowerShell 5.1 的 `-Encoding utf8` 通常带 BOM，`>`/Out-File 默认 UTF-16LE；PowerShell 6+ 文本输出默认 utf8NoBOM，7.4+ 原生命令字节重定向另有改进。明确指定读写编码，比较文件前检查前几字节和实际字节长度。[官方编码说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-7.5)

“多少行”先约定：LF 数、分隔后的元素数、逻辑非空行还是物理记录。`a\n\n` 有两个 LF、split 后三个元素；空文件单独定义。Get-Content/Measure-Object -Line、数组 Count 和原始文本方法可能采用不同定义；Out-String 会加入格式化与终止换行。对持续写入文件先做快照，不能把读时竞态当作编码丢行。Select-String -SimpleMatch 的 MatchInfo.Matches 不能当成所有字面命中的计数；需 occurrence 数时使用 escaped regex、明确大小写或直接字节逻辑。

Select-Object -Last 必须消费完整输入才能知道末尾，旧笔记关于它总会提前关闭 pipe 的说法不成立；-First 等操作有时会提前终止上游。对大型输出采用文件或完整消费者，检查原生命令退出状态及截断标识。

`$LASTEXITCODE` 指最近原生命令/脚本的退出码，必须在下一个原生命令前保存；PowerShell cmdlet 的成功另看 `$?`/异常。`ErrorActionPreference` 和 NativeCommandErrorActionPreference 的行为要按版本测试。[自动变量文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables?view=powershell-7.5)

时间用带 offset 的 DateTimeOffset；缺 offset 的文本先说明源时区，不能一律减8小时。压缩日志按格式流式解码，多帧 zstd 不按 magic 字符串切割。文件替换受文件和父目录的删除/创建权限影响，先查具体 ACL/占用，不用放宽整个树 ACL 或全局 execution policy 解决。cmd wrapper 用 ASCII 是兼容性选择，不代表 Unicode 路径永远不可用。
