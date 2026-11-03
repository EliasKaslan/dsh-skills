# 验收标准

这份文件是"凭什么算通过"的唯一出处。报告里的每个结论都要能对上这里的一条。

## 1. 结论只有五种，不要自造

| 结论 | 含义 | 能不能出报告 |
|---|---|---|
| `PASS` | 规范矩阵全部执行且逐位一致 | 能，且可以宣称"批次不变" |
| `PASS_PARTIAL` | 有场景通过，但有场景因资源跳过/未执行 | 能，但**必须列出没跑的组合**，不得宣称"批次不变" |
| `FAIL` | 至少一个场景出现 token 或 logprob 不一致 | 能，这本身就是结论 |
| `BLOCKED` | 证据不足，无法判定（缺权重、缺统计、容量不足、环境缺件） | 能，但**必须给原因码与下一步动作** |
| `SKIPPED_*` | 单个 TP/场景因资源不可用而跳过 | 只能作为场景级状态，不能当阶段结论 |
| `NEGATIVE_CONTROL_REJECTED_AS_EXPECTED` | 负控：故意关掉/扰动后，比对**看见**了差异 | 能，且是其它 `PASS` 有说服力的前提 |
| `NEGATIVE_CONTROL_INCONCLUSIVE` | 负控：关掉后输出仍逐位一致，什么也没证明 | 不能当通过，必须换更大形状重试 |

**红线**：`BLOCKED` 不许写成 `FAIL`（会把环境问题算成产品缺陷）；`SKIPPED` 不许写成 `PASS`（会拿别的 TP 外推）；没有负控的 `PASS` 只能算**弱结论**（无法排除"这个形状本来就不受批影响"）。

**负控的作用域规则（易错，必须按格子做，不能一次套全场）**：

1. 负控要**跟着形状走**。负控证明的是"这个 `(TP, BS, prompt:max_tokens)` 能看见差异"，不是"这套代码能看见差异"。换了形状就换了一把尺子，判别力可能完全不同。
2. 负控 `INCONCLUSIVE` ⇒ **同形状下所有 `PASS` 一并降级**，报该场景 `INCONCLUSIVE`（不参与阶段聚合），而不是留着一个好看但没牙的 `PASS`。
3. 阶段结论里要写明"哪些格子有同形状负控背书"。只有被背书过的格子才能用来支撑 `PASS` / `PASS_PARTIAL`。

> 实测反例：同一台机器、同一套代码，`TP=1/BS=4/64:32` 与 `TP=8/BS=16/256:64`（缩层模型）关掉开关后都是 `INCONCLUSIVE`，而 `TP=8/BS=32/512:128` 稳定 `REJECTED`（32/32 请求不一致）。把后面的结论套到前面的形状上，就是拿一把没刻度的尺子出报告。

## 2. 阶段 2（功能层）判据

### 2.1 单场景通过（可机检）

一个 `(TP, BS, prompt_len:max_tokens, rounds)` 场景算通过，必须**同时**满足：

| # | 条件 | 机检落点 |
|---|---|---|
| F1 | 进程以 `VLLM_BATCH_INVARIANT=1` 启动 | 脚本启动即校验，不等于 `1` 直接退出 2 |
| F2 | 每条 prompt 实际 token 数 == 基准长度 + 该条随机增量 | 日志 `all_exact=true`；构造失败即 `BLOCKED_EXACT_PROMPT_LENGTH` |
| F3 | BS=1 与 BS=N 每条都生成**恰好** `max_tokens` 步 | `len(logprobs) == max_tokens`，否则 `BLOCKED_STEP_COUNT` |
| F4 | token ID 序列**逐元素相同** | `tk1 == tkN` |
| F5 | 相同路径上的 chosen-token logprob **按位相同**（float32 `torch.equal`） | `torch.equal(lp1, lpN)` |
| F6 | 多轮时跨轮输出相同 | 跨轮签名逐轮相等 |
| F7 | KV 需求 ≤ KV 容量 | `required_kv_tokens <= capacity_kv_tokens` |

F4 不成立时**不再比 F5**：路径都不同了，比 logprob 没有意义，只会掩盖主因。

### 2.2 阶段通过

规范矩阵全跑完且全过 → `PASS`。矩阵是：

| 场景 | TP | BS | prompt : max_tokens | 轮数 | 备注 |
|---|---|---|---|---|---|
| 负控 | 8 | 32 | 512 : 128 | 1 | **先跑这个**，关掉开关或开扰动，期望看见差异 |
| 批维（短） | 8 | 64 | 128 : 128 | 1 | 最主要的判据 |
| 长输入 | 8 | 64 | 20480 : 2048 | 1 | `max_num_batched_tokens=131072` |
| 长输出 | 8 | 64 | 2048 : 20480 | 1 | 单场景约数小时，先估算 |
| 并行矩阵 | 1/2/4 | 16、32 | 100 : 512、1024 : 2048 | 3 | 每格 3 轮 |

**负控的形状要够大**：实测 TP=1 / BS=4 / 64:32 上关掉开关仍逐位一致（无鉴别力）；TP=8 / BS=32 / 512:128 上 32/32 请求暴露差异。负控形状太小，等于没做。

**任一场景未执行 → 最高只能给 `PASS_PARTIAL`。**

### 2.3 参数口径

| 参数 | 值 | 说明 |
|---|---|---|
| `temperature` | `0.6`（或 `0`） | 一次对比内不许变；两种温度要各出一份结论 |
| `seed` | `12345` | 多轮时逐轮 +1 |
| `max_model_len` | ≥ `22578` | `20480 + 50 + 2048`；差一点就会撞 `BLOCKED_PROMPT_LENGTH_EXCEEDS_MODEL_LIMIT` |
| `max_num_batched_tokens` | 自动，封顶 `131072` | 下限 `max(prompt_len + max_tokens)`；它只是单步预算，不是 KV 容量 |
| `block_size` | `128` | 与 Phase 1 profiling、Phase 3 必须一致 |
| `enforce_eager` | `True` | |
| `enable_chunked_prefill` | `False` | |
| `enable_prefix_caching` | `False` | |
| `async_scheduling` | `False` | |
| `ignore_eos` | `True` | 只为固定步数 |

> **易错**：Phase 2 的 `max_model_len` 是 `22578`（多了 50 的随机增量余量），Phase 3 的 Math500 是 `22528`（没有增量）。两个数都对，**照抄错的会失败**。

## 3. 场景状态 → 阶段结论

```
任一场景 FAIL                            → FAIL
否则 任一场景 BLOCKED_*                   → BLOCKED（给原因码）
否则 无任何场景 PASS                      → BLOCKED（没有任何证据）
否则 有场景 SKIPPED_*                     → PASS_PARTIAL（列出被跳过的 TP/场景）
否则                                      → PASS
```

`SKIPPED_TP_RESOURCE_UNAVAILABLE` 的判定边界很窄：**只认模型加载阶段**的 OOM / 分配失败 / `No available memory for the cache blocks`。**加载完成之后**的推理 OOM 算失败，不算跳过。

同一个启动错误只有同时出现 `free memory on device`、`desired`、`<`（或 `less than`）三者，才允许"配置不变重试 2 次"；正常的资源统计 INFO（例如 `on startup. Desired GPU memory utilization`）不许触发重试。

## 4. 阶段 3（Math500）判据

10 轮 × 500 样本，`temperature=0`、`seed=1234`，必须**同时**满足：

| # | 条件 | 常量 |
|---|---|---|
| M1 | 每轮 `status == ok`，且该轮 `accuracy` 存在 | 10 轮 |
| M2 | 每轮 `accuracy >= accuracy_threshold` | 默认 `93`（也接受 `0.93`） |
| M3 | 10 轮 accuracy **完全相同**（`len(set(scores)) == 1`） | 不许用平均值或容差替代 |
| M4 | 每轮成功且不重复的样本数 == 500 | `500` |
| M5 | 10 轮样本集合相同，且每个样本的原始 `prediction` 字符串**逐字符相同** | — |
| M6 | 场景配置逐项一致（模型、设备、TP/DP/PP/EP、数据集、temperature、seed、`VLLM_BATCH_INVARIANT=1`、prefix caching、长度、并发、`block_size`、chunked prefill、后端、显存利用率、eager、load format、async scheduling、日志统计） | 26 项 |

**对齐键**是 `(data_abbr, id)`，比较对象是完整原始 `prediction` 字段；**不要**用整文件 sha256 判一致性（行序和 UUID 会变），文件 hash 只作归档指纹。

**必须有真实权重**：权重缺失 → `BLOCKED_MISSING_REAL_WEIGHTS`。减层 / `load_format=dummy` / 随机权重的结果**不得**用于阶段 3。

**阈值必须执行前固定**：所有 `--expected-*` 只能来自事先固定的目标配置，禁止跑完按实际结果回填。

## 5. 报告骨架

```markdown
# Batch 不变性验收报告 — <模型>

## 结论
- 整体状态：PASS / PASS_PARTIAL / FAIL / BLOCKED
- 一句话结论：<说清哪些维度验了、哪些没验>
- 运行记录：<RUN_DIR>
- 模型与栈：<model path> / vllm <ver>@<sha> / vllm-ascend <ver>@<sha> / CANN <ver> / <chip>
- 并行能力：TP=<实测过的>；PP/EP/DP=<理论 or 未验证>

## 阶段汇总
| 阶段 | 状态 | 核心结论 | 主证据 |

## 场景明细（阶段 2）
| 场景 | TP | BS | prompt:max_tokens | 轮数 | 设备 | 状态 | KV 需求/容量 | 失败计数(step/token/logprob) | 证据 |

## 算子分诊（阶段 1）
| 判决 | 算子 | 占比 | 是否关键路径 | 处置 |

## 数据集验收（阶段 3）
| 轮 | accuracy | 样本数 | 文本一致性 | 证据 |

## 未覆盖与偏差
| 项 | 偏差 | 影响 | 下一步 |

## 复核方式
（每条结论 → 对应文件路径与 sha256）
```

**报告的硬要求**：
- 每个结论后面挂一个**能打开的路径**；
- "未覆盖"必须单独一节，不许混进"通过"里；
- 不许出现"应该没问题""基本一致"这类措辞。

## 6. 最容易错的三处口径

1. **`max_model_len` 两个值**：阶段 2 用 `22578`，阶段 3 用 `22528`。
2. **`SKIPPED` 的边界**：只认加载期 OOM，不认推理期 OOM。
3. **减层/dummy 权重**：只能用于"把链路跑通"，任何结论都要标注"该层数下"，不得外推到全量模型，更不得用于阶段 3。
