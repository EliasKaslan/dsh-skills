---
name: dsh-isolated-web-host
description: 起个隔离 DSH host 做实验——想不污染真实 ~/.dsh 就验证插件行或 patch、真实 host 占着 3080 不能重启时用它：必加 --no-open、启动先落盘 pid 与端口、不带 token 的 401 判就绪、taskkill /PID 收尾；本机端口枚举是盲的（netstat / Get-NetTCPConnection 恒空），判就绪与判清理只认 HTTP 探针与落盘 pid。适用于"起个隔离 host 试试 / 想不污染真实环境就验证插件行或 patch / 真实 host 占着 3080 不能重启 / 端口枚举查不到监听 / netstat 找不到 3080 / 改了 preset 想找干净环境挂载看看"。不适用：只想验能不能挂载 → 用 `dsh-agent-preset-verification`；改哪层/何时生效/怎么撤 → 用 `dsh-agent-customization`。
whenToUse: 需要一个不污染真实 ~/.dsh、不占 3080 的第二 host 来自由起停地试插件行 / patch / preset 改动时用；它只搭环境，不做验收。判就绪与判清理用 HTTP 探针 + 启动时落盘的 pid，别用端口监听状态（本机枚举恒为空）。模型看不到本节。
---

# 隔离启动第二个 DSH web host

> 本 skill 是总纲 `dsh-agent-customization` 的子 skill：只负责「起一个隔离 host」这一段；DSH 的分层、生效时机与上线纪律见总纲。

## 何时调用

**加载本 skill 当：**

- 要实测一个插件行、`cordis.patch.yml` 改动、或 agent preset 改动，但**不能**让用户真实 `~/.dsh` 被写脏。
- 用户真实 host 正在 3080 上跑着，不能重启它。
- 需要验证"这个改动到底能不能挂载"，需要一个能自由起停的宿主。
- 需要在不动用户真实 `~/.dsh`、不占 3080 的前提下，反复重启一个 host 来试改动。

**不要用本 skill（转交）：**
- 要判定 preset 挂载是否正确、配置键 / 工具名对不对 → 用 `dsh-agent-preset-verification`（离线静态）。
- 已起会话，要核对 persona、工具裁剪、委派结果与会话日志 → 用 `dsh-agent-preset-verification` 的「阶段二」（手册在 `dsh-agent-preset-verification` 的 `references/online-session.md`）。

**前置**：本机能跑 `node`，且**已按第 0 步从进程命令行取到 `$BIN`**（`~/.dsh/profiles/node_modules/.../bin.js` **不存在**，别照抄旧路径）；已知真实 host 的端口占用情况（3080 是否在跑）。 ／ **后继**：host 起来并 401 判就绪后，进 `dsh-agent-preset-verification` 的「阶段二」做会话级验收；实验结束按本 skill 第 8 步 taskkill 收尾。

## 前置检查

隔离**只需要重定向一个环境变量**：`DSH_HOME`。优先级 = 显式配置 > `$DSH_HOME` > `~/.dsh`，**纯空白值视为未设**（`dsh-home-paths/lib/index.js:73-76`）。

以下路径全部随 `DSH_HOME` 走，这是隔离能成立的全部理由：

| 数据 | 路径 | 出处 |
|---|---|---|
| sessions | `$DSH_HOME/sessions` | `dsh-base/cordis.patch.yml:113` |
| storages | `$DSH_HOME/storages` | `dsh-base/cordis.patch.yml:151` |
| credentials | `$DSH_HOME/.credentials.yaml` | `dsh-credentials-local/lib/index.js:58` |
| skills | `$DSH_HOME/skills` | `dsh-skill-filesystem/lib/index.js:172` |
| profile | `$DSH_HOME/profiles/<name>` | `dsh-app-boot/lib/index.js:323-326` |
| 用户 patch 层 | `$DSH_HOME/cordis.patch.yml` | `dsh/lib/profile-boot-*.js:116` |

先确认真实环境当前状态，收尾时要能对比 —— **这一步只能用 HTTP 探针，不能用端口枚举**（本机端口枚举是盲的，见坑「整机端口枚举是盲的」）：

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:3080/' -UseBasicParsing   # 401 = 真实 host 活着
```

- `Get-NetTCPConnection -State Listen` 在本机**恒为空**（实测监听总数 `0`，同一时刻有 20 个 node 进程在跑），拿它当前置检查会得出"3080 没被占用"的假结论。

## 步骤

0. **先确定"用哪棵树驱动"**——**不要照抄路径**（本机实测：活跃 host 来自 **npx 缓存树**，`~/.dsh/launcher/runtime` 在盘但没在跑；而 `~/.dsh/profiles/node_modules` **根本不存在**，本 skill 旧版写的那个 `bin.js` 路径是错的，照抄必失败）：

   ```powershell
   # 从进程命令行认，不要从目录布局猜
   Get-CimInstance Win32_Process -Filter "Name='node.exe'" |
     Where-Object { $_.CommandLine -match '@deepseek-ai\\dsh\\lib\\bin\.js' } |
     ForEach-Object { "$($_.ProcessId)  $($_.CommandLine)" }
   # → 取 bin.js 前面那段路径当 $BIN
   #   本次实测：C:\Users\admin\AppData\Local\npm-cache\_npx\<hash>\node_modules\@deepseek-ai\dsh\lib\bin.js
   ```

   - `<hash>` 会随 npx 重装而变 ⇒ **每次现场重取**，别把 hash 写死进脚本。
   - 用**它自己那棵树**驱动隔离 host 最省事：依赖闭包齐全，不需要额外 junction。
   - 验证：`Test-Path $BIN` 为 `True`，且 `node $BIN --help` 能打印用法、退出码 0。

1. **建测试 home 骨架**（profile 目录必须存在，见坑 1）：

   ```powershell
   $T = 'D:\dsh-test-home'
   New-Item -ItemType Directory -Force -Path "$T\profiles\web" | Out-Null
   ```

   - 验证：`Test-Path "$T\profiles\web"` 为 `True`。

2. **不需要 junction `profiles\node_modules`**（本 skill 旧版这一条已被实测证伪，**不要再照做**）：本机 `~/.dsh/profiles/node_modules` 与测试 home 的 `profiles\node_modules` **都不存在**，隔离 host 照常起，`--dump-config` 与 headless 真跑都退出码 0。
   - 原因：profile bundle 按 **dsh 的安装位置**解析（`~/.dsh/launcher/launch-dsh.mjs` 头注释原话），**不是**按 profile 目录 ⇒ 只要驱动的那棵树自带依赖闭包就够了。
   - `healProfilesModuleFallback` 仍会按需 `mkdirSync` 该目录并补依赖闭包链接（`dsh-app-boot/lib/index.js:657-666`），所以**即使事后出现**这个目录也不必惊讶；但它是自愈产物，**不是前置条件**。

3. **初始化 `<DSH_HOME>\profiles\web`**，二选一（`package.json` 缺失时 `readProfileManifest` 直接抛 `failed to read profile manifest`，`dsh-app-boot/lib/index.js:746-753`）：

   ```powershell
   # 路径 A：从 shipped 模板初始化（bin.js:85 接受 --from-default-profile；模板见 app-boot:333-336）
   node $BIN --profile web --from-default-profile web --no-open --port 3099
   ```

   ```powershell
   # 路径 B：手工放骨架（实测走的就是"profile 目录自己建"这条）
   Copy-Item C:\Users\admin\.dsh\profiles\web\package.json "$T\profiles\web\package.json"
   ```

   - `initProfile` 只补缺失文件、从不覆盖已有文件（`dsh-app-boot/lib/index.js:379-397`），所以重跑是 no-op。
   - 未验证：两条路径本次未逐条实跑，仅经源码核对；实测确认的是"profile 目录在测试 home 里是真实目录"这一前提。

4. **写测试 home 的用户 patch 层 = `[]`**：

   ```powershell
   Set-Content -Path "$T\cordis.patch.yml" -Value '[]' -Encoding ascii
   ```

   - **不要**复制真实 `~/.dsh/cordis.patch.yml`：它含 4 个 MCP rows（playwright / context7 / sequential-thinking / github），其中 github row 的 `env:` 里是硬编码 GitHub PAT。
   - 用 `-Encoding ascii` 写 `[]` 可以彻底绕开 BOM 问题（见坑 5）。

5. **复制 `settings.yaml`（可选，安全）**：

   ```powershell
   Copy-Item C:\Users\admin\.dsh\settings.yaml "$T\settings.yaml"
   ```

   - 已确认这份文件里**没有密钥、没有绝对路径**，只有 `apiKeyEnv` 变量名、模型路由、`permission.defaultPreset` 等。
   - 但它可能带着 `agent-presets: default: orchestrator` 这类**已死的旧键**：`.agent-presets` 目录在 0.2.0 线**没有任何代码读**（单一归属见 `dsh-agent-customization` §2.1），顶层键还必须是**有效 entry id**，否则只 `logger.warn` 后静默丢弃。要干净就**删掉这一段**；复制 `.agent-presets\orchestrator` **没有意义**（该目录在本机也不存在）。
   - 凭据文件 `~/.dsh/.credentials.yaml` **只在需要真实发 LLM 请求时**才复制；只做端口就绪验证不需要它。

6. **起 host**：

   ```powershell
   $env:DSH_HOME = 'D:\dsh-test-home'
   node $BIN --profile web --no-open --port 3099
   ```

   - launcher 参数 `--profile` / `--from-default-profile` / `--patch`（可重复）/ `--dump-config` / `--dump-default-config` **必须写在 app 参数之前**（`dsh/lib/bin.js:85`）。
   - web app 参数（`dsh-web-app/lib/startup.js:22`）：`--host <host>`、`--no-open`、`--port <port>`、`--trusted-host <authority...>`（可重复）。
   - `--no-open` **必加**（见坑 2）。
   - **启动时先把 `pid` 与 `port` 落盘**（例如 `$T\host.json`），收尾只认这份记录；**不要**在收尾时反查（pid 差集 / 按命令行模糊匹配都会误伤）：

     ```powershell
     # 用能拿到子进程对象的起法，把 pid 与 port 写文件；不要用 $PID —— 它是 PowerShell 自己（且是只读自动变量）
     $p = Start-Process node -ArgumentList '<bin.js 与上文的各参数>' -PassThru -NoNewWindow
     [IO.File]::WriteAllText("$T\host.json", ('{"pid":' + $p.Id + ',"port":3099}'), (New-Object System.Text.UTF8Encoding $false))
     ```

     - 未验证：本机未实跑 `Start-Process -PassThru` 这条取 pid 的路径；已确认的纪律是"pid 必须来自启动那一刻并落盘"，而不是收尾时靠枚举或差集反推。

7. **判就绪 —— 只用 HTTP 探针**：对目标端口发 GET，`401`（不带 token）= 已就绪；连接被拒 / 超时 / 5xx 才是不就绪。**不要**用"端口在不在监听"判就绪。

   ```powershell
   $code = $(try { (Invoke-WebRequest -Uri 'http://127.0.0.1:3099/' -UseBasicParsing -TimeoutSec 5).StatusCode } catch { if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'NO-CONNECTION' } })
   $code
   ```

   - `401` = 服务已起来、token 围栏在生效，**不是故障**；带 token 返回 200。
   - **`-SkipHttpErrorCheck` 是 PS7 参数，本机 5.1 会报 `A parameter cannot be found that matches parameter name 'SkipHttpErrorCheck'.`** —— 所以用上面的 `try/catch` 形式（`try` 是语句，必须放进 `$()`，见 `pwsh-on-windows`）。
   - 未验证：本机未实跑上面的 `catch` 分支；实测过的是 `Invoke-WebRequest -Uri 'http://127.0.0.1:3080/' -UseBasicParsing` → `401 Unauthorized`。
   - 同时 stdout 会打印 `dsh web: http://127.0.0.1:3099/?token=...`，这一行本身就是就绪信号。

8. **清理 —— 断言 = ①"进程没了" 且 ②"端口连不上"，两条同时成立才算干净**：

   ```powershell
   taskkill /PID <第 6 步落盘的 pid> /T /F
   Get-Process -Id <第 6 步落盘的 pid> -ErrorAction SilentlyContinue   # ① 必须无输出
   # ② 对同一端口再发一次第 7 步的 HTTP 探针：必须变成 NO-CONNECTION / 超时，不再是 401
   ```

   - **不要**用"端口没在监听"当清理判据（`Get-NetTCPConnection` 在本机恒为空，见坑「整机端口枚举是盲的」）—— 那是**恒真的空断言**，进程还在跑也会"通过"。
   - 3080 上真实 host 是否还在，同样只认 HTTP 探针（401 = 还在），不要用端口枚举。

## 坑与修法

- **不能 junction 整个 `profiles` 目录**。
  → 原因：`prepareProfile` 每次启动都会 `writeFileSync(join(profile.dir, 'cordis.yml'), ...)`（`dsh/lib/profile-boot-*.js:209`）。junction 整目录时 `<DSH_HOME>\profiles\web\cordis.yml` 会写穿到真实 profile 目录。
  → 修法：`profiles\<name>` 在测试 home 里必须是**真实目录**；`profiles\node_modules` **不需要**预先建（步骤 2 已实测证伪，事后出现也只是 `healProfilesModuleFallback` 的自愈产物）。

- **不加 `--no-open` 会在用户桌面弹出浏览器**。
  → 原因：`openBrowser: z.boolean().default(true)`（`dsh-web-app/lib/index.js:34`），且只在检测到 SSH 会话时才不弹（`:174`）。
  → 修法：命令里始终带 `--no-open`。

- **`--host 0.0.0.0` 被显式拒绝**，报 `error: --host 0.0.0.0 is intentionally not supported yet for safety: it would expose remote code execution to the network; use 127.0.0.1 instead`（`dsh-web-app/lib/startup.js:40`）。
  → 修法：用 `--host 127.0.0.1` 或省略（默认即本地）。

- **不带 token 的请求返回 401**，容易被误判成"启动失败"。
  → 原因：token 围栏，正常行为。
  → 修法：把 401 当作就绪判据；要 200 就带上 stdout 里那串 `?token=...`。

- **PowerShell 5.1 的 `Set-Content -Encoding utf8` 会写 3 字节 BOM**（`[System.Text.Encoding]::UTF8.GetPreamble().Length = 3`），而真实 `~/.dsh/cordis.patch.yml` 是无 BOM 的（首字节 `23 20 4D`）。同时 `Get-Content` 默认按 ANSI 读，UTF-8 中文会变 `鈥?`。
  → 修法：patch 文件内容只有 `[]`，直接用 `-Encoding ascii`；要读 UTF-8 文件加 `-Encoding utf8`。要写无 BOM 的 UTF-8 用 `[System.IO.File]::WriteAllText($p, $s, (New-Object System.Text.UTF8Encoding $false))`。

- **隔离生效的证据就是测试 home 被写**：harness 会自行创建 `<测试home>\storages\workspace.json`、`.credentials.yaml`、`.anonymous-user-id`。这几个文件出现在测试 home 而不是真实 `~/.dsh`，才算隔离成功。

- **整机端口枚举是盲的 → 任何"端口在不在监听"的断言在本机都是恒真的空断言（看起来在保护你，实际什么都没查）**。
  → 实测：`Get-NetTCPConnection -State Listen` 遍历后监听总数 = **0**，同一时刻 `Get-Process | Where-Object { $_.ProcessName -match 'node|dsh|bun' }` 有 **20 个 node 进程**；`netstat -ano | Select-String -Pattern ':3080\s' -SimpleMatch` → `netstat: 3080 NOT FOUND`。
  → 但**连通性完全正常**：`Invoke-WebRequest http://127.0.0.1:3080/ -UseBasicParsing` → **401 Unauthorized**（真实 host 活着）；`http://localhost:3080/` 同样 401。
  → **决定性对照实验**（证明是"枚举被屏蔽"而不是"真的没监听"）：自己在 loopback 起一个监听器并立刻回查——

    ```powershell
    $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 34567)
    $l.Start(); Start-Sleep -Milliseconds 400
    netstat -ano | Select-String -Pattern ':34567\s' -SimpleMatch   # → 无匹配
    ```

    结果 `SELF_LISTENER_VISIBLE=NO` —— 自己刚起的监听器，自己的 `netstat` 也看不见。
  → 修法：**判就绪只能用 HTTP 探针**（对目标端口发 GET，`401` = 就绪；连接被拒 / 超时 / 5xx 才是不就绪）；**判"我的进程已清理干净"不能用"端口没在监听"**，正确断言是**两条同时成立**：① `Get-Process -Id <启动时记录下来的 pid>` 无输出；② 对该端口发 HTTP 请求已连不上。
  → 推论：**启动时必须先把 pid 与端口落盘**（第 6 步），收尾只认这份记录；**不要**用 pid 差集、不要用按映像名 / 命令行的模糊匹配杀进程。
  → 判据：**没被真正触发过的安全网不算安全网 —— 一个恒真的断言看起来在保护你，实际什么都没查。**

## 不要做什么

- 不要 junction 整个 `profiles` 目录（会写穿真实 profile 的 `cordis.yml`）。
- 不要复制真实 `~/.dsh/cordis.patch.yml`（含硬编码 GitHub PAT 与 MCP rows）。
- 不要无条件复制 `~/.dsh/.credentials.yaml`（只在需要真实 LLM 调用时）。
- 不要占用 3080（用户真实 host 的端口）：不在上面起东西、不重启它、不杀它的进程；判它是否活着只允许用不带 token 的只读 GET（401 = 活着）。
- 不要用"端口在不在监听"判就绪或判清理（本机 `Get-NetTCPConnection` / `netstat` 恒为空 → 恒真空断言，见坑「整机端口枚举是盲的」）。
- 不要用 `--host 0.0.0.0`。
- 不要在清理时用 `taskkill /IM node.exe` 这类按映像名杀的写法——会连带杀掉用户真实 host；也不要用"启动前后 pid 差集"或命令行模糊匹配反查该杀谁（会误伤同机其他 host 与并发会话），只 kill 第 6 步落盘的 pid。

## 验收标准

- stdout 出现 `dsh web: http://127.0.0.1:<port>/?token=...`。
- `Invoke-WebRequest http://127.0.0.1:<port>/` 无 token 返回 `401`，带 token 返回 `200`（本机 5.1 用 `-UseBasicParsing`，**不要**用 PS7 的 `-SkipHttpErrorCheck`）。
- 测试 home 下自动出现 `storages\workspace.json`、`.credentials.yaml`、`.anonymous-user-id`。
- 真实 `C:\Users\admin\.dsh` 下 `sessions` / `skills` / `storages` 无新增文件。
- 清理后：`Get-Process -Id <第 6 步落盘的 pid>` 无输出，且该端口 HTTP 请求已连不上（**不要**用"端口监听数为 0"当判据——本机恒真）。3080 上原 host 是否仍在，同样用 401 探针判。
