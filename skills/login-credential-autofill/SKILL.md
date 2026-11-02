---
name: login-credential-autofill
description: 登录凭据自动填充的本地凭据库与防封号护栏——页面要登录时按账号取凭据填入、先复用已有登录态、每账号24小时最多1次密码提交、遇验证码/2FA/风控页立刻停手交人，附字段读取与额度记账脚本。适用于"帮我登录一下 / 用我的账号登进去 / 要输密码了 / 这个站点要登录 / 微软和 GitHub 账号密码在哪 / 我的密码存在哪台机器上 / 填完要不要帮我点提交 / 登录失败了还能不能重试 / 会不会把号登封 / 自动填密码安全吗"。不适用：GitHub API 或 PAT 提 PR → 用 `github-pr-flow`；读 Outlook 邮件 → 用 `outlook-mailbox-control`；过滑块验证码 → 用 `dingxiang-slider-captcha`；本机 pwsh 编码坑 → 用 `pwsh-on-windows`。
whenToUse: 页面出现登录表单或请求返回 401 时，按账号键从本机凭据库取字段填入，并受 LoginGuard 的 24h 额度约束；含读取/记账脚本与挑战页判据。模型看不到本节。
---

# 登录凭据自动填充（本地凭据库 + 防封号护栏）

2026-11-02 建立。凭据只存本机 `~\.dsh\.secrets\accounts.json`（ACL 仅当前用户），skill 正文**不含任何账号或密码**——因为 `~\.dsh\skills` 每天 02:00 被 `dsh-skills-publish` 推到**公开**仓，写进正文等于公开。

## 何时调用

**加载本 skill 当：**
- 浏览器页面出现登录表单（邮箱/密码两栏、或"先输邮箱再输密码"两步页），或 `browser_snapshot` 看到 `Sign in` / `登录`。
- 某个 MCP 工具、git push、网页后台返回 `401` / `403` / `not logged in`，需要先建立登录态。
- 用户说"登录一下 / 用我的账号登进去 / 帮我填一下密码 / 这个站点要登录"。

**不要用本 skill（转交）：**
- 目标是 GitHub 的 API / PR / fork 推送（用 PAT，不走密码）→ `github-pr-flow`。
- 读或回 Outlook 邮件（MSA 走设备码 OAuth，不走密码）→ `outlook-mailbox-control`。
- 遇到拼图/滑块类验证码 → `dingxiang-slider-captcha`（结论是成功率极低，别硬试）。
- 脚本跑不起来、中文乱码、`-File` 参数被拒 → `pwsh-on-windows`。

**前置**：`~\.dsh\.secrets\accounts.json` 存在且 ACL 只含本用户；`LoginGuard.ps1 -Action check` 返回 `ALLOW`。 ／ **后继**：登录成功后回到目标站点对应的领域 skill（GitHub 侧 → `github-pr-flow`，邮箱侧 → `outlook-mailbox-control`）。

## 0. 凭据在哪、怎么读（单一出处）

| 东西 | 路径 | 说明 |
|---|---|---|
| 账号库 | `~\.dsh\.secrets\accounts.json` | 键 = `microsoft` / `github`；字段 `identifier` / `username` / `password` / `mfa` / `auto_submit` |
| 额度账本 | `~\.dsh\.secrets\.login-ledger.json` | `LoginGuard.ps1` 自动建；每次填提交前后各写一次 |
| GitHub PAT | `~\.dsh\.secrets\github-pr-flow.token` | classic `ghp_`，2026-11-02 实测 `GET /user` → `login=EliasKaslan` |

**读法：一次只取一个字段，别整文件读。** 整文件 `read` 会把两个账号的密码一起灌进上下文和会话日志。

```powershell
$S = "C:\Users\admin\.dsh\skills\login-credential-autofill\scripts"
# 本机 execution policy = Restricted，裸 `& $S\xxx.ps1` 会被拦（原文见 §5.9），必须走 -File + Bypass
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\Get-LoginCredential.ps1" -Account github -Field identifier   # 邮箱
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\Get-LoginCredential.ps1" -Account github -Field username    # EliasKaslan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\Get-LoginCredential.ps1" -Account github -Field flags       # mfa=True auto_submit=False
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\Get-LoginCredential.ps1" -Account github -Field password -Reveal   # 只在要塞进密码框那一刻调用
```

下文写 `LoginGuard.ps1 -Action <x>` 时，一律按同一形状执行：
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$S\LoginGuard.ps1" -Action check -Account github`。

- 不带 `-Reveal` 时打印 `HIDDEN len=<n>` 并 **exit 4**——这是设计行为，不是报错。
- 脚本是纯 ASCII（PS 5.1 会把无 BOM 的 UTF-8 中文按 GBK 解码成语法错，见 `pwsh-on-windows`）。
- **绝不**把密码写进：skill 目录任何文件、ledger、命令历史、最终答复、commit。写进 skill 正文 = 公开。

## 1. 防封号铁律（L1–L10，逐条都要能指出做了什么）

- **L1 先复用登录态**：能确认已登录就**不登录**。Playwright MCP 用**持久 profile** `C:\Users\admin\AppData\Local\ms-playwright-mcp\mcp-chrome-a13d2a8`（实测本次 chrome 进程 `--user-data-dir` 就是它），cookie 跨会话保留 ⇒ 绝大多数"要登录"其实是伪需求。**新开 profile / 无痕 = 新设备指纹 = 风控加分**，是下策。
- **L2 每账号 24h 最多 1 次密码提交**：由 `LoginGuard.ps1 -Action check` 强制，`DENY` 就停手交人，不许绕（改参数、删 ledger 都算绕）。
- **L3 失败即停**：`fail` 之后 60 分钟冷却，期间再试一次都不行。**密码重试是触发锁号的头号原因。**
- **L4 遇挑战立刻锁 24h**：任何验证码/2FA/风控页 → `LoginGuard.ps1 -Action lock -Reason <原文>`，然后交人，**不自行绕过**。
- **L5 不并发**：同一账号同时只允许 1 个浏览器上下文/1 个会话。开第二个窗口同时登录是最危险的动作之一。
- **L6 不换出口、不换指纹**：不切 VPN/代理/Tor 重试，不改 UA、不禁 JS、不清 cookie、不屏蔽 webdriver 特征。这些操作全部提高风控分，不是降。
- **L7 2FA 只请用户报码**：不自己去邮箱翻验证码。
- **L8 "密码错"只认明确文案**（见 §3）。超时、空白页、网络错误 **≠ 密码错**，不许重试。
- **L9 不导出登录态**：不存 `storageState`、不复制 cookie 到文件、截图避开密码框与一次性验证码。
- **L10 提交受 `auto_submit` 管**：`auto_submit=False` 的账号（microsoft / github 现在都是）**填完就停**，把回车交给用户。

## 2. 标准流程（Playwright MCP）

1. **过闸门**：`LoginGuard.ps1 -Action check -Account <key>` → 必须 `ALLOW`（rc=0）；`DENY`（rc=3）就停。
2. **探登录态**：打开目标站的已登录页（如 `https://github.com/`），`browser_snapshot` 找头像/用户名。已登录 → 直接结束，**不碰登录页**。
3. **开登录页**：`browser_navigate` 到 `login_url`，`browser_snapshot` 确认这是密码表单、不是挑战页。
4. **填标识**：GitHub 是单页两栏，`browser_fill_form` 填邮箱 + 密码；**Microsoft 按两步处理**——先填邮箱 → 点 `Next` → 下一页才出密码框（本轮未实测该布局，以 `browser_snapshot` 实际内容为准，别硬等某个选择器）。
5. **取密码并填入**：`Get-LoginCredential.ps1 -Field password -Reveal` → 立刻 `browser_type` 进密码框；**不复述、不写注释、不进后续消息**。
6. **看 `flags`**：`auto_submit=False` → 停在这里，告诉用户"已填好，请确认后按回车"，然后等。
7. **要提交时**：先 `LoginGuard.ps1 -Action attempt`（吃掉 24h 唯一额度，**只在点提交前记**，填完没提交不许记），再 `browser_click` 提交。
8. **判结果**：`browser_snapshot` 按 §3 表处理，然后 `success` / `fail` / `lock` 记账。
9. **GitHub 出现 passkey 弹窗**（`Sign in with a passkey`）：点 `Use password`；点不到就停手交人，别反复点。

## 3. 判据表（看到的原文 → 判定 → 动作）

| 页面原文（GitHub / Microsoft） | 判定 | 动作 |
|---|---|---|
| `Incorrect username or password` / `Your account or password is incorrect` / `We couldn't find your account` | 密码或账号错 | `fail` 记账 → 停 → 60 分钟冷却 → 让用户核对，**不重试** |
| `Help us protect your account` / `Verify your identity` / `unusual activity` / `suspicious sign-in` | 风控挑战 | **`lock -Reason challenge` 24h** → 停手交人 |
| `Enter code` / `Authenticator` / `two-factor` / 6 位数字框 | 2FA | 停 → 请用户报当前验证码；不自己去邮箱翻 |
| `captcha` / 滑块 / `hCaptcha` / `I'm not a robot` | 人机验证 | 停手交人；自动化过码 = 高危 |
| 出现头像 / 用户名 / `Dashboard` | 登录成功 | `success` 记账 |
| 超时 / 空白页 / `net::ERR_*` / 未知页面 | **不是密码错** | 不记账 fail、不重试；重载一次仍不行 → 交人 |

> 上表文案是两家登录页的常见原文，**本轮没有逐个触发实测**（不拿真号去试）。真正起作用的判据只有一条：**只有能明确读成"密码/账号错"的才算 `fail`，其余一律按挑战处理（停手 + `lock`）**。

## 4. 为什么这两个账号不该走密码

- **GitHub**：网页登录基本 100% 要 2FA/通行密钥；git 与 REST 的密码认证早已停用。**任何 API / 推送需求直接用 PAT**（`github-pr-flow.token`，实测有效），根本不进登录页。另注 `cordis.patch.yml` 里还硬编码了一个 fine-grained PAT，两类 token 的权限差异见 `github-pr-flow` §0——fine-grained 不能对上游仓建 PR。
- **Microsoft（个人 MSA）**：从非惯用地/机房 IP 用密码登录，触发 `Help us protect your account` 的概率极高；一旦锁号要靠手机/备用邮箱解，代价远大于省下的那次输入。所以 `auto_submit=false`，**默认只填不提交**。

## 5. 坑与修法（本轮实测）

1. **别指望"脚本读密码、模型看不到"**：`browser_run_code_unsafe` 的沙箱里拿不到 fs，实测返回
   `{"has_require":"undefined","has_process":"undefined","fs_ok":false,"err":"A dynamic import callback was not specified."}`
   → 页面/代码上下文不是 Node 进程，`require` / `process` / 动态 `import` 全无。密码只能从 `-Reveal` 的输出进一次上下文；因此**每次登录只取一次、用完不再引用**。
2. **`file:` 被 MCP 拦**：`Access to "file:" protocol is blocked. Attempted URL: file:///...`
   → 本地自测用 `python -m http.server 8765 --bind 127.0.0.1 --directory <dir>` 起个 127.0.0.1 页面，再用 `browser_navigate http://127.0.0.1:8765/...`（本轮就是这样验通 fill+submit：返回 `{"submitted_ok":true}`）。现成的自测页与**假**凭据在本 skill 的 `assets\login-selftest.html` / `assets\selftest-accounts.sample.json`，复测不必碰真账号。
3. **`attempt` 记早了白吃额度**：填完但没提交就记 `attempt`，24h 唯一额度会被用掉，真需要登录时反而 `DENY`。**只在 `browser_click` 提交前那一瞬记。**
4. **`success` 不退额度**：24h 窗口是固定预算，成功也不清空（重复登录本身就是风控信号）。`success` 只清 `failCount` 与冷却。
5. **`HIDDEN len=<n>` 不是截断**，是没给 `-Reveal` 的正常拒绝（exit 4）。
6. **GitHub 的登录标识是邮箱不是用户名**：填 `identifier`（QQ 邮箱），别自己拼 `EliasKaslan@...`。
7. **脚本一律纯 ASCII**：中文写进 `.ps1` → PS 5.1 按 GBK 解码 → `Unexpected token` / `Missing closing '}'`。
8. **`icacls` 只对文件生效**：`accounts.json` 建好后必须 `/inheritance:r /grant:r "admin:(F)" "SYSTEM:(F)" "Administrators:(F)"`，否则继承父目录的 Everyone 读权限；改完用 `icacls <path>` 复核只剩三行。
9. **本机 `& script.ps1` 直接被执行策略拦**（实测 `$PSVersionTable.PSVersion` = `5.1.26100.9711`，`Get-ExecutionPolicy` 为 `Restricted`）：
   原文 `无法加载文件 ...\Get-LoginCredential.ps1，因为在此系统上禁止运行脚本。`（英文环境为 `cannot be loaded because running scripts is disabled`）
   → 这不是脚本坏了，也**别去改全局 ExecutionPolicy**；一律用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<绝对路径>" <参数>`。

## 6. 不要做什么

- 不为了"省一次输入"把 `auto_submit` 改成 `true`；不改 `MaxAttemptsPer24h` 默认值（1）去"多试一次"。
- 不用无痕/新 profile 反复试密码；不开两个浏览器上下文登同一账号；不切 VPN 换 IP 重试。
- 不自动过验证码、不自动读邮箱取 2FA 码、不导出 cookie。
- 不把密码/邮箱写进报告、日志、commit、skill 正文。
- 不刻意"模拟人类"（随机延迟、乱动鼠标）——没有证据表明有效，反而制造异常节奏。

## 7. 验收标准

- 动手前：`LoginGuard.ps1 -Action check` 输出 `ALLOW`；`-Action status` 能读回 `attemptsUtc` / `failCount` / `lockedUntilUtc`。
- 成功：`browser_snapshot` 里能看到头像/用户名，且 ledger `lastResult=success`。
- 挑战：ledger `lockedUntilUtc` 非空，之后 24h 内 `check` 一律 `DENY ... locked_until=`。
- 收尾自检：密码没有出现在 skill 目录任何文件、ledger、最终答复里（`grep` 密码字符串在 `~\.dsh\skills` 应零命中）。

## 8. 维护

- 换密码：只改 `accounts.json` 的 `password` 字段，然后重跑一次 ACL（`icacls` 三行）。
- 新增站点：在 `accounts.json.accounts` 加键，同时把键名加进 `Get-LoginCredential.ps1` 的 `ValidateSet`（否则 `-Account` 直接被拒，原文 `does not belong to the set`）。
- 清额度（确认是误记时）：删 `~\.dsh\.secrets\.login-ledger.json` 里对应账号的 `attemptsUtc` 项；**不要**整文件删了来绕过 `DENY`。
