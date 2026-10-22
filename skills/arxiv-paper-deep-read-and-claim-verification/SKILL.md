---
name: arxiv-paper-deep-read-and-claim-verification
description: arXiv 论文精读 + 开源声称独立核查——精读这篇论文、论文说的开源仓真实存在吗、论文数字能复现吗：web_fetch 抓 /html 会在正文中段被 (Content truncated.) 截断，改用 pwsh Invoke-WebRequest -UseBasicParsing 抓全文落盘再分块 read；abs 页判存在性、GitHub REST API 判仓（不抓网页，JS 渲染只剩导航栏）、HF models API 的 safetensors.total 判参数量；论文数字必须在 README/模型卡逐字找到，否则判未复现。适用于"精读这篇 arXiv 论文 / 给我这篇论文的中文技术总结 / 论文说的开源仓库真实存在吗 / 论文声称的数字能复现吗 / 核查论文说的模型有没有发布 / 论文的 star 数参数量帮我核一遍"。不适用：审上游仓库 docs 与内部需求缺口 → 用 `upstream-docs-refresh-audit`；向 GitHub 仓提 PR → 用 `github-pr-flow`。
whenToUse: 给定 arXiv 链接要出中文精读总结，并独立核查论文声称的开源仓库/模型是否存在、数字是否一致时用。模型看不到本节。
---

# arXiv 论文精读与开源声称核查

实测环境：Windows 10 + pwsh + DSH 联网工具，2026-06 实测论文 `2606.13392v2`（对象：MiniMax MSA 稀疏注意力 / M3）。全文抓取 416,464 字符 → 折行落盘 1,660 行 ≈ 99KB，7 次 `read` 读完。

## 何时调用

**加载本 skill 当：**

- 给一个 arXiv 链接，要「精读全文 + 中文技术总结」。
- 要**独立核查**论文里"已开源 / 已发布 / 达到 N 倍加速"这类声称，而不是照抄论文。
- 要判数字一致性：论文里的参数量、加速比、benchmark 成绩，能不能在 README / 模型卡里找到同一口径。
- 别人（含子代理）返回了 star 数 / 参数量 / license / 下载量，要复验。

**不要用本 skill（转交）：**
- 要审上游仓库 docs 与内部需求的缺口、产出刷新清单 → 用 `upstream-docs-refresh-audit`。
- 目标是把改动提成 PR（fork / DCO / CI 判读） → 用 `github-pr-flow` 或 `gitcode-pr-flow`。
- AI 厂商官方信息源真伪与覆盖面判定 → 用 `ai-vendor-official-source-audit`。
- 外部热度量级取证（HN points / HF likes 量级数字） → 用 `external-buzz-magnitude-check`。
- 只看 GitHub 组织提交增量 / 判某仓是否死仓 → 用 `github-org-delta-watch`。

**前置**：能跑 `pwsh` + `curl`（Windows 自带 curl.exe）+ 联网。 ／ **后继**：核查结论落盘成中文报告；发现某条数字无法复现时，明确写"未复现"并给出论文口径 vs 开源口径两栏，不要含糊。

## 前置检查

```powershell
curl -s https://arxiv.org/abs/<id>   # 判论文真实存在、版本、作者数、页数、DOI
```

- 验证：本次 HTTP 200，返回 v1/v2 两个日期、17 位作者、`30 pages, 14 figures`、DOI、PDF/HTML/TeX 链接。
- **不要凭编号判存在性**：arXiv 形如 `2606.xxxxx` 的"未来编号"也可能是真论文，必须抓 `abs` 页确认。

## 步骤

1. **抓全文（不要用 web_fetch 抓 `/html`）**：web_fetch 会在正文中段吐 `(Content truncated.)`（本次在 Section 3.2 处截断），信息会静默丢失。改用 pwsh 落盘：

   ```powershell
   $h=(Invoke-WebRequest -Uri 'https://arxiv.org/html/<id>v2' -UseBasicParsing).Content
   ```

   `-UseBasicParsing` 是硬要求，见「坑与修法」。
   - 验证：本次 `$h.Length` = 416,464 字符。

2. **清洗成可 read 的纯文本**（顺序不能换）：

   ```powershell
   $h = [regex]::Replace($h,'(?s)<(script|style)\b.*?</\1>','')      # 去 script/style
   $h = [regex]::Replace($h,'(?i)</(p|div|li|h[1-5]|td)>',"`n")       # 块级闭合标签换行
   $h = [regex]::Replace($h,'<[^>]+>','')                             # 去剩余标签
   $h = [System.Net.WebUtility]::HtmlDecode($h)                       # 解实体
   $lines = foreach($l in ($h -split "`r?`n")){ if($l.Length -gt 140){ for($i=0;$i -lt $l.Length;$i+=140){ $l.Substring($i,[Math]::Min(140,$l.Length-$i)) } } else { $l } }
   [System.IO.File]::WriteAllLines('D:\workspace\<dir>\paper_<id>v2.txt',$lines,[System.Text.Encoding]::UTF8)
   ```

   - 验证：本次落盘 1,660 行 ≈ 99KB。

3. **分块 read 读完**：按 `offset`/`limit` 逐块 `read`（本次 7 次），**References 段可跳过**（纯书目，无核查价值）。读时把每个被引用的表号/图号连**表标题原文**一起记下来。
   - 验证：能复述方法、实验设置、主结果表数字。

4. **核查"内核/代码已开源"**——**不要抓 GitHub 网页**（JS 渲染后只剩导航栏样板）：

   ```powershell
   curl -s https://api.github.com/repos/<owner>/<repo>              # private / license.spdx_id / stargazers_count / language / pushed_at
   curl -s https://api.github.com/repos/<owner>/<repo>/contents/    # 目录结构：有无 benchmarks/ tests/
   curl -s "https://api.github.com/repos/<owner>/<repo>/commits?per_page=5"
   curl -sL https://raw.githubusercontent.com/<owner>/<repo>/main/README.md   # 依赖 / 硬件 / 安装 / 集成方式
   ```

   - 验证：本次通过 contents/ 与 README 拿到 `GPU: NVIDIA SM100`（Blackwell）这一关键硬件口径。

5. **核查"模型已发布"**——**以 safetensors 参数量为准，不采信模型卡文字**：

   ```powershell
   curl -s https://huggingface.co/api/models/<org>/<name>                        # safetensors.total / cardData.license / downloads / likes / createdAt / gated
   curl -sL https://huggingface.co/api/models/<org>/<name>/raw/main/config.json  # model_type / architectures / max_position_embeddings / 稀疏注意力字段
   ```

   - 验证：本次 MiniMax-M3 实际 427B 总参 / 23B 激活。
   - 本节只给"判是否已发布"的最小路径；HF API 字段本身的真伪判据（`createdAt` 是仓库创建时间**不是发布日**、`/raw/` 与 `/resolve/` 可能返回 132 B 的 LFS 指针要改抓、二进制先验 magic、401 = 路径不存在而非鉴权失败）归属 → 用 `ai-vendor-official-source-audit`，本 skill 不重复写。

6. **出中文总结 + 核查结论**，两者分开写：

   - 总结：问题 / 方法 / 关键设计 / 实验设置 / 主结果 / 局限。
   - 核查：每条声称一行，三列——论文口径 | 开源侧实据（含命令与字段） | 判定（一致 / 不同口径 / 未复现 / 未确认）。

## 核心判据（这套流程的价值所在）

- **论文数字必须在 README / 模型卡里逐字找到，否则判"未复现"。** 实测：论文说 109B 模型 + H800 14.2×/7.6×，但开源 MSA 内核 README 标注 `GPU: NVIDIA SM100`（Blackwell）→ H800 数字无法用该内核复现；已发布模型 MiniMax-M3 实际 427B 总参 / 23B 激活，与论文的 109B/6B 是**不同模型**；模型卡口径是"vs M2 的 9× prefill / 15× decode、per-token compute 1/20"，与论文口径不同。
- **区分"存在性声明"与"数字声明"**：仓/模型真的存在（前者常真），数字能不能复现（后者常不一致）。核查报告必须两栏分开，否则会把"仓是真的"误读成"数字也是真的"。
- **论文内部交叉引用可能错位**：实测 C.2 正文写 `As shown in Table 6`，但该表标题是 `Table 5` → **以表标题为准**，引用时以标题兜底。
- **PPL ≠ 通过率**：核对 benchmark 成绩时先分清原文给的是 perplexity 还是 pass rate，两者不可互相换算。
- **子代理返回的外部事实（star 数、参数量、license、下载量）主 Agent 用一条 REST API 命令复验**：本次复验 4 个字段全部一致。

## 坑与修法

- 现象：`Invoke-WebRequest : Windows PowerShell is in NonInteractive mode. Read and Prompt functionality is not available.`
  → 原因：不带 `-UseBasicParsing` 会走 IE 引擎渲染，交互模式下要弹提示。
  → 修法：永远加 `-UseBasicParsing`；加上后本次成功取到 416,464 字符。
- 现象：`web_fetch` 返回正文里出现 `(Content truncated.)`，中段内容整块丢失且不报错。
  → 原因：web_fetch 有输出长度上限。
  → 修法：改走步骤 1 的落盘 + 分块 `read`，不要试图用 web_fetch 拼多次请求。
- 现象：查 HF 某仓回 `401`，被当成"鉴权失败"就停了。
  → 原因与修法：`401` 的具体语义、裸名 401 要回列表按前缀核 —— **单一归属在 `ai-vendor-official-source-audit`**（见其 HF 一节），本 skill 不重复；这里只需记住**查不到就写"未能确认"，不要编**。
- 现象：抓 GitHub 网页只拿到导航栏、"Sign in"等样板，看不到 README 正文。
  → 原因：GitHub 页面是 JS 渲染。
  → 修法：一律走 `api.github.com` + `raw.githubusercontent.com`（步骤 4）。

## 不要做什么

- 不要用 `web_fetch` 抓 `arxiv.org/html/<id>` 或 GitHub 仓库页——前者截断，后者空壳。
- 不要在 README / 模型卡没写数字时"按论文口径替它填"——那是编造，判"未复现"或"未能确认"。
- 不要用模型卡正文的参数量数字取代 `safetensors.total`。
- 不要在抓 401 / 404 时把"查不到"写成"不存在"。
- 不要把 PPL 当通过率引用。

## 验收标准

- 落盘全文文件存在，行数与 `read` 覆盖完整（本次 1,660 行 / 7 次 read），References 之外无遗漏。
- 中文总结覆盖问题/方法/实验/主结果/局限。
- 核查表每条声称都有：论文口径、开源侧实据（附命令或字段名）、判定。
- 至少一条明确的"未复现"或"不同口径"结论，或明确写出"全部逐字一致"（本次为未复现：H800 数字 vs SM100 内核；427B/23B vs 109B/6B）。
