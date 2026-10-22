---
name: outlook-mailbox-control
description: Outlook.com（个人 MSA）邮箱接管——接管我的 outlook 邮箱、查收件箱、按关键词搜邮件、读正文和附件、以我的名义回信、存草稿：MS365 MCP discovery 直调的能力配方（工具名＋最小 parameters JSON）、三条个人账户硬规则（authority 必须 consumers／只支持 delegated／app password 已硬禁用）、设备码登录与令牌核验、🤖 前缀护栏、逐字错误原文。适用于"接管我的 outlook 邮箱 / 查一下收件箱 / 按关键词搜邮件 / 读某封邮件的正文和附件 / 以我的名义回一封信 / 帮我存个草稿 / outlook 邮件工具报错 / authority 该填什么 / app password 为什么用不了"。不适用：QQ 邮箱 IMAP → 用 `qq-mail-control`；改 DSH 插件行与 MCP 接入层 → 用 `dsh-agent-customization`；PowerShell 的坑 → 用 `pwsh-on-windows`。
whenToUse: 通过 DSH 的 `mcp__outlook__*` 工具接管 Outlook.com 个人邮箱（列/搜/读/附件/回复/草稿）或排查其认证与调用错误时使用。基线：ms-365-mcp-server 0.157.0 ＋ consumers ＋ --discovery。模型看不到本节。
---

# Outlook 邮箱接管（MS365 MCP，discovery 直调）

## 何时调用

**加载本 skill 当：**
- 用户说"接管我的 outlook 邮箱 / 查一下收件箱 / 按关键词搜邮件 / 读某封邮件的正文和附件 / 以我的名义回一封信 / 帮我存个草稿 / 邮件相关的排查"。
- 命令输出里出现这些可观测信号：`mcp__outlook__`、`execute-tool`、`Tool not found: `、`ErrorInvalidIdMalformed`、`InefficientFilter`、`AADSTS500200`、`AADSTS700038`、`File C:\Program Files\nodejs\npx.ps1 cannot be loaded`。
- 需要给 `@softeria/ms-365-mcp-server` 写/核对接入配置行（**写法纪律在 `dsh-agent-customization`，本 skill 只给已验证的那一行**）。

**不要用本 skill（转交）：**
- 本机 PowerShell 自身的坑（GBK 乱码 / BOM / 执行策略 / 管道吞输出 / PS7 语法）→ 用 `pwsh-on-windows`。
- 改 DSH 自身的插件行、MCP 接入层、上线与回滚纪律（五层何时生效、热重载≠冷启动）→ 用 `dsh-agent-customization`。
- 判断这条经验该不该沉淀、写到哪个根 → 用 `sedimenting-skills`。
- `SKILL.md` 的 frontmatter / description / 「何时调用」段的写法契约 → 用 `dsh-skill-authoring`。

**前置**：① `C:\Users\admin\.dsh\.secrets\ms365\` 下已有已登录的令牌缓存（否则先做 §5 设备码登录，需要**人在场**点同意）；② MCP server 已接进 DSH，工具名以 `mcp__outlook__` 开头。 ／ **后继**：任何写操作（send / reply / forward / create-draft / move / delete / update）**先给用户看 dry-run 再确认**（§6）。

## 1. 架构与为什么这样接

链路：DSH ←（`@deepseek-ai/dsh-mcp-client`，stdio）← `npx -y @softeria/ms-365-mcp-server --discovery`。`serverName: outlook` ⇒ 公开工具名 = `mcp__outlook__<工具名>`。下面是**已落盘的那一行**（隔离 home 版 `_build\dsh-iso-home\cordis.patch.yml:1-16` 原文逐字；同一行随后作为第 6 个 insert row 写进真实配置，见下「真实部署」）：

```yaml
- insert:
    - id: mcp-outlook
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: outlook
        transport: stdio
        command: npx
        args:
          - '-y'
          - '@softeria/ms-365-mcp-server'
          - '--discovery'
        env:
          MS365_MCP_TENANT_ID: 'consumers'
          MS365_MCP_TOKEN_CACHE_PATH: 'C:\Users\admin\.dsh\.secrets\ms365\.token-cache.json'
          MS365_MCP_SELECTED_ACCOUNT_PATH: 'C:\Users\admin\.dsh\.secrets\ms365\.selected-account.json'
          MS365_MCP_MESSAGE_SIGNOFF_PREFIX: '🤖 '
```

**已验证：DSH 侧注册与可调（此前"只验 server 端、未验 DSH 侧目录"的缺口已闭合）**：
- 隔离 host 冷启动后就绪判据 = `Invoke-WebRequest http://127.0.0.1:3099/ -UseBasicParsing` → **401 Unauthorized**。
- 在该 host 的**真实 DSH 会话**里，模型调 `mcp__outlook__execute-tool`（`{"tool_name":"list-mail-folders","parameters":{}}`）**成功返回真实邮箱文件夹**：`["草稿","存档","对话历史记录","发件箱","垃圾邮件","收件箱","已发送邮件","已删除邮件"]`；**两个独立会话均成功**（一个返回 JSON 数组、一个返回空格分隔字符串）。
- ⇒ `mcp__outlook__*` 确实注册进 DSH 且可被模型调用。工具数/字符数（§1 引用的 4,404 / 272,769）仍是对 server 端 `tools/list` 实测的，不是对 DSH 侧目录实测的。
- **DSH 侧注册的是 9 个工具**（权威清单，来自隔离会话页面记录 `_build\mcp-scratch\iso-run\session-page.json`）：`mcp__outlook__execute-tool` / `get-tool-schema` / `search-tools` **＋ 6 个认证工具** `login` / `logout` / `verify-login` / `list-accounts` / `select-account` / `remove-account`（该文件 `:171,:221,:417,:472,:506,:550` 命中，其中 `:221` 是 `mcp__outlook__login`）。
- ⇒ **6 个认证工具是直接挂在 DSH 工具面上的独立工具，模型可按名直接调用**（`mcp__outlook__login`、`mcp__outlook__list-accounts`…），**不是**只能经 `execute-tool` 间接调用。两种语境的区分见 §2 末条。

**真实部署（不是隔离 home，已落盘）**：
- 该行已写入**真实的** `C:\Users\admin\.dsh\cordis.patch.yml`——该文件是**单一的 `- insert:` 列表**，新行是**第 6 个 insert row**，文件 83 行。
- 部署前后校验：`HAS_BOM=false`、`HAS_CR=false`、`YAML_OK=true`、`INSERT_ROWS=6`、`OUTLOOK_ROW_COUNT=1`、`MS365_MCP_MESSAGE_SIGNOFF_PREFIX` 的 codepoints = `1f916+20`（emoji 完好）、**原有 5 行逐字节未改动（纯追加）**。
- 备份：`C:\Users\admin\.dsh\cordis.patch.yml.bak-20260930-114106`（1787 字节、无 BOM）。
- **生效条件**：必须**重启 host**；真实 host 的启动链实测为 `npx @deepseek-ai/dsh@latest web`（其下 `cmd /d /s /c dsh web` → `@deepseek-ai/dsh/lib/bin.js web`）。
- **回滚**：删掉追加的那一段（含注释），或用备份覆盖。（**只记这条 outlook 行本身**；通用的五层生效时机与上线/回滚纪律 → 用 `dsh-agent-customization`。）

`--discovery` 暴露恒 9 个工具 = 3 个 discovery（`search-tools` / `get-tool-schema` / `execute-tool`）+ 6 个恒注入认证工具（`login` / `logout` / `verify-login` / `list-accounts` / `select-account` / `remove-account`），DSH 注入 **4,404 字符**（≈1.1k token）。

**为什么不用 `--preset mail`**：51 个工具、**272,769 字符**，其中 `inputSchema` 占约 88%，且工具 schema 属于 request header、**每一轮请求都重发**。4,404 vs 272,769 = 省 98.4%（61.9×）。代价见 §6（写面没变小、参数零校验）。

**`execute-tool` 是无状态直通**：实测不调 `search-tools`、不调 `get-tool-schema`，第一次 `tools/call` 直接打 `execute-tool` 即成功；那两个工具只是元数据查询，**不参与"加载/注册"**。所以只有名字/参数写错才会失败——这正是本 skill 必须把配方逐条写下来的原因。

## 2. 调用形态

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
  "name":"execute-tool",
  "arguments":{"tool_name":"list-mail-folders","parameters":{}}}}
```

| 工具 | 参数名 | 必填 | 形态 |
| --- | --- | --- | --- |
| `execute-tool` | `tool_name` | 是 | 工具名字符串，如 `"list-mail-messages"`（**不是** `tool` / `name`） |
| `execute-tool` | `parameters` | 否 | object；**Path/Query 参数放顶层，请求体放 `"body"`** |
| `get-tool-schema` | `tool_name` | 是 | 同上 |
| `search-tools` | `query` / `category` / `limit` | 否 | `limit` 默认 10、上限 50 |

- `parameters` 的 schema 是 `additionalProperties: {}` ⇒ **discovery schema 对参数零校验**，形状错只在**调用期**以 Graph 400 暴露。照抄 §3，别凭记忆拼。
- **认证工具的两种调用语境必须分清（旧写法只说了第一种，会让人以为认证/登录得绕道）**：
  - **经 `execute-tool` 间接调用 → 找不到**：`execute-tool(tool_name="list-accounts")` → `Tool not found: list-accounts`。这 6 个（`login` / `logout` / `verify-login` / `list-accounts` / `select-account` / `remove-account`）不在 `execute-tool` 的隐藏 catalog 里。
  - **作为独立 `mcp__outlook__<rawName>` 工具直接调用 → 可用**：DSH 侧实测注册的 9 个工具里就含这 6 个（§1 权威清单），模型可直接调 `mcp__outlook__login` / `mcp__outlook__list-accounts`；裸 `tools/call` 侧同理，按工具本名直调。
  - ⇒ **认证/登录不需要也无法经 `execute-tool` 走**，直接调独立工具即可。

## 3. 15 项能力配方（照抄这一列，不要回忆）

标 ✅ = 真跑成功并见到返回原文；标 📄 = 只有 `get-tool-schema` 背书、**未执行**。

| # | 能力 | `tool_name` | 最小 `parameters` JSON | 状态 |
| --- | --- | --- | --- | --- |
| 1 | 列邮件 | `list-mail-messages` | `{"top":10,"select":"id,subject,from,receivedDateTime,isRead,hasAttachments"}` | ✅ 0.67s |
| 2 | 按关键词搜索 | `list-mail-messages` | `{"search":"\"Microsoft\"","top":10}`（`search` 值须带一对双引号；`filter:"isRead eq false"` 亦 ✅） | ✅ 0.22s |
| 3 | 读单封正文 | `get-mail-message` | `{"messageId":"<id>","select":"id,subject,from,isRead,hasAttachments"}` | ✅ 0.19s |
| 3b | 读原始 MIME 全文 | `get-mail-message-mime` | `{"messageId":"<id>"}` | ✅ 0.23s |
| 4 | 列附件 | `list-mail-attachments` | `{"messageId":"<id>"}` | ✅ 0.20s（本例 `{"value":[]}`） |
| 5 | 下载附件 | `download-bytes` | `{"target":"/me/messages/<messageId>/attachments/<attachmentId>/$value"}` | 📄 参数名 `target`（必填）已取 schema |
| 6 | 发送 | `send-mail` | `{"body":{"Message":{"subject":"S","body":{"contentType":"text","content":"B"},"toRecipients":[{"emailAddress":{"address":"a@b.c"}}]},"SaveToSentItems":true}}` | 📄 |
| 7 | 回复 | `reply-mail-message` | `{"messageId":"<id>","body":{"Comment":"OK"}}` | 📄 |
| 8 | 全部回复 | `reply-all-mail-message` | `{"messageId":"<id>","body":{"Comment":"OK"}}` | 📄 |
| 9 | 转发 | `forward-mail-message` | `{"messageId":"<id>","body":{"ToRecipients":[{"emailAddress":{"address":"a@b.c"}}]}}` | 📄 |
| 10 | 建草稿 | `create-draft-email` | `{"subject":"S","body":{"contentType":"text","content":"B"},"toRecipients":[{"emailAddress":{"address":"a@b.c"}}]}` | 📄 |
| 10b | 建回复草稿 | `create-reply-draft` | `{"messageId":"<id>","body":{"Comment":"OK"}}` | 📄 |
| 10c | 建全回复草稿 | `create-reply-all-draft` | `{"messageId":"<id>","body":{"Comment":"OK"}}` | 📄 |
| 10d | 建转发草稿 | `create-forward-draft` | `{"messageId":"<id>","body":{"ToRecipients":[{"emailAddress":{"address":"a@b.c"}}]}}` | 📄 |
| 11 | 发送草稿 | `send-draft-message` | `{"messageId":"<draftId>"}`（**无 body**） | 📄 |
| 12 | 移动 | `move-mail-message` | `{"messageId":"<id>","body":{"DestinationId":"<folderId>"}}` | 📄 |
| 13 | 删除 | `delete-mail-message` | `{"messageId":"<id>"}`（**无 body**） | 📄 |
| 14 | 列文件夹 | `list-mail-folders` | `{}`（可加 `{"top":50}`） | ✅ 0.18s，8 个文件夹 |
| 14b | 列子文件夹 | `list-mail-child-folders` | `{"mailFolderId":"<folderId>"}` | ✅ 0.21s |
| 14c | 列某文件夹内邮件 | `list-mail-folder-messages` | `{"mailFolderId":"<folderId>","top":10}` | ✅ 0.22s |
| 15 | 标记已读/未读 | `update-mail-message` | `{"messageId":"<id>","body":{"isRead":true}}` | 📄 ⚠ 见下 |
| 16 | 取邮箱设置 | `get-mailbox-settings` | `{}` | ✅ 0.28s（`timeZone`/`language`/`workingHours`） |
| 16b | 取身份（推荐） | `verify-login` **直调** | `{}` | ✅ 0.22s，返回 `displayName`/`userPrincipalName` |
| 16c | 列已登录账户 | `list-accounts` **直调** | `{}` | ✅ 0.00s，返回 `email`/`name`/`isDefault` |

**`contentType` 必须全小写**（`"text"` / `"html"`）——本表第 6、10 条原先写成大写 `"Text"`，那会**在调用期被 MCP 参数校验直接拒掉**，已修正为小写（逐字错误原文与修法见 §7 坑 11）。

⚠ **第 15 条是本表唯一没有 schema 逐字背书的配方**：`update-mail-message` 的 body schema 里**没有** `isRead`（只有 `flag`，其 `flagStatus` enum = `["notFlagged","complete","flagged"]`），但工具自己的 description 逐字写着 "mark it read or unread (**isRead**), flag it (flag)"，且 `additionalProperties` 未封死 ⇒ `{"body":{"isRead":true}}` 成立。首次使用先 `get-tool-schema("update-mail-message")` 确认。

**id 名陷阱（本会话真踩）**：路径参数名是 **camelCase 且必须逐字匹配**。`messageId`（不是 `message_id`）、`mailFolderId`（不是 `folder_id`/`folderId`）。正确名可从 `get-tool-schema` 的 `"in":"Path"` 条目读出（自带提示 "Pass it under the name 'messageId', not as 'id'"）。

## 4. 个人 MSA 账户的三条硬规则

1. **authority 必须 `consumers`**（`MS365_MCP_TENANT_ID=consumers`）。README 逐字：*"Personal Microsoft accounts should set this to `consumers` - as of June 2026, refresh tokens issued via the default 'common' authority are rejected at the first refresh, so sessions die roughly an hour after login"*。症状：`/common` 登录能成功，但**约 1 小时后会话死掉**；用门户里的 Directory ID 当 tenant 则 `/me` 200 而 `/me/messages` 401。
2. **只支持 delegated 权限**；个人 MSA **不可能**走 application permission / app-only（无人值守）。踩到时报 `AADSTS500200: User account '***@outlook.com' is a personal Microsoft account. Personal Microsoft accounts are not supported for this application unless explicitly invited to an organization.` ⇒ 改 delegated 交互流，**不要**去调 `/adminconsent`。
3. **基本身份验证 / 应用密码已被微软全租户硬禁用且不可恢复**（POP/IMAP/SMTP/EWS… 全在内），官方原文：*"Basic authentication is now disabled in all tenants."*、*"no one (you or Microsoft support) can re-enable Basic authentication in your tenant"*、*"prevents the use of app passwords with apps that don't support two-step verification"*。⇒ 只剩 OAuth2 一条路，别去试"开 app password / 用密码登 IMAP"。IMAP/SMTP 走 XOAUTH2 对 outlook.com 仍官方可用。

> 三条的取证出处（含官方页面原文与日期）：`D:\workspace\agent\skill\_recon\outlook-access-research.md` §1、§2.5、§5.7（第 351 行的 AADSTS500200 原文）。

## 5. 认证与令牌

**设备码登录（一次性、需要人在浏览器点同意）**：

```powershell
$env:MS365_MCP_TENANT_ID='consumers'
$env:MS365_MCP_TOKEN_CACHE_PATH='C:\Users\admin\.dsh\.secrets\ms365\.token-cache.json'
$env:MS365_MCP_SELECTED_ACCOUNT_PATH='C:\Users\admin\.dsh\.secrets\ms365\.selected-account.json'
npx.cmd -y @softeria/ms-365-mcp-server --login    # 打印 URL + user_code，浏览器侧完成（含 2FA）
```

- **必须用 `npx.cmd`，不能写 `npx`**：执行策略 `Restricted` 会拦下 `npx.ps1`，逐字原文 `File C:\Program Files\nodejs\npx.ps1 cannot be loaded because running scripts is disabled on this system.`（Python 侧 `shutil.which('npx')` 按 PATHEXT 已解析成 `npx.CMD`，只有 PowerShell 会踩）。
- **但 §1 配置里的 `command: npx` 是安全的，别当成同一个执行策略坑**：那条由 `@deepseek-ai/dsh-mcp-client` 用 MCP SDK 的 `StdioClientTransport` 启动（`lib/index.js:6` 导入），SDK 的 `client/stdio.js` **第 1 行 `import spawn from 'cross-spawn'`、第 65 行 `spawn(this._serverParams.command, ...)`** ⇒ cross-spawn 在 Windows 上按 PATHEXT 把 `npx` 解析为 `npx.cmd`，**不经过 PowerShell**，所以不会踩 `npx.ps1` 被执行策略拦截。该坑只在**你在 PowerShell 里手敲 `npx`** 时出现（属 `pwsh-on-windows`）。
- 令牌缓存是**密文信封**：`{_cacheEnvelope, v, alg, iv, tag, data}`（AES-256-GCM），**32 字节 key 存在 Windows 凭据管理器**（keytar），不在文件里。
- **核验方法（三条都是只读，实测输出在括号里）**：

```powershell
Get-ChildItem 'C:\Users\admin\.dsh\.secrets\ms365' -Force          # .selected-account.json / .token-cache.json
(Get-Content 'C:\Users\admin\.dsh\.secrets\ms365\.token-cache.json' -Encoding utf8 -Raw | ConvertFrom-Json).PSObject.Properties.Name
cmdkey /list | Select-String 'ms-365-mcp-server'                   # → LegacyGeneric:target=ms-365-mcp-server/cache-key
```

- 登录态用只读工具确认，别猜：`verify-login`（直调）拿到 `displayName`/`userPrincipalName`；`list-accounts`（直调）拿到 `email`/`isDefault`。
- **未验证（明确的待办，别当成已解决）**：**跨小时的静默刷新（refresh token 首次续期）仍未验证**——`consumers` authority 下的 refresh token **首次刷新尚未被真触发过**；access token 仍有效时不会有刷新动作，所以"1 小时内所有调用都成功"**不构成**刷新成功的证据。**待办：登录约 1 小时后跑一次只读调用（例如 `list-mail-folders`）来证明刷新成功**；这一步做完之前，跨小时首次使用请先只读调 `verify-login` 确认会话还活着。
- **未验证（另一条路线，本次未采用）**：若之后改成"自研 client_id + 纯 `requests` 设备码"（脚本 `_build\outlook_dc_auth.py`，自测见 `_build\SELFTEST.md`），**那条路线的设备码 HTTP 管道/轮询/401 分支都只经桩验证，从未做过真人登录**；脚本自身还记录了一个坑：`icacls` 收权限时用 `(R,W)` 会让替换 token 文件报 `PermissionError: [WinError 5] 拒绝访问。: '...\fake.token.json.tmp' -> '...\fake.token.json'`，必须给 `(F)`。

## 6. 护栏（靠纪律，不靠工具白名单）

- **🤖 前缀标记**：`MS365_MCP_MESSAGE_SIGNOFF_PREFIX: '🤖 '`（README：*"Signoff prepended to outgoing messages so recipients can tell they were agent-sent"*；作用范围原文 `mail sends and drafts`；`--no-message-signoff` 或空值关闭）。让收件人能分辨"agent 代发"。
- **该变量名已核实不是静默失效**（所以写错名字会立刻暴露，不会"配了但没生效"）：`dist/cli.js:20` 文档化该变量、`dist/lib/message-signoff.js:19` 用 `resolveEnvText("MS365_MCP_MESSAGE_SIGNOFF_PREFIX")` 读取；且 `dist/lib/message-signoff.js:5` 有一条"配置了却应用不上就报错"的显式告警。
- **写操作先 dry-run**：任何 send / reply / reply-all / forward / create-*-draft / send-draft / move / delete / update **先把"收件人 + 主题 + 正文 + 目标文件夹"念给用户**，得到确认才真调。`sendMail` 返回 **202 只代表已受理，不代表已投递**，不许据此宣称"已发送成功"。
- **本次任务边界同样适用于下次接管**：不要调 `logout` / `remove-account`（会动凭证缓存），不要在没有明确授权时执行任何写工具。
- ⚠ **`--discovery` 让写面"没变小，只是变隐"**，这是本路线最大的安全代价，必须知道：
  - 14 个写工具**仍在 catalog 里**，模型只要拼对名字就能直接 `execute-tool` 发信/删信；`--discovery` **不提供**任何工具级白名单收窄。
  - 6 个认证工具（含 `logout` / `remove-account`）**无法被任何过滤项排除**，而且已**作为独立 `mcp__outlook__<rawName>` 工具直接暴露在模型工具面上**（§1 清单、§2 末条）——模型一句话就能调 `mcp__outlook__logout` / `mcp__outlook__remove-account`（会动凭证缓存）。`ENABLED_TOOLS` 的下限也是这 6 个。⇒ **裁不掉，护栏只能靠纪律**：🤖 前缀 + 写操作 dry-run 确认 + 不主动调注销类工具（本节前三条即是）。
  - 少掉的"每轮可见的参数 schema"本身就是一层隐式护栏 ⇒ 护栏只能写在 prompt / skill 里（本节即是），**别指望配置层兜住**。

## 7. 坑与修法（全部带逐字错误原文）

1. **`--discovery` 与 `ENABLED_TOOLS` 同时写 = 白名单被静默作废**
   现象：工具表**恒为 9**（4,404→4,402，一分上下文都不省），而白名单里的写工具全变成
   `{"error":"Tool not found: send-mail","tip":"Use search-tools to find available tools."}`（同理 `list-mail-attachments`）。
   → 原因：`registerDiscoveryTools()` 把 `enabledTools` 当**隐藏 catalog 的过滤器**用，不是暴露给模型的工具表。
   → 修法：**二选一**。走 discovery 就不要设 `ENABLED_TOOLS`；要收窄写面就退到 `--enabled-tools` 白名单路线（29 工具 / 134,818 字符）。
   → **补强：这也是选 `--discovery` 的第二个理由（与上一条同源，别拆成两处）**。cross-spawn 往 `.cmd` 传参**仍要过 cmd.exe 转义**，而含 `|` / `(` `)` 的正则参数（`--enabled-tools` 的典型值）正是会被拆坏的那一类（现象见坑 7）；`--discovery` **不带任何正则参数**，正好绕开这个参数面。
2. **路径参数用 snake_case → Graph 400**
   现象：`execute-tool("get-mail-message", {"message_id":"AQMkADA..."})` →
   `{"error":"Microsoft Graph API error: 400 Bad Request - {\"error\":{\"code\":\"ErrorInvalidIdMalformed\",\"message\":\"Id is malformed.\"}}"}`
   → 修法：改 `{"messageId":"AQMkADA..."}` 即成功；`mailFolderId` 同理。名字从 `get-tool-schema` 的 `"in":"Path"` 读。
3. **`filter` 与 `orderby` 同用 → Graph 400**
   现象：`{"error":{"code":"InefficientFilter","message":"The restriction or sort order is too complex for this operation."}}`
   → 修法：**去掉 `orderby`**，只留 `filter`（`filter=hasAttachments eq true` 单独用即成功，`result_count=5`）。
4. **工具级错误藏在 `result.isError`，不是 JSON-RPC `error` → 假通过**
   现象：`--tool no-such-tool` 返回 `{"result":{"content":[{"text":"MCP error -32602: Tool no-such-tool not found"}],"isError":true}}`，`result` 里**没有** `error` 字段；只判 `'error' in resp` 会把失败报成 `status=OK`、退出码 0。
   → 修法：**两个都判**（`resp['error']` 与 `result.isError is True`），失败退出码 1。
5. **内联 JSON 传参被 Windows shell 打碎**
   现象：`cmd /c ... --args '{"top":3,...}'` →
   `mcp_call.py: error: unrecognized arguments: top\:3,\filter\:\hasAttachments eq true\}`（引号被剥、反斜杠被注入）。
   → 修法：**用 `--args @args.json`**（`@` 前缀 = 从文件读 JSON）；JSON 文件用 Python 写（`encoding='utf-8'`, `newline=''`），别用 PowerShell 写。
6. **`npx` 被执行策略拦死** → 见 §5 第 1 条；用 `npx.cmd`。**仅限 PowerShell 手敲**——§1 配置行里的 `command: npx` 走 cross-spawn、不经 PowerShell，不受影响（§5 第 2 条）。
7. **`npx.cmd` 会把含 `|` / `(` `)` 的 `--enabled-tools` 参数拆坏**
   现象：`'logout' is not recognized as an internal or external command, operable program or batch file.`（rc=255，随后 `INITIALIZE FAILED: EOFError stdout closed`）。
   → 修法：过滤正则放 `env: ENABLED_TOOLS`（`dist/cli.js` 里 env 优先级高于 CLI 参数，且不经 shell 解析），或直接跑已装好的 `node <...>\dist\index.js`。
8. **`--verify-login` 不能当握手探测**
   现象：打印用户名横幅后**不进入 stdio MCP 循环**，写 stdin 报 `OSError: [Errno 22] Invalid argument`。
   → 修法：探测登录态直接看它的 stdout 横幅，或用 MCP 工具 `verify-login` / `list-accounts`（§3 16b/16c）。
9. **`--preset mail` 里根本没有身份工具**
   现象：查 `/me` 资料会找不到工具（`get-user` / `get-my-profile` 都不在 mail preset 的 51 个里）。
   → 修法：身份走 discovery 直调 `verify-login` / `list-accounts`（推荐），或加 `--preset personal`（163 工具，含 `get-current-user` = `GET /me`、`get-my-profile` = `GET /me/profile`）。
10. **`otherMails` / `proxyAddresses` 静默消失（不报错）**
    现象：`select` 里带上它们 → **HTTP 200**，但返回体里根本没有这两个键（MSA 的 `/me` 也不暴露）。
    → 修法：别指望它们；别名只能靠 `toRecipients` 投递证据 + `/me/profile` 的 `emails[]`。
11. **`contentType` 传大写 → 被 MCP 参数校验直接拒（不是 Graph 400）**
    现象：`send-mail` 传 `"contentType":"HTML"` →
    `MCP error -32602: Input validation error: Invalid arguments for tool send-mail: Invalid enum value. Expected 'text' | 'html', received 'HTML' at body.Message.body.contentType`
    → 原因：`@softeria/ms-365-mcp-server` 该枚举做的是**严格小写**校验（`'text' | 'html'`），**不是** Graph API 本身那种大小写不敏感的行为；照抄文档或凭 Graph 习惯写大写必败。
    → 修法：**枚举一律小写**（`"text"` / `"html"`；`create-draft-email` 的 `body.contentType` 同理，§3 第 6、10 条已改为小写）。改传小写 `"html"` 后同一 payload 立即成功（`isError=None`，Graph 侧写入已发送邮件）。
    → **这条坑不在工具层之外**：用 `python mcp_call.py --tool send-mail --args @payload.json` 直走 stdio（绕开 MCP 工具层）**也**会撞到同一校验 —— 别把"绕过工具层"当成逃生路。
    → 辨识：`-32602` + `Invalid enum value` 属**入参校验层**失败，与坑 4 的"只在 `result.isError` 里报错、看 JSON-RPC `error` 会假通过"是两码事（这里校验错误本身就带 `isError=true`）；同类枚举还有 `flagStatus` 的 `notFlagged`/`complete`/`flagged` 等，照抄 §3 与 `get-tool-schema` 的逐字枚举值，**不要改大小写**。

## 8. 不要做什么

- **不要**把 `--preset mail` 原样接进来图省事：272,769 字符、每轮重发，且 24.1% 花在"建/改文件夹"这类用不到的工具上。
- **不要**在 discovery 路线里同时设 `ENABLED_TOOLS`（坑 1），也不要指望它收窄写面。
- **不要**凭记忆拼工具名或参数名——`parameters` 零校验，错了只在调用期吃 Graph 400（坑 2）。不确定就先 `get-tool-schema`。
- **不要**调用 `logout` / `remove-account`；**不要**在用户没确认前执行任何写工具（§6）。
- **不要**在 `/common` 下登录个人 MSA 并以为能长期用（§4 规则 1）。
- **不要**拿 `202 Accepted` 当"已投递"（§6）。

## 9. 验收标准

1. `mcp__outlook__list-accounts`（或 `verify-login`）返回本机账户 ⇒ 链路与登录态都活着。
2. 只读四连能跑通：`list-mail-folders`（→ 8 个文件夹）→ `list-mail-messages`（`top=10`）→ `get-mail-message`（`messageId`）→ `list-mail-attachments`。
3. 任何写操作：先给用户看过 dry-run 摘要并得到确认；发送类还要记住 202 ≠ 已投递。
4. 拿不准参数时，`get-tool-schema(tool_name=...)` 能返回 `"in":"Path"` 等条目（这也是表里 📄 条目的唯一依据）。
