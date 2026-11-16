# 一致性实验设计与证据

用于选择测试范围、构造最小反例及判断一个 PASS 能证明什么。测试顺序按现有失败和成本调整；下表不是必须逐项执行的流水线。

## 先固定比较语义

选择同一策略版本，冻结 prompt/response token IDs、有效历史、position、attention/loss mask、特殊 token 分支和状态起点。保存实际生成的 IDs 后重放，不重新 tokenize。校对 label shift：历史位置 t 的 logits 预测哪个目标 token，response 首 token 的条件历史是什么。

区分 raw model logprob、temperature/penalty 后的分布、top-k/top-p 截断后重新归一化的分布、采样概率和统计指标。两侧 raw 与 processed score 混比，结果再小也无效。用全词表诊断时允许单独分析 raw logits 的全局平移，不把它直接解释成概率变化。

若比较自由生成，两条轨迹只在共同前缀上有相同条件概率语义；分叉以后不能逐位置比较并归因到数值误差。改动使轨迹改变时，保留旧轨迹作因果重放，另用新候选实际生成轨迹完成端到端比较。

## 可组合的实验维度

| 维度 | 典型比较 | 通过范围 |
|---|---|---|
| 同侧 A/A | 同权重/输入/状态重复；必要时独立进程 | 所覆盖路径的重复性 |
| 推理 BI | 单条、不同 companion/批量、正逆序、偏移、padding/packing | 所覆盖调度/几何下的批次不变性 |
| PD | 同历史 full prefill、chunked prefill、逐步 decode | 所覆盖 cache/位置/分块路径 |
| 训练自身 | native old-logprob A/A 与实际 grad-enabled forward；改变 packing | 训练路径的重复性/布局敏感性 |
| 跨栈前向 | rollout 对 native old-logprob、对真实训练前向各独立比较 | 约定策略与输入下的训推一致性 |
| 更新后 | 同版本导出/同步后重做比较，探测实际权重与派生状态 | 所覆盖更新/驻留生命周期 |
| 质量/性能 | 约定数据、采样、负载和计时边界上的配对评测 | 对应指标，不代替数值验收 |

根据模型边界选长度和并发：tile、page、SWA、chunk、压缩比例、expert capacity、top-k 截断阈值两侧；必要时包含混合 prefill/decode、cache 复用/清空、sleep/wake、Graph capture/replay、重计算和目标并行拓扑。不要照搬旧案例的长度列表或固定样本数。

记录目标分支确实命中。例如稀疏 key 数始终小于 top-k，只覆盖了“不发生有效截断”的路径；纯文本 fixtures 不证明视觉或特殊 token 路由相同；缩小 TP 后失败消失不证明原拓扑已修复。

## 两条训练前向不能互相替代

分别从实际框架入口观察：

- old-logprob：保留其真实 no_grad/forward-only 语义，记录 model mode 和实际 operator/backend。
- grad-enabled forward：使用真实训练分支，在 loss transform 前采集本次前向的 logprob，记录 requires_grad、recompute、packing、分片和可导连接。

两条路径对同一冻结策略分别与 rollout 比较。禁止只把 no_grad 改成 enable_grad 就认定覆盖了真实 actor；训练框架可能跳过零 advantage 的前向并返回默认统计 0，需证明目标 callsite 与有效微批实际执行。

若正式算法在一轮内多次更新 minibatch，不能要求已经改变的 actor 与旧 rollout 的同版本分布相等，也不能改变算法制造相等。显式标记实际参数版本。

## 原始位比较

保留原 dtype 位模式或可无损恢复的原始 tensor。FP32/BF16/FP16 等不同 dtype 是契约差异，不能先全部转低精度再声明 bitwise 通过。连续化比较有效元素字节或同宽整数视图，避免浮点相等漏掉正负零；NaN/Inf 即使字节相同也不能通过。

对每条路径报告：

- 有效样本/token 数、缺失或重复的映射、非有限值数量。
- 原始 dtype、shape，以及语义对齐后的 bit mismatch 数。
- logprob 绝对差的 mean/max/分位数与首个失败样本/位置。
- 可选的差异分布、最长连续尾段、与长度/边界/特殊 token/rank 的关系。

这些统计用于选实验，不能单凭“差异从某处开始”断言根因。空 mask、全零占位输出、缺 rank、不同历史、同一份结果被复用作两侧，属于 INVALID。容差任务可以另报通过，但不能把非零位差记成 bitwise PASS。

KL/ratio、概率差、relative L2、cosine 可作辅助，须明确公式、采样分布与非有限值处理。固定旧轨迹上的诊断统计不自动具有当前策略 KL 的估计语义。

## 首个差异的低成本定位

先利用已有失败回执判断：某几条全序列不同、跨边界后连续尾部不同、全局低位漂移，还是只在更新后不同。依次挑能排除假设的实验，而非盲目全量 dump。

典型定位方法是粗扫层输出 → 二分首个不同模块 → 对照相同输入下的内部边界。若输入本身已不同，向上游查；若输入位相同而算子输出不同，再看数学/精度/几何/执行状态。离散选择先看集合和次序，不能只看 logits 距离。

每次修复保留原反例。缩小模型、TP、长度或关闭 Graph 后必须检查原故障是否仍重现；不重现的 proxy 只能支持有限结论。诊断分支和正式候选分开记录，去掉调试替代后重验交付路径。

## 建议的证据关联字段

优先适配框架已有 dump 格式。下面是便于跨框架审计的字段语义，不要求所有任务采用同一文件结构：

~~~yaml
identity:
  run_id: 独立执行标识
  candidate: 源码/环境/配置/算子产物指纹
  policy: 同步完成后实际计算权重版本及内容标识
path: inference_decode / inference_prefill / native_old / native_grad 等实际路径
execution:
  rank_and_worker: 实际 rank、进程或 worker 身份
  model_mode_and_grad: train/eval、grad mode、requires_grad
  determinism: 实际设置、查询结果与后端
sample:
  id: 稳定样本标识
  prompt_ids: 原始 IDs 或不可变工件引用及 SHA
  response_ids: 同上
  positions_and_masks: 有效位置、有效 token 与映射
score:
  semantics: raw / processed 以及处理顺序
  dtype_and_bits: 原始 dtype 和位模式/无损工件
result:
  valid_count: 大于零
  mismatch_count: 原始位比较
  first_failure: 样本、位置、左右位值
~~~

同一策略的跨路径回执应具有独立执行身份，避免把同一 tensor/文件当成两次运行。纯 CPU 可重读原始回执做独立比较；它审计已有执行证据，不代替新的 NPU 运行。

## 结论与回归范围

修改共享算术时复测相应 forward/backward；改 metadata 时复测边界与布局；改同步时复测更新后 actual weights/derived state；换环境或 Graph 路径时补该路径的证据。不因一次低影响文档修改重跑所有 NPU 测试。

阶段结论区分 PASS、FAIL、INVALID/INCONCLUSIVE、NOT RUN；SKIP 不等于 PASS。完整模型、proxy、单算子、固定权重、更新后分别列范围。数值通过不代表训练质量、长期稳定性或性能通过，报告应给出各自计时边界与未覆盖项。
