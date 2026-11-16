---
name: "pwsh-on-windows"
description: "在 Windows 排查 PowerShell 版本、编码/BOM、原生命令参数与退出码、管道和文本计数问题；用于脚本行为与观察不一致，先区分 Windows PowerShell 5.1 和当前 pwsh。"
whenToUse: "在 Windows 排查 PowerShell 版本、编码/BOM、原生命令参数与退出码、管道和文本计数问题；用于脚本行为与观察不一致，先区分 Windows PowerShell 5.1 和当前 pwsh。 模型触发仍以description为准。"
---

# Windows shell 的可靠执行

先记录 `$PSVersionTable.PSEdition`、PSVersion、实际可执行文件和有关的原生命令参数模式。2026-11-16本机默认为 Core 7.6.9，powershell.exe 5.1 仍存在；旧“只有5.1”已失效。语法/编码按实际执行器解释。

- 复杂代码写成工作区脚本再 `-File` 执行，逐层确定 PowerShell、cmd、Python/Node 谁解析引号与 `$`。尽量用结构化参数数组，Core 可用 ProcessStartInfo.ArgumentList；Windows PowerShell 所依赖 .NET Framework 不能照搬。JSON.stringify 不是 shell quoting。
- 立即保存原生命令退出码（`$LASTEXITCODE`/subprocess.returncode），同时检查预期产物。stderr 有内容不等于失败，目录存在或 git 打印进度不等于成功；记录 tool 包装错误与真实子进程状态的区别。
- 需要原样字节时用二进制读写/重定向接口，不经 Out-String、Get-Content、格式化表格或跨 shell 转手。默认编码和 BOM、行数定义、管道消费方法见 [版本与字节](references/encoding-process.md)。
- 不用 `$PID`、`$HOME` 等自动变量作临时变量。脚本别名/函数可能遮蔽命令，必要时用 Get-Command 查解析结果。Native stderr 与 PowerShell terminating error 分开处理。
- 文件操作始终使用同一 shell 的 LiteralPath，递归移动/删除前解析绝对路径并验证在指定边界内。不要把 PowerShell 枚举结果拼成 cmd 删除命令。后台辅助进程需要隐藏窗口时显式配置，保留 PID/创建时间用于定向停止。

对可疑结论做最小合成 fixture，保存输入字节、shell 版本、stdout/stderr/exit。不要用真实凭据、生产配置或现场被持续写入的日志做编码实验。
