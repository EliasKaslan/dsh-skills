# Ascend 硬件约束、坑位与故障速查

## 1. 内存层级（不可跨级）

```text
GM ──T.copy──▶ L1（Cube 核）──▶ L0A/L0B ──▶ L0C ──T.copy──▶ GM
GM ──T.copy──▶ UB（Vector 核）──▶ GM
```

- UB→L1、L0C→UB 存在专门的跨 C/V 直通路径：`copy_op.py:197-205` 的 `_is_cross_cv_copy` docstring 明写 "UB→L1 or L0C→UB only"，`copy_op.py:410` 的 `copy_cv_experiment` 为 L0C→UB 的 TMOV 直拷（注释标 "PTO A5 only"）。除这两条外，C↔V 交互仍须经 GM workspace 或 Developer 模式片上直连。
- 容量（910B）：UB 192KB、L1 512KB、L0A/L0B 64KB、L0C 128KB。分配超限编译报错。⚠️ **L1/L0C 数值有冲突且谁权威未证实**：本行数字有 Ascend 侧依据（`testing/python/language/test_tilelang_ascend_language_l1_to_l0.py:26-37` 记 910B3 为 L1 512KB / L0C 128KB），但 `tilelang/carver/arch/ascend.py:34-43` 的 `CHIP_SPECS["Ascend910B"]` 记 L1 1024KB、L0C 512KB（该表 910A/310P 的 L0C 均 256KB，910B 是孤例）。保留文档数值，以 `npu-smi` / 官方规格为准。
- 对齐：UB/L1 32B；L0A/L0B 512B；L0C 64B。
- **以上是 910B 口径**。换平台（其它 SoC/die）必须重新确认容量与核数，不要把这里的数字套过去；
  UB 可用额度可直接用运行时 `GetCoreMemSize(UB)` 取真实值，其余层级以编译报错为准。

## 2. GEMM 分形限制

L0A/L0B 分形 512B、L0C 分形 16×16。`block_M/block_N ≥ 16` 恒成立；fp16 `block_K ≥ 16`、fp32 `≥ 8`、int8 `≥ 32`。不满足会**结果错误而不报错**。分形数值有 Ascend 侧依据：`testing/python/language/test_tilelang_ascend_language_l1_to_l0.py:39-42` 逐行列出 fp16/bf16 → L0A、L0B 均 16x16（K ≥ 16）、int8/uint8 → L0A 16x32 / L0B 32x16（K ≥ 32）、int32/float32 → L0A 16x8 / L0B 8x16（K ≥ 8）。

## 3. T.copy 限制

- 底层 DataCopyPad：行内连续、行间可有 gap。切片列维必须是最内维，否则会**数据错位**（“静默”即不报错这一半未证实）。
- 尾块两条路都可用，**「只传起始下标 + 完整 UB」是可靠的**：常量 extent 的 `T.copy(A[base_m, n0], ub)` 写法由 lowering 按 `min(extent, dim - off)` 自动裁剪，实测 N 尾块 `(M=64, N=130, block_N=128)` 与 M 尾块 9 组组合全部 PASS（矩阵见 §9.1）。
- 要走显式 region（`valid = T.max(T.min(block, dim - off), 0)`，输入输出两侧都写）也可以，但**钳位 `T.max(..., 0)` 不能省**：写成 `valid = T.min(block, dim - off)` 时，M 维被 `vid` 分片越过 M 的那个行块会得到**负 extent** 并报 507015（实测复现，见 §9.2）。
- 尾 tile 写重叠：用自动裁剪时由 lowering 负责裁剪范围；要额外收紧再手写 valid extent。

## 4. T.Parallel / SIMD 限制

- 仅 1D/2D 并行；循环边界须编译期常量；不支持 `if/else`。`T.if_then_else` **能写但会静默降级**：
  它阻止 `ascend_lower_parallel` 向量化，整个 `T.Parallel` 退化为串行标量（不报错、只是慢几十倍）。
  改用 `compare`+`select`，或做数学等价变换后全用 `T.tile.*`。
- 离散索引（`a[idx[i]]`）退化为标量 serial 循环，性能骤降——大张量主路径禁止。
- 动态 loop 边界（运行时变量）在 Ascend 上受限：优先把 stride/shape 作为 `@tilelang.jit` 的 Python 参数（编译期常量）传入，kernel 内用 `T.alloc_var` 累加偏移，而不是打包成 int32 GM tensor 传入。

## 5. dtype 与硬件路径

- fp16/bf16 输入建议升 fp32 计算、`CAST_NONE` 升 / `CAST_RINT` 降，保证精度。
- `T.tile.transpose` 硬件路径仅 2/4 字节（B16：fp16/int16/uint16；B32：fp32/int32），int8 与 bf16 退化为标量实现（依据 `ascend_tile.py:1618-1645` docstring 原文 "Supports B16 and B32 via hardware instruction; int8 and bfloat16 fall back to scalar implementation"）；bf16 用 host `view(torch.int16)` 零拷贝（仅纯搬数据）；int8 kernel 内 cast 到 fp16；int64 用聚合 DMA 或块 DMA + UB 重排（未证实）。禁止 host `.to(dtype)` / `.contiguous()`。
- `T.tile.compare` 对 int32 仅 EQ 有效（**未证实**：Python 层 `compare` 接受 EQ/NE/GT/GE/LT/LE，无 int32 限制）；先 cast fp32。NaN 在所有 mode（含 EQ）返回 False。
- `select` 的 SPR 模式 N≤64 且非 int32，否则用 TENSOR_TENSOR_MODE（**硬件行为断言，仓库内查无依据、未证实**，按经验值用）。另：`sel_mode` 须与 `src1` 类型匹配——`src1` 为标量时只能 VSEL_TENSOR_SCALAR_MODE。

## 6. host 侧 Buffer 操作红线（生成/评审时逐条核对）

算子的核心计算必须全部在 kernel 内。host 侧只允许：

1. 元数据视图：`reshape/view/transpose/permute/expand`（不物理拷贝）。
2. 输入准备（CPU 上生成随机数/特殊值）、kernel 调用、结果验证（D2H）。

禁止（否则直接改）：

- 重绑 tensor 的 `data_ptr` 后传 kernel；
- 真实拷贝/重排：`.contiguous()`、`torch.cat/stack`、`F.pad/interpolate`；
- host 改写数据：`x[:] =`、in-place `_()`、`out=`；
- 用「新建 buffer → host 处理 → 替换原 tensor」作弊；
- 隐式 aclnn：`.to(dtype)`、`.clone()`、非 contiguous 切片后 reshape。

需要裁剪 padded 输出时，改为 kernel 直接输出到目标 shape 的 buffer（`T.copy` + `pad_value` 处理尾块）。

## 7. 故障速查

| 症状 | 常见原因 | 处理 |
| ------ | --------- | ------ |
| 编译报 buffer 超限 | UB/L1/L0 分配超容量 | 缩小 block，或开 MEMORY_PLANNING |
| 编译报错（API 参数） | 签名/参数记错 | 查 api-reference.md；读 `get_kernel_source()` |
| `T.Scope` 与 AUTO_CV_COMBINE 冲突 | 同时手写 Scope | 二选一 |
| 结果错误但无报错 | 分形不满足；copy 列维非最内维；同步缺失 | 按 §2/§3 复核 |
| 索引越界（OOB） | 未钳位的运行时 extent 变负（M 维 vid 分片越过 M）；vid 偏移错误 | 按 §3 与 §9.2 复核 |
| 精度差 | fp16 直接算；golden 实现不一致 | fp32 中间计算；核对 golden |
| ImportError / set_env 相关 | 未 source CANN/set_env.sh | 按 testing.md §3 设置 |
| 性能远低于基线 | 未 V 核并行；无流水线；标量主路径 | 按 programming-model §6 检查 |
| `GetValue/SetValue` 满屏 | 降级为标量路径 | 检查 dtype 硬件路径（§5）、索引写法（§4） |

## 8. 生成代码后的强制自查

本机自查只覆盖"代码能不能跑对"，**交付判定要看 [acceptance-checklist.md](acceptance-checklist.md)**。生成后先过这四条：

1. host 侧红线（§6）逐条过，并打印 `[HOST-METADATA-AUDIT]` 证据块（格式见 checklist §0）。
2. 每条 dtype/路径用 `kernel.get_kernel_source()` 确认走硬件向量指令而非标量回退。
3. 分形（§2）、对齐、UB/L1 预算（§1）计算一遍并写注释。
4. 尾块路径单独构造非整除 shape 用例实跑。

## 9. 尾块（非整除 shape）实测约束 ⚠️

以下结论来自 CANN 9.1.0 + ascendc_pto（commit 74cf793）在昇腾 NPU 上的实测。实验配方统一为
op-patterns.md §3.1 的 softmax（`block_N = N`，只让 M 不整除），**一组 shape 一个进程**
（aicore 异常会直接杀进程，合并跑会丢结果），命令：

```bash
python case1.py {impl} {M} {block_M} 128 128
```

> **复测（2026-10-26，`ascendc_pto` commit `43b0b69` / CANN 9.1.0 / npu-smi 25.5.1）**：按
> `assets/test_template.py` 与 §3.1 配方写出的 softmax 走完整 `--level all` 一次通过 ——
> L0 fp16/bf16/fp32 各 1 例、L1 尾块 `(65,256)/(96,320)/(97,251)/(1,256)`、
> l2 正确拒绝 int8 dtype、boundary 的 zero/inf/nan 三例、perf `(512,1024)` 165.8 us，
> 全部 `[PRECISION_PASS]` / `[BOUNDARY_PASS]`，与本节结论一致（含 `M=1` 这种 M 远小于
> `block_M=64` 的极端尾块，未出现 507015 或负 extent）。

### 9.1 配方写法（常量 extent）实测：**不触发越界**

「`M % block_M != 0` + 按 `vid` 分片 ⇒ MTE 越界（507015）」这一断言**已被证伪**：

| M | block_M | M % block_M | 结果 | matched_ratio |
| --- | --- | --- | --- | --- |
| 128 | 32 | 0（整除） | PASS | 1.0000 |
| 100 | 32 | 4 | PASS | 1.0000 |
| 90 | 32 | 26 | PASS | 1.0000 |
| 80 | 32 | 16 | PASS | 1.0000 |
| 48 | 32 | 16 | PASS | 1.0000 |
| 65 | 64 | 1 | PASS | 1.0000 |
| 100 | 64 | 36 | PASS | 1.0000 |
| 20 | 64 | 20（M < block_M） | PASS | 1.0000 |
| 1000 | 32 | 8 | PASS | 1.0000 |

9 组（含 `M < block_M`、余数 1/4/8/16/20/26/36）全部 PASS、精度判据全过、退出码 0、无任何 aicore 异常。
原因：配方里 copy 的 extent（`sub_M` / `block_N`）是**编译期常量**，lowering 按 `min(extent, dim - off)`
裁剪，越界行进 `pad_value` 兜底——它不会自己算出负 extent。

### 9.2 真正会触发 507015 的条件（已复现）

**把「剩余行数」这类运行时值不加钳位直接当 copy extent**：

```python
valid_m = T.min(sub_M, M - base_m)      # 漏了 T.max(..., 0)
T.copy(A[base_m:base_m + valid_m, n0:n0 + block_N], a[0:valid_m, 0:block_N])
```

M 维比 N 维多一层 `vid` 分片：`base_m = bx * block_M + vid * sub_M`，`vid * sub_M` 可以越过 M，
所以 `M - base_m` 可能为负。记 `rem = M - (ceildiv(M, block_M) - 1) * block_M`
（最后一个行块的实际行数，`1 ≤ rem ≤ block_M`）、`sub_M = block_M / 2`：

| rem 与 sub_M | valid_m（vid=1） | 结果 |
| --- | --- | --- |
| `rem < sub_M` | **负** | **FAIL：507015** |
| `rem == sub_M` | 0 | PASS |
| `rem > sub_M` | 正 | PASS |

实测（`impl=softmax_negext`，同一 runner、同样只改 extent 写法）：

| M | block_M | rem | valid_m | 结果 |
| --- | --- | --- | --- | --- |
| 128 | 32 | 32 | 16 | PASS |
| 96 | 32 | 32 | 16 | PASS |
| 90 | 32 | 26 | 10 | PASS |
| 80 | 32 | 16 | 0 | PASS |
| 100 | 64 | 36 | 4 | PASS |
| 100 | 32 | 4 | **-12** | **FAIL 507015** |
| 1000 | 32 | 8 | **-8** | **FAIL 507015** |
| 20 | 64 | 20 | **-12** | **FAIL 507015** |
| 65 | 64 | 1 | **-31** | **FAIL 507015** |
| 80 | 64 | 16 | **-16** | **FAIL 507015** |

错误原文（截断）：

```text
RuntimeError: npuSynchronizeDevice:torch_npu/csrc/core/npu/NPUStream.cpp:575
NPU function error: AclrtSynchronizeDeviceWithTimeout, error code is 507015
```

同一条日志里还出现 `aicore exception`、`EZ9999`、`out of bounds`。注意失败是**异步**的：
kernel 调用本身返回正常，要在 `torch.npu.synchronize()` 处才抛出——所以尾块用例必须显式同步，
否则会把崩溃误判成 PASS。

### 9.3 修法（按推荐排序）

1. 用**常量 extent** 的「起始下标 + 完整 UB」写法（即 op-patterns.md §3.1 配方原样），
   由 lowering 裁剪——实测最稳（§9.1 九组全过）。
2. 要显式控制时把 extent **钳到非负**：`valid = T.max(T.min(block, dim - off), 0)`，输入输出两侧都写
   （实测 M=90、M=100 的显式切片写法 PASS）。
3. 选整除 M 的 `block_M`（必要时用 host 传参时对齐 M 到 block 倍数，禁止 host padding 数据）。
4. 用 layer_norm/softmax 式的**串行累加结构**：1D grid + `T.serial(n_num)` 循环且循环体跨迭代累积
   （`sum += tile`），该结构不会触发坏化简（仓库 `examples/normalization/layer_norm.py` 验证 M=34 通过）。
5. 尾块单行退回：`if vid == 0:` 单独处理剩余行（`if vid == 0` 是运行时标量条件，可用）。

### 9.4 本次未能复现的旧断言

- **「`if valid_m > 0:` 守卫会被错误化简并丢弃钳位、产生负 extent」→ 未复现**。
  两种写法在 §9.2 里未钳位必崩的同一 shape（M=100、block_M=32）上均 PASS：
  - 钳位在守卫外：`valid_m = T.max(T.min(sub_M, M - base_m), 0)` 后再 `if valid_m > 0:`（M=128/100/90 PASS）；
  - 钳位在守卫内：`if valid_raw > 0:` 后 `valid_m = T.max(valid_raw, 0)`（M=100/1000/20 PASS）。
  后者在逻辑上也不该崩：守卫 `valid_raw > 0` 已经蕴含钳位结果为正，编译器丢弃这个冗余钳位是**语义等价**的化简。
  保留此条作为待观察项，但不要再据此建议「别用守卫」。
- **0 行拷贝（extent=0）本身是安全的**：`rem == sub_M` 时 `valid_m == 0`，实测 M=80/block_M=32 PASS。
  危险的是**负** extent。
