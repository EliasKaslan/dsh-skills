# 检索、正文、附件与版本陷阱

## 当前工具族（2026-11-23 本会话 schema 实测）

- QQ：`mcp__qqmail__qqmail_folders` / `_search` / `_list` / `_read` / `_attachment` / `_send` / `_reply` / `_mark` / `_move` / `_delete` / `_status` / `_config`，共 12 个。附件参数是本机绝对路径；`_read` 默认 `markSeen=false`（读信不自动标已读）；`_search` 的中文关键词走本地窗口过滤（约最近 400 封），英文/数字走服务器端，`mode=local` 只代表该窗口内的结论。
- Outlook：`mcp__outlook__search-tools` → `get-tool-schema` → `execute-tool`，身份核对用 `list-accounts`/`select-account`/`verify-login`。工具名是 kebab 式 Graph 操作名（如 `list-mail-messages`、`create-draft-email`、`send-mail`、`send-draft-message`），不存在 `mcp__outlook__mail_*` 这类按名字猜的逐信箱工具；每次调用前先 `get-tool-schema`。
- 只在本次会话实际注册的工具里选，不凭记忆调用没出现过的名字；schema 里没有 draft/delete 就说明没有，不要绕道模拟。

## 检索覆盖

枚举 INBOX、归档和其他相关文件夹；仅 INBOX 无结果不足以排除邮件。分页要继续到完整，记录 matched/returned 差异、nextLink/游标、服务限制和 truncated。本地中文窗口搜索只说明最近N封；用已知存在的阳性和针对性的阴性查询测试字段语义，必要时拉取受限候选在本地按地址/时间过滤。

旧 QQ MCP build 的 from 曾只匹配显示名，组合 before 与关键词曾静默零条；这些是实现级回归线索，不是 IMAP 协议规则。当前 query 逐个加字段，比较阳性差分；不能据旧bug永远禁 before。日期通常上界排除，但工具可有时区转换，前后一天的合成/已知样本核对后再定窗。正文内商家时区和邮件 Date/列表时区分开。

IMAP 只读检索用 readonly/examine 和 BODY.PEEK，避免 BODY fetch 偷标已读；动作前后采样 flags。非 ASCII 文件夹以当前 MCP/插件 列出的规范名称/id 传递；直连库若要求 modified UTF-7 才在协议层转换，不把编码串塞给已经接受 UTF-8 的工具。

## MIME 与附件

区分 text/plain、HTML、multipart/alternative、inline cid 和真实附件；用 MIME 声明 charset 解码，保留原始字节用于定位乱码，不把 header 编码词/HTML源码当正文。列表/摘要可能截断，用户问精确内容时读取正文。下载前检查 message/attachment id、名称、大小和类型，输出到指定目录，防路径穿越/同名覆盖；核对返回字节数，必要时算 SHA256。读邮件/下载附件不自动运行附件代码。

发送前逐个确认绝对路径、存在性、实际字节数和 MIME/filename 编码；不把 base64 字符数当附件大小。QQ 侧 `qqmail_send`/`qqmail_reply` 收本机绝对路径数组；Outlook 侧只收 base64：小于 3MB 用 `add-mail-attachment` 的 `contentBytes`（截断即 `400 UnableToDeserializePostBody`），3–150MB 必须 `create-mail-attachment-upload-session` 后自行 PUT 分片，小于 3MB 会被 `ErrorAttachmentSizeShouldNotBeLessThanMinimumSize` 拒绝。当前 `create-draft-email` schema 的 `body.contentType` 枚举是小写 `text`/`html`，与 Graph 原生的 `Text`/`HTML` 不同；按工具 schema 传，不沿用旧 Message/Comment 配方。

## 能力与认证

当前 Outlook 走 `mcp__outlook__search-tools` → `get-tool-schema` → `execute-tool`：`search-tools` 实测报 `total: 197`，但 MCP 只注册 9 个工具（3 个 discovery + 6 个账号/登录）。看到的工具数只反映展示，不代表实际写面。若需只读须确认实际授权/allowlist执行，不靠工具数量推断权限。`execute-tool` 另有 `confirm` 门，仅当 `MS365_MCP_REQUIRE_CONFIRM=true` 时生效（默认关）；默认关不等于可以不问用户就直接发信或删除。若需以其他路径操作，先确认账号是否已用 `list-accounts`/`select-account`/`verify-login` 核对，个人 MSA 与组织 tenant 的 OAuth/scopes 支持不同，查当前官方支持矩阵，不用旧 basic-auth 结论替代认证诊断。设备码/同意流程交给用户完成。

QQ 旧 CLI `--read-only false` 曾把 false 丢成位置参数、端口字符串曾落为0；仅在该实现维护时检查 parser 和回读有效配置，不能把这些 flag 用到现有直连skill。当前任务不为检索而关闭只读或改系统配置。Sent 文件夹副本缺失也不能单独证明发送未发生，先核对 SMTP/API 回执及实际 Sent 位置。
