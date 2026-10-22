---
name: ai-vendor-official-source-audit
description: AI 厂商官方源真伪与覆盖——这家厂商官方报告有哪些来源、这个文档链接是真的吗、抓下来是空壳还是真页：产品名≠API model id（按官方列表逐名计数）、新闻页与详情页都抓；体积极小或与假 slug 同档判空壳；HF &full=true 拿时间、401 只按状态码判（裸名要回列表按前缀核）、createdAt≠发布日；/raw/ vs /resolve/ 二进制验 magic。适用于"这家厂商官方报告有哪些来源 / 这个文档链接是真的吗 / 抓下来是空壳还是真页 / 这个模型 id 官方有没有对外提供 / 某模型是否真发布了 / 二手稿说的超越是真的吗 / 这个 arXiv 编号算不算官方 / 某产品是否已下线查无"。不适用：只精读论文并核查开源声称 → 用 `arxiv-paper-deep-read-and-claim-verification`；只做外部热度量级 → 用 `external-buzz-magnitude-check`；只看 GitHub 组织增量 → 用 `github-org-delta-watch`。
whenToUse: 要判某模型厂商的官方来源有哪些、某文档链接或模型 id 是不是真的、某模型是否真发布、二手稿的竞品对标方向对不对时用；含 sitemap 取权威索引、假 slug 对照破空壳、逐名计数核 id、HF 与 ModelScope 端点陷阱。模型看不到本节。
---

# AI 厂商官方信息源真伪与覆盖面判定

实测环境：Windows + DSH 联网工具，对象 MiniMax（platform.minimaxi.com / platform.minimax.io / arXiv / HuggingFace / ModelScope）。目标：判"某模型厂商的官方技术报告 / 模型信息到底有哪些来源、哪些链接是真的"。

## 何时调用

- **触发信号**：用户问"这家厂商的官方技术报告/模型信息有哪些来源 / 这个文档链接是真的吗 / 抓下来是空壳还是真页 / 这个模型 id 官方到底有没有对外提供 / 某模型是不是真的发布了 / 二手稿说它超越了某竞品是真的吗 / 这个 arXiv 编号算官方论文吗 / ModelScope 上有没有这个模型 / 某产品是不是已下线（查无）"。
- **转交边界**：只精读某一篇论文并核查其开源声称 → 用 `arxiv-paper-deep-read-and-claim-verification`；只做外部热度量级（HN points / HF likes） → 用 `external-buzz-magnitude-check`；只看 GitHub 组织提交增量 → 用 `github-org-delta-watch`。本机 PowerShell 命令本身的坑（计数恒 0 / BOM / PS7 语法） → 用 `pwsh-on-windows`。
- **前置**：pwsh + 联网（本流程全部端点免 token；`/api/v2/data/llms/models` 那类需 key 的端点不要走）。 ／ **后继**：结论按"来源清单（真 / 假 / 查无）+ 每条证据 URL + 响应体字节数（二进制另附 magic）+ 官方 id 出现次数"落盘。

## 前置检查

- 抓取时**必须记录响应体字节数**，不能只看状态码。
- 每个域名准备一个**明显不存在的假 slug** 作对照（如 `/this-slug-does-not-exist-zzz`）。

```powershell
$r=Invoke-WebRequest -Uri 'https://platform.minimaxi.com/this-slug-does-not-exist-zzz' -UseBasicParsing
$r.StatusCode; $r.RawContentLength
```

- 验证：本次得 200 + 6466 B ⇒ 空壳。

未验证：上面的 pwsh 包装沿用同环境兄弟 skill 的写法；证据包只给到端点与字节数，命令外壳未逐字记录。

## 步骤

1. **用 `robots.txt` + `sitemap.xml` 拿权威页面索引**，不要猜路径：
   - `https://platform.minimaxi.com/robots.txt`、`https://platform.minimaxi.com/sitemap.xml`
   - 实测：国内站 robots 自报 canonical 是 `platform.minimax.cn`，而实际常用域是 `platform.minimaxi.com`——两者都是真站。
   - 验证：从 sitemap 拿到真实文档页路径清单，再逐个抓。
2. **判 catch-all SPA 空壳（最重要）：假 slug 对照 + 字节数**。
   - 实测：platform.minimaxi.com 对**任意路径**都返回 HTTP 200 + 同一个约 6466 B 的 JS 空壳，连不存在的 slug 也 200。
   - 判定规则：响应体 **< 10000 B ⇒ 判为无有效内容**；真实文档页实测 **47 万 ~ 70 万 B**。
   - 阳性对照：platform.minimax.io 对假 slug 正常返回 **404** ⇒ 同厂商不同站行为不同，必须逐站实测。
3. **arXiv 检索用机构名，不用产品名**：
   - 端点：`http://export.arxiv.org/api/query?search_query=all:%22MiniMax-AI%22`
   - 实测：`all:MiniMax` 返回 40 条里 38 条是数学的 minimax 概念，几乎全是噪声；`all:%22MiniMax-AI%22` 返回 7 条全是官方论文。
4. **逐个访问 abs 页读作者署名判"是否官方"**：
   - `https://arxiv.org/abs/<id>`
   - 实测：`2512.13687`、`2601.10343` 确实存在（HTTP 200）但作者名单里**没有 MiniMax 署名** ⇒ 不能当官方技术报告引用。
   - 判定规则：编号存在（200）≠ 官方；官方性只由作者署名决定。
5. **HF 列表：时间信息必须加 `&full=true`**：
   - `https://huggingface.co/api/models?author=<ORG>` → 实测**无 `lastModified` 字段**（键为 `_id,id,likes,private,downloads,tags,pipeline_tag,library_name,createdAt,modelId`）。
   - 加 `&full=true` 才拿得到时间信息。
6. **HF 单模型缺失：401 就是 not found**：
   - 实测 HF 上查 MiniMax-Speech-01 / Speech-2.8 / Hailuo-02 / Video-01 均 **401** ⇒ 含义是 not found，不是鉴权失败。
7. **ModelScope：只有逐模型 API 可用**：
   - 可用：`https://www.modelscope.cn/api/v1/models/<Namespace>/<model>` → 实测 4/4 成功，返回 `Code=200`、`Downloads`、`Stars`、`Architectures`。
   - 列表类 API 试了 7 种写法（GET/PUT、有无 www、users/organizations/dolphin、Name 参数）**全部** 404「未找到」/ 400「错误的请求」。
   - `/api/v1/organization/<ns>` 返回 200 但仅约 **4767 B 纯 JS 外壳** ⇒ **不能**作为"组织存在"的强证据（同第 2 条字节数规则）。
8. **判"查无"必须三条同时成立**：
   - 实测 abab 系列（已下线产品）：官网路径 404 + 文档模型列表里 0 次出现 + arXiv 检索 0 条。
   - 判定规则：**三条同时成立才可判"查无"**；任一缺失只能写"未检索到 / 未能确认"。
   - **判 not found 只认 HTTP 状态码，不认异常文本**：同一台机器上 HF 不存在的仓抛的是**中文**异常 `远程服务器返回错误: (401) 未经授权。`，**不是**本文件坑里记的 `Invalid username or password.`（同一 401 的另一种本地化文案）⇒ 按 `StatusCode` 判，别写按异常文本匹配的分支（本轮实测两条文案来自同一个 401）。

8.5 **`safetensors.parameters` 的计数不是字节数（packed quant 陷阱）**：
   - 实测 `{"F32":11122432,"BF16":57179884544,"U8":2722740830208}`。把 `U8` 当字节 ⇒ 得出"**3.1 TB 权重**"的错误结论。
   - 真关系：`U8` numel ÷ 剩余可用字节 = **1.882 ≈ 2** —— MXFP4 把 **2 个权重打包进 1 个 U8**，且 U8 里还混有 **per-32 的 scale 字节**。⇒ `U8` 既不是字节数、也不能简单 ×2。
   - 另：`safetensors.total`（实测 2.78e12）与 `.safetensors` 文件总字节（实测 1.56e12）**不是一个量**，别互相替代（一个含打包后的逻辑计数、一个是盘上存储）。
   - 判定规则：参数量一律报**逻辑参数 × dtype 字节数**，并显式说明口径；存储量另算。

8.6 **HF 仓名大小写不敏感**：`moonshotai/kimi-k3` 与 `moonshotai/Kimi-K3` 同样返回 200 ⇒ **不能用大小写差异当"另一个仓"**的证据（要判两个仓是否同源，比 `id` / `sha` / `lastModified`，不比 URL 大小写）。

9. **产品名 ≠ API model id：判"某模型是否真的对外提供服务"必须看官方模型列表 / 价格页里的 id**。
   - 做法：把官方模型列表页 / 定价页整页抓下来，对候选 id 逐个**计数**：`[regex]::Matches($t,[regex]::Escape($m)).Count`（计数规则的坑归 `pwsh-on-windows`，本 skill 只留指针：**不要**用 `Select-String -SimpleMatch -AllMatches`，它 `Matches.Count` 恒为 0）。
   - 实测：产品名写作 `DeepSeek-V4.1-Flash` 的那一档，官方对外 id 是 `deepseek-flash`；把产品名当 id 去官方文档搜，命中 **0 次**。⇒ 产品名是市场口径，**不能**当"已提供服务"的判据。
10. **官方"新闻页 / 博客"与"模型详情页"承载的信息不同，必须两页都抓**：
    - 竞品对标口径（"超过谁 / 仍落后谁"）常只出现在**新闻页 / 博客**；只抓 `/models/<slug>` 详情页会得出"官方没有提及某竞品"的**错误结论**（实测首轮子代理即漏报，主 Agent 用 `$t.IndexOf('关键词')` 取上下文复验纠正）。
    - 做法：抓全文后取 `$t.IndexOf('<关键词>')` 前后 **±700 字符**上下文再判语义，**不要**只数出现次数。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `ai-vendor-official-source-audit`；加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\<name>\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。

11. **二手稿的"超越 X"断言必须回厂商官方原文核对方向**：
    - 实测：二手稿依据的是 AutoEval 子榜**"持平"**，而厂商官方页原文是**"仍有差距"**——传成"超越"后方向完全反转。
    - 判定模板：官方页搜该竞品名 → 取上下文 → **逐字记下原文**；二手来源只能标注为"二手转述"，不得升级为事实。
12. **厂家自有模型站的权威索引 = 该站的 `sitemap.xml`**（比猜路径可靠）：
    - `https://<厂商模型站>/sitemap.xml` → `[regex]::Matches($s,'<loc>([^<]+)</loc>')`，逐条取 `<loc>`，含 `<lastmod>` 时一并记。
    - 实测：`mimo.mi.com` 得 **178 条 loc**，含 V2.6 三款模型页 + lastmod。与第 1 条配合：robots/sitemap 给"有哪些页"，逐页抓下来再按第 9 条数 id。
13. **破 catch-all 空壳的"同路由假 slug 字节对照法"**（第 2 条字节数规则的加强版）：
    - 在**同一路由形状**上抓真页与假 slug 各一次，比字节：实测真页 **137~138 KB** vs 假 slug **13,020 B**（**10.6×**）⇒ 判非空壳。**判空壳要"真页/假 slug 字节比"，不是单看一个绝对阈值。**
    - **补充限制：不要把"<10KB 一刀切"用到 SSR 站**。实测 DeepSeek Docusaurus 新闻页仅 **24,438 B**，但正文完整可读 ⇒ 小 ≠ 空壳。**判空壳前先确认该站是不是 SPA**（假 slug 是否也返 200 / 是否回同一份 JS 骨架）。
14. **HF 组织 / 仓库三层判真伪**：
    - ① 列表：`https://huggingface.co/api/models?author=<org>&full=true`（**必须带 `&full=true`** 才有时间字段，见第 5 条）。
    - ② **裸名 401 ≠ "没有该模型"**：官方常只公开后训练变体。实测裸名 `MiMo-V2.6-Pro` → 401，而真仓是 `MiMo-V2.6-Pro-RL` / `MiMo-V2.6-Pro-MOPD` ⇒ 必须回列表按**前缀匹配**交叉确认，不能凭单次 401 下"未发布"结论。
    - ③ **HF 仓 `createdAt` ≠ 发布日**：仓常提前占位。实测 Kimi-K3 仓 `createdAt` 2026-06-13，而官方到 7 月中旬才发布 ⇒ 发布日只认**官方博客 / News 原文 + 权重落地日**。
15. **HF 二进制文件必须走 `/resolve/` 并校验 magic**：
    - 实测：`/raw/main/<file>` 返回 **HTTP 200 但仅 132 B**，magic 是 `version `（Git LFS 指针文本）；换 `/resolve/main/<file>` 得 **1,809,802 B**、magic `%PDF-1.5`。
    - 判定规则：**别只看 200，也别只看字节数**——取前几字节比对 magic（`%PDF` / `PK`；见到 `version ` 即 LFS 指针，须改走 `/resolve/`）。
16. **Artificial Analysis 的可抓姿势**：
    - 它**不是** catch-all SPA（假 slug → 真 **404**）；真值在 SSR 载荷的 JSON 字段里，且在 HTML 中被转义为 `\"intelligenceIndex\":`。
    - 正则必须写成 `'\\"intelligenceIndex\\":\s*([0-9.]+)'`——**漏掉反斜杠会 0 命中**，看着像"官方没这个数据"。
    - 排行榜表格只渲染**整数**，故"46.32 vs 46"是**精度差不是造假**。
    - `/api/v2/data/llms/models` → **401 需 key**，别走这条路。
17. **榜单 / 接口的 502 / 404 必须与"0 条命中"显式区分**：
    - 实测：LMArena 数据集 `config=text` → **502**、`config=code` → **404**，正确 config 是 `agent`。把抓取失败写成"查无"就是造假。
    - 连接失败时**同时刻**用其它站点（HF / arXiv）作对照，以区分"区域封锁 / 瞬时故障"与"资源不存在"。
18. **自报数字必须带 harness / 口径，不做跨口径减法**：
    - 实测：同一官方模型两个数字口径可能不同（Kimi DeepSWE 博客 **67.3** vs HF yaml **67.5**；Toolathlon 博客 **73.2** vs yaml **76.5**，属官方自报内部矛盾）；`safetensors.total` ≠ 官方"参数量"（口径不同）⇒ **两者并列陈述**，不推断差值。
    - 厂商自报一手源可取 `https://huggingface.co/<org>/<repo>/raw/main/.eval_results/<bench>.yaml` 与 `/raw/main/README.md`；列文件名**不要猜**，先读 HF API 的 `siblings`。
19. **"存在"与"查无"的证据不对称**（对第 8 条的补充）：
    - 判**"存在"**只需跨源**任一**一手阳性；判**"查无"**才要求三类全阴（官方发布页 / 模型卡 + 官方文档或模型列表 + arXiv）。
    - 实测：**单看 GitHub 组织会误判"未发布"**——小米 GitHub 组织 18 个仓里没有 `MiMo-V2.6*`，但官网 sitemap / HF / 新闻页齐全 ⇒ GitHub 组织不是发布判据。
     - **修正：判"官方仓"必须先用 `fork=true` 过滤**。组织下的同名仓可能是 fork（实测 `XiaomiMiMo/verl`、`XiaomiMiMo/vllm` 的 `fork` 字段均为 `true`）⇒ **不能当"官方实现"引用**；取组织仓清单时逐个读 `fork`，或直接用 `orgs/<org>/repos?type=sources`。
     - **修正：判"无官方技术报告 / 无基准表"必须把 HF 模型卡算进去**。官方技术报告可能只挂在 HF 仓内（实测 `MiMo_V2_6_technical_report.pdf`：`/resolve/` HEAD **200 / 3,046,687 B**、magic `%PDF-`，而官网不链、arXiv 也没有）；HF 模型卡里的 benchmark 表也**不等于**"官网有表"。⇒ 判"无报告 / 无表"前必须先读 HF 仓的 `siblings` 文件清单与模型卡正文（同第 14 / 15 条做法）。
20. **arXiv 判官方性始终看第一作者署名，检索用机构名布尔式**：
    - 机构名布尔式（如 `all:"Xiaomi" AND all:"Moonshot"`）；实测 `all:"MiMo"` 会被 MIMO 通信 / 雷达论文淹没（**9134 条**噪声）。
    - 建议成对使用"无意义词阴性对照"（如 `zzzq-not-a-real-term-98765` → 0 条）**证明检索链路正常**——否则 0 命中无法区分"真没有"与"检索写错"。
    - `Kimi Team` / `DeepSeek-AI` 这种第一作者署名判官方；编号存在（200）≠ 官方（同第 4 条）。

## 坑与修法

- 现象：任意路径（含假 slug）都 HTTP 200，看起来"页面存在"。
  → 原因：catch-all SPA 路由对未知路径也回同一个 JS 空壳。
  → 修法：记响应体字节数 + 假 slug 对照；< 10000 B 判无内容（真文档页 47 万 ~ 70 万 B）。
- 现象：`all:MiniMax` 命中 40 条，误当官方论文。
  → 原因：minimax 是数学概念，产品名检索噪声极大。
  → 修法：改用机构名 `all:%22MiniMax-AI%22`（实测 7 条全官方）。
- 现象：arXiv 编号返回 200 就当成官方技术报告。
  → 原因：把"存在性"当"官方性"。
  → 修法：逐个开 `https://arxiv.org/abs/<id>` 读作者署名；无厂商署名一律不算官方。
- 现象：`https://huggingface.co/api/models?author=<ORG>` 响应里找不到 `lastModified`。
  → 原因：该端点默认不返回时间字段。
  → 修法：加 `&full=true`。
- 现象：HF 单模型查询返回 `401`，误判为需要登录 / 无权限。
  → 原因：不存在的仓库在该路径下以 401 表达 not found。
  → 修法：把 401 记为"查无此仓"，再用 `?author=<ORG>` 列表普查确认。
  → **补充（文案会随本地化变）**：同一台机器另一次实测抛的是中文 `远程服务器返回错误: (401) 未经授权。`，**不是** `Invalid username or password.` ⇒ **判 not found 只按 HTTP 状态码**，别按异常文本写分支。
- 现象：读 HF 仓的 `config.json` 判模型规模 / 架构，**所有字段都查不到**，于是判"这个 config 是空壳 / 元数据缺失"。
  → 原因：**多模态 config 把语言塔全部参数嵌在 `text_config` 下**——顶层只有 `architectures` / `dtype` / `tie_word_embeddings` / `text_config` / `vision_config`；且键**改过名**：`torch_dtype` → **`dtype`**，MoE 字段是 `num_experts` / `num_experts_per_token` / `num_shared_experts`（**不是** `n_routed_experts` / `num_experts_per_tok` / `n_shared_experts`）。
  → 修法：先 `if 'text_config' in d: d = d['text_config']` 再取字段；取不到时先怀疑**嵌套与改名**，别先怀疑模型（本体同时保留新旧键名作为回退）。要拿它算显存 → 用 `ascend-moe-ep-capacity-planning`。
- 现象：拿 `createdAt` 当发布日。
  → 原因：`createdAt` 常是**空占位**（仓建好了但里面没权重）。实测 `createdAt` **2026-06-13**，而权重落地是 **2026-07-27** 的 `Initial commit`，**差 44 天**。
  → 修法：发布日只认 **commits 里的 `Initial commit`（权重落地日）**+ 官方 Blog / News 原文，`createdAt` 只当"仓何时被创建"。
- 现象：抓官方博客正文找不到发布日期（全文 `20\d\d-\d\d-\d\d` 正则只命中 2 个图片 URL）。
  → 原因：发布日**不在博客正文、也不在 HF**，而在**官网首页卡片的 `<span class="_cardDate_*">`** 里。
  → 修法：发布日按顺序找：官方首页卡片日期 `<span class="_cardDate_*">` > HF `Initial commit` > 博客正文；`createdAt` 与"图片 URL 里的日期"都不算。
- 现象：抓 HF 二进制/大文件时用 `[System.IO.File]::WriteAllBytes($out, $r.Content)` 落盘。
  → 原因：`$r.Content` 是字符串不是字节数组，**异常消息里会把整份文件正文喷出来**（逐字原文 `Cannot convert value "# SPDX-License-Identifier..." to type "System.Byte[]"`）⇒ 瞬间炸掉上下文。
  → 修法：一律 `Invoke-WebRequest -OutFile <path> -UseBasicParsing`；该坑的归属与完整修法见 `pwsh-on-windows`。
- 现象：ModelScope 组织页返回 200，就写下"组织存在"。
  → 原因：200 只证明 SPA 外壳返回了（约 4767 B）。
  → 修法：一律记字节数；组织存在性用逐模型 API 的结果反推。
- 现象：ModelScope 列表类 API 7 种写法全部 `404 未找到` / `400 错误的请求`。
  → 原因：未找到可用的列表端点。
  → 修法：改逐模型 `/api/v1/models/<Namespace>/<model>`（实测 4/4 成功）。
- 现象：robots.txt 自报 canonical 域（platform.minimax.cn）与常用域（platform.minimaxi.com）不一致，疑心有假站。
  → 原因：同厂商多真域并存。
  → 修法：把 robots/sitemap 当权威索引来源，不当真伪判据。
- 现象：数某 id 在官方文档里出现几次，`Select-String -SimpleMatch -AllMatches` 的 `Matches.Count` 恒回 **0**，看着像"官方没有这个 id"。
  → 原因：`-SimpleMatch` 下 `Matches` 集合恒空（不是 null，是空 `Match[]`）；详见 `pwsh-on-windows`。
  → 修法：一律 `[regex]::Matches($t,[regex]::Escape($m)).Count`。
- 现象：HF 按裸名查模型 `HTTP 401 {"error":"Invalid username or password."}`，直接写成"该模型未发布"。
  → 原因：官方常只公开**后训练变体**，裸名确实不存在，但模型已发布。
  → 修法：用 `?author=<org>&full=true` 拉列表做**前缀匹配**（实测 `MiMo-V2.6-Pro` 401，真仓为 `MiMo-V2.6-Pro-RL` / `-MOPD`）；401 只记"该裸名无此仓"。
- 现象：`/raw/main/<file>` 返回 **HTTP 200**，就把 LFS 指针当文件本体。
  → 原因：Git LFS 大文件在 `/raw/` 只返回服务端指针：实测 **132 B**，magic 为 `version `。
  → 修法：改走 `/resolve/main/<file>`（实测 1,809,802 B、magic `%PDF-1.5`），并**校验前几字节 magic**，两者都要看。
- 现象：抓 Artificial Analysis 的指标，正则 `"intelligenceIndex":\s*([0-9.]+)` **0 命中**，判"没有该字段"。
  → 原因：真值在 SSR 载荷里被 HTML 转义成 `\"intelligenceIndex\":`，未转义的正则匹配不到。
  → 修法：正则写成 `'\\"intelligenceIndex\\":\s*([0-9.]+)'`；假 slug 返 **404** 证明它不是 catch-all SPA。
- 现象：某榜单数据集 `config=text` 回 **502**、`config=code` 回 **404**，被写成"该榜查无此事"。
  → 原因：config 名错 / 瞬时故障与"资源不存在"没区分开；正确 config 是 `agent`。
  → 修法：抓取失败状态（5xx/4xx）与"检索 0 条命中"分开记；失败时**同时刻**抓 HF / arXiv 作对照，判"封锁 / 抖动"还是"真没有"。

## 不要做什么

- 不要只用状态码判内容有无（200 可能只是约 6466 B 的空壳）。
- 不要拿 `all:MiniMax` 的命中数当官方论文数。
- 不要用"编号 200"或作者数推断官方性。
- 不要用 HF 默认列表端点取时间字段。
- 不要把 ModelScope 组织页 200 / 约 4767 B 外壳当组织存在证据。
- 不要把单条阴性（例如只有 arXiv 0 条）写成"查无"。
- 不要把**产品名**当 API model id 去官方模型列表 / 价格页搜。
- 不要只抓 `/models/<slug>` 详情页就断言"官方没提某竞品"（新闻页 / 博客必抓，见第 10 条）。
- 不要把 502 / 404 / 401 这类**抓取或鉴权失败**写成"0 条命中 / 查无"。
- 不要用 HF 仓 `createdAt` 当发布日。
- 不要只看 HTTP 200 就认 `/raw/` 拿到的二进制（先验 magic，LFS 指针也是 200）。
- 不要把二手稿的"超越 X"当厂商口径（回官方原文核方向）。

## 验收标准

1. 每条"是真链接"的结论都附响应体字节数（且 > 10000 B）与假 slug 对照结果。
2. arXiv 候选编号逐个给 abs URL + 作者署名是否含厂商名。
3. HF 条目时间字段来自 `&full=true`；401 明确标注为 not found。
4. ModelScope 结论只来自逐模型 API 的 Code / Downloads / Stars / Architectures。
5. "查无"结论必须三条（官网 404 / 文档列表 0 次 / arXiv 0 条）齐全，缺一条改写为"未检索到"。
6. 判"存在"只需任一跨源一手阳性；判"查无"才要三类全阴（第 19 条），**不得**把"某单一源没查到"升格为查无。
7. "某模型对外提供服务"的结论必须给官方模型列表 / 价格页里的 **API id 原文** + 出现次数（`[regex]::Matches` 计数），不是产品名。
8. 每条竞品对标断言附**官方页原文片段 + 上下文**，二手来源单独标注"二手转述"。
9. 二进制文件证据给 `/resolve/` 的字节数 **+ magic 前几字节**。
10. 所有引用的自报数字都带 harness / 来源口径；发现官方自报内部矛盾时**并列陈述**，不做减法推断。
