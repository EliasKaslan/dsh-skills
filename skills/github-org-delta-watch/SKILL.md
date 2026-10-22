---
name: github-org-delta-watch
description: GitHub 组织增量追踪——基准日之后谁在动：rate_limit 的 Date 头取"今天"、orgs/{org}/repos?sort=pushed 覆盖全组织找活性、pushed_at 冻结即内容冻结、issues 要 created 与 updated 各拉一遍。适用于"组织基准日后有什么新动作 / 谁在动 / 有没有发新版 / 组织调研报告要更新增量 / 这个仓是不是死仓 / 官方那个承诺兑现了吗 / GitHub 403 额度耗尽后怎么继续取证"。不适用：向 GitHub 仓提 PR → 用 `github-pr-flow`；读 AIDD 扫描报告 → 用 `aidd-report-reader`。
whenToUse: 已有一份带基准日的 GitHub 组织/仓库调研报告，要产出基准日之后的增量热点与观察点变化清单时使用；也用于判某仓是否死仓、某个官方承诺是否已兑现。模型看不到本节。
---

# GitHub 组织增量热点追踪（基线 → 今天）

2026-09-28 在 `MiniMax-AI` 组织上真跑通（基线日 2026-09-20，见 `D:\workspace\Minimax\research\h3-delta-watch.md` 与 `research\H3-热点增量简报-2026-09-28.md`）。19 次 API 调用 0 失败，未认证余额 54/60。

## 何时调用

- **触发信号**：手上有某组织的调研报告（如 `MiniMax-AI-组织调研报告-2026H2.md`，基准日 2026-09-20），用户说"基准日之后谁在动 / 哪些观察点变了 / 出个增量简报"；或要判某仓是否死仓、某承诺是否兑现。
- **转交边界**：要向上游仓提/关 PR → 用 `github-pr-flow`；读 aidd.huawei.blue 扫描报告 → 用 `aidd-report-reader`；只做论文精读 + 开源声称核查 → 用 `arxiv-paper-deep-read-and-claim-verification`。
- AI 厂商官方信息源真伪与覆盖面判定 → 用 `ai-vendor-official-source-audit`。
- 外部热度量级（HN points / HF likes） → 用 `external-buzz-magnitude-check`。
- 判某模型在昇腾生态里的适配程度与缺口 → 用 `ascend-model-adaptation-recon`。
- **前置**：能跑 pwsh + 联网；先拿到**基线日**（本地报告 frontmatter/首行，如 `> 调研基准日：2026-09-20`）与**基线结论清单**（哪些观察点要复核）。 ／ **后继**：产出"活跃仓表 + 观察点变/未变表 + 增量热点清单"三节，并逐条给证据 URL。

## 前置检查

```powershell
# 拿"今天"的权威 UTC 时间 + 限流额度（一次调用同时完成两件事）
(Invoke-WebRequest -Uri 'https://api.github.com/rate_limit' -Headers @{'User-Agent'='x'} -UseBasicParsing).Headers['Date']
Get-Date -Format 'yyyy-MM-dd HH:mmzzz'
```

- 验证：本次得到 `Mon, 28 Sep 2026 06:29:48 GMT`，本地 `2026-09-28 14:29+08:00` → UTC 与 +08:00 互证。
- 看余额：同一响应体的 `resources.core.remaining/limit`。未认证 = 60 次/小时；本次 19 次调用后余额 54/60。
- `-Headers @{'User-Agent'='x'}` 是硬要求（GitHub 对无 UA 请求返回 403）。

## 步骤

1. **一次性找"谁在动"**（覆盖全组织，最省额度的入口）：
   ```powershell
   Invoke-RestMethod -Uri 'https://api.github.com/orgs/<ORG>/repos?per_page=100&sort=pushed&direction=desc' -Headers @{'User-Agent'='x'} |
     Where-Object { $_.pushed_at -ge '2026-09-20' } |
     Select-Object name,pushed_at,stargazers_count,forks_count,open_issues_count
   ```
   - 验证：本次 35 仓中仅 4 仓 `pushed_at >= 2026-09-20`（minimax-code 9/28、MiniMax-Provider-Verifier 9/27、MiniMax-Code-MiniApps 9/25、MiniMax-Code-Plugins 9/21）→ 活性全在 Agent 工具链，模型/算子线零动作。

2. **`pushed_at` 冻结 = 内容冻结**（免抓 HTML 的强判据）：单仓调 `https://api.github.com/repos/<O>/<R>`，`pushed_at` 与上次相同即该仓自那时起零提交。
   - 验证：H3 `pushed_at` 停 6 周未变 → 无需再调 `/commits`、`/contents` 确认"稀疏 kernel 有没有加进来"。

3. **全生涯提交数用 Link 头取，不翻页**：
   ```powershell
   Invoke-WebRequest 'https://api.github.com/repos/<O>/<R>/commits?per_page=1' -UseBasicParsing |
     Select-Object -ExpandProperty Headers | Select-Object Link
   ```
   - 验证：读 `Link` 里的 `rel="last"` 页号 = 总提交数，本次 H3 = 42 条。

4. **判"死仓"看最后几条提交的性质**：`/commits?per_page=3` 读 message 前缀与 `commit.verification.verified`。
   - 验证：H3 最后 3 条全是 `Merge pull request #NN from <外部用户>` 且 `verified=true` → 尾部完全由社区贡献，官方已撒手。

5. **观察点核查用"同名词无则无"的清单式端点**：`/releases`、`/tags`、`/branches`、`/pulls?state=open` 各 1 次调用即可判"是否发版 / 是否打标 / 是否回流 main"。
   - 验证：MSA `/releases` = `[]`、`/tags` = `[]`，三分支均未回流 main。

6. **官方没动，查生态是否替它动了**：`/commits?path=<file>` 一次给出该文件的完整时间线。
   ```powershell
   'https://api.github.com/repos/vllm-project/vllm-ascend/commits?path=vllm_ascend/models/minimax_m3/ops/msa_m3_npu.py&per_page=10'
   ```
   - 验证：9/20 启用 → 9/21 **Revert** → 9/23 改可选 → 结论"能跑但没跑稳"。

7. **增量 issue 必须 `created` 与 `updated` 各拉一遍**（只看 `sort=updated` 会被旧帖新评论遮蔽）：
   - `issues?state=all&sort=updated&direction=desc&per_page=30` → 本次最前的 #70/#74 创建于 8/31、9/02，属旧帖被顶。
   - `issues?state=all&sort=created&direction=desc&per_page=30` → 才看到真新增的 9/23 #82、9/25 #83。
   - 提醒：`/issues` 同时返回 issue 和 PR，按 `pull_request` 字段分流后再计数。

## 免额度取证通道（未认证 core 耗尽后）

2026-10-05 对 `vllm-project/vllm` 与 `vllm-project/vllm-ascend` 做 RL×LoRA 侦察时全程实测（共享出口 IP）。下面 1 条讲额度、2~6 条是 0 额度通道。

1. **额度是共享的、比预期更紧**：`rate_limit` 的 `Date` 头同时给出"今天"与额度；本轮共享 IP **16/60 起步，3 次 core 调用即归零**（`git/trees` + `releases` 之后 `commits?path=` 立刻 403 `API rate limit exceeded for <ip>`）⇒ core 只留给"定全局"的两次聚合调用：`git/trees?recursive=1` 定全树、`releases` 定版本列表。
2. **路径提交时间线（主力，0 额度）**：`https://github.com/<O>/<R>/commits/<branch>/<path>.atom` 给该路径完整提交时间线（日期 + commit SHA + 标题）。可抄写法：
   ```powershell
   $x=[xml](Invoke-WebRequest 'https://github.com/<O>/<R>/commits/main/<path>.atom' -UseBasicParsing -Headers @{'User-Agent'='x'}).Content
   $x.feed.entry | ForEach-Object { $_.updated.Substring(0,10) + ' | ' + $_.title }
   ```
   （`link[@rel=alternate]` 即 commit URL。）
3. **tag / release 列表（0 额度）**：`https://github.com/<O>/<R>/releases.atom`、`https://github.com/<O>/<R>/tags.atom`。
4. **发布日期 / 预发布 / "最新"三件事的 oracle（0 额度）**：单条 release 页 HTML 里 `<relative-time … datetime="…">` 是**发布时间**，页面另有 `Pre-release` / `Latest` 字样；`https://github.com/<O>/<R>/releases/latest` 会 **302** 到"最新**非**预发布"的 tag（PS 5.1 取最终 URL：`$r.BaseResponse.ResponseUri.AbsoluteUri`）。⚠️ 两种页头措辞都要兼容：`released this` 与 `tagged this`（否则会把正常 release 页误判成 404）。
5. **单条 issue / PR 的正文与元数据（0 额度）**：抓 `/issues/<n>`、`/pull/<n>` 的 HTML，从**页面嵌入 JSON** 里取 `"state"`、`ClosedEvent.createdAt`、`linkedPullRequests`、`bodyHTML`（分块）；react 后的页面**没有** `comment-body` 类名、**没有** Status 徽章、**没有** `mergedAt` 字段，别按旧 DOM 找。
6. **全树快照（0 额度）**：`https://codeload.github.com/<O>/<R>/tar.gz/refs/heads/main` 直接下 tarball（本轮实测 17.5 MB → 4425 文件 + 845 目录 = 5270 节点），本地做"某字符串在全仓出现几次"的内容级检索。

## 坑与修法

- **第三方包 ≠ 官方兑现**：`https://pypi.org/pypi/h3-sparse-attn/json` 搜到的是第三方 `Occipital-Labs`（0★、8/20 上传后停更）→ 原因：包名极像官方 → 修法：判"官方是否兑现"只认官方仓的 `pushed_at` / `contents`，第三方包仅记作"生态补位"。
- **旧闻 ≠ 增量**：InfoQ" H3 团队 Reddit 回应一切 / Apache-2.0 在考虑"看似最新热点 → 原因：转载 URL 日期段是 `...20260808...`，早于基准日 2026-09-20 → 修法：转载 URL 里的 `YYYYMMDD` 作低成本日期兜底，早于基准日一律归入"旧闻"，不进热点榜。
- **`license` 为 `null` ≠ 无许可证**：MiniMax-H3 用非 SPDX 的 "MiniMax H3 Community License"，GitHub API `license=null` → 原因：自定义许可无 SPDX id → 修法：`null` 时必须回 README 看许可证正文。
- **字段名拼错会静默返回空，不报错**：`stargazers_forks_count`（臆造）返回空 → 原因：PowerShell `Select-Object` 对不存在属性不报错 → 修法：字段名为 `stargazers_count` / `forks_count` / `open_issues_count`；关键数字先 `ConvertFrom-Json` 再显式取字段并做存在性断言。
- **未认证限流 60 次/小时**：先看 `rate_limit` 余额（本次 19 次 / 余额 54）→ 403 时**改走下面的「免额度取证通道（未认证 core 耗尽后）」**；"抓 `commits` 页 HTML 兜底"这条路已被实测证伪（只回导航栏 + `(Content truncated.)`，拿不到提交列表）。
- **别把子代理报告当独立信源**：两个子代理读过同一份本地缓存时，其"交叉核对一致"是**循环引用**，不构成独立验证。
- **纯联网 / 需落盘的任务不要派给只读型子代理**：实测某类子代理无联网工具也无写权限，会静默降级为读本地缓存 → 派发前要求子代理自检工具可用性。
- **`updated` ≠ 发布日期**：实测 `vllm` v0.31.0 的 release 页发布时刻是 `2026-10-05T06:44:55Z`，而同名 atom 条目的 `<updated>` 是 `2026-10-06T06:49:35Z`；`vllm-ascend` 侧受检 3 条两者恰好相同 ⇒ **不是每次都差，必须两条都取**，只取 `updated` 会算错"最新版本 / 最新动作"。
- **`search/issues` 不带 `is:issue`/`is:pr` 直接 422**：`{"message":"Query must include 'is:issue' or 'is:pull-request'"}`。
- **`mcp__github__list_commits` 忽略 `path` 参数**：传不同 `path` 返回同一批 main 提交，单次 130–220 KB 且含 PGP 签名块 ⇒ 别拿它做文件时间线，改用上面第 2 条的 atom（`commits/<branch>/<path>.atom`）。
- **`merged_at=null` + `state=closed` ≠ "没做"**：实测同标题内容可以只以 commit 落入 main ⇒ 以**文件时间线**为准，不要用 PR 元数据反推"未实现"。
- **路径级 0 命中 ≠ 内容级 0 命中**（★本轮最大教训）：实测 `vllm-ascend` 全树 5270 个**路径**里 `mindspeed`/`grpo`/`collective_rpc`/`update_weight` 命中 **0**，但**内容**命中 `grpo`=4、`collective_rpc`=27、`update_weight`=34（如 `grpo@sleep_mode.md:5`、`collective_rpc@upstream_config.yaml:37`）⇒ 判"某能力不存在"必须**路径与内容各搜一遍**。
- **词边界**：`-match '(?i)verl'` 会命中 `fused_sparse_attention_ov``erl``ap`（实测 27 处路径命中**全部**是词内假命中；内容级 2350 命中里 2243 是假命中）⇒ 用 `\bverl\b`，并先数假命中样例。
- **判"某 bug 修没修"要读 `linkedPullRequests`，别只看 label**：实测 issue #39934 的 label 有 `stale`（描述 "Over 90 days of inactivity"），但它是按 `stateReason=COMPLETED` 关闭的，且链着**已合入**的修复 PR `#39935 state=MERGED`（`[Bugfix] Fix level-2 sleep/wake/reload with enable_lora=True`）⇒ "被 `stale` 关掉"不等于"没修"。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `github-org-delta-watch`；要联网核外部来源时再加 `ai-vendor-official-source-audit`。加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\github-org-delta-watch\SKILL.md` 与 `C:\Users\admin\.dsh\skills\ai-vendor-official-source-audit\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。
> 并发成员 ≥2 或子任务 ≥3 时，按 `orchestrating-subagents` §9.1 在本轮 cwd 落 `.dsh-run\<日期>-ledger.md` 台账，收尾清空。

## 不要做什么

- 不要为了"确认今天日期"额外调一次接口——`rate_limit` 的 `Date` 头已同时给出日期与额度。
- 不要用 `/commits` 逐页遍历去数总提交数，`Link` 头的 `rel="last"` 就是答案。
- 不要用抓 HTML 判"某仓是否新增文件"，`pushed_at` 冻结即可判内容冻结。
- 不要把"第三方 PyPI 包存在"写成"官方承诺已交付"。
- 不要只按 `sort=updated` 产出新增 issue 榜。

## 验收标准

1. 有一张"基准日后有 push 的仓"表，字段含 `pushed_at` 与证据 URL，并注明活性集中在哪条产品线。
2. 观察点逐条"变 / 未变"，每条变更有可点开的 API URL 或 release tag。
3. 增量热点清单里**没有**早于基准日的旧闻；第三方包与官方兑现分开表述。
4. 全程 API 调用数可控（单组织一轮 ≈ 15~25 次，未认证额度内），无 403。
