# 性能反模式清单（症状 / 根因 / 做法）

先看 [programming-model.md](programming-model.md) §6 的五项可度量门禁——本文件是那五项在具体写法上的表现。

标注说明：

- **[实测]**：本仓在昇腾 NPU 上跑过、有输出或错误码为证。
- **[参考]**：来自上游 TileLang-Ascend 技能库的口径，**本机未复核**；按此实施后必须用
  `msprof op` + 精度用例自行确认，不能当结论引用。

归类方式看固定开销的倍数：搬了 0 有效数据（纯冗余）= ∞；搬运次数爆炸 = N 倍；
单次搬运量太小 = `tile 容量 / 有效元素` 倍；流水线空转 = 每轮一个空泡；
布局限制被迫全量拷贝 = 100%。

---

## 1. host 侧全量拷贝 [实测]

**症状**：`forward()` 里出现 `x.permute(...).contiguous()`、`x.reshape(M, N)`、`x.to(dtype)`。
**根因**：`permute + contiguous` = 整个张量 GM→GM 全量拷贝。`[8192, 2048]` 的 fp16 就是 32MB 额外搬运，
而算子本身可能只读一遍。
**做法**：把布局差异下沉到 kernel——用 `[outer, dim, inner]` 三维分解，靠 stride/offset 在 GM 上直接定位，
host 侧只传元数据。参考实现常用 `torch.chunk` 建零拷贝 view，值得照抄。
**判定**：`[HOST-METADATA-AUDIT]` 里 `contiguous=0 .to=0`（见 [acceptance-checklist.md](acceptance-checklist.md) §0）。

## 2. 逐行 DMA 循环 [参考]

**症状**：CopyIn/CopyOut 写成 `for row in range(rows): T.copy(A[row, n0], ub_row)`。
**根因**：每次 `T.copy` 都有固定的 DMA 建链开销（地址计算、通道分配、同步信号）。行多（上万行）
而每行很短时，固定开销占主导，实测同形状下与一次 2D 搬运差 20~30 倍。
**做法**：一次搬运多行——行内连续、行间用 stride 表达（二维 `T.copy`，或显式 `srcStride/dstStride`），
把 `blockCount` 设为行数。前提是**切片列维必须是最内维**（[constraints.md](constraints.md) §3），
否则会数据错位。

## 3. tile 太小 [参考]

**症状**：`block_M = 16, block_N = 64`，各层 buffer 实际用量远小于容量。
**根因**：tile 小 → 任务数、循环次数、同步次数、GM 往返次数全部上升，片上缓存复用不起来。
**做法**：成倍放大（16→32→64、64→128），每放大一档重算三层预算：

```text
UB  = Σ(buffer 元素数 × dtype 字节数 × stage 数) + 临时 buffer（broadcast/双缓冲都要算）
L1  = Σ(L1 tile 元素数 × dtype 字节数 × stages)
L0C = block_M × block_N × accum 字节数 × stages
```

放大到任务数少于物理核数时，要同步按 [programming-model.md](programming-model.md) §6 第 5 项处理 launch 核数。

## 4. 单缓冲 / 双缓冲只加了 buffer 没加 flag [参考]

**症状 A**：一圈只有一份 UB buffer，`copy → compute → copy` 完全串行。
**症状 B**：确实分配了两份 buffer（`side = i % 2`），但 stage 之间没有任何 `set_flag`/`wait_flag`。
**根因**：A 让「第 N 块的 Compute」无法与「第 N+1 块的 CopyIn」重叠；B 更隐蔽——**分配双份 buffer
只是给了并行的可能，没有 flag 就没有约束关系**，编译器不会替你排程，结果是数据竞争或退化为串行。
**做法**：`stages = 2`，并在每级之间配对事件：

| 事件 | 含义 |
| ------ | ------ |
| `mte3 → mte2` | 该 stage 已写回，可以重新搬入 |
| `mte2 → v` | 该 stage 输入已到，可以计算 |
| `v → mte3` | 该 stage 输出已算完，可以写回 |

收尾（最后一轮的 epilogue）必须单独写一次，不要在循环体里塞 `if tile < n-1`。
**不适用**：循环次数很少（< 2）时 pipeline 起停开销可能吃掉全部收益。

## 5. launch 核数两个方向都错 [参考]

见 [programming-model.md](programming-model.md) §6 第 5 项。两个方向都要防：任务数远大于核数
（按任务数 launch 会把初始化/workspace/地址/同步按任务数放大）与任务数小于核数
（空核照样进 kernel）。**物理核数必须现场探，不要写死**。

## 6. Vector 核内逐元素 / 逐行 for loop [参考]

**症状**：`for row in range(block_M): T.tile.sub(acc[row, :], acc[row, :], mx[row])`。
**根因**：每行单独发一条指令，Vector 利用率低，scalar 侧的地址计算、循环控制与指令下发开销全暴露。
**做法**：`T.tile.broadcast(mx_2d, mx_1d)` 把 `[rows]` 扩成 `[rows, block_N]`，再整 tile 一次算
`T.tile.sub(acc, acc, mx_2d)`。注意 broadcast 自身要吃一份 UB 临时 buffer。
**不适用**：行与行之间存在真实的数据依赖且无法数学等价重排。

## 7. `T.if_then_else` 让整段 `T.Parallel` 退化成标量 [参考]

**症状**：`for i, j in T.Parallel(bM, bN): y[i,j] = T.if_then_else(x[i,j] < t, approx(x[i,j]), full(x[i,j]))`。
**根因**：`T.if_then_else` 阻止 `ascend_lower_parallel` 向量化，**整个** `T.Parallel` 静默降级为串行标量
迭代——每 tile 数千次循环，而**没有任何报错**。
**做法**：先找数学等价变换消除分支。典型例子是 log-sum-exp：

```python
# ln(1 + exp(x)) 在 x 很大时溢出、x 很小时精度差
# 等价变形 + 全 T.tile.* 向量化：
T.tile.max(t1, a, 0.0)          # max(x, 0)
T.tile.abs(t0, a)               # |x|
T.tile.mul(t0, t0, -1.0)        # -|x|
T.tile.exp(t0, t0)              # exp(-|x|)
T.tile.add(t0, t0, 1.0)         # 1 + exp(-|x|)
T.tile.ln(t0, t0)
T.tile.add(out, t1, t0)
```

确实无闭式解时才允许保留分支，并在交付说明里标注这是已知性能代价。
区分于第 8 条：这条是"条件分支无法向量化"，第 8 条是"多条基础指令本可合成一条"。

## 8. 基础指令拼接未融合 [参考]

**症状**：`T.tile.mul(tmp, x, w)` 紧跟 `T.tile.add(acc, acc, tmp)`；`T.tile.max(out, x, 0.0)`；
`T.tile.sqrt(tmp, x)` 紧跟 `T.tile.div(out, one, tmp)`。
**根因**：多条基础指令本可由一条复合指令完成，白多吃一次 UB 往返与一次指令下发。
**做法**：改用复合原语（以 `tilelang/language/ascend_tile.py` 为准）：

| 现状 | 换成 | 语义 |
| ------ | ------ | ------ |
| `mul` + `add` | `T.tile.mul_add_dst(acc, x, w)` | `acc = x*w + acc` |
| `mul` + `add`（带标量） | `T.tile.axpy(dst, src, a)` | `dst = a*src + dst` |
| `max(x, 0)` | `T.tile.relu(out, x)` | ReLU |
| `sqrt` + `div` | `T.tile.rsqrt(out, x)` | `1/sqrt(x)`，要 `y/sqrt(x)` 再乘 `y` |

**风险**：融合会改变中间舍入路径，fp16/bf16 必须**重跑精度**；NaN 与边界行为也要重新确认。

## 9. 冗余全局同步 [参考]

**症状**：循环体内反复 `T.barrier_all()` / `T.sync_all()`。
**根因**：全局同步把无关的 pipeline / 核一起等，制造 MTE / Vector / Cube 气泡；放在内层循环时
开销被循环次数放大。
**做法**：删掉无依赖的同步；需要收窄范围时用 `T.set_flag(src, dst, event_id)` / `T.wait_flag`
（核内）与 `T.set_cross_flag` / `T.wait_cross_flag`（跨核）；结构化的流水交给 `T.Pipelined`。
**已开 `AUTO_SYNC` 时不要再手写 `barrier_all`**（[programming-model.md](programming-model.md) §2）。

## 10. AIC/AIV 混合未开 CV overlap [参考]

**症状**：`get_kernel_source()` 里同时出现 `IS_ASCEND_AIC` 与 `IS_ASCEND_AIV`，但主循环仍是
「Cube 写 workspace → Vector 读 workspace」的串行结构。
**根因**：Vector 等 Cube 产出、Cube 等 Vector 消费，两核互相空等。
**做法**：开 `AUTO_CV_COMBINE` + `AUTO_CV_SYNC`，并把主循环改成 `T.Pipelined(loop_k, num_stages=2)`。
`num_stages` 从 2 起逐步加，**不能超过循环次数**；不要嵌套多个 `T.Pipelined`。
同步开销占比高时可试 `cross_interval=2`，但要复测并行度是否反而下降。

## 11. 归约遍数过多（3-pass → 2-pass） [参考]

**症状**：softmax 类算子对归约维度扫三遍——求 max 一遍、求 sum 一遍、写输出再读一遍。
**根因**：每多扫一遍就多一次完整 GM 搬运；memory bound 场景下耗时几乎与遍数成正比。
**做法**：用 online 修正公式把前两遍合成一遍：

```text
初始化 m = -inf, s = 0
对每块 tile:
    m_new = max(m, max(tile))
    s     = s * exp(m - m_new) + sum(exp(tile - m_new))
    m     = m_new
```

总搬运量从 3×M×N 降到 2×M×N（约 −33%）。可泛化到：LogSumExp 2→1、Stable L2 Norm 2→1、
带数值稳定的归一化 3→2。
**前提**：归约维度远大于 UB 单次容量（否则一次装进去就不用分块了），且相邻两遍存在可推导的修正关系。
**坑**：`exp(m_old - m_new)` 在 fp16 下精度不足，**中间计算必须提到 fp32**；初始值必须是
`m = -inf`、`s = 0`；非整除时 `T.copy` 的 `pad_value` 必须是 `-inf`（否则污染 max）。

## 12. 多行 tile 循环内逐块归约 [参考]

**症状**：`for si in T.serial(s_num): ... T.reduce_sum(buf, col_buf, dim=-1); T.reduce_sum(col_buf, scalar, dim=0)`。
**根因**：两个问题叠加——每轮多发射两条归约指令，抵消多行 tile 带来的收益；更严重的是
**`reduce_sum(dim=0)` 作用在 `[rows, 1]` 形状上行为不确定，可能产出 NaN**。
**做法**：循环内只做 tile 间的逐元素累加（`T.tile.add(accum, accum, buf)`，accum 形状 `[rows, block_S]`），
循环外再做两步归约，且**只用 `dim=-1`**：

```text
[rows, block_S] --reduce_sum(dim=-1)--> [rows] --reduce_sum(dim=-1)--> 标量
```

前提是每个元素都在最内维连续；`dim=0`/`dim=1` 的列归约在二维完整矩阵上是另一回事（api-reference.md §5 可用），
本条的坑**只针对归约后只剩一维的 `[rows, 1]`**。

## 13. 正交轴被串行化（scan 类） [参考]

**症状**：`for r in range(rows): for i in range(1, L): if a[r,i] <= v[r,i-1]: ...`——内层是标量
`if` / `GetValue` / `SetValue`。
**根因**：扫描轴有真实依赖不能消，但**与扫描垂直的轴各元素彼此独立**，串行做等于放弃整个向量并行能力；
指令数随并行轴规模线性增长，icache miss 一起涨。
**做法**：先 transpose 让并行轴连续（`[rows, L] → [L, rows]`），再用向量比较把整行折叠成若干条
`T.tile.compare` / `T.tile.select` / `T.tile.min`，让 NaN 按语义正确传播。
**风险**：transpose 本身要求访存连续，且 2/4 字节类型才走硬件路径（[constraints.md](constraints.md) §5）。

## 14. 为迁就 kernel 强制 reshape 成 2D [参考]

**症状**：kernel 侧 `TORCH_CHECK(x.dim() == 2)`，于是 wrapper 必须先 `reshape` 成二维才能调。
**根因**：为了把目标 `dim` 挪到末尾被迫 `permute + contiguous`（回到第 1 条的全量拷贝）；
即使 `dim` 本来就是最后一维，强行 reshape 也丢掉了原始维度语义、用不上 stride 跨行。
**做法**：归一化 `dim = dim < 0 ? dim + ndim : dim`，累乘出 `outer`（`i < dim` 各维）与
`inner`（`i > dim` 各维），kernel 里用 `rowSize = dim_size * inner` 之类的行列跨度直接在 GM 上定位。

## 15. 纯 Vector 算子开 `AUTO_CV_COMBINE` 后误分核 [参考]

**症状**：`get_kernel_source()` 只有 `IS_ASCEND_AIV`，却同时开了 `AUTO_CV_COMBINE`，且 kernel 用了
`T.alloc_var`；运行结果异常或编译失败。
**根因**：某些 lowering 形态会把 `alloc_var` 的定义与使用分到不同核上。**这不是必然失败的规则**。
**做法**：先看生成代码或做最小复现，确认变量确实跨核且未正确传递；确认后才关掉这个不需要的开关，
保留 `AUTO_SYNC` 与 `MEMORY_PLANNING`。默认写法见 [op-patterns.md](op-patterns.md) §1。

---

## 优化纪律

1. **一次只改一个点**，改完立即复测精度 + 性能。多点混改则结论不可归因。
2. **精度未过禁止开始调优**。
3. 计时只用 `msprof op`，Python 计时只能粗筛、不得作为结论：

   ```bash
   msprof op --kernel-name="main_kernel" --output=./msprof_output python <你的脚本>.py
   ```

4. **性能哨兵必须实跑**：取最大 dtype + 最大 shape 的用例计时，不得只测最小 case，
   也不得因为耗时长而跳过——跳过就等于没有性能结论。
5. 多个优化点同时待做时先写 `[ORDER-PLAN]`：布局依赖（改 layout 的排在其消费者之前）→
   数量依赖（涉及预算的排在改 buffer 数量的之后）→ 配置依赖（`pass_configs` 留到功能生效后再调）。
6. **连续 3 轮无提升即停并上报**，不要无限试。
7. 关键判据看 **GM 读字节数**与总耗时，而不是只看 wrap 时间：归约融合应能看到读量约 −33%。
