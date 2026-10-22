---
name: external-buzz-magnitude-check
description: 外部热度量级取证——这事在外网真的火吗（HN points/评论、HF likes/下载量、Artificial Analysis/OpenRouter 体验指标、社区情绪分级）——判某事在外网是否真热、某模型是否真难用，给可复现量级数字；与 GitHub 提交活性解耦，双榜分开列。适用于"这事在外网真的火吗 / 给我外部热度量级证据 / 这个模型是不是真的很难用 / 社区有没有人在骂 / HN 有多少 points 和评论 / 这个模型速度慢不慢 / 内部提交多但外面没动静算不算热点"。不适用：只看 GitHub 组织内部提交增量 → 用 `github-org-delta-watch`；核查论文声称能否复现 → 用 `arxiv-paper-deep-read-and-claim-verification`。
whenToUse: 外部热度取证：先定权威 UTC 再算 epoch，取 HN points/评论、HF likes/下载量/许可、中文站正文日期，内外双榜分开列。模型看不到本节。
---

# 外部热度与量级取证（HN / HF / 中文站）

2026-09-28 在 MiniMax 上真跑通（HN / HF API / 中文站 / 英文大媒体四路）。**核心用途**：当 GitHub 内部活跃度与外部热度完全脱钩时，避免把"内部提交多"误判成"热点"。

## 何时调用

- **触发信号**：用户问"这事在外网真的火吗 / 有量级证据吗"；或要复核一份组织调研报告里"热点"结论；或出现"内部 release 连发但外面好像没动静"。要拿的数字形如 `440 pts / 98 comments`、`likes=5734 downloads=3672292`。
- **转交边界**：只要 GitHub 组织内部提交增量/观察点变化 → 用 `github-org-delta-watch`；只做论文声称核查 → 用 `arxiv-paper-deep-read-and-claim-verification`；向 GitHub 仓提 PR → 用 `github-pr-flow`。
- AI 厂商官方信息源真伪与覆盖面判定（响应体空壳 / arXiv 编号是否官方） → 用 `ai-vendor-official-source-audit`。
- **前置**：能跑 pwsh + 联网。HN Algolia 与 HF API **免 key、实测未限流**，无需令牌。 ／ **后继**：产出两节——「外部量级榜（HN/HF/媒体）」+「内部 GitHub 活性（另见 `github-org-delta-watch`）」，逐条给 URL 与日期。

## 前置检查

```powershell
# 一次调用同时拿到权威当前 UTC 与 GitHub 额度（Date 响应头是权威时间）
(Invoke-WebRequest -Uri 'https://api.github.com/rate_limit' -Headers @{'User-Agent'='x'} -UseBasicParsing).Headers['Date']
```

- 验证：本次得 `Mon, 28 Sep 2026 06:29:48 GMT`。**拿到 UTC 后才能算 epoch，顺序不能反。**
- `-Headers @{'User-Agent'='x'}` 是硬要求（GitHub 无 UA 返回 403）；HN / HF 端点不需要头部。

## 步骤

1. **epoch 自校验锚点**（写完阈值先对一遍，再发查询）：
   - `2026-09-20T00:00Z = 1789862400`（实测锚点，可作为换算正确性的对照）
   - `reset=1790577045` 与权威 UTC `2026-09-28T06:29Z` 同批实测值，仅用于交叉核对换算，不作为"今天"。
2. **HN 量级一次取到**（免 key）：
   ```powershell
   Invoke-RestMethod 'https://hn.algolia.com/api/v1/search?query=<KW>&tags=story&numericFilters=created_at_i%3E<EPOCH>,created_at_i%3C<EPOCH2>&hitsPerPage=20'
   ```
   - 取每条 `points` / `num_comments` / `created_at` / `title`。
   - 验证（本期实测锚点）：`H3-metal 440 pts / 98 cmts`(2026-08-11)、`ComfyUI Day-0 334 / 94`(08-03)、`Nunchux AMD MI355X 7 / 3`(09-23，本期天花板)、`MiniMax M3.1-Flash-Preview 1 / 0`(09-28) → 本期外部热度**量级极低**。
3. **单条详情**（要 `url` 和评论树时）：
   ```powershell
   Invoke-RestMethod 'https://hn.algolia.com/api/v1/items/<ID>'
   ```
   - 取 `points`、`children.Count`、`url`。
4. **HF 热度与许可**：
   ```powershell
   Invoke-RestMethod 'https://huggingface.co/api/models/<org>/<name>'
   ```
   - 取 `likes`、`downloads`、`lastModified`、`tags`（**许可在 tags 里**，形如 `license:other`）。
   - 验证：`MiniMaxAI/MiniMax-H3` → `likes=5734 downloads=3672292 lastModified=2026-08-13 license:other`。
   - HF 字段口径与 401 判因（`createdAt`≠发布日、列表要 `&full=true`、401=not found、`/raw/` 对 LFS 只给 132 B 指针）归属 → 用 `ai-vendor-official-source-audit`，本 skill 不重复写。
5. **中文站判"新旧"**：`Invoke-WebRequest <url> -UseBasicParsing` → 剥掉 `<script>/<style>` → 取**正文内的日期**（不要用列表页摘要或 URL 猜）。
   - 验证：一条热门旧闻的转载 URL 含日期段 `20260808`，据此判为 2026-08-08 旧闻，**不进本期热点榜**。
6. **英文大媒体阴性也要记录**：本期 TechCrunch / VentureBeat / The Information **零命中**，写"未检索到"。

## 坑与修法

- **`query=MiniMax` 误报**：命中 "minimal / minimize / minimax 算法" 等。实测 `nbHits=33` 里绝大多数是误报 → 修法：**逐条看 `title` 再计数**，不要直接报 `nbHits`。
- **epoch 算错会静默返回空结果**：URL 语法正确但数字不对 → 空数组、不报错，是本次最隐蔽的坑 → 修法：先用第 1 步锚点核对换算，再发查询。
- **HF 该端点不返回 `trendingScore`**：想拿 trending 排名需换端点或读页面（未验证：具体替代端点未实测，不要臆造 URL）。
- **`license:other` ≠ Apache-2.0，也 ≠ 无许可证**：`MiniMax-H3` 的 `license:other` 对应自定义的 MiniMax H3 Community License Agreement → 修法：照抄 `tags` 里的原始值；`license` 为 `null`（GitHub API）同样只是**自定义许可无 SPDX id**，必须回仓库正文确认。（`github-org-delta-watch` 里已有同一坑的 GitHub 侧版本。）
- **Reddit 全路 403**：`www.reddit.com`、`old.reddit.com`、`api.reddit.com`、`/comments/<id>.json` 与 web_fetch **全部 403**；镜像 `safereddit.com` 返回 Anubis 拦截页、`redlib.catsarch.com` 429 → 修法：拿不到一手 upvote/评论时**必须显式标注"无一手数据"**，Reddit 量级一律标为**二手转述**，**不得混入量级榜**。
- **反爬页：状态码 200 ≠ 内容可取**：36kr 快讯 HTTP 200 但正文是火山引擎反爬质询页 → 修法：剥标签后看正文特征（质询页无正文日期与实体名），判为不可取，不要当正文用。
- **搜索类结论不要写成"不存在"**：搜不到就写"未检索到"，并写上检索范围与端点。
- **第三方 / 旧闻 / 幻觉三防**：第三方包（如 PyPI 上的同名包）不等于官方兑现；早于基准日的报道单独归"旧闻"；数字必须来自 API 响应原文。

## 不要做什么

- **不要用 GitHub 提交数/发版数推断外部热度**。实测同一时段 `minimax-code` 连发 7 个 release，而中英文媒体与 HN **双零命中** → 结论必须两个榜单分开列。
- 不要把 Reddit 的二手转述量级混进量级榜。
- 不要把 `license:other` / `license=null` 写成 Apache-2.0 或"无许可证"。
- 不要在没先拿权威 UTC 的情况下手算 `created_at_i`。
- 不要用 URL 里的日期段之外的信息（列表页摘要、页面 banner）判新闻新旧——正文日期优先，URL 的 `YYYYMMDD` 作低成本兜底。

## 体验指标与社区情绪取证

来源：2026-09-29 一轮"某模型实际使用体验是否真差"取证真跑通（Artificial Analysis / OpenRouter / 官方缺陷自陈 / HN / HF / 知乎 / B 站）。

1. **判"客观指标异常"必须有同期竞品对照**（本节最重要的一条）：**单模型指标不构成结论**。同一个实测数字（output speed 40.76 tok/s）单看会判"很慢"，与竞品同口径并列后（另一厂商 36.32 tok/s）结论才变成"慢但不是最慢"。判据：**≥3 家同口径并列**（同 provider 口径、同 prompt 类型、同时间窗），少于 3 家只写"实测值"、不写"快/慢"。
2. **Artificial Analysis 取数法**（模型页 URL 形状 `artificialanalysis.ai/models/<slug>`）：
   - 模型页**非 SPA**：假 slug → 真 **404** ⇒ 可用来判 slug 真假。
   - 载荷是 SSR 的 HTML，字段被转义成 `\"field\"` ⇒ **先把 `\"` 反转义再按大括号配对（brace-match）**，并用 `{"id":"<uuid>","slug":"...","name":"` 锚定目标模型对象；**页面上有几百个 model 对象，直接 `[regex]::Matches('\\"intelligenceIndex\\"…')` 会命中任一个**（实测 684 个）⇒ 必须 brace-match 到目标对象后才读字段，否则拿到的是别的模型。
   - 速度 / 延迟类**真字段名**：`timescaleData.medianOutputSpeed`、`timescaleData.medianTimeToFirstChunk`、`timeToFirstAnswerToken.total`、`endToEndResponseTime.total`、`outputSpeedVariance{p05,median,p95}`、`performanceByPromptType{long,medium,hundredK,mediumParallel}`、`omniscienceHallucinationRate`、`intelligenceIndexIsEstimated`、`performanceDataSource{type,providerName}`、`price1mInputTokens` / `price1mOutputTokens`。
   - **`performanceDataSource.type` 要一起读**：`firstParty` = 速度取自厂商自家端点，**不是第三方托管**口径。
   - 反例：`medianTimeToFirstToken`、`ttft` 在该 HTML 里命中数为 **0** ⇒ 不要凭印象臆造字段名，先搜字段是否存在。
   - AA 官方 API `/api/v2/data/llms/models` → **401 需 key**，别走。
   - **残差警告（不要当成已验证结论）**：本流程**未查清 HTML 里 `self.__next_f.push` 分块索引与字段名的对应关系** ⇒ brace-match 拿到的字段**可能只是同名字段的另一个副本**（同一模型在页面里有多个数据块，同名键可能重复出现），而本流程没做"块 ↔ 图表"的映射校验。**下次第一步**：先把 `self.__next_f.push` 的分块拆出来、给每块编号并定位每个分块里的字段名，确认目标字段**唯一出现在哪一块**之后再去取值；在那之前，取到的数字只写"某分块内该字段的值"，不写成"该模型的官方指标"。
3. **OpenRouter 三个面**：
   - ① `/api/v1/models/<slug>/endpoints` 判**是否被下架 / 降权**；若某 slug 返回含数据的 **200** 但 `latency_last_30m` / `throughput_last_30m` **恒为 null** ⇒ 速度不能从这个端点拿（不是它慢，是它不供数）。
   - ② **真值在模型页 HTML 内嵌的 React Query 载荷**：含 `p50_latency/p95_latency/p99_latency/p50_throughput/request_count/window_minutes`，以及体验类字段 `requests_with_tool_call_errors` / `total_tool_calls`（**按 key 分别取全部值再求和算比率**，不要取单条 record）。
   - ③ **同一页有两个日粒度序列**（`model_chart` 与 `top_apps_chart`），口径可差数倍 ⇒ **必须按字符位置把每条 record 归属到所属序列**，否则把两个口径混成一条数。可抄写法（先取两个序列的**起始字符索引**当边界，再按递增覆盖把每条 record 归属）：

     ```powershell
     $mk=$html.IndexOf('"model_chart"'); $tk=$html.IndexOf('"top_apps_chart"')   # 两个起点都须 >0，否则该字段不在本页
     $bnd=@($mk,$tk) | Sort-Object
     foreach($m in [regex]::Matches($html,'\\?"p50_latency\\?":\s*([0-9.]+)')){   # 合成样本实测：对 JSON 的 `\"` 与裸 `"` 都能命中
       $pos=$m.Index; $sec=0
       for($i=0;$i -lt $bnd.Count;$i++){ if($pos -ge $bnd[$i]){ $sec=$i } }        # 递增覆盖 = 落到最后一个 <= pos 的起点
       $name=@(if($sec -eq $bnd.IndexOf($mk)){'model_chart'}else{'top_apps_chart'})
       "$name $($m.Groups[1].Value)" }
     ```

     - 合成样本干跑实测（数字是测试值，不是真数据）：**不切分**天真写法把 4 条混在一起求和 **94.6**；按区间归属 → `model_chart` **29.3** / `top_apps_chart` **65.3** ⇒ 两个口径必须分开陈述，**不做跨序列减法**。
     - **键名到序列的映射要自己复核**：本流程只按字符位置切分；`p50_latency` 是否只出现在 `model_chart` 块、`requests_with_tool_call_errors` 落在哪个块**未逐块验证（未验证）** ⇒ 先 `IndexOf` 确认两个起点都在，再读归属结果。
   - ④ `/rankings` 主体是 skeleton（`data-testid="rankings-skeleton-row"`），真值只在 sr-only 文本 + JSON-LD（`"@type":"ItemList"`，其 `name` 逐字为 "Top LLMs by weekly token usage on OpenRouter"）；前端 API `/api/frontend/*`、`/api/v1/analytics/rankings` **全 404**。
4. **官方"自认缺陷"类博客是最硬的一手证据**：厂商自己发的复盘文（tolerance 线、分 harness 的错误率、修复成本、修复版权重后缀、API 切换时间）既证明"体验差"有据，也说明**"厂商承认" ≠ "用户传闻"**，两者分列。同时：**修复版权重的下载量极低 ≠ 问题没修** ⇒ 要核对 API 是否已切到修好的版本。
5. **社区情绪必须分级计数**，三档分别给数字、**不得把 ③ 混进结论**：
   - ① 一手实测（贴 prompt / 截图 / 日志）
   - ② 二手转述（只转述结论）
   - ③ 仅存在性（只拿到标题，正文取不到）
   - 且**主动找反证**：正面 / 中性反馈同样分档计数，避免确认偏误（只计数"骂的"＝自证）。
6. **中文站反爬绕行矩阵**（下表是实测码 + 实测结论，不是推断）：

   | 目标 | curl | 浏览器（Playwright） | 结论 |
   |---|---|---|---|
   | 知乎 | **403** | 正常 | 抓正文必须走浏览器 |
   | B 站 | API **412** 风控 | 正常 | 可读 `window.__INITIAL_STATE__` 取 view/reply/like |
   | 掘金 | 200 但仅 **2397 B**，正文只有 "Please wait..." | — | 判"未取到" |
   | 少数派 | 200 但仅 **2709 B**，只有 JS | — | 判"未取到" |

   - **DNS 劫持判定法**：本机解析结果与 DoH 权威解析不一致即劫持（可抄写法）：

     ```powershell
     $h='www.cloudflare.com'   # 换成目标站
     $local=(Resolve-DnsName $h -Type A -ErrorAction Stop | Where-Object {$_.IP4Address} | Select-Object -ExpandProperty IP4Address | Sort-Object -Unique) -join ','
     $r=Invoke-WebRequest -Uri "https://1.1.1.1/dns-query?name=$h&type=A" -Headers @{'Accept'='application/dns-json'} -UseBasicParsing
     $j=[Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json   # 响应无 charset，必须走字节流（同 AGENTS 铁律）
     $doh=($j.Answer | Where-Object {$_.type -eq 1} | Select-Object -ExpandProperty data | Sort-Object -Unique) -join ','
     if($j.Status -ne 0 -or $doh -eq ''){ "上游查询失败 status=$($j.Status)，不判劫持" } else { "local=$local`ndoh=$doh`n两侧一致=" + ($local -ceq $doh) }
     ```

     - **`-Unique` 两侧都要有**：只对一侧排序/去重会造出新的不对称（本地吐重复 A 记录时假报不一致）。实测：`Sort-Object` 单用不去重（`1.1.1.1,1.1.1.1`），加 `-Unique` 才归一。
     - **先判 `$j.Status -eq 0` 且 `$doh` 非空**：DoH 上游失败时 `$doh` 恒为空串且**不报错**，否则会把"上游查询失败"报成"劫持"。
     - 实测本机 `128.121.243.76` vs 权威 `104.20.16.234` / `172.66.166.61`，表现为 `ERR_CERT_COMMON_NAME_INVALID` / schannel `0x80090367`；`curl --resolve` 打通后转 Cloudflare `Just a moment...` **403** ⇒ 该类站只能标"未取到"，不得写成"查无"。
     - **集合不等 ≠ 劫持**：CDN 就近应答 / GeoDNS / TTL 过期都会让两侧合法地拿到不同子集 ⇒ `两侧一致=False` 只写"两侧集合不一致，需人工判因"，**不要直接写成"被劫持"**（未验证：区分"劫持"与"GeoDNS 就近"需要额外证据链，本流程未建立该判据）。
   - **TLS 兜底**：**不要在 PS 5.1 里设 `ServicePointManager::ServerCertificateValidationCallback`**（实测会把所有 HTTPS 全挂，报"基础连接已经关闭: 发送时发生错误"）⇒ 改用 `curl.exe -k` 落 `$env:TEMP` 再**按 UTF-8 读回**。
   - **镜像站的 views 是镜像自身计数**（个位数）⇒ **不可当原站量级**。
7. **HN 取量级用 Algolia**：`https://hn.algolia.com/api/v1/search?query=<KW>&tags=story&hitsPerPage=20`，**逐条看 `title` 再计数**（`nbHits` 含大量误报，同上面「坑与修法」第 1 条）。HF discussions 端点返回的是 **dict 不是 list**（`{discussions:[…],count,…}`），正文在 `/discussions/{num}` 的 `events[].data.latest.raw`；总条数与实际可读条数常不一致 ⇒ 分档计数（同 pin 5）。

## 验收标准

1. 每个量级数字都能回放到一条可点开的 URL，并带该条的日期。
2. **外部榜与内部 GitHub 榜分开列**，互不推导；有脱钩时明确写"内部活性 ≠ 外部热度"。
3. HN 计数已逐条核对 `title`，未把 `nbHits` 当命中数。
4. HF 条目标明 `likes` / `downloads` / `lastModified`，许可照抄 `tags` 原值。
5. Reddit 相关一律标注"无一手数据 / 二手转述"，或干脆不出现在量级榜。
6. 阴性结果写"未检索到"（附检索范围），不写"不存在"。
