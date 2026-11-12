---
name: batch-invariant-weekly-digest
description: Batch 不变性周报：四仓已合入 PR 的概览表 + 转发形态邮件发黄区。适用于"跑 BI 周报 / 不变性有什么进展 / vLLM 这周合了哪些不变性 PR / 把周报改成列表"。
whenToUse: 每周跑一次的 BI 合入汇总，出列表版周报并发黄区（模型看不到本节，触发只看 description）。
---

# Batch 不变性周报（列表版）

## 何时调用

**加载本 skill 当：**
- 用户说"跑一下本周的 BI 周报 / Batch 不变性周报 / vLLM 这周合了哪些不变性 PR / SGLang 确定性有什么进展"。
- 用户对既有周报提格式要求："表格改成列表 / 每条 PR 下面挂时间背景影响 / 重点加粗 / 发黄区"。
- 要复用取数与发送链路：GraphQL 取窗、qqmail 发信、Sent/INBOX 回环验证。

**不要用本 skill（转交）：**
- 只看组织增量、发版与仓活性 → `github-org-delta-watch`
- 单个 PR 的读写或向上游提 PR → `github-pr-flow`
- 本机 shell 的编码 / 执行策略 / 计数坑 → `pwsh-on-windows`

**前置**：GitHub PAT（细粒度，可读公开仓 issue/PR）；qqmail 授权码（发信时才需要）。／ **后继**：发完在回话里写"已发出 + 证据（Message-ID / Sent uid / INBOX 回环）"，不要写"已送达"。

## 1. 取数

- 窗口：上一期截止时间 → 今天，用 **UTC 日期**做 `merged:YYYY-MM-DD..YYYY-MM-DD`；表格里一律换算 **UTC+8**，否则边界 PR 会重复或漏。
- 仓：`vllm-project/vllm`、`vllm-project/vllm-ascend`、`sgl-project/sglang`，外加生态仓 `flashinfer-ai/flashinfer`（BI 算子 API 都在这）。
- **GraphQL `search` 单次最多 100 条且按相关性排序**：vLLM 一周 500+ merged，翻 3 页只到 200 条 ⇒ 要么按关键词逐条搜（每条结果 <100），要么以 **label 为准**（vLLM 有 `batch-invariance`，一周 7 条左右，权威且不漏）。
- 关键词：`batch invariance`、`batch-invariant`、`batch_invariant`、`invariant`、`deterministic`、`bitwise`、`bit-exact`。
- **判"某仓本周无 BI 合入"要全量 changed-files 负证**：body 里出现 `bitwise/deterministic` 多半是顺带提及（vllm-ascend 实测 12 条全不沾 BI），必须拉 `/pulls/{n}/files` 看路径是否命中 `batch_invariant`。
- 落盘：每个仓一份 JSON（number/title/merged_at/labels/adds/dels/body），body 截到 ~3800 字符再交给子代理；要抄结论时回 API 取全文（关键性能表常在截断之后）。

## 2. 进与剔

**进**：BI/deterministic 选核被钉死；归约序、平局打破、reducer 状态之类的正确性修复；专门扩 BI 用例或改 tested-models；把"开了就崩"变成能开的解禁；BI 性能表（要有量化）。
**剔**：正文顺带提一句的 perf PR；纯 CI / 纯文档（除非专门扩 BI）；关了没合的（在途放单独一节）。
**量级参考**：vLLM 8~12、SGLang 6~9、vLLM-Ascend 多数周为 0、FlashInfer 0~8。为凑数放宽是错。

## 3. 输出格式（用户 2026-11-06 定稿）

文件 `reports/YYYY-MM-DD-bi-weekly.md`。**框架不变**：概览 + 各仓（+ 可选的「在途」「本周判断」）。

- **概览仍是五列表**：`仓库 | 本周合入 | 本周主线 | 关键变化 | 风险 / 观察`。它不是 PR 列表，不转成列表。
- **各仓明细改有序列表**，外层一条 = 一个 PR，名称带链接；每条下面缩进一个无序列表，固定四行（顺序不许换）：

```markdown
# VLLM

1. **[#62192 [Kernel] …](https://github.com/vllm-project/vllm/pull/62192)**
   - 合入时间：10-31 23:25
   - 合入背景：…
   - 做了什么：…
   - 合入影响：…
2. [#65000 …](https://github.com/vllm-project/vllm/pull/65000)
   - 合入时间：11-02 08:17
   - 合入背景：…
   - 做了什么：…
   - 合入影响：…
```

- 缩进用 **3 个空格** + `- `；段间不留空行，条目之间也不留空行。
- 按合入时间**正序**排；时间 `MM-DD HH:mm`（UTC+8）。
- **加粗只包 PR 名称那一条**（`1. **[#N 标题](url)**`），四行字段里一个 `**` 都不许有。全文 `**` 个数 = 重点数 × 2。
- 重点 3~5 条/周、不超过条目总数 1/3；判据：有数量级性能变化 / 解除一类阻断 / 修挂死或静默失效 / 跨平台改变默认行为。
- 空仓写一行 `1. 本周无与 BI 直接相关的合入` + 四条字段（时间写 `—`），别省掉整节。
- 概览的"本周合入"必须等于该仓条目数。

## 4. 发黄区

- 收件人固定两个：`xumingzhe4@huawei.com`（黄区）+ `3248569436@qq.com`（私人）。**只发这两个时免二次确认**（2026-10-30 授权）；要加别人先问。
- 主题：`转发：Batch 不变性周报（MM-DD ~ MM-DD）`，改版重发加 `v2`。
- **发往黄区必须是转发形态**：`text` 首行 `【AI 代发】`，紧跟 `-------- 转发的邮件 --------` 头块四要素（发件人 / 发送时间 / 收件人 / 主题；发送时间用渲染时的 datetime.now()，**别手写固定值**——本期两次把 15:19/15:37 的发送写成了 15:30/15:45）。普通格式会在收件侧被拦，而工具照样返回成功。
- `text`：每条 PR 一行 `★ #号 标题（时间）`，下面三行 `合入背景：/做了什么：/合入影响：`；**不要放 URL**，不要保留反引号。
- `html`：同一份 md 渲染成 `<ol>` + 嵌套 `<ul>`，两张概览/在途表保留；**加粗只包第一列的链接**。
- 通道：优先 `mcp__qqmail__qqmail_send`（`to` 传两地址数组，同时给 `subject`/`text`/`html`）。会话里没有这些工具时，直接 `node <mcp-server.js> --allow-write` 走 stdio JSON-RPC（`initialize` → `notifications/initialized` → `tools/call`），效果相同。
- 发完必验：`Sent Messages` 有副本（uid + 体积）+ `INBOX` 有回环（发给 `3248569436` 就是发给自己）。工具报 `Mail already saved to Sent by SMTP, no need to APPEND again` 不代表没发出。

## 5. qqmail MCP（重建步骤，会话里没有 `mcp__qqmail__*` 时照抄）

```powershell
cmd /c "npm install --prefix C:\Users\admin\.dsh\mcp\qqmail @zhengjunyao/dsh-qqmail@0.1.1 2>&1"
$env:DSH_QQMAIL_CONFIG='C:\Users\admin\.dsh\.secrets\qqmail\config.json'
$env:DSH_QQMAIL_DATA_DIR='C:\Users\admin\.dsh\.secrets\qqmail\data'
$env:QQMAIL_AUTH_CODE='<16 位授权码>'
node "C:\Users\admin\.dsh\mcp\qqmail\node_modules\@zhengjunyao\dsh-qqmail\lib\cli.js" config --preset qq --email 3248569436@qq.com --imap-host imap.qq.com --imap-port 993 --imap-secure=true --smtp-host smtp.qq.com --smtp-port 465 --smtp-secure=true --smtp-require-tls=true --read-only=false
# CLI 把端口当字符串静默丢成 0，必须改回数字
node -e "const fs=require('fs');const p=process.argv[1];const j=JSON.parse(fs.readFileSync(p,'utf8'));j.imapPort=993;j.smtpPort=465;fs.writeFileSync(p,JSON.stringify(j,null,2)+'\n');" $env:DSH_QQMAIL_CONFIG
node "C:\Users\admin\.dsh\mcp\qqmail\node_modules\@zhengjunyao\dsh-qqmail\lib\cli.js" status --probe
```

- `status --probe` 要看到 `IMAP 通过（… 已发送=Sent Messages）` 与 `SMTP 通过`。
- 长期可用还得在 `cordis.patch.yml` 加一行 `mcp-qqmail`（`serverName: qqmail`、`command: node`、args 指到 `mcp-server.js`、env 两个 `DSH_QQMAIL_*`）；**加行后要重启 DSH 才会出现工具**，当次发送走 §4 的 stdio 直连。
- 凭据只落 `.secrets\qqmail\config.json`（ACL 仅 SYSTEM/Administrators/本机用户），别写进 skill、别贴进对话。

## 6. 坑

1. **标题里嵌套方括号会截断正则**：`[#62192 [Kernel] …](url)` 用 `\[#[^\]]*\]` 只能截到 `[Kernel`，取标题要用 `\[#\d+ (.*)\]\(https?://` 贪婪匹配到链接。
2. **`to` 传两个地址时别漏私邮**：漏了就没有 INBOX 回环，只剩 Sent 副本，无法证明投递。
3. **body 截断**：分发给子代理前截 3800 字符，但要抄性能数字时回 API 取全文。
4. **GraphQL 100 条上限**（见 §1）：vLLM 500+ merged/周，翻页拿不全。
5. **`npm` 在 pwsh 被执行策略拦** → 一律 `cmd /c "npm …"`。

## 7. 验收清单

1. 概览"本周合入"= 各节条目数；空仓保留了小节。
2. 每个 PR 恰好四条字段，顺序为 合入时间 / 合入背景 / 做了什么 / 合入影响；字段里无 `**`。
3. 全文 `**` 数 = 重点数 × 2，重点数 3~5 且 ≤ 条目数 1/3。
4. 邮件：主题带 `转发：`，text 首行 `【AI 代发】` + 头块四要素，html 是 `<ol>` 结构。
5. 发送证据：Message-ID + Sent 副本 uid + INBOX 回环；回话写"已发出"。
