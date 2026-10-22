---
name: ascend-model-adaptation-recon
description: 判定某模型在昇腾/vllm-ascend 生态里的适配程度（实测 MiniMax-H3）——一次全树 API 判「主仓有无代码」、追 import 链定位跨仓分工（vllm-ascend 基座 ↔ vllm-omni NPU 平台层）、查镜像与启动模式、硬件能力矩阵、未闭合缺口，并给「媒体通稿 ≠ 已适配」的存在性反证。适用于"某模型在昇腾/vllm-ascend 侧适配到什么程度 / H3 在昇腾上能不能跑 / 该用哪个镜像 / vllm-ascend 主仓有没有这个模型的代码 / 适配缺口在哪 / 昇腾 Day-0 适配是真的吗"。不适用：要装或跑 vllm-ascend → 用 `vllm-ascend-source-install` / `ascend-vllm-serve`；只做组织增量 → 用 `github-org-delta-watch`。
whenToUse: 要对某个模型（尤其国产/新发模型）出一份"主仓有无代码 + 跨仓分工 + 硬件能力矩阵 + 未闭合缺口"四段结论时用；本次实测对象 MiniMax-H3（2026-09-28）。模型看不到本节。
---

# 模型在昇腾生态的适配程度取证（vllm-ascend ↔ vllm-omni）

实测：Windows + pwsh + DSH，2026-09-28，对象 MiniMax-H3（33B 全模态视频模型，非 LLM）。产出范本 `D:\workspace\Minimax\research\vllm-ascend-MiniMax-H3-适配总结-2026-09-28.md`（189 行，八节）。**核心发现：适配主战场可能不在 vllm-ascend 主仓**——H3 在 `vllm-project/vllm-omni` 的 NPU 平台层，vllm-ascend 只被当 worker 基座复用。

## 何时调用

- **触发信号**：用户问"X 模型在昇腾上适配到什么程度 / 能不能跑 / 该用哪个镜像 / 主仓有没有代码 / 缺口在哪"；或看到"某厂商 Day-0 适配昇腾"的通稿要工程核实。
- **转交边界**：装/编译/跑 vllm-ascend → `vllm-ascend-source-install`、`ascend-vllm-serve`；组织级增量追踪 → `github-org-delta-watch`；上游 docs 缺口审计 → `upstream-docs-refresh-audit`；要判某能力的 **e2e CI 覆盖**（PR 套件 / nightly / weekly 三条通道，estimated_times 登记门禁）→ `vllm-ascend-e2e-ci-wiring`。
- **前置**：pwsh + 联网 + 未认证 GitHub 额度（60 次/h）。 ／ **后继**：四段结论落盘后，按"缺口清单"决定是否复核 issue/PR 进展。

## 前置检查

```powershell
$H=@{'User-Agent'='x'}   # 硬要求：无 UA 访问 api.github.com = 403
$rl=Invoke-RestMethod 'https://api.github.com/rate_limit' -Headers $H
$rl.resources.core | Select-Object limit,remaining   # 未认证 60/h；本轮一度只剩 12
(Invoke-WebRequest 'https://api.github.com/rate_limit' -Headers $H -UseBasicParsing).Headers['Date']  # 同时拿到"今天"
```
- 验证：本轮得 `Date: Mon, 28 Sep 2026 06:29:48 GMT`，与本地 `Get-Date -Format 'yyyy-MM-dd HH:mmzzz'` 互证。

## 步骤

1. **主仓"有无代码"用一次全树定论（最省额度）**——**别裸搜 `h3`**：
   ```powershell
   $t=(Invoke-RestMethod 'https://api.github.com/repos/vllm-project/vllm-ascend/git/trees/main?recursive=1' -Headers $H).tree
   $t.Count                                                    # 本轮 5169
   $t.path -match '(?i)minimax' | Where-Object { $_ }          # 本轮只剩 M2/M2.5/M2.7/M3
   (Invoke-RestMethod 'https://api.github.com/repos/vllm-project/vllm-ascend/contents/vllm_ascend/models' -Headers $H).name
   $t.path | Where-Object { $_ -match '(?i)minimax.{0,3}h3' }  # 本轮 0 命中
   ```
   - 验证：`contents/vllm_ascend/models` 只有 `minimax_m3`；`minimax.{0,3}h3` 0 命中 → "主仓无 H3 代码"成立。
   - ⚠ `-match '(?i)h3'` 会被 `arch35`（Ascend 架构目录名）淹没，还有 `H310`、sha512、Mermaid 节点 `H3["CANN…"]` → 一律用 `minimax.{0,3}h3` 或 `minimax`。URL 必须加引号（`?` 会被 pwsh 当参数）。`-match` 对数组返回的是**匹配元素**，不是布尔值。
2. **换仓找真适配点**（同一方法，换成 `vllm-project/vllm-omni`）：
   ```powershell
   $t2=(Invoke-RestMethod 'https://api.github.com/repos/vllm-project/vllm-omni/git/trees/main?recursive=1' -Headers $H).tree
   $t2.Count                                                                # 本轮 5017
   $t2.path | Where-Object { $_ -match '(?i)(platforms/npu.*minimax|recipes/MiniMaxAI|models/minimax_h3|deploy/minimax_h3)' }
   ```
   - 验证：命中 `vllm_omni/platforms/npu/models/minimax_h3.py`、`diffusion/models/minimax_h3/*`、`model_executor/models/minimax_h3/*`、recipes `MiniMax-H3-NPU.md` / `-950PR.md`、`deploy/minimax_h3_disaggregated*.yaml`、`tools/minimax_h3/build_adaln_cache.py`、`tests/**/minimax_h3/`（40+ 单测 + e2e）。
3. **跨仓分工靠 import 链，不靠猜**：读失败 issue 的栈回溯最省事。
   ```powershell
   (Invoke-RestMethod 'https://api.github.com/repos/vllm-project/vllm-ascend/issues/17318' -Headers $H).body
   ```
   - 验证：栈回溯 `vllm_omni/platforms/npu/worker/base.py → from vllm_ascend.worker.worker import NPUWorker` → 结论"vllm-ascend 提供 `NPUWorker` 基座，omni 的 NPU 平台层做 H3 专属适配"。
4. **H3 的全部 GitHub 条目用 search 枚举，才知道"只有 2 条"**：
   ```powershell
   (Invoke-RestMethod 'https://api.github.com/search/issues?q=repo:vllm-project/vllm-ascend+is:issue+minimax+H3' -Headers $H).total_count
   ```
   - 验证：本轮 = 2（PR #13596 + issue #14272）。**search 查询必须带 `is:issue` 或 `is:pr`**，否则本轮真收到 422（见坑）。
5. **PR 是否真的合入，看 `merged_at` + `state` 两个字段**：
   ```powershell
   $pr=Invoke-RestMethod 'https://api.github.com/repos/vllm-project/vllm-ascend/pulls/13596' -Headers $H
   $pr | Select-Object state,merged,merged_at,merge_commit_sha,created_at,updated_at
   $pr.changed_files; $pr.files_url   # /pulls/N/files 看改了什么
   ```
   - 验证：本轮 `state=open` / `merged_at=null` / `merge_commit_sha=6fb7…` → **有 `merge_commit_sha` 也代表没合入**（那是 test-merge 结果）；主体是纯文档 4 文件（`docs/source/tutorials/models/MiniMax-H3.md` 314 行 + `mkdocs.yml` + `docs/hooks/nav_titles.py` + `docs/source/user_guide/support_matrix/supported_models.md`）。
6. **镜像/启动口径从 PR 正文与 recipe 抄，不从媒体抄**：本轮 `quay.io/ascend/vllm-omni:v0.29.0`(A2) / `:v0.29.0-a3`(A3) / `:v0.29.0-a5`(950PR/950DT)，启动 `vllm serve ... --omni`，只暴露 `/v1/videos/sync`（无 chat/completions），关键 env `VLLM_OMNI_VIDEO_SYNC_TIMEOUT`；**不用 vllm-ascend 镜像**。
7. **硬件能力矩阵逐行给依据**（每条状态列必须挂到某 PR/issue/recipe）：
   | 硬件 | 状态 | 依据 |
   |---|---|---|
   | A3 64G 8 卡 | ✅ 真机出片（720p/8s/60 步含音轨） | PR #13596 自述 |
   | A2 64G | ✅ 可拉起出片 | issue #14272 |
   | A2 32G | ❌ 拉不起来，open 无 assignee | issue #14272 |
   | 950PR/950DT 4×128GB | ✅ 官方 recipe（无损/有损两套） | `MiniMax-H3-NPU-950PR.md` |
   | A3 8 物理卡/16 die/32GB | 🚧 未验收，5 项未闭合 | vllm-omni issue #8228 |
8. **"Day-0 适配"用存在性反证，不逐家核实**（最省事）：
   ```powershell
   try { Invoke-RestMethod 'https://huggingface.co/api/models/FlagRelease/MiniMax-H3-ascend-FlagOS' -Headers $H | Select-Object id,likes,downloads } catch { $_.Exception.Response.StatusCode.value__ }
   Invoke-RestMethod 'https://huggingface.co/api/models/FlagRelease/MiniMax-M3-ascend-FlagOS' -Headers $H | Select-Object id,likes,downloads
   ```
   - 验证：H3 版 **404**（改造前无认证时也可能回 **401**）；同族 M3 版**存在**（likes 0 / downloads 80）→ 反证成立。

## 坑与修法

- **`h3` 裸搜索满是假命中**：`arch35`、`H310`、sha512、Mermaid 节点 `H3["CANN…"]` → 用 `minimax.{0,3}h3` / `minimax` 过滤；`rg` 版正则会报 `look-around, including look-ahead and look-behind, is not supported`（`(?<![a-z0-9])h3` 被拒）→ 改 `\bH3\b`。
- **GitHub search 直接 422**：`repo:vllm-project/vllm-ascend minimax H3` 不带 `is:issue`/`is:pr` → 修法：查询串补上 `is:issue` 或 `is:pr`（服务端未回可读的拒绝原因，只能靠加限定符消解）。
- **`github.search_code` 这类 MCP 搜索单次结果约 500 KB**，两次就把上下文吃掉（本轮实测）→ 主仓存在性判定**一律改用**一次全树 REST + 本地过滤（步骤 1 那条），1 次调用、输出几十行。
- **新模型代码不在 `vllm/model_executor/models/` 了**：vLLM 0.27+ 已改为分层目录 `vllm/models/<model>/{common,nvidia,amd}/`。本轮实测 `vllm/model_executor/models/` 下**已无** `kimi_k3.py`（只剩 kimi_audio / kimi_k25 / kimi_vl）⇒ **按旧路径判"上游无代码"会误判**。修法：全树过滤时同时匹配 `model_executor/models/<name>` 与 `models/<name>/`。
- **上游与插件两层注册表对勘**：光看主仓文件树不够，还要同时读 `vllm/model_executor/models/registry.py` 与 `vllm_ascend/models/__init__.py`，**两处都命中才算"上游有 + 昇腾有"**（本轮 K3 两处都命中）。
- **API 额度分两档**：`raw.githubusercontent.com` **不占** GitHub API 额度，`api.github.com` 未认证 **60/h**（本轮开工 59 → 收工 38）⇒ 抓正文走 raw 并 **pin SHA**，只有 tree/branch 才用 API；一次 `rate_limit` 调用同时拿剩余额度与 `Date`（见前置检查）。
- **无 UA 头访问 `api.github.com` 返回 403**；未认证 60/h（本轮一度只剩 12）→ 先查 `/rate_limit`，并用它的 `Date` 头同时拿"今天"，不要为问日期多花一次调用。
- **`merged_at=null` 但 `merge_commit_sha` 非空 ≠ 已合入**（那是 test-merge）→ 必须 `state` 与 `merged_at` 一起看。
- **`pushed_at` 冻结 ≠ 仓无活动**（vllm-ascend 9/28 仍在 push）；反过来 H3 官方仓 8/15 后冻结是"发布即冻结"的公告型仓设计，**不能**读成"官方停摆"。
- **`license=null` ≠ 无许可证**：非 SPDX 自定义许可（MiniMax H3 Community License）在 GitHub API 就是 `null` → 回 README/模型卡看许可证正文。
- **只有"媒体通稿 + 无代码链接"时不能写"已适配"**：②级证据只能记作"媒体口径"；第三方包/第三方仓（如 `BHUHD/minixmax-h3`）不等于官方兑现。
- **别把同族成熟模型的成熟度记到目标模型头上**：vllm-ascend 的 MiniMax-M3 教程、`vllm_ascend/models/minimax_m3/ops/msa_m3_npu.py`、nightly 配置一个都不能套给 H3。
- **派子代理做联网取证会静默降级**：本轮 3 个子代理全部无联网/无写盘工具，自报工具缺失后转为读本地缓存 → 联网取证由主 Agent 亲自做，或派发时显式要求它先自检工具清单。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `ascend-model-adaptation-recon`；若该子任务要联网核官方来源，再加 `ai-vendor-official-source-audit`；加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\<name>\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。
> 并发成员 ≥2 或子任务 ≥3 时，按 `orchestrating-subagents` §9.1 在本轮 cwd 落 `.dsh-run\<日期>-ledger.md` 台账，收尾清空。

- **未验证**：本地 `git -C <repo_main> grep -E 'minimax.{0,3}h3'` 这类本地克隆兜底命令（本轮仅在缓存稿中引用，主 Agent 未在本 session 亲跑）；需本地克隆时按 `upstream-docs-refresh-audit` 的只读 worktree 流程自建副本再跑。

## 不要做什么

- 不要在 `(?i)h3` 的结果上判"有 H3 代码"或"无 H3 代码"——假命中会让两个方向都判错。
- 不要只查主仓就下"昇腾没适配"的结论：先查 `vllm-omni`（omni 生成类模型的主战场常在平台层）。
- 不要用 GitHub 网页 HTML 判仓内容（JS 渲染；REST API 更省事且可复现）。
- 不要把"recipe 存在 / 镜像 tag 存在"写成"该硬件已验收"——recipe 是配置，验收要看真机验证记录与 issue 勾选框。
- 不要把 `merge_commit_sha` 非空当合入信号；不要把 `pushed_at` 冻结当"仓已死"。
- 不要为"确认今天日期"额外调接口。

## 验收标准

1. 四段结论齐备：①主仓有无代码（带全树计数 + 过滤命令 + 命中清单）②跨仓分工（带 import 链或栈回溯原文）③硬件×能力矩阵（每行挂 PR/issue/recipe）④未闭合缺口（带 issue 号与勾选状态）。
2. 每条否定结论都有排除性证据（`contents/*` 清单、`minimax.{0,3}h3` 0 命中、search `total_count`），不是"我没搜到"。
3. 媒体口径与一手证据分表；第三方仓/包与官方兑现分开表述；404/401 反证注明认证状态。
4. 缺口清单每项可执行（合入状态、assignee 有无、未完成勾选框数），并显式区分同族模型的成熟资产。

## 可复用片段（本轮真跑过）

```powershell
$H=@{'User-Agent'='x'}
# ① 全树过滤（换 <ORG>/<REPO> 即可复用；URL 必须加引号）
$t=(Invoke-RestMethod "https://api.github.com/repos/<ORG>/<REPO>/git/trees/main?recursive=1" -Headers $H).tree
$t.Count; $t.path | Where-Object { $_ -match '(?i)minimax.{0,3}h3' }
# ② 单目录内容清单（判"主仓有无该模型目录"）
(Invoke-RestMethod "https://api.github.com/repos/<ORG>/<REPO>/contents/<dir>" -Headers $H).name
# ③ PR 真实状态
$pr=Invoke-RestMethod "https://api.github.com/repos/<ORG>/<REPO>/pulls/<N>" -Headers $H; $pr|Select-Object state,merged_at,merge_commit_sha
# ④ search 必须带类型限定
Invoke-RestMethod "https://api.github.com/search/issues?q=repo:<ORG>/<REPO>+is:issue+<model>" -Headers $H | Select-Object total_count
```
