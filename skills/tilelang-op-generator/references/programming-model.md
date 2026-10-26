# 编程模式与 pass_configs

## 1. Developer vs Expert vs 混合

| 维度 | Developer（自动化） | Expert（手动控制） |
| ------ | -------------------- | -------------------- |
| 内存分配 | `alloc_shared` / `alloc_fragment` | `alloc_ub/L1/L0A/L0B/L0C` |
| 计算（惯用写法，非判据） | `T.Parallel` + 符号运算 | `T.tile.xxx` 原语 |
| 作用域 | 编译器自动分离 C/V | 手动 `with T.Scope("C"/"V")` |
| 同步 | 编译器自动插入 | 手动 `barrier_all` / `set_flag` / `wait_flag` |
| CV 交互 | `threads=2` + 片上直连（无 workspace/vid） | GM `workspace` + 手动 `vid` |
| pass_configs | 按 §2 选择（含 Cube 的算子 4 个全开） | 全关或不设 |
| 适用 | 快速开发、原型、跨平台 | 极致性能、需要精确控制 |

**判据只有一条：是否需要手动控制内存层级与同步。**
不是"用了哪个 API"——`T.tile.*` 与 `T.reduce_max/sum/min` 在两种模式下都能用，在 Developer 的
pass_configs 下正常工作（见 op-patterns.md 的多步 Vector 配方）。出现 `T.Scope` / `barrier_all` /
`set_flag` / `workspace_idx` / 手动 `vid` 偏移，就是 Expert 或回退写法；都没有才是 Developer。

**混合模式（推荐默认）**：Developer 主体（自动同步/内存规划）+ 关键路径少量 `T.tile.xxx` 原语，仍走 Developer 的 pass_configs，不写 `T.Scope` 与手动同步。绝大多数实际算子用它。

## 2. pass_configs 按场景选择

先记住口径（与 SKILL.md §3.2、op-patterns.md §1/§3 同一口径）：

四个键**默认都是 False**（底层键名与默认值见 api-reference.md §9），即"不写就不开"，所以必须显式打开。

- `TL_ASCEND_AUTO_SYNC`、`TL_ASCEND_MEMORY_PLANNING`：**与算子类型无关，适用于所有算子**。
- `TL_ASCEND_AUTO_CV_COMBINE`、`TL_ASCEND_AUTO_CV_SYNC`：**只在同时含 Cube 与 Vector 工作的算子上才有意义**。
  纯 Vector 算子**默认不开**。实测在纯 Vector 算子上「开 3 键」与「开 4 键」都能编译通过、精度判据同为
  `matched_ratio=1.0000`、退出码同为 0 且输出逐位相同——所以开了也**没有收益**；但 kernel 用到
  `T.alloc_var` 时存在"该变量的定义与使用被分到不同核"的已知风险（不是必失败，但排查代价高）。
  **结论：纯 Vector 不开 CV 两键；若已开且遇异常，先关它再排查，不要先去改算法。**
  **不必为了「凑齐 4 个」而把 CV 键补上。**

| 场景 | AUTO_SYNC | MEMORY_PLANNING | AUTO_CV_COMBINE | AUTO_CV_SYNC |
| ------ | ----------- | ----------------- | ----------------- | -------------- |
| 纯 Vector（elementwise/reduction/softmax/norm 单核） | ✅ | ✅ | ❌（无收益且有 alloc_var 风险） | ❌ |
| 纯 Vector 多步（softmax/norm 分块扫描） | ✅ | ✅ | ❌ | ❌ |
| GEMM / Developer CV 融合 / Developer FlashAttention | ✅ | ✅ | ✅ | ✅ |
| 混合模式 CV 融合 | ✅ | ✅ | ❌ | ❌（手动 Scope） |
| Expert 极致性能 | ❌ | ❌ | ❌ | ❌（手动同步） |

注意：

- 开 AUTO_CV_COMBINE 时禁止手写 `T.Scope`。
- 开 AUTO_SYNC 时禁止手写 `T.barrier_all`。
- 只有**同时含 Cube 与 Vector** 的算子，第 3、4 个键才有实际作用——纯 Vector 算子不写它们不影响正确性。

## 3. Developer 模式 CV 融合：消除 workspace/vid

Developer 模式默认不写 GM workspace、不手动二分 vid，前提链：

```text
threads=2 → vid 消除 → workspace 消除
```

四步：

1. `T.Kernel(block_num, threads=2, is_npu=True) as (cid)`（编译器自动并行 2 个 V 核）。
2. 删 `workspace_idx=[...]` 与 kernel 签名中的 workspace 参数。
3. 删 `vid * ...` 索引偏移，循环恢复整程。
4. Cube↔Vector 改片上 `T.copy` 直连（`alloc_shared`/`alloc_fragment`），中转与同步交给 4 个 pass。

复杂同步/多版本流水场景可回退 workspace+vid 写法：`@jit(out_idx=[-1], workspace_idx=[3])`，签名含 workspace 参数，C 核写 workspace、V 核读 workspace。

## 4. Expert → Developer 转换对照

| Expert | Developer |
| -------- | ----------- |
| `T.alloc_L1 / alloc_ub` | `T.alloc_shared` |
| `T.alloc_L0A/L0B/L0C` | `T.alloc_fragment`（gemm_v0 内部处理 L0A/B） |
| `with T.Scope("C"/"V")` | 删除（编译器自动） |
| `T.barrier_all / set_flag / wait_flag` | 删除 |
| `T.set_cross_flag / wait_cross_flag` | 删除 |
| `T.annotate_address(...)` | 删除（开 MEMORY_PLANNING） |
| `@jit(..., workspace_idx=[...])` | 删除 + `threads=2` 片上直连 |
| `T.Kernel(..., is_npu=True) as (cid, vid)` | `T.Kernel(..., threads=2, is_npu=True) as (cid)` |
| `T.tile.exp(dst, src)` | `for i,j in T.Parallel(...): dst[i,j]=T.exp(src[i,j])`（或保留） |

## 5. V 核并行（示例内的局部常量 `VEC_NUM=2`）

每个 AI Core 有 1 个 Cube 核 + 2 个 Vector 核（硬件规格，仓库源码未编码）。两个 V 核默认执行相同代码 → 浪费一半算力。

> `VEC_NUM` **不是框架 API**，而是各示例文件内自定义的局部常量（仓库示例恒取 2，如 `examples/pipeline/matmul_add_pipeline.py:22`、`examples/pipeline/gemm_v0_pipeline.py:25`）。框架侧 `tilelang/` 全目录 `grep VEC_NUM` 零命中；`vid` 的取值范围 0/1 由 `T.Kernel(...) as (cid, vid)` 给出。

**按行切分**（最常见）：

```python
VEC_NUM = 2
sub_M = block_M // VEC_NUM
with T.Kernel(grid, is_npu=True) as (cid, vid):
    row = bx * block_M + vid * sub_M          # 每核负责 sub_M 行
    a_ub = T.alloc_ub((sub_M, block_N), dtype)
    T.copy(A[row, by * block_N], a_ub)
    ...                                        # 计算
    T.copy(c_ub, C[row, by * block_N])
```

铁律：load/compute/store 必须用同一 `row` 基址；workspace 读写索引逻辑必须一致。Cube 核部分（gemm_v0）不参与 vid 切分，读完整 block。

## 6. 五项可度量性能门禁（不是"看起来快"，是能判达标）

`性能 = 有用数据量 / (有用数据量 + 固定开销)`。下面五项是固定开销的五个来源，逐项有达标线和度量方法；
**任一项不达标就不是"最优实现"**，改完每轮都要重查：

| # | 检查项 | 怎么量 | 达标标准 | 不达标的典型代价 |
| --- | -------- | -------- | ---------- | ------------------ |
| 1 | 冗余搬运 | host `forward()` 里的全量拷贝次数 | **= 0** | dim≠-1 时 10~30 倍劣化 |
| 2 | 单次 DMA 传满 | kernel 里 `T.copy` 是否有逐行循环 | **无逐行循环** | 同形状下延迟差 20~30 倍 |
| 3 | 每个 tile 算满 | 实际有效元素 / tile 容量 | **≥ 80%** | 小末尾维 10~30 倍劣化 |
| 4 | 流水线不空转 | 各级 buffer 的 stage 数 | **≥ 2** | 计算密集型约 20~30% |
| 5 | 多核不空闲 | 实际参与计算的核数 / 可 launch 核数 | **≥ 90%** | 并行度直接损失 |

第 5 项的两个方向都要防（现场探核数，**不要写死**——不同 SoC/die 的物理核数不同，实测口径里
20 与 24 都出现过）：

- 任务数 **远大于** 核数却按任务数 launch：kernel 初始化、workspace 分配、地址与同步开销全部按
  任务数放大，而同一时刻只有核数个任务在跑 → 改成「按核数 launch + 核内循环跑多任务」，
  循环体里用 `if block_idx < block_num` 防越界。
- 任务数 **小于** 核数却按最大值 launch：空核仍会进 kernel 执行初始化与分支 → 改成
  `launch_core_num = T.min(block_num, core_num)`（或 host 侧 `min(block_num, core_num)`）。

第 3 项顺带约束了尾块：`T.ceildiv` 只决定块数，末块有效数据可能远小于 tile 容量。末块占比高时
（例如 `N = block_N * k + 1`）应改用更小的 block 或把尾块单独走一条路径，否则有效算力被摊薄。

## 7. 生成时就要满足的最低标准

- [ ] V 核并行已做（纯 Vector 算子），或 `threads=2` 自动并行（Developer）。
- [ ] GEMM/多级循环用了 `T.Pipelined(..., num_stages≥2)` 或双缓冲，且 pipeline 边界是编译期常量。
- [ ] 含 Cube 的算子开了 AUTO_CV_COMBINE + AUTO_CV_SYNC（或等价手动流水）。
- [ ] block 在内存预算内取分形倍数（见 api-reference.md §4），且第 3 项 ≥ 80%。
- [ ] 尾块用动态切片而非 host padding（不额外搬运、不越界）。
- [ ] GM↔片上用最大块的二维 `T.copy`，无逐元素标量搬运主路径（第 1、2 项）。
- [ ] launch 核数按 §6 第 5 项处理，不按任务数硬套。
- [ ] host 侧无真实数据搬运冒充算子实现。

逐条的症状/根因/修法见 [perf-antipatterns.md](perf-antipatterns.md)。
