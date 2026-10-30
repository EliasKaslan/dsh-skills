---
name: batch-invariant-weekly-digest
description: Batch 不变性周报——按周汇总 vLLM、vLLM-Ascend、SGLang 三仓「已合入」PR，出四节 Markdown（概览 + 三张带链接的表），并自动发到黄区。适用于"跑一下本周的 Batch 不变性周报 / BI 周报 / vLLM 这周合了哪些不变性 PR / SGLang 确定性推理有什么进展 / 把上周合入的 PR 汇总成表 / 生成周报并发我邮箱"。不适用：只看组织谁在动、有没有发版 → 用 `github-org-delta-watch`；只发信或查收件箱 → 用 `qq-mail-control`；查单个 PR 状态或提 PR → 用 `github-pr-flow`。
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

**前置**：GitHub classic PAT 在 `C:\Users\admin\.dsh\.secrets\github-pr-flow.token`；qqmail MCP 已配置且 `readOnly=false`。 ／ **后继**：发完把 md 留在 `reports/`，下周同一路径覆盖同名新日期文件。

## 0. 流程

```
算窗口 → 三仓×4 关键词搜索 → 逐条取 merged_at 复核 → 人工判定相关性
      → 写 4 节 Markdown → 渲染 HTML → 发黄区 → 核对 Sent Messages
```

## 1. 窗口与仓库

- 运行日 `D`（Asia/Shanghai）。窗口 = **D-7 00:00 ~ 当前时刻**，表里写 `MM-DD HH:mm`（北京时间，24 小时制）。
- 三个仓，顺序固定：`vllm-project/vllm` → `vllm-project/vllm-ascend` → `sgl-project/sglang`。
- 统计口径只有一句：**只统计已合入（merged_at 非空）且落在窗口内的 PR**。不写「口径」章节到报告里。
- 换主题只要换 §2 的 repo 列表 + §3 的关键词，节数仍是四节（概览 + 三个仓）；「三仓 + BI 关键词」只是本主题的默认值。

## 2. 取数（脚本可直接跑）

存成**纯 ASCII** 的 `.ps1`（见坑 1），用 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <脚本>` 跑。

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

- 搜索的 `total_count` 含**正文提及**，不是结果数；返回的 `state=closed` 也**不代表已合入**，必须用 `/pulls/{n}` 的 `merged_at` 复核（漏这步会把关闭未合并的 PR 写进表）。
- 限速：搜索 30 次/分钟（本脚本 12 次，安全）；core 5000/小时。
- 候选 200+ 是常态，属正常。

## 3. 判定「与 BI 相关」

**收**（任一满足）：
- 标题含 `batch invariant` / `batch invariance` / `deterministic inference` / `bit-exact`，或正文出现 `VLLM_BATCH_INVARIANT` / `--enable-deterministic-inference` / `deterministic mode`；
- 标题是具体 BI 修复对象（matmul table、AITER、RMSNorm 融合、MoE 派发、FP8 反量化）且 PR 描述点明是为不变性/确定性而改。

**剔**（默认不算）：
- 只在正文顺带提一句的（多数 `[Perf]`、`[ROCm]` 优化属于此类）；
- 纯 CI / 纯文档，除非它专门扩 BI 用例或改 tested-models；
- 关了但没合并的。

**经验量级**（别为了凑数放宽）：vLLM 3~6 个 / SGLang 2~6 个 / vLLM-Ascend 0~2 个（多数周为 0）。

## 4. 输出：四节，别的不要

文件写到 `reports/YYYY-MM-DD-bi-weekly.md`，**Markdown**。只允许四节，不写「口径 / 方法 / 局限 / 附录」。

```markdown
# Batch 不变性周报（MM-DD ~ MM-DD）

## 1. 概览
- 一周合计：vLLM N 个、vLLM-Ascend N 个、SGLang N 个。
- 主线一：<一句话>。
- 主线二：<一句话>。
- 值得注意：<一句话，跨仓信号 / 风险>。

## 2. VLLM
| PR | 合入时间 | 简要描述 |
| --- | --- | --- |
| [#57092 Make online FP8 MoE experts batch-invariant…](https://github.com/vllm-project/vllm/pull/57092) | 10-23 13:14 | 在线 FP8 MoE 改 per-token 量化并修 stride bug，修 #57016 |

## 3. VLLM-Ascend
本周无与 BI 直接相关的合入。
（有则同 §2 建表；值得关注的未合入 PR 用一行 `未合入但值得关注：…` 收尾，不建表）

## 4. SGLang
| PR | 合入时间 | 简要描述 |
| --- | --- | --- |
```

硬规则：
- **第一列必须是链接**：`[#<号> <原标题>](<PR html_url>)`，展示文字保留 `#号`；标题超 60 字截断加 `…`。
- 第二列 `MM-DD HH:mm`，北京时间；**UTC 直接写会错一天**（20:55Z → 次日 04:55）。
- 第三列 ≤ 50 字：**改了什么 + 效果/数字**，不写「修复了问题」这类套话；有数字就写数字。
- 空仓只写一句「本周无与 BI 直接相关的合入」，**不建空表**。
- 未合入 PR 默认不出现；只有「会改变结论」的才在该节末尾加一行，且不建表。
- 概览的合计数字必须等于三张表的行数和。

## 5. 发送到黄区

- 收件人固定：`xumingzhe4@huawei.com`（黄区 = 本人工作邮箱，按 `qq-mail-control` §4 免二次确认）。
- 用 `mcp__qqmail__qqmail_send`，同时给 `subject` / `text` / `html`：
  - `subject`：`转发：Batch 不变性周报（MM-DD ~ MM-DD）` —— 发往黄区一律转发格式。
  - `text` 首行 `【AI 代发】`，紧跟 `-------- 转发的邮件 --------` 头块（发件人/发送时间/收件人/主题），正文用无表格的纯文本兜底（每行 `· 标题 —— 时间 —— 描述`）。**兜底里不要放 URL**：链接只放 HTML 版，纯文本塞 URL 会变成一长串噪声（首次实跑就在末尾多挂了一行废链接）。
  - `html`：把同一份 md 渲染成 `<table border="1" cellspacing="0" cellpadding="6">`，**第一列是 `<a href>`**，否则手机上点不开；表格首列给 50% 以上宽度，标题长。
- 发送后用 `qqmail_list`（mailbox=`Sent Messages`, limit=3）核对：主题以 `转发：` 开头、时间对得上。`Sent Messages` 有副本 ≠ 对方放行，回话里写「已发出」即可，别写「已送达」。

## 6. 坑（都实测过）

1. **含中文的 `.ps1` 在 PS 5.1 下被按 GBK 解码 → 脚本里的中文路径直接找不到文件**（原文 `Cannot find path 'D:\workspace\BI鐗规€ц窡韪猏...'`）。→ 脚本保持纯 ASCII，输出路径写 `$env:TEMP\bi_research\...`；确实要读工作区中文路径，先在主 shell 里 `Copy-Item` 到 ASCII 临时路径再交给脚本。
2. **执行策略拦截**：裸 `& script.ps1` 报 `UnauthorizedAccess`，必须 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File`。
3. **搜索 API 的 `merged:` 只到日粒度且含边界日**，必须用 `merged_at` 换算北京时间再筛窗口，否则窗口首日会混进窗口外的 PR。
4. **UTC→CST 跨日**：`2026-10-26T21:12Z` 是北京时间 10-27 05:12，直接抄日期会把合入时间写错一天。
5. **`total_count` 不是结果数**（body 命中占大多数）；一条 200+ 的候选池最后只剩 5 行表是正常的。
6. **vllm-ascend 多数周为 0**，但其 BI 工作常在 issue 与在途 PR 里；写「本周无合入」可以，别写成「没有相关工作」。
7. **qqmail 没有转发工具**，转发形态只能手工拼（主题前缀 + 正文头块）；带附件必须走转发形态，否则收件侧拦截。
8. **`Out-File` 按 80 列折行**，TSV 结果被拆成多行、解析出 0 条 → 用 `Set-Content` 落盘再读。
9. **md→html 的链接正则会被标题里的方括号打断**：`\[([^\]]+)\]\(…\)` 遇到 `[#63283 [CI][ROCm] …](url)` 只转出 1 条链接、其余原样输出。→ 用非贪婪且以 `](http` 为锚：`\[(.*?)\]\((https?://[^)\s]+)\)`（实测 9 行表全转出）。

## 7. 验收

1. 文件存在且只有四节（`^## ` 恰好 4 条），没有「口径 / 局限 / 附录」。
2. 三仓各一张表或一句「本周无」；表头三列顺序为 PR / 合入时间 / 简要描述。
3. 每行第一列形如 `[#12345 …](https://github.com/…)`，能在浏览器打开。
4. 概览合计 = 表格行数总和；所有合入时间都在 D-7 ~ D 之间。
5. `Sent Messages` 首条主题以 `转发：` 开头、正文首行是 `【AI 代发】`。
