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

## 落盘编码与 WSL bash 路径：git blob 重定向、/mnt/d、CRLF 假语法错

本次实测：`pwsh` 工具表现出来的仍是 Windows PowerShell 5.1 的编码行为（`>` 重定向写 UTF-16LE），不要因为工具名叫 pwsh 就假定是 Core 7。下面是把 git/文本工具产物落盘的三个真实坑：

1. **`git show <blob> > file` 会用 UTF-16LE 写盘**。PowerShell 的 `>` / `Out-File` 默认编码不是 UTF-8，落到文件首字节是 `FF FE`，随后 `python yaml.safe_load` 直接报
   `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte`，`bash -n` 也会执行不到。
   要逐字节拿 blob 就用 Python 抓字节：`subprocess.run(['git','-C',repo,'cat-file','blob',':'+path], capture_output=True).stdout`，再 `open(...,'wb').write(...)`；用 PowerShell 时必须 `[IO.File]::WriteAllText($p, $s, (New-Object Text.UTF8Encoding($false)))`。

2. **本机的 `bash` 是 WSL，不是 Git Bash**。`bash --version` 报 `x86_64-pc-linux-gnu` 时，Windows 盘路径要写成 `/mnt/d/...`；写成 `/d/...` 会得到
   `/bin/bash: /d/workspace/...: No such file or directory`（exit 127），很容易被误读成「脚本语法错」。先 `bash -n /mnt/d/...` 再判断。

3. **判断脚本语法前先确认行尾**：`git ls-files --eol <file>` 会显示 `i/lf w/crlf` —— 工作树是 CRLF（`core.autocrlf`），但 index/提交是 LF。直接 `bash -n` 工作树文件会报
   `syntax error near unexpected token $'{\r'`，这不是脚本问题；用 `git cat-file blob :<path>` 拿到提交版再检查，或转换行尾后再查。

同一目录下的 `git diff` 看不到这些差异（autocrlf 会归一化），所以「diff 干净」不能替代「落盘字节正确」。
