# 失败定位

前提：你已经有一个 `FAIL`，并且**失败是可复现的**。不可复现的失败先归到"运行间不确定"，那是另一类问题（见 §6）。

## 1. 先分清这是哪一类失败

这一步比任何调试技巧都重要。分错了会白烧一天。

| 症状 | 类别 | 去 §几 |
|---|---|---|
| 步数不一样（一边提前 EOS） | **证据问题**，不是不变性问题 | §2 |
| `BLOCKED_EVICTION_UNSUPPORTED` / 有 preemption | **资源问题**，不是不变性问题 | §2 |
| KV 需求 > 容量 | 资源问题 | §2 |
| 所有请求都不同，且差异从第 0 步就有 | 大概率真实缺陷 | §3 |
| 只有部分请求不同，差异出现在中后段 | 真实缺陷（累积误差） | §3 |
| 只有某些 TP 不同 | 并行路径问题（all-reduce 分块） | §4 |
| 只有长序列不同 | prefill 切分 / 长序列 kernel | §4 |
| 同一个配置重复跑结果不一样 | 运行间不确定 | §6 |

## 2. 先排除"不是不变性"的失败

按顺序核，**每一条都能把一类假失败挡掉**：

1. **`VLLM_BATCH_INVARIANT` 真的是 `1` 吗**——不是 `1`（含未设置、`0`、空串）时跑出来的"一致"是巧合。脚本已强制校验。
2. **步数是否恰好等于 `max_tokens`**——`ignore_eos=True` 没生效、或某个请求撞了 `max_model_len`，都会让步数不一致。步数不同就**不要再比 logprob**。
3. **prompt 长度是否精确**——近似长度会让 BS=1 与 BS=N 的实际形状不可比。日志里应有 `all_exact=true`。
4. **KV 需求是否超容量**——超了必然发生换出/重算，此时的差异与不变性无关，判 `BLOCKED`。
5. **有没有 preemption / eviction**——有就停下，调参数消除后再重跑；驱逐场景当前不支持给出不变性结论。
6. **调度统计是否读到**——读不到不是"没关系"，是 `BLOCKED_SCHEDULER_EVIDENCE`。

> **日志措辞陷阱**：昇腾的统计行是 `NPU KV cache size: ...`。只认 `GPU` 的正则会让**每一次** NPU 运行都判 `INCOMPLETE`。正则要写 `(?:GPU|NPU|DEVICE)`。

> **判定顺序陷阱**：pytest 明明 `1 passed`，却在后面被调度证据检查改写成 `BLOCKED`——因为先判了调度再判 pytest。正确顺序是**先 pytest，调度证据作为并列记录**。

## 3. 定位顺序（真实缺陷）

| # | 做什么 | 判据 |
|---|---|---|
| 1 | 固定现场：模型、完整并行拓扑、设备、prompt、seed、temperature、长度、prefix caching、调度参数 | 只允许泛化 temperature；采样侧不许有别的变量 |
| 2 | 读 attempt 日志，判有没有驱逐/抢占 | 命中驱逐 → 到此为止，先消除驱逐 |
| 3 | 对**失败配置**采 profiling，跑算子分诊 | 见 [算子分诊](operator-classification.md) |
| 4 | 验关键路径上的白名单外算子；必要时单独验 AllReduce | 见 [算子分诊](operator-classification.md) §6 |
| 5 | 同参数下换 TP=1 或 TP=2 再跑 | 用来区分"通信/切分路径"和"单卡计算路径" |
| 6 | 读 `failure_manifest.json` + scheduler JSON + 日志 | 证据不齐先补齐，不许靠猜选 dump 方法 |
| 7 | 只有当 msprobe 装不上/注不进/覆盖不到时才下钻到工具链 Demo | Demo 过 → 回模型场景查配置；Demo 挂 → 修条件重验，仍不可用标 `BLOCKED_MSPROBE_UNAVAILABLE` |
| 8 | 只有"全层稳定复现 + msprobe 可用 + 全层采集太贵"三条同时成立，才允许减层 | 改 `config.json` 的 `num_hidden_layers` |
| 9 | 修完重跑**原失败场景** | 减层模型和调试配置**不能**作为正式验收证据 |

## 4. 三层定位：从粗到细

### 调度层
- 怎么开：无需开启，读 attempt 日志与 scheduler 证据。
- 看什么：有没有 preemption/eviction、活跃请求数有没有回退（满批后 Running 减少且 Waiting 增加）、请求有没有分波。
- 正常现象：初始 `Running<BS, Waiting>0` 属正常排队，**不要求**观察到 `Running=BS, Waiting=0`。
- 结论：命中驱逐 → 停止数值定位；证据缺失 → `BLOCKED_SCHEDULER_EVIDENCE`。

### Profiling 层
- 看什么：失败配置的 `op_statistic.csv`，按算子耗时排序，跑分诊。
- 注意：profiling 必须在**与验收相同的配置**下采（`enforce_eager=True`、`block_size=128`），否则算子集合不一样。

### 单算子层
边界判定规则（这是全流程最有用的一张表）：

| 输入统计 | 输出统计 | 结论 |
|---|---|---|
| 一致 | 不一致 | **该算子是候选异常边界**，但还要在完整 tensor 上按位确认 |
| 不一致 | — | 差异来自上游，继续往前走 |
| 一致 | 一致 | 统计级没发现差异，继续看下游 |

**统计级一致 ≠ 逐元素一致。** 只有对候选算子启用 `statistics.tensor_list` 保存完整 tensor、在相同 rank 相同位置上做 `torch.equal`，才能把它定为差异边界。

如果边界算子**已经**在批次不变注册表里却仍然不一致，两种可能：注册实现有问题，或它不是根因（差异是从上游传播过来的）。

### dump 层（msprobe）
进这层前有门禁：必须**完整获取并通读** msprobe 仓的官方两份说明（`docs/zh/user_guide/dump/vllm_dump_instruct.md` 与 `.../config_json_introduct.md`，均在 `https://gitcode.com/Ascend/msprobe`），并记录仓库地址、实际 commit、获取时间、本地快照路径与 sha256。缺任一项 → `BLOCKED_MSPROBE_DOCUMENTATION_INCOMPLETE`。

默认只做统计（`task: statistics`），要逐元素证据才用 `statistics.tensor_list` 或 `task: tensor`；完整 tensor 采集保持 `async_dump: false`。

**静态切片 vs 动态 request id** 二选一，按场景判断，不要默认用静态：
- 静态切片（按 prompt 位置切）适合固定形状、请求集合不变的场景；
- 动态 request id 适合有 join/leave、批组成变化的场景。
选错的后果是 dump 出来的东西对不齐，白采。

## 5. 常见误判速查

| 现象 | 真因 | 处置 |
|---|---|---|
| 探测算子全 `False` | 没 import 包；或用了 `hasattr`/`dir` 这种恒真/恒空的判据；或该构建确实没编 | 按语义探能力，逐个 `getattr` 具体名字，见 [算子分诊](operator-classification.md) §1 |
| 每次都 `INCOMPLETE` | 正则只认 `GPU`，NPU 日志是 `NPU` | 正则兼容 `(GPU\|NPU\|DEVICE)` |
| `1 passed` 却判 `BLOCKED` | 判定顺序错 | 先 pytest，再看调度 |
| index 集合相同、顺序不同 | tie 的发射顺序随打包形状变 | 按该 token 自身分数升序规范化后再比 |
| 白名单外算子凭空变多 | 为了排查把融合算子拆成两步 | 拆开的算子各自不在白名单，是自造的 |
| 减层/随机权重下"通过" | 验的不是目标模型 | 只报 `BLOCKED_MISSING_REAL_WEIGHTS` |
| 长序列 OOM | `max_num_batched_tokens` 太小 | 显式给 `131072`；它只影响单步预算，不改 KV 容量要求 |
| 显存不足被当成失败 | 加载期 OOM 应判 `SKIPPED`，推理期 OOM 才是失败 | 按发生阶段区分 |

## 6. 运行间不确定（同一配置两次结果不同）

这**不是**批次不变性问题，但会让所有其它结论失效，所以要先修。

| 来源 | 怎么确认 | 怎么消除 |
|---|---|---|
| 随机种子没固定 | 两次跑 `seed` 不同 | 固定 `seed`，多轮逐轮 +1 |
| 采样温度 > 0 且实现里有非确定性 kernel | `temperature=0` 时消失 | 先用 `temperature=0` 定基线 |
| `PYTHONHASHSEED` 影响集合/字典迭代顺序 | 改 `PYTHONHASHSEED` 结果变 | 固定 `PYTHONHASHSEED=0`；**禁止用 `hash()` 派生种子**（每进程随机化），改用 CRC32 |
| 异步调度或流式重叠 | 关掉 `async_scheduling` 后消失 | 关掉 |
| prefix caching 命中与否随批变化 | 关掉 `enable_prefix_caching` 后消失 | 关掉 |

## 7. 负控：先证明你的检查有牙

在相信任何 `PASS` 之前，先跑一次**负控**：

```bash
VLLM_BATCH_INVARIANT=0 python scripts/bi_equivalence.py ... --allow-non-bi
```

期望结果 `NEGATIVE_CONTROL_REJECTED_AS_EXPECTED`（即检查看见了差异）。两种偏差都要单独报：

| 负控结果 | 含义 |
|---|---|
| `REJECTED_AS_EXPECTED` | 比对逻辑能看见差异，且批次不变模式在这条路径上确实起作用 |
| `INCONCLUSIVE` | 关掉开关后输出仍然逐位一致 → 要么这个模型/形状本来就不受批影响，要么开关根本没接上，此前的 `PASS` 可能是**空过** |

`INCONCLUSIVE` 不出结论，必须换一个更大的形状或换模型再试。

**形状要够大才有鉴别力**（实测，Qwen3-30B-A3B，TP=8）：

| 形状 | 关掉 BI 后的结果 |
|---|---|
| BS=4 / 64:32（TP=1） | 0/4 请求有差异 → `INCONCLUSIVE` |
| BS=32 / 512:128（TP=8） | 32/32 请求有差异 → `REJECTED_AS_EXPECTED` |

那次 32 个失败请求里，**只有 6 个 token 序列不同，26 个是 token 相同但 chosen-token 的 logprob 不逐位相等**。

> **这直接说明：只比 token 会漏掉 26/32 的真实差异。** 任何只比输出文本的"批次不变性验收"，结论都不可信。

如果实现自带扰动开关注入批相关扰动（GLM-5.x 是 `VLLM_BI_GLM_SELFTEST=perturb`），优先用它：它按批大小注入，并刻意保证扰动在 routing 权重归一化之后仍然存活。

## 8. 什么时候该停

同一个问题**五轮**还不能闭环，就停下请求人工介入，并交出：已排除的假设清单、每轮的命令与结论、当前最小复现、还剩下的候选原因。

不要在同一个方向上换参数硬试第六轮。
