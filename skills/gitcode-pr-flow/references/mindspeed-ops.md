# MindSpeed-Ops 仓专属事实

> 上游 `https://gitcode.com/Ascend/MindSpeed-Ops`（昇腾训练业务自定义算子仓，Apache-2.0）。
> 平台通用流程见本体 `SKILL.md`，本文件只记**该仓专属**的交付件、backport 与常量。

## 常量

- 项目 id `9612429`；fork 仓 id `10648379`；代码门禁流水线 id `dc050eb8a847445c8fe635fb50d1f99d`。
- 里程碑：`MindSpeed 26.3.0` = `849946`、`MindSpeed 26.2.0` = `579831`。
- 门禁阶段比 MindSpeed-Agent 多 `UT_MindSpeed_1~4` 分片。
- 本地产物目录惯例 `D:\workspace\MindSpeed-Ops\...`。

## 8. 新增算子 PR 的附加交付件（docs/zh/ops.md，硬性要求）

- 实现：torch 实现 + NPU 优化实现（+ 原 triton 实现，可选）。
- **UT 精度用例**：覆盖所有支持 dtype/shape；双标杆对齐（CPU 高精度实现 + torch 小算子实现 或 原 triton 实现）；竞品（GPU）上也能跑（昇腾亲和接口优化时可条件跳过，但仓上要有份竞品实现便于竞品测试）。路径惯例 `tests/unit_tests/triton/test_<op>.py`。
- **ATK 测试三件套**（generator + yaml + api），PR 描述中**提供 ATK 测试通过截图**：精度、性能、内存。参考仓内 `tests/atk_tests/` 既有算子。
- **算子文档** `docs/zh/triton/<op>.md`（概述/函数签名/参数表/实现原理/使用示例/性能对比/常见 Shape/注意事项）+ 在 `docs/zh/supported_operators.md` 登记清单。
- pre-commit 全绿（ruff/pylint/bandit/codespell/typos）。
- 参考 PR：#158（feat(triton) 完整交付件样例，含性能表与测试说明）。

## 12. 版本分支回合并（backport：master → 26.1.0 / 26.2.0）

GitCode 与 Gerrit 不同：**版本分支没有独立的合入系统**，把 master 的改动带到版本分支只有两条路——**维护者直接 push 版本分支**，或**向版本分支提 PR**（`base=<版本分支>`，贡献者侧走这条，因为贡献者没有 push 权限）。

**项目惯例证据（决定能不能直推）**：`26.1.0` 上有 4 个**不在 master 里**的提交，全部是维护者 `liu_zhi_xu` 用网页直接提交的 `update: 更新文件 setup.py|pyproject.toml|requirements.txt|README.md`（带 `Signed-off-by`），**不是 PR 合入**；同时也有面向版本分支的 PR 在走（开放的 PR #162 base=26.1.0，贡献者侧的迁移 PR）。**结论：维护者对未保护的版本分支直推是既有做法，不需要提 PR；贡献者侧才走 PR。**

### 12.1 权限探测（先确认自己能不能直推）
```powershell
function Get-GitCodeJson([string]$Url, [string]$Token) {   # 见 §7，PS 会按 Latin-1 解码 UTF-8
    $h = @{}; if ($Token) { $h['PRIVATE-TOKEN'] = $Token }
    $r = Invoke-WebRequest -Uri $Url -Headers $h -UseBasicParsing -Method Get
    return ([System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json)
}
# 分支级：protected / developers_can_push / developers_can_merge / can_push
# can_push = "当前 token 用户能否 push 该分支"，与 protected 一一对应
Get-GitCodeJson 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/branches/master'  $tok
Get-GitCodeJson 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/branches/26.2.0' $tok
# 更权威：协作成员 access_level（10=Guest 20=Reporter 30=Developer 40=Maintainer 50=Owner）
$cs = Get-GitCodeJson 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/collaborators?per_page=200' $tok
$me = $cs | Where-Object { $_.username -eq 'EliasKaslan' }   # → 40 / Maintainer / admin
```
实测（2026-09-24）：`master` protected=true / can_push=**false**；`26.1.0`、`26.2.0` protected=false / can_push=**true**；`EliasKaslan` 在 `Ascend/MindSpeed-Ops` 的 `access_level=40`（Maintainer、permission=admin）。**即：对未保护的版本分支可直推，对 master 仍无合并权限（"用户无当前保护分支的合并权限"只对 master 成立）。**

### 12.2 三步判定"这个版本分支到底缺不缺这一笔"
```powershell
cd <本地克隆>                                    # remote origin = 上游 Ascend/MindSpeed-Ops
git fetch origin '+refs/heads/26.2.0:refs/remotes/origin/26.2.0'   # 步骤1
git merge-base origin/master origin/26.2.0                          # 步骤2：分叉点
git rev-list --count origin/26.2.0..origin/master                   # master 领先几个
git rev-list --count origin/master..origin/26.2.0                   # 版本分支领先几个（=0 即纯落后）
git diff --stat origin/26.2.0 origin/master                         # 步骤3：内容差
```
实测：`26.2.0` tip `46f76f6` 恰好是 master 上 PR #163 的 squash commit `1d1239b` 的**父提交** → 版本分支自身提交数 0、merge-base 就是它的 tip，即 **26.2.0 是 master 的严格祖先**；`git diff --stat origin/26.2.0 origin/master` 正好列出 #163 那 13 个 md 文件、`+113/-92`（PR #163 自己后续又拆过一轮纯格式改动，其语义子集是 13 文件 `+44/-40`；这里是"整条 master 增量"的口径），与 `GET /pulls/163/files` 的文件清单一致。**"缺的就是这一个改动"由此得证。**

### 12.3 合入前先证明"不会多带东西"（关键）
```bash
git merge-tree --write-tree origin/26.2.0 da51074     # da51074 = PR #163 原始分支 head
git rev-parse '1d1239b^{tree}'                        # master 侧同一颗树
```
两边第 1 行输出的 tree OID **完全相同**（实测都是 `9a434b8da6fca82275518ec30c3bf8dcc206024f`），`merge-tree` exit 0 → **合并结果与 master 逐字节一致**，不会带入任何额外提交。校验员忘掉这一步就等于"合并了但没证明合了什么"。

### 12.4 合入（纯 fast-forward → 不需要 PR）
```bash
git push origin refs/remotes/origin/master:refs/heads/26.2.0
# 实测回显：46f76f6..1d1239b  origin/master -> 26.2.0
#           remote: Start Git Hooks Checking [PASSED]        exit 0
```
因为是 FF，**不加 `--force` 也不会覆盖别人的工作**——分支若已被别人推进会直接报 non-fast-forward 而失败，天然安全。
> ⚠️ 这条 push 会**真的推进版本分支**，属于"先确认再执行"的破坏性操作：动手前必须先把 12.2/12.3 的证据摆给用户看。

**回读校验（三件套，缺一不可）**：
```powershell
Get-GitCodeJson 'https://api.gitcode.com/api/v5/repos/Ascend/MindSpeed-Ops/branches/26.2.0' $tok   # commit.id = 1d1239b4...
```
```bash
git fetch origin '+refs/heads/26.2.0:refs/remotes/origin/26.2.0'
git rev-parse 'origin/26.2.0^{tree}' 'origin/master^{tree}'   # 两行相同
git rev-list --count origin/26.2.0..origin/master             # = 0
```

**CI/PR 视角**：直推 FF **没有待合入的 PR，所以不需要发 `compile`**（#163 的 CI 早就在 master 上跑绿了）；本次也未创建 PR、未评论。只有走 PR 路线（`base=26.1.0` 那种）才需要 §5/§7 那套 `compile`。

### 12.5 已直推过的版本分支要回退：叠加回退提交（FF），不要 force-push 改写共享历史

**场景（实测）**：一笔纯文档改动**同时**落在 master 的 PR 分支和 `26.2.0`（直推 FF）上；随后需求变更要把这份改动**回退**（删掉新建的英文文件、还原目录结构清单、只保留中文那一节）。

**做法**：`26.2.0` 上先有直推提交 `fb093500`（新增英文文件），回退时**没有** force-push，而是基于它新增一个提交 `05a911c`（删文件 + 还原清单），再推上去：
```bash
git push origin <branch>:refs/heads/26.2.0
# 实测回显：fb09350..05a911c   exit 0（纯 FF，不需要 --force）
```

**判据（哪一侧可以改写历史）**：

| 目标 | 可否改写历史 | 理由 |
|---|---|---|
| master 侧 **PR 的特性分支** | 可以 `amend` + `--force-with-lease` | PR 未合入、无评审标签时无副作用；代价是摘 `lgtm` / `approved` / `ci-pipeline-passed`，并需补发 `compile`（本体 §9「强推的代价」） |
| 已在**共享版本分支**上直推过的提交 | **不要改写历史**，改为叠加一个回退提交（FF） | 版本分支是共享的，force-push 会让已 fetch 的人分叉；FF 不覆盖别人的工作（分支被别人推进会直接 non-fast-forward 失败） |

**旁证（这不是特例）**：`26.2.0` 上本来就有修正链式提交 `f178776 → 9b1f12d → 72d34b8`（同一份 SECURITYNOTE 公网地址声明被连续收窄两次）——该分支的既有做法就是**叠加修正提交**，不是改写历史。

**回退后回读（与 12.4 同口径）**：`git fetch origin '+refs/heads/26.2.0:refs/remotes/origin/26.2.0'` + `git rev-parse 'origin/26.2.0^{tree}'`；直推 FF 后**没有待合入的 PR，不需要发 `compile`**。

**未验证的观察**：`26.1.0` 与 master 在那 13 个文件上 "13 of 13 differ"，但 26.1.0 是**已分叉**的旧版本分支（另有 4 个自有提交），差异很可能来自旧版文档内容本身。**是否要给 26.1.0 也回合并 #163 尚未核实**，需要逐文件看它是否还停在 #163 之前的同名内容，不能照搬 26.2.0 的结论。
