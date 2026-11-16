# 算子数值契约与典型适配方法

当跨栈前向、BI/PD 或单算子比较失败时按需阅读。先证明两侧算的是同一个函数，再讨论最后几位。相同算子名、相同公式、相同 Python 源码都不足以证明实际浮点执行相同。

## 先建立算子地图

以实际调用栈为准，按 embedding → 各层模块 → final norm/head → scorer 列出：训练与推理实现、输入/累加/输出 dtype、layout/stride、可训练参数、量化与离散选择、状态及所需 backward。按模型结构增加跨层 KV、压缩、递归状态、特殊 token、视觉分支、adapter 或共享模块，不只列普通 decoder block。

不支持的训练模块、缺失的 backward、冻结但影响前向的 buffer 也列入。裁层或合成 proxy 只有保留关键几何和触发条件才有定位价值；层数由结构决定，不能默认“4 层覆盖所有模型”。某项只有全规模才能复现时，保留必要规模并说明理由。

单个算子可用下列紧凑记录表达，无需强制统一 schema：

| 契约 | 必须看实际值的地方 |
|---|---|
| 数学语义 | bias/sink/scale、温度、clamp、归一化 epsilon、mask、special token 条件分支 |
| 精度 | 参数存储、计算输入、accumulation、输出、cast 顺序、fused epilogue |
| 几何 | shape、stride、contiguous、转置/分块、真实长度、padding 与无效行 |
| 算法 | reduction tree、split-K、tiling、autotune/specialization、近似函数、FMA |
| 离散状态 | top-k 集合与顺序、tie-break、无效索引、dispatch/combine 与缓存位置 |
| 训练 | saved tensors、重计算时恢复的状态、梯度目标、通信与可导路径 |
| 运行产物 | Python module 来源、SO/vendor/算子 schema、实际 backend 与编译边界 |

先比较输入和参数原始位；不同输入下输出接近不能归因到当前算子。相同输入后比较各中间边界，优先定位第一个 cast、归约、离散选择或状态写入差异。强制专家索引、替代 attention 等可隔离下游，必须标为诊断控制，不能用于最终通过。

## 常见方法及使用条件

| 类型 | 典型差异 | 可考虑的方法与限制 |
|---|---|---|
| GEMM / grouped GEMM | M 随 token 数变化触发算法/累加顺序改变，weight pack 不同 | 先固定同一实现与计算精度；再评估确定性 kernel、固定几何或算法。保留真实 K/N、专家分组和 stride。不要靠逐 token Python 循环掩盖结构性能问题 |
| Norm / residual | FP32 中间值直接传下游，与先 BF16 舍入再 FP32 不同 | 显式写出 cast 位置；匹配 norm epsilon、residual 是否 FP32、融合边界与输出分支 |
| 激活 / gate | 近似 sigmoid/SiLU、clamp 次序、多次低精度乘法 | 对齐 fused 或逐步实现及 alpha/beta/limit；共享/路由分支可能有不同精度契约，不能统一升精度后直接宣布正确 |
| RoPE / 位置编码 | 默认设备、CPU/NPU 建表、缩放除法次序、交错维度与 inverse | 显式工厂 device 和 dtype；核对表、position IDs、YaRN 等变体与乘加顺序；CPU 建表是候选方法，不是所有模型的要求 |
| Attention / KV | cache 量化、paged/TND 布局、SWA/causal、sink、metadata ABI | 同时核对 cache spec、分配、写入、读出与算子接口；区分 attention KV 和 indexer 等缓存，不能只看一个 dtype |
| MoE / 稀疏索引 | router bias/归一化、top-k 次序、通信选择、权重舍入 | 先对齐 logits、选择集合/顺序和 unbiased 权重；再查 dispatch、expert math、unpermute、route scale 与 shared combine |
| recurrent / cross-layer | 单步状态与全序列状态更新不同，replay 未恢复状态 | 保存初始状态和更新时点；比较状态写入与输出，保留跨层/跨 chunk 依赖，不能只比较一个无状态层 |
| 量化 / QAT | scale、zero point、分组、舍入/saturation、master 与部署 grid 不同 | 记录全转换链和实际部署值；明确 scale 更新及 STE 契约，不能把 BF16 路径通过外推为量化路径通过 |
| Scorer | 相同 logits 下 logsumexp 分块、词表并行、温度/penalty 不同 | 用相同 logits 分别跑实际 scorer；必要时共享真实生产 scorer 并补可训练 backward |

## 固定几何是一种候选方法

当证据表明算子对独立行的 launch shape 敏感，可分块、补齐、调用、裁剪，固定底层看到的几何。块大小由本轮 shape/芯片/kernel 实测决定，没有通用的 128 行。先证明 padding 不改变有效行语义：

- 不跨 token 归约、不进入有效 attention/路由容量或量化 scale 的统计。
- 补齐的 mask、position、metadata 和状态更新正确。
- backward 裁剪和梯度回传正确，dummy 行不污染梯度。
- 覆盖尾块、空输入（若支持）、跨块偏移与目标混批，并记录额外开销。

对 token 独立的 mHC 成功，不代表可原样用于有跨 token 统计的算子。若只知道固定几何消除了观测差异，就报告该事实，不把二进制内部 tiling 猜测写成已证明根因。

## 精度契约用表达式写清楚

例如下面两式在有限精度下不等价：

~~~text
BF16(FP32(routed) * scale + FP32(shared))
BF16(BF16(routed * scale) + shared)
~~~

提前把 scale 乘入每条专家权重也可能改变合并结果。应逐项记录“存储值 → cast → 乘法 → 归约 → cast”，而不是笼统说“改成 FP32”。

计算使用 FP32 shadow 也不意味着权重没有丢精度。必须检查载入/同步时是否先落到 BF16/量化参数，再转 FP32；初始 checkpoint 恰好可表示不代表真实更新后仍可表示。更新后的 shadow/packed/scale 需要单独核对。

## Attention 的接口与数学问题分开

从当前 CANN 和绑定的真实 schema 读取合法参数、metadata 大小、layout、长度、sink 与 residual 的约定。模型配置“无压缩=0”与底层 ABI 的无压缩标记不一定同值；paged 的 block table 与 TND 的 cu_seqlens 也不能混用。合法调用、相同前向、真实 backward 是三个证据。

对 right padding，要证明有效 query 不可见补齐 token、有效位置编码未移动、loss mask 正确；对左 padding、双向 attention、归一化统计或递归模型不自动成立。限制 cache 池可能解决 workspace OOM，但不是数学正确性的证明。

## Logprob 与可训练 scorer

若 logits 已相同而 logprob 不同，先核对实际执行的 token scorer，而不是按包名猜通用版本。不同分块归约、减 max 与减 logsumexp 次序、词表 padding/shard reduction 都可能改变最低位。

共享生产 scorer 时仍用训练模型自身的 logits 和目标 labels。对于普通 selected log-softmax：

~~~text
d log p(y) / d z_j = 1[j=y] - softmax(z)_j
~~~

可考虑为无 autograd 的 forward 补解析 VJP。该式要求当前 z 的定义与 temperature、processed score、截断集合等契约匹配；不能直接套到任意采样处理器。记录是否只支持一阶导数，并对大/小 logits、有符号与零上游梯度、边界 labels 等，使用独立参考验证。

## Backward 的证据等级

优先复用现有真实 backward/autograd/通信。新增 backward 或 STE 时明确哪些前向量被保存、哪些是可导 master、哪些离散量视为常量，以及重计算如何恢复一致状态。

独立参考不能调用被测 backward；可采用相同数学契约的展开 autograd、适当精度参考或针对可微部分的有限差分。逐项检查 dX/dW/bias/scale/premix 等实际可训练目标，预先确定容差。前向 bitwise 标准与梯度容差分开，不能通过开关 level 降级来满足性能。

“有限且非零”证明梯度存在；一次 optimizer 改变参数证明有更新；独立 VJP 通过才支持相应范围的梯度正确性。STE、量化离散点和高阶导数需单独说明，不能从 logpdiff=0 外推。
