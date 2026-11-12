---
name: pr-change-equivalence-audit
description: 审计「这个 PR 是否只是等价改写、功能/精度/性能是否不变」——先锁 diff 与 dtype 链，再按 IEEE 穷举 ±0/NaN/FTZ，证明有效区逐位等价与掩码区差异，最后给出「代码可证 / PR 自述 / 未验证」三级证据表。适用于"这个PR改前后功能一样吗 / 精度和性能有没有变化 / 是不是纯重构 / 掩码改成乘法安全吗 / 这个bugfix有没有副作用 / PR描述说的无影响能信吗"。不适用：审第三方漏洞扫描报告 → 用 `vuln-scan-report-verification`；向 GitCode 提 PR 或判门禁 → 用 `gitcode-pr-flow`。
disable-model-invocation: true
warm-triggers: 这个 PR 是不是等价改写 / 精度性能没变吧
warm-reason: 低频审计方法论
---

# PR 变更等价性审计（功能 / 精度 / 性能）

**核心纪律：把"没有变化"拆成四个层次分别回答，不要给一句总判。**
PR 作者（或机器人摘要）说"语义等价、精度性能无影响"时，四层里通常只有第 1 层完全成立。

## 何时调用

- 用户给一个 PR 链接，问"改前改后功能/精度/性能是否不变、有没有副作用、是不是纯重构"。
- 要审一个 workaround/fix 是否只是规避、有没有改变数值语义。
- 要判断 PR 描述里的"numerically identical / no user-facing change / perf unaffected"能不能信。

不适用：要提 PR / 看门禁标签 → `gitcode-pr-flow`；要核漏洞报告 → `vuln-scan-report-verification`。

## 第 0 步：把证据锁死（先做，别先读 PR 描述）

1. 取 diff 与两个版本源码（GitCode 匿名 API 可用）：
   - `GET https://api.gitcode.com/api/v5/repos/<owner>/<repo>/pulls/<n>`（正文）
   - `.../pulls/<n>/files`（patch，含 base/head blob）
   - `.../pulls/<n>/commits`（head 与 parent sha）
   - `.../pulls/<n>/comments?per_page=100`（评审与机器人摘要）
2. 用 `raw.gitcode.com/<owner>/<repo>/raw/<sha>/<path>` 下载 **head 与 parent 两版全文**，本地 `difflib` 对拍，确认 patch 里没有 API 没显示的东西。
3. 逐行定位改动，记录 `head:line` 与 `base:line`；**行号会漂移，引用时带源码片段**。
4. 检查 PR 描述与机器人摘要是否互相矛盾（实测常见：作者自认"IR 未重新 dump"，机器人摘要却写"计数已降为 0"）。

## 第 1 步：四层判定

| 层 | 判据 | 常见结论 |
| --- | --- | --- |
| ① 契约层 | 签名/参数/dtype/shape/返回顺序/文档 | 通常真不变 |
| ② 有效区（mask=1） | dtype 提升链 + 乘 1.0 精确性 | 通常 **bit 级相同** |
| ③ 掩码区（mask=0） | `where(x,0)` vs `x*0` | **符号零 / NaN 差异** |
| ④ 极端值 | Inf/NaN/次正规/FTZ | 失效模式可能升级 |

### 掩码改写（`where(mask,x,0)` → `x*mask`）的固定检查表

| 掩码位的 x | where | x*0.0 |
| --- | --- | --- |
| 有限正 / +0 | +0.0 | +0.0 |
| 有限负 / -0 | +0.0 | **-0.0** |
| ±Inf | +0.0 | **NaN** |
| NaN | +0.0 | NaN |

- `mask.to(tl.float32)` 若是 `i1→f32`，要追问：MLIR/LLVM 存在 `uitofp i1 → select(1.0,0.0)` 与反向规范化 → **可能被折回 select（vsel）**，workaround 失效。源码层不可证，必须 dump IR。
- 用 `dtype` 链证明"没有多一次舍入"：`acc(fp32) * beta(fp16)` 提升到 fp32；store 目标也是 fp32 时无二次舍入。
- 零符号是否被下游吸收，要**逐跳证明**：`+0.0 + (-0.0) = +0.0`、`(-0.0)+(-0.0) = -0.0`，累加器初值通常是 `+0.0` → 有效区不被污染。但 NaN 不会被吸收：`NaN*0 = NaN`，`NaN + 0 = NaN`，一个 masked lane 的 Inf 可经 matmul 扩散到整个有效区（`NaN·A` 即使 `A=0` 仍是 NaN）。
- 可达性要算物理范围：fp16 最大 65504，`65504² × V` 仍远小于 fp32 上限；所以"fp16 输入 + fp32 累加"不可能溢出 → NaN 差异只有用户传非有限值或 `exp2` 溢出才可达。

## 第 2 步：精度口径必须分开说

- **vs 参考实现**（PR 最常给的）：只证明"改后达标"，**不证明"改前=改后"**。
- **vs 旧实现**（真正需要的）：同一输入跑 base/head，给 `max|Δ|` 与逐位差异；按 mask 拆成有效区/掩码区分别报。
- **bitwise**：`np.array_equal` / `allclose` / `assert_allclose(atol=0,rtol=0)` **都会把 -0.0 判等**；只有 `view(int32)`、`signbit`、位模式能区分。别拿 allclose 通过就说"bit 级一致"。
- 检查测试是否真的覆盖：`grep -n "@pytest.mark.skip"`；若精度用例被 skip，`4 passed 6 skipped` 与本次缺陷无关。
- 参考实现若仍用 `torch.where`，它产生 `+0.0`，与被改 kernel 的 `-0.0` 天然不同 → bitwise 断言必然红，但 allclose 永远绿。

## 第 3 步：性能只能说"有证据/无证据"

- 先搜证据：PR 正文+全部评论里 `耗时|性能|msprof|benchmark|latency|throughput|us|ms`；仓库 ATK 用例里的 `perf:` 字段（`not_key` = 不设性能门限）；CI workflow 里有无 perf job。
- **没有数据就不能写"性能不变"**；结构性分析（多一次 mul、少一次 vsel、多一块 UB）只能给方向，不能给结论。
- 崩溃修复类 PR 对"改前崩"的形状**不存在性能基线**（改前跑不完），只能报改后绝对值；A/B 要放到改前能跑的形状上。
- 最小可信方案：同 die、同 CANN/torch_npu/triton；base/head 各一 worktree；ATK `--task performance_device --bm_file <基线.xlsx>`；`msprof` 取 per-kernel `Task Duration(us)`；丢首 10 次、≥100 次取 median+p90、A/B 交错、预注册判据（median |Δ| ≤ 3% 且 CI 上界 < 5%）。

## 第 4 步：输出三级证据表

| 声称 | 证据 | 等级 |
| --- | --- | --- |
| 签名/返回不变 | diff | 代码可证 |
| 有效区数值不变 | dtype 链 + IEEE | 代码可证（可加 A/B 实测） |
| 掩码区 ±0 / NaN | IEEE | 代码可证 |
| 40/40、rms x | PR 自述 | 自述，未复现 |
| IR vsel 计数 | 机器人摘要 vs 作者自述 | 可能矛盾，未验证 |
| 性能不变 | 无 | 无证据 |

结论句式：**"契约与有效区语义不变；掩码区有符号零差异、极端输入下 NaN 语义不同；崩溃路径行为改变；精度缺 A/B；性能无证据。"**

## 坑

- `tl.where` 的谓词若已被 `tl.load(..., boundary_check=...)` 补零，或被 `BK=BDA` 之类常量证明恒真 → 这些 where 是 **语义 no-op**，不改它们不是遗漏；别把"其余 where 未同步改"当问题。
- 判断"哪些 where 会 emit vsel"：只有**非冗余**的掩码才会保留成 select；no-op 会被编译器折掉。
- numpy/BLAS 与 Triton 累加顺序不同，`max|Δ|=0` 是本地模拟结论，**"绝对 bit 相等"仍要在 NPU 上用同输入跑 base/head**。
- Ascend VEC 的 FTZ/DAZ 行为源码不可判定：若开 FTZ，有效区次正规会被乘 0 冲掉，而 select 原样透传。
- 固定触发条件别照抄 PR：实测存在"同样是 32 块却不崩"的反例（BT=64），"块数 > AICore 数"往往只是必要不充分条件。

## 复现实验（本机无 NPU 也能做）

```bash
# 逐元素：when vs mul，统计 bit 差与符号位
python exp1_elementwise.py
# 三段链路：mask -> matmul -> mask，按 mask 拆分统计
python exp2_chain.py
# 比较器语义：array_equal / allclose / assert_allclose(atol=0,rtol=0)
python exp3_semantics.py
```

判据：有效区 `bit_diff == 0`；掩码区 `value_diff == 0` 且 `sign_diff == masked_count`（A 为下三角时通常 100%）。
