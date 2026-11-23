---
name: github-org-delta-watch
description: "GitHub组织与发行差集入口，按既有基线追踪仓库、PR、commit和release变化。"
whenToUse: "已有GitHub组织/仓库基线，需要梳理后续commit、PR、release与观察点变化。"
---

# GitHub 组织与发行差集

按 [研究增量与主题周报](../lora-weekly-report/SKILL.md) 恢复组织/仓库范围、基线日期及完整 commit SHA，分页读取仓库、PR、release 与 compare。pushed_at 只召回线索，内容差异以目标分支与实际 diff 为证；注意 compare 截断和预发布。

分别报告已合入、已发版、准备中和未覆盖项。签名 verified、少量提交或沉寂不能单独判定维护者身份或死仓；不因旧承诺推断下一版必带。保留来源和采样时间，报告生成不自动发信或设置周期。

## 何时调用

**触发**：用户问"某组织/某仓最近两周有哪些新进展""有没有新提交、新 PR、发版""增量报告更新一版"；或 `research/` 里已有旧增量报告要出下一期。
**前置**：先拿到**基线**（上一份报告的窗口终点 + commit SHA）。没有基线先定基线，否则"增量"无从比较。
**不适用**：只查某个 PR 是否合入 → 直接看 `merged_at`；要写成周报叙述 → 转 [lora-weekly-report](../lora-weekly-report/SKILL.md)；要沉淀本轮经验 → `sedimenting-skills`。
**后继**：报告落盘 `research/<主题>-<窗口终点>.md`，关键数字复验一遍，再按"下个窗口观察点"续跑。

## 跨组织 fork 与统计口径（踩坑）

**fork 盲区**：目标组织的开发线可能已搬到**另一个组织的 fork**，只看本组织 `orgs/<org>/repos` 会漏。本次 `MiniMax-AI/MSA` 之外，`vllm-project/MSA` 挂着活跃 `dev` 与独有 `feature/q8kv4-*` 分支。排查顺序：

```powershell
git ls-remote --heads https://github.com/<other-org>/<repo>.git      # 探存在（不计 API 配额）
git -C <clone> show-ref refs/heads/main                             # 与上游 main 同 sha ⇒ 同血脉 fork
git -C <clone> merge-base origin/dev upstream/nv_dev                # =初始提交 ⇒ 各自独立演化
git -C <clone> rev-list --count upstream/nv_dev..origin/dev         # 两侧分叉规模
git -C <clone> for-each-ref --sort=-committerdate refs/remotes --format='%(committerdate:short)|%(refname:short)|%(authorname)|%(subject)'
```

**PR 号跨仓不同步**：fork 侧编号与上游错位（本次约 7，vllm `pull/26` = 上游 `pr/19`）。跨仓引用 PR 必须带仓名，否则追错对象。

**引用 SHA 会张冠李戴**：PR 正文与代码注释里的来源 SHA 一律实测，别照抄。本次 `#32` 注释的 `51f4f5c` 实为 "paired Q tiles (#48)" 那个 PR，**不含**所引 topk 文件；正确来源是另一 SHA。

**统计口径**：`git diff --shortstat A..B` 是**净**值，**不等于**相邻两提交 `--stat` 之和（后一提交会改写前者新增的行；本次 2133/212 vs 2128/207）。报告规模用净 diff，逐提交规模单独列。

**fetch"无输出"不等于失败**：`git rev-parse refs/remotes/origin/<br>` 与 `git -C <p> ls-remote origin refs/heads/<br>` 双向核对，确认是真 no-op。注意 `git ls-remote <本地路径>` 读的是本地 refs，不是 GitHub（会给出假 MISMATCH），必须带 remote 名。

**`pushed_at` 假活跃实证**：某仓 `pushed_at` 落在窗口内，但默认分支与全部 88 个远端分支 tip 都停在更早日期（推送来自已删分支）。必须拉全 `refs/heads/*` 按 committerdate 核，不能只看 `pushed_at` 或 `log -1`。

**通信/算子类检索防子串误报**：裸 `comm` 会命中 `common/`、`combine.py`；用完整词 `nccl|allreduce|all_reduce|all2all|all_to_all|nvls|multimem|dsmem|expert_parallel`。`dispatch` 必须抽查命中行——Go/TS 任务分发与 EP 派发同名不同义。大小写不敏感检索才能抓到 `NVLS`（`git grep -E` 默认区分大小写）。

## 深读已合入提交：返工与口径判定

**先判"合入是不是新工作"**：本地 `refs/pull/N/head` 常常是**旧 draft 快照**。`git diff --stat <draft-ref> <squash-sha>` 为空 ⇒ 合入只是 rebase，PR 正文里的性能数字其实是 draft 期测量。要拿最新 head 就另存成 `pr/N-final`，**别覆盖 draft 基线**（draft 本身有对照价值）。

**跨 base diff 会混入兄弟 PR**：堆叠 PR 用 `git diff <sha>^..<sha>` 只看自身 change-set；用 `base..head` 会把上一个 PR 的改动算进来，得出假规模。

**规模一律看 `--numstat`**：`--stat` 里 "+379" 是**变更行数**（增+删），不是净增；另外两个相邻提交的逐提交统计之和 **≠** 净 diff（后者会改写前者新增的行）。

**性能降幅必须核对照基线**：常见 "−66%" 是对**另一个输出类型的旧路径**，同输出口径可能只有 −57%。引用时把降幅、硬件、batch/Q/H/seqlen 一起带上，缺任一项就标 `未验证：`。

**正文与注释里的来源 SHA 要实测**：`git cat-file -t <sha>` 返回 `fatal: Not a valid object name` ⇒ 该承诺无法验证（跨组织 fork 的 head 常常不在本仓）。别照抄 PR 正文的 provenance。

**同名参数跨路径语义可能不同**（同一 `blocks_per_tile` 在 prefill/decode 策略不一致），别把一侧结论套到另一侧。

**Windows PowerShell 读长 diff**：`git show` 长输出会被渲染成红字且**被截断**（实测 537 行只回前半），容易误判"只改了两处"。先落盘再按 `^@@` hunk 头逐段读；落盘别用 `Out-File -Encoding utf8`（Windows PowerShell 5.1 会写 BOM，首行被污染），用 `[System.IO.File]::WriteAllText()` 或 Python `io.open(..., encoding='utf-8', newline='')`。

## 提交性质与分支归属的判定

**先判"这是不是 PR"，再谈它在哪个仓。** `git show -s --format='%P' <sha>` 看父提交个数：**单父 = 直接推送**，不可能是 PR 合入；再用 `git log --merges` 把全仓合并历史列出来交叉验证。别因为提交标题带 `(#123)`、或话题与某个 PR 吻合，就假定它是 PR（实测踩过：某次"公开后又下架"的两个提交都是单父直推，全仓 merge 列表里根本没有它们，用户按 PR 理解就会问错方向）。

**判是否进过主干**：`git merge-base --is-ancestor <sha> origin/<branch>; $LASTEXITCODE`（0=是祖先）。活跃分支上能看到 ≠ 进过默认分支，对外"发过没有"要按主干判。

**判"回退"的性质**：全仓找不到 `Revert "..."` 提交，就不是 revert，只是普通删除提交；删它的理由可能只写在 commit 标题里，正文为空——查 `%b` 为空时别当成信息缺失，标题就是全部说明。

**复查第三方仓"现在"状态不耗 API 配额**：直接拉固定 raw 路径（README、`server_args.py` 之类）看**状态码**并 grep 关键词，比 REST 便宜、且能证明"当下"；REST 配额留给必须枚举的场景。仓可能同名不同义（如某组织下的小写 `vllm` 只是 fork），先确认血缘再用它的内容下结论。

**扫生态方向**：`git ls-remote --heads <url>` 后按关键词过滤分支名（仓可能有上千个分支，用 `Select-String` 过滤别全打印）。这能看出某个概念是否已扩散到**别的模型/别的硬件**——扩散了但自己那条线没有新分支，说明该线在收缩。
