# 算子分诊

**目的**：在跑端到端之前，把"注定不满足"的算子挡掉；端到端失败之后，把问题定位到具体算子。

**边界**：算子层通过 **不等于** 端到端通过。它只是必要条件。反过来，算子层命中黑名单也**不等于**代码走的就是那个算子——先看实际调用路径。

## 1. 先搞清"批次不变算子"长什么样

同一份能力在不同构建里有三种形态，**名字完全不同**，探测方式也不同：

| 形态 | 例子 | 怎么探 |
|---|---|---|
| (a) `torch.ops` 命名空间 | `torch.ops.batch_invariant_ops.npu_mm_batch_invariant` | `getattr(ns, "<具体算子名>")`，取不到会抛 `AttributeError` |
| (b) python 函数 | `batch_invariant_ops.npu_matmul_batch_invariant` | `dir(包)` 再筛名字 |
| (c) 被 patch 的原算子 | `torch.ops.npu.npu_fused_infer_attention_score` 内部换实现 | 看 patch 日志 |

> **实测（2026-11，CANN 9.2.0 + vLLM 0.31.0 源码构建）**：(a) 和 (b) 同时存在——`torch.ops.batch_invariant_ops.npu_mm_batch_invariant` 等**能取到**，python 层也暴露了 15 个含 `batch_invariant` 的名字。

### 探测这件事本身有两个陷阱，两个都会让你得出相反结论

跑一遍这段代码就能看出来：

```python
import torch
print(hasattr(torch.ops, "batch_invariant_ops"))              # True
print(hasattr(torch.ops, "definitely_not_a_real_ns_xyz"))     # 也是 True  ←！
print([a for a in dir(torch.ops.batch_invariant_ops) if not a.startswith("_")])  # ['name']  ←！
```

1. **`hasattr(torch.ops, X)` 恒为 `True`**：`torch.ops` 是惰性命名空间，访问任意属性都会当场造一个空命名空间对象。所以拿它判断"算子包在不在"**永远得到 True**，这个判据是废的。
2. **`dir()` 枚举不出注册的算子**：`dir(torch.ops.batch_invariant_ops)` 只给 `['name']`。所以"遍历命名空间把算子列出来"这条路也是死的，会得到"一个算子都没有"的错觉。

**唯一可靠的判据是逐个取具体名字**：

```python
for name in ("npu_mm_batch_invariant", "npu_matmul_batch_invariant", ...):
    try:
        getattr(torch.ops.batch_invariant_ops, name); hit = True
    except AttributeError:
        hit = False
```

同一个坑还有第二个来源：`.so` 在 `site-packages/batch_invariant_ops_lib.cpython-312-x86_64-linux-gnu.so`，**不在包目录里**。只在包目录 `rglob("*.so")` 会找不到，然后误判"动态库没编"。

正确做法：**按语义探测能力，不按名字探测包**。`scripts/bi_preflight.py` 里 `REQUIRED_CAPABILITIES` 就是这么写的——`attention` / `matmul` / `reduce_sum` / `softmax` / `add_rms_norm` 五个能力，每个给一组候选名字，两个命名空间都试，命中任一即可。这样命名空间换形态也不会误判。

## 2. 强制黑名单

| 算子 | 为什么要黑 |
|---|---|
| `SoftmaxV2` | 归约轴的切分随批形状变化 |
| `MatMulV2` | 归约顺序随 M/N/K 分块变化 |
| `FusedInferAttentionScore` | 融合算子的规约顺序不可控 |
| `AddRmsNorm` | 融合了归约，且归约轴受 token 打包影响 |
| `ReduceSum` | 归约顺序直接依赖输入形状 |

**只做精确名匹配**——这是有意的（宁窄不宽，避免误杀），也是最大的判读盲区，见 §5。

命中黑名单的处置顺序：**先留证据 `FAIL_BLACKLIST` → 再确认实际跑的是不是变体 → 再决定改代码**。不要反过来。

## 3. 白名单

按芯片分区，A2 复用 A3。分四类，每类的"为什么可以放行"不同：

| 类别 | 代表 | 放行理由 |
|---|---|---|
| `*BatchInvariant` 变体 | `MatMulV2BatchInvariant`、`FusedInferAttentionScoreBatchInvariant` | 本身就是修好的版本 |
| shape / 数据搬移 | `Transpose`、`Slice`、`Tile`、`GatherV2`、`ScatterPaKvCache`、`Fill` | 不改变元素值，与批形状无关 |
| 逐元素 / 比较 | `Add`、`Mul`、`Cast`、`SwiGlu`、`MaskedFill` | 每个元素独立计算 |
| 沿固定轴的归约 | `ReduceMax`、`ArgMaxV2`、`RmsNorm` | 归约轴不是批维 |
| MoE | `GroupedMatmul`、`MoeInitRoutingV3`、`MoeGatingTopK` | 需结合 expert 路由方式确认 |
| 通信 | `hcom_allReduce`、`allreduceAicpuKernel` | 单独出现不代表失败，要单独验 AllReduce 的分块 |
| 采样 | `DSARandomUniform` | 只在 seed 与采样阶段确定的前提下可放行 |

完整清单见 `scripts/bi_ops_triage.py` 里的 `ALLOWLIST_A3` / `ALLOWLIST_A5`（代码即事实，不再抄一份到文档里，避免两处漂移）。

**白名单是快照**，随 vLLM-Ascend 版本变化。换版本后必须重新采集 profiling 并更新。

## 4. "关键路径"怎么定

按设备耗时占比从高到低累加，覆盖到阈值（默认 90%）为止的那批算子。

只看关键路径，是因为占 0.01% 的算子即使不一致也翻不动 top-1。但这只是**缩小范围**：报告里要列出被排除的算子及其占比，不能假装它们不存在。

判决：

| 判决 | 条件 | 下一步 |
|---|---|---|
| `PASS` | 关键路径全在白名单 | 进功能层 |
| `PASS_WITH_NOTE` | 关键路径清白，非关键路径有未知算子 | 进功能层，结论里写明 |
| `REVIEW_REQUIRED` | 关键路径有白名单外算子 | 逐个排除或做单算子验证 |
| `FAIL_BLACKLIST` | 关键路径有黑名单算子 | 先留证据，再查实际路径 |

## 5. 四个判读盲区

1. **同族融合算子漏匹配**：黑名单里是 `AddRmsNorm`，但图里跑的是 `AddRmsNormBias`——名字不同，精确匹配抓不到。凡是"名字里带黑名单算子名但多了后缀"的，都要人工看一眼。
2. **`Tensor.sum` 绕过 `torch.sum` 替换**：vLLM 的批次不变模式替换的是 `torch.sum`，而 `x.sum()` 走的是 `Tensor.sum` 这个注册名，替换不到。判 `ReduceSum` 相关失败时先确认调用写法。
3. **拆开融合算子会脱离白名单**：白名单里是 `AddRmsNormBatchInvariant` 这个**融合**算子。如果你为了排查把它拆成 add + rmsnorm 两步，那两步各自不在白名单里，会凭空多出 `REVIEW_REQUIRED`。
4. **`enable_custom_op()` 返回 `False` 但调用方照旧调用**：能力探测的结果没有形成门禁。这类路径下"算子已注册"和"算子被用到"是两件事。

## 6. 白名单外算子怎么办

两条路，选一条并写进报告：

**A. 排除**——给出"它为什么不可能影响批维"的证据。可接受的证据：
- 它的输入在批维上互相独立（elementwise、index、搬移）；
- 它的归约轴与批维正交（沿 head_dim 归约 vs 沿 batch 归约）；
- 它是 shape-only 操作。

**B. 单算子验证**——造 1e4 条用例，覆盖：

| 维度 | 要覆盖 |
|---|---|
| shape | BS ∈ {1, 2, 8, 64}，seq ∈ {1, 128, 1024, 4096}，含非对齐长度 |
| dtype | bfloat16 / float16 / float32 |
| 参数 | 该算子所有会影响归约切分的属性（轴、keepdim、分组数） |
| 比对 | 同一份输入，逐 BS 切分与整批算，输出 `torch.equal` |
| 判定 | 1e4 条全过才算过；任一条不过就是 `FAIL`，并留下最小复现 |

**统计级一致不算过**：Max/Min/Mean/Norm 全等只能说明统计级没发现差异，不能证明逐元素或按位一致。

## 7. 稀疏注意力 / DSA 的硬口径

GLM-5.x 这类带稀疏索引（LightningIndexer / SFA）的模型，端到端比 token 之外还要注意：

| 项 | 口径 |
|---|---|
| `sparse_indices` 形状 | `[T, 1, topk]`，`T` 是打包后的 token 总数 |
| paged block table | 每个请求必须占**互不重叠、非零**的连续区间 |
| 随机种子 | 用 CRC32 派生，**不能用 `hash()`**（`hash()` 对 str 每进程随机化，跨进程不可复现） |
| tie 的处理 | 同分并列的发射顺序随打包形状变化 → 按该 token 自身分数升序规范化后再比 |
| 判失败先看什么 | 先看 `same_index_multiset`（选中的 index 集合是否相同）；集合相同而顺序不同 = 规范化没做对，不是真失败 |

## 8. 怎么更新白名单

1. 在目标版本上采一次 profiling（`enforce_eager=True`，与验收同配置）；
2. `python scripts/bi_ops_triage.py --csv <csv> --chip A3` 看哪些算子落进 `review_all`；
3. 对每个新算子按 §6 走 A 或 B；
4. 把结论写回 `ALLOWLIST_A3`，并在提交信息里注明"依据哪个版本的 profiling、用了哪种证据"。

**不要把"某个算子在这次 profiling 里没出现"当成它安全**——没出现可能只是这个模型没走到。
