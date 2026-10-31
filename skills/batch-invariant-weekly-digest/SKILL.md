---
name: batch-invariant-weekly-digest
description: Batch 不变性周报——按周汇总 vLLM、vLLM-Ascend、SGLang 三仓已合入 PR，出四节 Markdown（概览 + 三仓，各一张「PR / 合入时间 / 背景 / 做了什么 / 影响」五列表），并自动发给黄区与私人邮箱。适用于"跑一下本周的 Batch 不变性周报 / BI 周报 / vLLM 这周合了哪些不变性 PR / SGLang 确定性推理有什么进展 / 把上周合入的 PR 汇总成表 / 生成周报并发我邮箱"。不适用：只看组织谁在动、有没有发版 → 用 `github-org-delta-watch`；只发信或查收件箱 → 用 `qq-mail-control`；查单个 PR 状态或提 PR → 用 `github-pr-flow`。
whenToUse: 每周一次的三仓 BI 合入 PR 汇总 + 自动发信配方（模型看不到本节，触发只看 description）
---

# Batch 不变性周报（每週一次）

## 何时调用

**加载本 skill 当：**
- 用户说「跑一下这周的 BI 周报 / Batch 不变性周报」「vLLM / SGLang 这周合了哪些不变性 PR」「上周的进展汇总一下发我」。
- 距离上次出周报已满 7 天，且用户此前要求过「每周自动跑」。

**不要用本 skill（转交）：**
- 只看某个组织谁在动、仓是不是死了、有没有发新版 → `github-org-delta-watch`。
- 只发一封邮件 / 查收件箱 / 读某封邮件 → `qq-mail-control`（发信格式与坑都在那边，本 skill 只引用结论）。
- 查单个 PR 的 CI、评审、合并状态，或要提 PR → `github-pr-flow`。
- 本机 PowerShell 的编码 / 执行策略 / 中文路径坑 → `pwsh-on-windows`。

**前置**：GitHub classic PAT 在 `C:\Users\admin\.dsh\.secrets\github-pr-flow.token`；qqmail MCP 已配置且 `readOnly=false`。 ／ **后继**：md 留在 `reports/`，下周同名新日期文件。

## 0. 流程

```
算窗口 → 三仓×4 关键词搜索 → 逐条取 merged_at 复核 → 人工判定相关性
      → 写 4 节 Markdown（每节一张表）→ 渲染 HTML → 发两个收件人 → 核对 INBOX/Sent
```

## 1. 窗口与仓库

- 运行日 `D`（Asia/Shanghai）。窗口 = **D-7 00:00 ~ 当前时刻**，表里写 `MM-DD HH:mm`（北京时间，24 小时制）。
- 三个仓，顺序固定：`vllm-project/vllm` → `vllm-project/vllm-ascend` → `sgl-project/sglang`。
- 只统计**已合入**（`merged_at` 非空）且落在窗口内的 PR。报告里**不写**「口径 / 方法 / 局限」。
- 换主题只要换 §2 的 repo 列表 + §3 的关键词，节数仍是四节；「三仓 + BI 关键词」只是本主题的默认值。

## 2. 取数（脚本可直接跑）

存成**纯 ASCII 或带 BOM 的 UTF-8** `.ps1`（见坑 1），用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <脚本>` 跑。

```powershell
param([int]$Days = 7)
$tok = (Get-Content "C:\Users\admin\.dsh\.secrets\github-pr-flow.token" -Raw).Trim()
$h = @{ Authorization = "token $tok"; "User-Agent" = "dsh"; "Accept" = "application/vnd.github+json" }
$since = (Get-Date).AddDays(-$Days).ToString("yyyy-MM-dd")
$repos = @("vllm-project/vllm", "vllm-project/vllm-ascend", "sgl-project/sglang")
$kws = @("invariant", "invariance", "deterministic", '"batch invariant"')

$cand = @{}
foreach ($repo in $repos) {
    foreach ($kw in $kws) {
        $q = "repo:$repo is:pr is:merged merged:>=$since $kw"
        $u = "https://api.github.com/search/issues?q=" + [uri]::EscapeDataString($q) + "&per_page=100"
        try { $r = Invoke-RestMethod -Uri $u -Headers $h } catch { Write-Output "ERR $q"; continue }
        foreach ($i in $r.items) { $cand["$repo#$($i.number)"] = $i }
        Start-Sleep -Milliseconds 1200
    }
}
foreach ($k in $cand.Keys) {
    $c = $cand[$k]
    $p = Invoke-RestMethod -Uri "https://api.github.com/repos/$($c.repository_url.Replace('https://api.github.com/repos/',''))/pulls/$($c.number)" -Headers $h
    if (-not $p.merged_at) { continue }
    $t = ([datetime]$p.merged_at).ToUniversalTime().AddHours(8).ToString("MM-dd HH:mm")
    Write-Output ("{0}#{1}`t{2}`t+{3}/-{4}`t{5}`t{6}" -f $c.repository_url.Split('/')[-1], $p.number, $t, $p.additions, $p.deletions, $p.title, $p.html_url)
    Start-Sleep -Milliseconds 150
}
```

- 输出是 5 列 TSV：`repo#num / 时间 / +a/-d / 标题 / url`（**标题是第 4 列**，别取错）。
- 搜索的 `total_count` 含**正文提及**，不是结果数；`state=closed` 也**不代表已合入**，必须用 `/pulls/{n}` 的 `merged_at` 复核。
- 单查询最多返回 100 条，热点周会被截断：**已知的 BI PR（上周表里出现过的）要单独 `GET /pulls/{n}` 补核**，别只信搜索。
- 限速：搜索 30 次/分钟（本脚本 12 次）；core 5000/小时。

## 3. 判定「与 BI 相关」

**收**（任一满足）：
- 标题含 `batch invariant` / `batch invariance` / `deterministic inference` / `bit-exact`，或正文出现 `VLLM_BATCH_INVARIANT` / `--enable-deterministic-inference` / `deterministic mode`；
- 标题是具体 BI 修复对象（matmul table、AITER、RMSNorm 融合、MoE 派发、FP8 反量化、top-k 平局、renorm）且 PR 描述点明是为不变性/确定性而改。

**剔**（默认不算）：
- 只在正文顺带提一句的（多数 `[Perf]`、`[ROCm]` 优化属于此类）；
- 纯 CI / 纯文档，除非它专门扩 BI 用例或改 tested-models；
- 关了但没合并的。

**经验量级**：vLLM 3~6、SGLang 2~8、vLLM-Ascend 0~2（多数周为 0）。为凑数放宽是错。

## 4. 输出：四个 H1 + 四张表

文件写到 `reports/YYYY-MM-DD-bi-weekly.md`，**Markdown**。全文只有四个一级标题，**每个标题下正好一张表**，不写第五个章节：

```markdown
# 概览
| 仓库 | 本周合入 | 本周主线 | 关键变化 | 风险 / 观察 |
| --- | --- | --- | --- | --- |
| VLLM | 4 | … | … | … |
| VLLM Ascend | 0 | 无 | 无 BI 合入 | … |
| SGLang | 8 | … | … | … |

# VLLM
| PR 名称 | 合入时间 | 合入背景 | 做了什么 | 影响 |
| --- | --- | --- | --- | --- |
| [#57092 …](https://github.com/vllm-project/vllm/pull/57092) | 10-23 13:14 | … | … | … |

# VLLM Ascend
（同五列；无合入时一行「本周无与 BI 直接相关的合入」，`—` 占位，不省略表）

# SGLang
（同五列）
```

列与排序硬规则：
- **五列固定**：PR 名称 / 合入时间 / 合入背景 / 做了什么 / 影响。概览表同样是五列，语义换成「仓库 / 合入数 / 主线 / 关键变化 / 风险观察」。
- **按合入时间正序**（最早的在上），不是倒序。
- 第一列必须是链接：`[#<号> <原标题>](<PR html_url>)`，标题超 60 字截断加 `…`。
- 第二列 `MM-DD HH:mm` 北京时间；**UTC 直接写会错一天**（20:55Z → 次日 04:55）。
- 「背景」写**为什么要改**（触发的问题、被谁挡住）；「做了什么」写**改动本身**（含 +/− 行数或关键常量）；「影响」写**可验证的结果**（数字、覆盖范围、修掉哪类故障）。三列都不写「修复了问题」这类套话。
- **加粗只给重点 PR 的第一列（PR 名称），给完整行**。挑中的行只把第一列包一层，其余四格一个 `**` 都不许有（用户 2026-10-31 明确否掉了整行加粗）：

  ```
  | **[#62219 …](url)** | 10-27 00:36 | 背景… | 做了什么… | 影响… |
  ```

- **表格内禁用一切部分强调**：不许出现 `**半句话**` 这种格内加粗，不许斜体（`*…*` / `_…_`）。要强调标识符、命令、变量、环境变量，用行内代码：`` `VLLM_BATCH_INVARIANT=1` ``、`` `atomicAdd` ``。
- **自检口径**：全文 `**` 的个数必须正好等于 `重点 PR 数 × 2`；斜体星号（非成对的单 `*`）必须为 0。上一版把 5 行做成 25 对 `**`，被明确判为「滥用」。
- **什么算重点**（4 条里中 1 条即可）：① 性能有数量级变化（如 BI 税 2.1~3.0x → 1.03~1.20x）；② 解除一类阻断（某硬件/精度组合从「开了就崩」变成能用）；③ 修的是挂死、静默失效、结果不确定这类正确性问题；④ 影响面跨平台或改变默认行为。纯 CI、纯小修、单卡调优不算。
- **比例纪律**：一周挑 3~5 行，别超过总行数的 1/3；全标 = 没有重点。
- 概览表不加粗、不加斜体，纯文字。
- 空仓也要保留表：一行「本周无与 BI 直接相关的合入」，其余列用 `—`。
- 概览的合计数必须等于三张表的行数。

## 5. 发送（两个收件人）

- 收件人固定两个：`xumingzhe4@huawei.com`（黄区）+ `3248569436@qq.com`（私人邮箱）。**这是用户 2026-10-31 明确指定的长期收件人**；要增减收件人必须重新确认。
- 用 `mcp__qqmail__qqmail_send`，`to` 传**两个地址的数组**，同时给 `subject` / `text` / `html`：
  - `subject`：`转发：Batch 不变性周报（MM-DD ~ MM-DD）` —— 发往黄区一律转发格式。
  - `text` 首行 `【AI 代发】`，紧跟 `-------- 转发的邮件 --------` 头块（发件人 / 发送时间 / 收件人 / 主题）。正文用**分行**兜底：每条 PR 先一行 `· #号 标题（时间）`，下面三行 `背景：/做了什么：/影响：`。**兜底里不要放 URL**，也不要留反引号。重点 PR 的行首加 `★`，并在概览后写一行说明 `★ = 本周重点`（纯文本没有粗体，只能用符号代替）。
  - `html`：同一份 md 渲染成表格，五列，第一列 `<a href>`；窄屏下把首列压到 ~28%、时间列 ~9%，字号 12px。**加粗只包第一列的链接**（`<td><b><a href=…>…</a></b></td>`），不要给 `<tr>` 加 `font-weight:bold`，也不要在其它格里放 `<b>`；代码用 `<code>`。
- 发送后若工具报「存副本失败」（原文 `Mail already saved to Sent by SMTP, no need to APPEND again`），**不代表没发出**：去 `INBOX` 看有没有自己那份回环（发给 3248569436 就是发给本账号），有就是已送达；`Sent Messages` 里查不到就不用管。这一次报错、下一次同一套调用又成功存了副本，属服务端抖动，不是参数问题。
- **头块里的「发送时间」先取真实时钟**（`Get-Date`），别凭估计填：填 10:50 实际 10:47，收件侧一眼能看出差 3 分钟；发完用 `qqmail_list` 的时间戳回填核对。
- 回话里写「已发出」，不要写「已送达」——黄区侧是否放行无法从本机证明。

## 6. 坑（都实测过）

1. **含中文字面量的 `.ps1` 在 PS 5.1 下被按 GBK 解码 → 解析器直接崩**（原文 `Missing ')' in method call.` / `Unexpected token '路' …`）。→ 二选一：脚本保持纯 ASCII（输出路径写 `$env:TEMP\...`），或保存成**带 BOM 的 UTF-8**（`[System.IO.File]::WriteAllText($p,$t,(New-Object System.Text.UTF8Encoding($true)))`）。
2. **执行策略拦截**：裸 `& script.ps1` 报 `UnauthorizedAccess`，必须 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`。
3. **`Out-File` 按 80 列折行**，TSV 被拆散、解析出 0 条 → 用 `Set-Content` 落盘。
4. **搜索 API 的 `merged:` 只到日粒度且含边界日**，必须用 `merged_at` 换算北京时间再筛窗口。
5. **UTC→CST 跨日**：`2026-10-30T11:01Z` 是北京时间 10-30 19:01；直接抄日期会错一天。
6. **`total_count` 不是结果数**（body 命中占大多数）；单查询 100 条上限会漏掉热点周的中段结果。
7. **md→html 的链接正则会被标题里的方括号打断**：`\[([^\]]+)\]\(…\)` 遇到 `[#63283 [CI][ROCm] …](url)` 只转出 1 条链接。→ 用 `\[(.*?)\]\((https?://[^)\s]+)\)`。
8. **vllm-ascend 多数周为 0**，但其 BI 工作常在 issue 与在途 PR 里；写「本周无合入」可以，别写成「没有相关工作」。
9. **qqmail 没有转发工具**，转发形态只能手工拼（主题前缀 + 正文头块）。

## 7. 验收

1. `^# ` 恰好 4 条，且就是「概览 / VLLM / VLLM Ascend / SGLang」；没有第五节。
2. 每个标题后紧跟一张表；表头五列顺序为 PR 名称 / 合入时间 / 合入背景 / 做了什么 / 影响（概览为仓库 / 合入数 / 主线 / 关键变化 / 风险观察）。
3. 每行第一列形如 `[#12345 …](https://github.com/…)`，能在浏览器打开。
4. 表内按 `合入时间` 正序；所有时间落在 D-7 ~ D。
5. 加粗只出现在重点行的第一列：3~5 行、不超过总行数 1/3；`**` 总数 = 重点数 × 2；其它格无 `**`、全文无斜体；代码用行内代码。概览合计 = 三表行数。
6. 邮件 `to` 是两个地址；`INBOX` 里有回环副本（Sent 可能有、也可能报存副本失败）。
