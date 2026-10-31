---
name: lora-weekly-report
description: LoRA 周报——汇总 vLLM、vLLM-Ascend、SGLang 三仓近 7 天「已合入」的 LoRA PR，出四节 Markdown（概览 + 三张带链接的表）并发到黄区。适用于"跑一下这周的 LoRA 周报 / LoRA 特性跟踪 / vLLM 这周合了哪些 LoRA PR / SGLang 的 LoRA 有什么进展 / 把本周 LoRA 合入汇总成表发我"，不适用：BI 与不变性周报 → 用 `batch-invariant-weekly-digest`；只看组织活跃度或发版 → 用 `github-org-delta-watch`；只发信或查收件箱 → 用 `qq-mail-control`。
whenToUse: 每周跑一次的 LoRA 合入汇总，出四节 Markdown 并自动发黄区。
---

# LoRA 周报（每周一次）

## 何时调用

**加载本 skill 当：**
- 用户说「跑一下这周的 LoRA 周报」「LoRA 特性跟踪」「vLLM / SGLang / vLLM-Ascend 这周合了哪些 LoRA PR」「把本周 LoRA 进展汇总发我」。
- 距上次出周报已满 7 天，且用户此前要求过「每周自动跑」。

**不要用本 skill（转交）：**
- BI / batch invariance / 确定性推理周报 → 用 `batch-invariant-weekly-digest`（同一套机制，判定标准不同，别混用）。
- 只看某组织谁在动、仓是不是死了、有没有发新版 → 用 `github-org-delta-watch`。
- 只发一封邮件 / 查收件箱 / 读某封邮件 → 用 `qq-mail-control`。
- 查单个 PR 的 CI、评审状态，或要提 PR → 用 `github-pr-flow`。
- 本机 PowerShell 编码 / 执行策略 / 中文路径坑 → 用 `pwsh-on-windows`。

**前置**：GitHub classic PAT 在 `C:\Users\admin\.dsh\.secrets\github-pr-flow.token`；qqmail MCP 已配置且可写。 ／ **后继**：报告留在工作区 `reports/`，下周同路径出新日期文件。

## 0. 流程

```
算窗口 → 三仓「is:merged + lora in:title」搜索 → 逐条取 merged_at 复核并落 json
      → 写四节 Markdown（概览 + 三张表） → md2mail 渲染 → 发黄区 → 核对 Sent Messages
```

## 1. 窗口与仓库

- 运行日 `D`（Asia/Shanghai）。默认窗口 = **运行时刻往前 7×24 小时**（`--days 7`，无重叠无空档）；要按自然周就传 `--start YYYY-MM-DD --end YYYY-MM-DD`。表里合入时间写 `MM-DD HH:mm`（北京时间）。
- 三仓顺序固定：`vllm-project/vllm` → `vllm-project/vllm-ascend` → `sgl-project/sglang`，对应报告第 2/3/4 节。
- 只统计 **merged_at 非空且落在窗口内** 的 PR。报告里**不写**「口径 / 方法 / 局限 / 附录」这类章节。

## 2. 取数（跑脚本，别手搓搜索）

脚本目录 = 本 skill 的 `scripts\`。用带 python-docx 的运行时 python 执行：

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$out = "D:\workspace\LoRA特性跟踪\runs\2026-10-30"
& $py "C:\Users\admin\.dsh\skills\lora-weekly-report\scripts\collect_lora_week.py" --days 7 --out $out
```

产物：

| 文件 | 用途 |
| --- | --- |
| `lora_prs.json` | 每个合入 PR 的完整记录（含 body、增删行、精确 merged_at CST） |
| `worksheet.md` | 给模型看的紧凑工作表：每仓一段，每条含 `#号 / 日期 / 规模 / 标题 / body 摘要` |

参数：`--days 7`（默认）｜`--start 2026-10-23 --end 2026-10-30`（自然周，CST，含首尾）｜`--any` 把关键词从 `in:title` 放宽到标题+正文（只在某仓为 0、怀疑漏了时补跑一次）｜`--keyword` 换主题（默认 `lora`）。

脚本已做：`merged_at` 精确复核（不信 `state=closed`）、窗口过滤、UTC→CST 换算、按合入时间倒序。

## 3. 判定「与 LoRA 相关」

- **收**：标题含 `LoRA`（大小写不限）的已合入 PR，**包括** `[CI]` / `[Bugfix]` / `[Perf]` / `[Model]` / `[Ops]` 各类前缀——用户要的是"所有已合入"，CI 与测试类也照收，描述写清它改了 LoRA 的什么。
- **剔**：正文只是顺带提到 LoRA、实际与 LoRA 无关的（`--any` 模式才需要这一步）。
- **经验量级**（别为凑数放宽，也别因少而怀疑脚本）：vLLM 12~18 个 / vLLM-Ascend 0~3 个 / SGLang 8~14 个。vLLM-Ascend 多数周为 0——此时**别留空表**，把最值得关注的 1~3 个在途 PR 填进去，合入时间列写「未合入（在途）」，这就是用户要的「很值得关注」例外。
- 某仓为 0 但你知道有在途 LoRA 工作 → 补跑 `--any` 看标题外的命中，人工判 1~2 条。

## 4. 输出：四个一级标题，每个标题下一张表

写到 `<工作区>\reports\YYYY-MM-DD-lora-weekly.md`。**只有四个 `# ` 一级标题，每个标题下面只有一个表格，不写任何正文段落、不加大标题、不加序号。**

```markdown
# 概览

| 仓库 | 合入 PR 数 | 本周主线 |
| --- | --- | --- |
| VLLM | 15 | <一句话：这一周在干什么> |
| VLLM Ascend | 0 | <一句话> |
| SGLang | 11 | <一句话> |
| 合计 | 26 | <一句话：两边的节奏差异> |

# VLLM

| PR | 合入时间 | 合入背景 | 做了什么 | 影响 |
| --- | --- | --- | --- | --- |
| [#63489 Bugfix LoRA: Refuse adapters with LoRA on modules vLLM does not wrap](https://github.com/vllm-project/vllm/pull/63489) | 10-23 18:55 | 以前怎样、为什么会错 | 改了什么机制 | 谁受影响、后果或数字 |

# VLLM Ascend

| PR | 合入时间 | 合入背景 | 做了什么 | 影响 |
| --- | --- | --- | --- | --- |

# SGLang

| PR | 合入时间 | 合入背景 | 做了什么 | 影响 |
| --- | --- | --- | --- | --- |
```

硬规则：

- 标题逐字为 `# 概览` / `# VLLM` / `# VLLM Ascend` / `# SGLang` 四条，**不出现任何 `##` / `###`**。
- 概览表固定三列（仓库 / 合入 PR 数 / 本周主线），末行 `合计`；合计数字必须等于三张 PR 表的行数之和。
- PR 表固定五列，顺序不可变。第一列是链接 `[#<号> <原标题>](<html_url>)`，标题超 70 字截断加 `…`，`[Bugfix]` 之类前缀保留。
- **第二列按正向（从早到晚）排序**，`MM-DD HH:mm` 北京时间。脚本给的是**倒序**，成表时要翻过来；UTC 直抄会错一天。
- 三列文字各 40~80 字：背景写「以前怎样 / 为什么会错」，做了什么写「改了哪个机制」，影响写「谁受影响 + 后果或数字」。不写「优化了性能」这类套话。
- **加粗挑重点**：每行 1~2 处 `**…**`，加在结论词或数字上（`**升级阻断项**`、`**90 秒**`、`**40% e2e**`）；本周最值得看的 5~8 个 PR，把第一列整条链接加粗成 `**[#号 标题](url)**`。
- 单元格里不能出现 `|`，也不能有换行。
- 空仓不写散文：整周 0 合入时，把最值得关注的 1~3 个**在途** PR 填进那张表，合入时间列写 `未合入（在途）`。

**详细版（可选）**：用户要「每个 PR 展开讲」时有两种做法，先问是哪一种：

- **仍是表格，但把三列写长**（默认）：沿用上面五列表，每格放宽到 80~120 字，行序仍正向。
- **改成分节散文**：先跑 `scripts/fetch_pr_details.py <run 目录> 1000`，它把每个合入 PR 的正文清洗后（去掉 checklist 的 `<details>`、HTML 注释、折叠空白）落到 `details.md`；然后每个 PR 写成 `### [#号 短名](url)` + 一行 `时间 · +N/−M · 文件数 · 原标题` + `**背景**/**做了什么**/**影响**` 三段。

## 5. 发送

收件人固定两个：`xumingzhe4@huawei.com`（黄区）与 `3248569436@qq.com`（本人私人邮箱）。

1. 渲染邮件正文（`--subject` 必给，因为文档里没有标题行，首个 h1 是「概览」）：

```powershell
& $py "C:\Users\admin\.dsh\skills\lora-weekly-report\scripts\md2mail.py" `
  --md "D:\workspace\LoRA特性跟踪\reports\2026-10-30-lora-weekly.md" `
  --out "D:\workspace\LoRA特性跟踪\runs\2026-10-30\v2" `
  --subject "LoRA 周报（10-23 ~ 10-30）" `
  --to "xumingzhe4@huawei.com,3248569436@qq.com"
```

  产出 `mail.txt`（纯文本兜底，表格摊成 `· 名 —— 时间 —— 背景 —— 做了什么 —— 影响（url）`）与 `mail.html`（真表格、首列可点、`**…**` 渲染成 `<strong>`），并打印 `subject`。

2. 读这两个文件，调 `mcp__qqmail__qqmail_send`：`to=["xumingzhe4@huawei.com","3248569436@qq.com"]`，`subject` / `text` / `html` 全给。默认**不带附件**（.md 会被标 `application/octet-stream`，网关可能拦；正文已经完整）。

3. 发完用 `qqmail_list`（`mailbox="Sent Messages"`, `limit=3`）核对：主题以 `转发：` 开头、时间对得上。

结论只能写「已发出」——`Sent Messages` 有副本只说明 QQ 收下了，不等于收件侧放行。

## 6. 坑（都实测过）

1. **`is:merged` 必须用，`state=closed` 不等于已合入**：vLLM-Ascend 常见「批量关闭未合入」（2026-10-30 凌晨一次关了 4 个 LoRA PR，`merged=False`）。脚本已用 `/pulls/{n}` 的 `merged_at` 复核，别绕过脚本手搓。
2. **`in:title` 是精度换召回**：标题不含 `lora` 的改动（例如 MoE LoRA 只被称作 "MoE routing"）不会进表。这是刻意的——放宽后候选会从 30 涨到 200+，噪音压不住。
3. **搜索 `merged:>=DATE` 只到日粒度且含边界日**，窗口首日会混进窗口外 PR；必须用 `merged_at` 精确时间再筛（脚本已做）。
4. **UTC→CST 跨日**：`2026-10-30T02:21Z` 是北京时间 `10-30 10:21`；`2026-10-29T20:42Z` 是 `10-30 04:42`。照抄 UTC 日期会把两周的 PR 写到同一周。
5. **两个仓的标题习惯不同**：vLLM-Ascend 用 `[Feature][LoRA]` / `[v0.26.0rc][Feature][LoRA]`（带版本前缀），SGLang 用 `[Feat] lora:`（小写）。判定只看是否含 `lora`，别按前缀匹配。
6. **合并 ≠ 该仓已有能力**：同一能力可能先合 SGLang 再合 vLLM，概览里别把两边写成同一次进展。
7. **qqmail 无转发工具**：转发形态只能手工拼（`转发：` 主题 + 正文头块），`md2mail.py` 已经拼好，别自己另写一份。
8. **别把「本周无」写成「没有相关工作」**：空表只说明这一周没有合入，不说明没人做；用「未合入（在途）」那几行把话说清楚。
9. **单元格里不能有 `|`**：哪怕写 `test ... ||` 这种，也会把表格切歪。改写掉，或挪进 HTML 实体。
10. **整条链接加粗时 `**` 要在外面**：写 `**[#号 标题](url)**`，不要写 `[**#号 标题**](url)`——后者 `md2mail` 匹配不到链接，纯文本兜底会丢 URL（脚本已能处理外层加粗）。

## 7. 验收

1. `^# ` 恰好 4 条，逐字为 `概览` / `VLLM` / `VLLM Ascend` / `SGLang`；`^## ` 与 `^### ` 均为 0 条，标题之外没有散文段落。
2. 每个标题下恰好一张表；概览表 3 列（末行 `合计`），PR 表 5 列且列序为 `PR / 合入时间 / 合入背景 / 做了什么 / 影响`。
3. 第二列正向排序、全在窗口内或标 `未合入（在途）`；第一列是可打开的 `[...](https://github.com/...)` 链接。
4. 概览合计 = 三张 PR 表的行数之和。
5. 至少 5 处 `**…**`；`mail.txt` 首行 `【AI 代发】`；`Sent Messages` 里收件人是 `xumingzhe4@huawei.com` 与 `3248569436@qq.com` 两个。
