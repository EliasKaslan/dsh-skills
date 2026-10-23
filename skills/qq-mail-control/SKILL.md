---
name: qq-mail-control
description: QQ 邮箱接管（IMAP/SMTP，`mcp__qqmail__*`）——发一封 QQ 邮件、查收件箱、搜邮件、读某封邮件的参数配方与坑：文件夹名编码（回显中文原文、UTF-8 原文直传可用，传 `&UXZO1mWHTvZZOQ-` 这类 modified UTF-7 串报 `Error： Command failed`）、FETCH 只读铁律、中文搜索只覆盖本地窗口、发信必须带【AI 代发】前缀、凭据位置与 `--read-only` 静默陷阱。适用于"发一封 QQ 邮件 / 查一下 QQ 邮箱收件箱 / 搜一下 QQ 邮箱里的邮件 / QQ 邮箱 MCP 怎么用 / 帮我读某封 QQ 邮件 / QQ 邮箱文件夹名乱码 / QQ 邮箱只能读不能发"。不适用：Outlook / MSA 邮箱 → 用 `outlook-mailbox-control`；改 patch 与 MCP 接入层生效时机 → 用 `dsh-agent-customization`；本机 PowerShell 的坑 → 用 `pwsh-on-windows`。
whenToUse: 用 DSH 的 `mcp__qqmail__*` 工具接管 QQ 邮箱（列/搜/读/附件/发/回复/标记/移动/删除）或排查其授权码、只读开关、文件夹名编码时使用。凭据是明文 JSON。模型看不到本节。
---

# QQ 邮箱接管（stdio MCP `qqmail`）

## 何时调用

**加载本 skill 当：**
- 用户说"发一封 QQ 邮件 / 查一下 QQ 邮箱收件箱 / 搜一下 QQ 邮箱里的邮件 / QQ 邮箱 MCP 怎么用 / 帮我读某封 QQ 邮件 / QQ 邮箱能不能存草稿"。
- 命令输出里出现这些可观测信号：`mcp__qqmail__`、`Unsafe Login`、`qqmail_status` 回显的 `wwgv…` 形态授权码前缀、传中文夹名或 modified UTF-7 串时报 `Error: Command failed` / 找不到文件夹、`mode:"local"`、`readOnly`、`DSH_QQMAIL_CONFIG`。
- 要把这个 MCP server 新挂进 `cordis.patch.yml`（**接入层写法与生效时机在 `dsh-agent-customization`，本 skill 只给已落盘那一行的形状**）。

**不要用本 skill（转交）：**
- 接管 Outlook.com / 个人 MSA 邮箱（MS365 MCP discovery）→ 用 `outlook-mailbox-control`。
- 改 DSH 的插件行 / MCP 接入层、上线与回滚纪律、追加 row 的验收三段 → 用 `dsh-agent-customization`。
- 本机 PowerShell 自身的坑（GBK 乱码 / BOM / 执行策略 / PS 5.1 的重定向编码）→ 用 `pwsh-on-windows`。
- 判断这条经验该不该沉淀、写到哪个根 → 用 `sedimenting-skills`。

**前置**：① 已有一个 QQ 邮箱**授权码**（不是登录密码；QQ 邮箱设置 → 账户 → 开启 IMAP/SMTP 服务时生成）；② 配置 JSON 与数据目录已就位（§2），且文件权限已按 Windows 收紧（§2）。 ／ **后继**：任何写操作（send / reply / mark / move / delete）**先给用户看收件人 + 主题 + 正文摘要**再确认（**例外**：收件人只有本人工作邮箱 `xumingzhe4@huawei.com` 时免确认，见 §4），且发信正文**必须**带 【AI 代发】前缀（§4）；发往该收件人**带附件时必须用「转发」格式**（§4）。

## 1. 形态与工具清单

链路：DSH ←（`@deepseek-ai/dsh-mcp-client`，**stdio**）← `node <dsh-qqmail>\lib\mcp-server.js --allow-write`。`serverName: qqmail` ⇒ 对模型暴露的名字是 `mcp__qqmail__<工具名>`（与 `dsh-agent-customization` §2.7 的命名规则一致）。

**12 个工具（逐字名，别改大小写 / 别缩写）**：

| 组 | 工具 | 真实 schema 参数（**以工具自带 schema 为准**） |
| --- | --- | --- |
| 状态 | `qqmail_status` | `{}` |
| 配置 | `qqmail_config` | `{}` |
| 文件夹 | `qqmail_folders` | `{}` |
| 列表 | `qqmail_list` | `{mailbox, limit, order, unseen, flagged, preview}`；最小可用 `{"mailbox":"INBOX","limit":10}`；**只读模式**另有 `{"mailbox":"INBOX","unseen":true}` |
| 搜索 | `qqmail_search` | `{mailbox, since, before, from, to, subject, body, text, order, limit, preview, unseen, flagged, larger, smaller}`；**没有 `query` 这个参数** |
| 读信 | `qqmail_read` | `{uid 或 uids(≤10 批量), mailbox, html, markSeen, maxBodyChars}`；最小可用 `{"uid":<uid>}` |
| 附件 | `qqmail_attachment` | `{"uid":<uid>,"index":1}`（**`index` 从 1 开始**，与 `qqmail_read` 返回的附件清单顺序一致；另有可选 `mailbox` / `outDir`） |
| 发送 | `qqmail_send` | `{"to":["a@b.c"],"subject":"S","text":"B"}`（**`to` 是数组**，`cc` / `bcc` 同；传字符串不一定报错但别赌） |
| 回复 | `qqmail_reply` | `{"uid":<uid>,"text":"B"}` |
| 标记 | `qqmail_mark` | `{"uid":<uid>,"seen":true}` |
| 移动 | `qqmail_move` | `{"uid":<uid>,"destination":"<folder>"}`（**字段是 `destination` 且必填**；写 `to` 会参数校验失败） |
| 删除 | `qqmail_delete` | `{"uid":<uid>}` |

- **`folder` 与 `query` 都是误记的旧参数名**——真实字段是 **`mailbox`**（不是 `folder`），搜索**没有 `query`**（按 `subject` / `from` / `body` / `text` 分腿过滤）。照旧名拼参数 = 参数校验报错，白跑一轮。
- `qqmail_attachment` / `qqmail_send` / `qqmail_reply` 的**完整参数本轮未复核**，保持真调用成功过的那次写法；要确认就先看工具自带 schema，别凭记忆拼。
- **没有转发工具**：12 个工具名里 `forward` / `Fwd` 逐字 grep **零命中**；`qqmail_send` 的 `attachments` 只负责把**本机文件绝对路径**挂上去，**不生成转发头** ⇒ 发往 `xumingzhe4@huawei.com` 的带附件邮件必须**手工拼成转发形态**（§4）。
- **只读模式只放 7 个**（少 `qqmail_send` / `qqmail_reply` / `qqmail_mark` / `qqmail_move` / `qqmail_delete`）。看到工具少 5 个 = 只读还开着（§3），不是接入失败。
- 数字是**时刻值**：`qqmail_folders` 返回的 `INBOX(N 封/M 未读)`、`Sent Messages`、`Drafts`、`Junk`、`Deleted Messages` 与自定义子文件夹的计数每次都会变，**别当常量**。

## 2. 凭据、配置与权限

- 配置是**明文 JSON**，含 `authCode` 字段；`DSH_QQMAIL_CONFIG` 指定配置文件路径，`DSH_QQMAIL_DATA_DIR` 指定数据目录。
- **默认路径**是 `C:\Users\admin\.dsh\dsh-qqmail.json`；改指到 `C:\Users\admin\.dsh\.secrets\qqmail\` 这类目录是允许的，但**改指之后所有工具调用都读新路径**，旧路径那份就变成"改了不生效"的假象来源。
- **它的源码写 `{mode:0o600}` 在 Windows 上毫无作用**——Windows 不认 POSIX mode ⇒ 必须**显式 ACL** 收紧（实测可抄写法，顺序不能反）：

```powershell
icacls "C:\Users\admin\.dsh\.secrets\qqmail\config.json" /inheritance:r
icacls "C:\Users\admin\.dsh\.secrets\qqmail\config.json" /grant:r ($env:USERNAME + ':(F)')   # 必须这样拼：写 "$env:USERNAME:(R,W)" 会被 PS 当作用域变量取空并报 Invalid parameter
```

- **`qqmail_status` 会回显授权码前 4 位**（实测形如 `wwgv…`）。不是完整泄露，但别把它的输出原样贴到公开处；也别据此说"授权码没泄露"就放松 ACL。
- 判 ACL 生效：`icacls <path>` 输出里**没有** `BUILTIN\Users` / `Everyone` 这类继承项，只剩你自己那一行。

## 3. 开关真相与两个静默陷阱

| 开关 | 事实 |
| --- | --- |
| 配置文件里的 `readOnly: false` | **就解锁写工具**（这是主控）；只读 7 个 vs 全 12 个的差别由它决定 |
| `--allow-write` | MCP 启动参数侧的 flag |
| **环境变量** | **没有** readOnly 环境变量——别去找 |

**陷阱 1（会永久改坏配置）：CLI 的 `--read-only false`**
- 现象：`--read-only false` 不但不解锁，反而把 `readOnly:true` **永久写进配置文件**；而 `false` 这个独立参数被静默丢弃，**不报错**。
- 原因：`--read-only` 属 BOOLEAN_FLAGS，布尔 flag 后面跟的位置参数不会被当它的值读。
- 修法：要显式关只读就用 **`--read-only=false`**（等号形式），或直接改配置 JSON 里的 `readOnly` 字段。

**陷阱 2（静默数据丢失）：`--imap-port 993 --smtp-port 465` 落盘成 `0`**
- 现象：CLI 传字符串端口被丢弃、配置里写成 `0`，**不报错**；随后连接按 0 端口失败。
- 原因：这两个字段只收 `number` 类型，CLI 侧传进来的是字符串。
- 修法：**直改配置 JSON**，写成 `"imapPort": 993, "smtpPort": 465`（数字、不带引号），改完用 `qqmail_config` 复核落盘值。
- 通用纪律：**改完配置一律用 `qqmail_config` / `qqmail_status` 读回归值复核**——这两条陷阱的共同点就是"不报错但值不对"。

## 4. 发信硬规则：【AI 代发】前缀

- **所有 AI 代发的邮件，正文必须带可识别前缀「【AI 代发】」**（用户明确选择的护栏）。
- **这个 MCP server 没有任何"强制前缀"钩子**：对比同机的 outlook 行有 `MS365_MCP_MESSAGE_SIGNOFF_PREFIX` 这类服务端变量，`qqmail` 侧**没有**对应物 ⇒ **前缀只能在指令层保证**（写在本 skill + 会话提示词里，并在每次 `qqmail_send` / `qqmail_reply` 前自检）。
- ⇒ 发信前的三步：① 确认正文首行就是 `【AI 代发】`；② 把收件人 + 主题 + 正文摘要念给用户确认；③ 才真调 `qqmail_send` / `qqmail_reply`。
- **例外（2026-10-22 用户明确授权）：收件人只有本人工作邮箱 `xumingzhe4@huawei.com` 时跳过第②步** —— 直接发，不必念摘要等确认（"这是我本人的邮箱"）。第①步（前缀 + 正文）照做。**只要 cc/bcc 里还有别人、或 to 里混入任何其它地址，就回到完整三步。**
- **不要**在用户没确认前发信，也不要用"工具返回成功"代替"用户确认过"（上面那个本人邮箱例外除外）。

**附件硬规则（发给 `xumingzhe4@huawei.com`，2026-10-23 用户明确告知）**：

- **带附件发往该收件人，必须是一封「转发」形态的邮件**；普通格式（正常主题 + `attachments`）会被**收件侧拦截**。拦截发生在收件侧，`qqmail_send` 照样返回成功 ⇒ **工具报成功 ≠ 对方收到**。
- **本 MCP 生成不了真正的转发**：12 个工具无 forward，`qqmail_send` 只能挂 `attachments` + 写 `subject` / `text` ⇒ 「转发格式」只能**自己拼**：
  1. `subject` 用 `转发：<原主题>`（或 `Fwd:`）打头；
  2. `text` 顶部写转发头块（`-------- 转发的邮件 --------` + 发件人 / 发送时间 / 收件人 / 主题），下面接原文；
  3. `attachments` 传**本机文件绝对路径数组**，逐个 `Test-Path` 确认真在并报出体积——`qqmail_send` **没有 dry-run**，发出去了撤不回。
- **发前自检两句**：① 主题是否 `转发：` / `Fwd:` 打头；② 正文顶部有没有那段转发头块。缺任一条先别发。
- **若用户说的「转发」是 MIME 层真正的转发**（带 `Resent-*` 头，或把原邮件当 `message/rfc822` 附件）⇒ **本 MCP 做不到**（无转发生成能力）；这种情况只能改用邮件客户端手动转发，**别在本 skill 里硬凑**。
- **降级路径**（确实投不进去时）：内容内嵌进正文 + 不带附件（既有实战：`send_plan_mail.py` 就是先试「正文 + 附件」，失败自动降级为「仅正文」），或把文件放到中转、正文给链接。
- **送达判据**：`Sent Messages` 里有副本只说明 SMTP 收下了，**不说明收件侧放行**；带附件时若用户没回话，结论只能写「已发出，收件侧未确认」。
- **仍未验证**：这套「转发形态」是否真能过华为网关——本轮没有收件侧回执。首次实发后必须向用户核实；确认有效就把实际过关的写法（主题前缀、头块样式、原始发件人地址要不要保留）补进这几条。

## 5. 无草稿能力与替代做法

- 12 个工具名对 `/draft/i` **命中 0**——**没有**任何草稿工具。
- 底层也写不了草稿：唯一的 IMAP `APPEND` 只用于写 `\Seen`（存"已发送"副本），**写不进 `\Drafts`**。
- 实测该邮箱**确实有 Drafts 文件夹**（读得到、写不进）⇒ 不要因为"文件夹列表里有 Drafts"就承诺能存草稿。
- 用户已明确接受"不做草稿"。若之后真要草稿，替代做法（**均未采用、未验证**）：① 自己在本地文件里存待发正文，需要时再 `qqmail_send`；② 发给自己当占位。
- **不要**用 `qqmail_send` 冒充草稿（会真发出去）。

## 6. QQ IMAP 的可复用坑

1. **层级分隔符是 `/`**（不是 `.`），`qqmail_move` 的 `to` 与 `qqmail_list` 的 `mailbox` 都按这个写。
2. **子文件夹的 uid 空间是独立的**：同一个 uid 数字在不同文件夹指**不同邮件**（实测归档夹 uid **32–39**，INBOX uid **582–619**）。⇒ 提到 uid **必须同时报文件夹**，只说 "uid 32" 无法定位。
3. **非 ASCII 文件夹名直接传 UTF-8 原文**（**已被证伪的旧断言，直接改正**：旧版写"必须传 modified UTF-7 编码串"）——本 build 的 `qqmail_folders` **不回显 modified UTF-7**，照旧写法传编码串**两次都报错**：
   - 可用：`其他文件夹` / `其他文件夹/elysiumkaslana@outlook.com`（中文原文，逐字传）
   - 报错原文（传编码串时）：`Error: Command failed`（`&UXZO1mWHTvZZOQ-` 与 `&UXZO1mWHTvZZOQ-/…` 两次均如此）
   - ⇒ 别手算 modified UTF-7；文件夹名以 `qqmail_folders` 的回显为准，**回显是什么就传什么**。
4. **QQ 不要求先发 IMAP ID**：无 ID 直连 `login()`、先发 ID 再 `login()`、SELECT 路径**三条全成功**；网传的 `Unsafe Login` 本轮**未复现**。⇒ 见到 `Unsafe Login` 先怀疑授权码/ACL/端口，别急着照抄"必须先发 ID"的说法。
5. **中文关键词搜索会退回本地窗口扫描**：返回里带 `mode:"local"` ⇒ 结论是"**最近约 N 封之内**"，**不是全库结论**。要么把窗口说清，要么改用 `qqmail_list` + 自己过滤，**不要把 local 结果说成"邮箱里没有这封邮件"**。
6. **只读取证的铁律：FETCH 必须用 `BODY.PEEK[...]`**，用 `BODY[...]` 会把邮件**误标 `\Seen`**（等于偷偷改了用户的已读状态）。自证方法：抽样读几封后调 `qqmail_list` / 看返回的 `FLAGS ()` 仍为空即未被标记。
7. **判"某词是否真在邮件里"用 `body:"单词"` 或 `subject:"词组"`，不要用 `text:` 多词全文查询**——`text:` 会返回"匹配 548 封"这种结果，看着像**没过滤**。并配**阳性对照做差分**：本例 `body:"annotations"` 命中 **37**、`body:"payments"` 命中 **0** ⇒ 差分把"没读到"变成"确实没有"。
8. **拉失败邮件时间线用 `subject:"Run failed"` + `since` + `order:desc/asc`；`qqmail_list` 的首条常被无关邮件压在上面**（本例最新一条是 dependabot 评论，**不是**最新失败邮件）⇒ **别按 list 首条判"最新失败日期"**。
9. **关键词腿只用 `since`：`before` 与 `from`/`subject` 同时出现 ⇒ 恒返回 0（静默假阴性）**。实测矩阵：`from+since+before` = **0**、`from+before` = **0**、`subject+since+before` = **0**；**去掉 `before` 后 `from+since` = 38**。⇒ 修法：**窗口上界人工按返回的时间列裁**，别用 `before` 收口。
10. **`before` 是左闭右开**：要含 09-20 必须写 `before:"2024-09-21"`。自证法 = **前后各探一格**（`since:09-07 before:09-08` → 只返 09-07 的 1 封）。另：**`since` 偏宽约 1 天**（整窗会带回窗口前一天的信），属**多带**、不影响"有没有"的结论。
11. **`from:` 只匹配发件人显示名，不匹配邮件地址**——阴性对照全 0：`from:"steampowered.com"` / `from:"steampowered"` / `from:"microsoft"` / `from:"outlook.com"`；阳性 `from:"steam"` = **47**（命中的显示名是 "Steam Support" / "Steam Team" / "Steam Store" / "Steam 客服"）。⇒ 搜 `from:"steampowered.com"` 得 0 **会直接误判成"Steam 没发过邮件"**；要按地址判发件人只能用 `to:` 侧思路或改抓显示名。
12. **零命中判据：只认「匹配数 = 返回数」**。实测**静默丢条**：`qqmail_list {limit:200}` 只返 **196/200**；用 `since 2024-01-01 before 2024-06-01` 时报「匹配 **86** 封，返回 **85** 封」。⇒ 凡"匹配 ≠ 返回"，结论就**不能**写成"全库没有"。
13. **必须枚举归档 / 其它文件夹，不能只看 INBOX**：实测 Steam 活动（客服案件、重置密码、新设备登录）落在「其他文件夹/<子文件夹名>」里而**不在 INBOX**；只看 INBOX 会漏判"无残留访问"。（配套事实见坑 2：子文件夹 uid 空间独立。）
14. **时间对照：列表头时间是本地 UTC+8**（**已被证伪的旧断言，直接改正**：旧版说正文里的时间也是 UTC、只差 8 小时）——实测 **Steam 类收据正文里的时间是 Valve 太平洋时间 PDT(UTC-7)**，与列表头 UTC+8 **相差 15 小时**。证据：列表头 `2024-09-10 03:08` vs 正文 `Mon Sep 9 12:08` ⇒ 换算要按 **15 小时**，别按 8 小时。
15. **"工具存在 ≠ 该用"**：即便 `readOnly=false`（写工具全在），也只调 `status` / `folders` / `list` / `read` / `search` 这**五个读工具**；`markSeen:false`（BODY.PEEK）生效可用「**读前后未读数不变**」自证（本例读前后均 **548 封 / 14 未读**）。

## 7. 不要做什么

- **不要**用 `--read-only false`（陷阱 1）——要用 `--read-only=false` 或直改 JSON。
- **不要**用 CLI 传 `--imap-port` / `--smtp-port`（陷阱 2）——直改 JSON 并回读复核。
- **不要**手算 modified UTF-7，也别把 UTF-7 编码串当文件夹名传（**直接传中文原文**，见 §6 坑 3）。
- **不要**承诺草稿能力（§5），也不要用 `qqmail_send` 冒充草稿。
- **不要**把 `qqmail_status` 的输出（含授权码前 4 位）原样转贴到公开位置。
- **不要**把 `mode:"local"` 的搜索结果当全库结论（坑 5）。
- **不要**放弃 `BODY.PEEK` 去"图省事"（坑 6）。
- **不要**把关键词腿和 `before` 一起用（恒返 0 的静默假阴性，坑 9）；**不要**用 `from:"<邮件地址>"` 判发件人（只匹配显示名，坑 11）；**不要**在"匹配 ≠ 返回"时断言"全库没有"（坑 12）；**不要**只看 INBOX 就下"无残留访问"的结论（坑 13）。
- **不要**发不带 【AI 代发】前缀的邮件（§4）。
- **不要**用普通格式（正常主题 + 附件）发往 `xumingzhe4@huawei.com`——带附件必须是转发形态，否则收件侧拦截（§4）；**也不要**凭 `Sent Messages` 里有副本就断言对方收到了。

## 8. 验收标准

1. `mcp__qqmail__qqmail_status` 返回账户信息 + `readOnly` 当前值 ⇒ 链路与授权码都活着（注意它回显授权码前 4 位）。
2. `qqmail_folders` 返回文件夹清单，且**中文夹名以 UTF-8 原文**（如 `其他文件夹/elysiumkaslana@outlook.com`）直接可传给 `mailbox` ⇒ 编码这一关是对的（**别传 modified UTF-7 编码串**，§6 坑 3）。
3. 只读四连：`qqmail_folders` → `qqmail_list`（`{"mailbox":"INBOX","limit":10}`）→ `qqmail_read`（某个 `uid`）→ `qqmail_attachment`。做完 `FLAGS` 仍为空 ⇒ `BODY.PEEK` 生效、没有污染已读状态。**报 uid 时一并写清 mailbox**（子文件夹 uid 空间独立，§6 坑 2）
4. 写操作：工具**存在**（说明只读已关）+ 用户已确认摘要（收件人只有 `xumingzhe4@huawei.com` 时免，§4）+ 正文首行是 `【AI 代发】`。
5. 想改配置时：改完用 `qqmail_config` 读回，确认 `imapPort: 993` / `smtpPort: 465` 是**数字**而不是 `0`。
6. 带附件发往 `xumingzhe4@huawei.com`：主题 `转发：` / `Fwd:` 打头 + 正文含转发头块 + `attachments` 路径逐个 `Test-Path` 存在 ⇒ 才算按格式发出；**收件侧是否放行以用户回话为准**，别拿 `Sent Messages` 当送达证据（§4）。

## 9. 凭据卫生（明文授权码外溢的收尾）

- **委派即外溢**：把明文 `authCode` 交给任何子代理 ⇒ 它多半会把副本写进工作区临时文件。收尾必做**全树字面量扫描**（`grep -rF --binary-files=without-match "<授权码>" <工作区>`）归零；`exact=0` 才算完。
- **跳过的目录必须补扫**：默认扫描排除了 `node_modules` 之类 ⇒ 补扫一次并报**命中数**（`grep -rF -c …` / 逐文件计数求和），命中 0 才能说"未泄漏"。跳过**不是**判据。
- **清完验权威副本**：比对权威配置文件的 sha256 未变、`authCode` 字段仍在且非空 —— 否则是"为清副本把真凭证弄坏了"。
- **判历史泄漏面**：先 `git rev-parse --is-inside-work-tree` 判目标目录是不是 git 仓（非仓 exit 128 ⇒ 无提交历史面）；是仓再查 `git log -S"<授权码>" --all`。
- **屏蔽靠忽略规则**：`C:\Users\admin\.dsh\.secrets\.gitignore` 的 `*` 匹配任意层级 ⇒ 已覆盖子目录（含 `qqmail/`），无需逐目录再加。
