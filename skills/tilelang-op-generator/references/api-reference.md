# TileLang-Ascend API 速查（ascendc_pto 路线）

> 本文档对应 `tilelang-ascend` 仓库 `ascendc_pto` 分支。写 kernel 前先查这里；若签名与仓库不符，以仓库源码 `tilelang/language/ascend.py`、`ascend_tile.py`、`reduce_ascend.py` 为准。

## 目录

- [1. Kernel 定义与启动](#1-kernel-定义与启动)
- [2. 内存分配](#2-内存分配)
- [3. 数据搬运 T.copy](#3-数据搬运-tcopy)
- [4. 矩阵计算](#4-矩阵计算)
- [5. 归约](#5-归约)
- [6. 逐元素与 T.tile 原语](#6-逐元素与-ttile-原语)
- [7. 循环与流水线](#7-循环与流水线)
- [8. 同步与作用域](#8-同步与作用域)
- [9. pass_configs](#9-pass_configs)

## 1. Kernel 定义与启动

```python
import tilelang
from tilelang import language as T

@tilelang.jit(out_idx=[-1], target="pto", pass_configs=pass_configs)
def my_op(M, N, block_M, block_N, dtype="float16"):
    @T.prim_func
    def main(A: T.Tensor((M, N), dtype), C: T.Tensor((M, N), dtype)):
        with T.Kernel(T.ceildiv(M, block_M) * T.ceildiv(N, block_N), is_npu=True) as (cid, vid):
            ...
    return main
```

- `@tilelang.jit`：`out_idx` 指定输出参数下标（`[-1]`=最后一个）；`target="pto"` 选择 PTO 代码生成目标（本文档对应的 `ascendc_pto` 分支），**它不是 Developer/Expert 模式开关**——实测本分支上加与不加编译与精度一致，按示例保留即可；`pass_configs` 见 §9。
- `T.Kernel(block_num, threads=2, is_npu=True) as (cid)`：`threads=2` 让编译器自动并行 2 个 V 核；
  不带 `threads` 时用 `as (cid, vid)` 手动区分，`vid` ∈ {0,1}——每 AI Core 含 1 个 Cube 核 + 2 个
  Vector 核，属硬件规格、仓库源码未编码。两种写法的对应关系见
  [programming-model.md](programming-model.md) §3/§4。
- ⚠️ **`T.Kernel` 的网格必须是一维**（第一个实参是标量表达式）。三维网格不可用——多轴任务一律
  自己折算成一个轴（`bx = cid // n_num; by = cid % n_num`）或用 `block_metadata` 预计算表。
- 矩阵乘用 `T.gemm_v0`；`T.gemm` 在本分支**可能不支持**，不要用（见 §4）。
- 动态 shape：用 `T.symbolic("K")`，等价 `T.symbolic("K", "int32")`（`tilelang/language/__init__.py:89`，内部返回 `tir.Var`），可直接作为 `T.Tensor((M, K), dtype)` 的维度。**注意：`T` 命名空间下没有 `dyn`，也没有 `dynamic`** —— 运行时 `hasattr` 对这两个名字均为 False，全仓亦无其定义；照抄旧写法会直接 AttributeError。仓库示例有 93 处 `T.symbolic` 用法，可参照 `examples/pipeline/sparse_flash_attn_gqa_pipeline_pto.py`。
- 编译后调试：`kernel = my_op(...)`；`kernel.get_kernel_source()` 查看生成的 AscendC 代码。

## 2. 内存分配

| API | 层级 | 说明 |
| ----- | ------ | ------ |
| `T.alloc_shared(shape, dtype)` | shared（自动 L1/UB） | Developer 模式 |
| `T.alloc_fragment(shape, dtype)` | fragment（自动 L0A/B/C） | Developer 模式 |
| `T.alloc_var(dtype, init=...)` | 标量 | 标志位/计数器 |
| `T.alloc_ub(shape, dtype)` | UB（V 核） | Expert |
| `T.alloc_L1(shape, dtype)` | L1（C 核） | Expert |
| `T.alloc_L0A / L0B / L0C(shape, dtype)` | 矩阵寄存器 | Expert |

容量上限（910B）：UB 192KB，L1 512KB，L0A/L0B 64KB，L0C 128KB。对齐：UB/L1 32B，L0A/L0B 512B，L0C 64B。

> **这套数字是 910B 口径，换平台必须重新确认**（见 [../SKILL.md](../SKILL.md) §0）。UB 的实际可用额度
> 可以用运行时接口 `GetCoreMemSize(UB)` 问出来——它返回的是该卡该 die 的真实上限，比查表可靠；
> 其它层级没有等价接口时以编译报错为准（分配超限会直接编译失败，不会静默截断）。
>
> ⚠️ **L1/L0C 数值存在冲突，谁权威未证实，不可单方面采信任何一边。** 本行数字有 Ascend 侧依据：`testing/python/language/test_tilelang_ascend_language_l1_to_l0.py:26-37` 记 Ascend910B3 为 L1 512KB / L0C 128KB / UB 192KB / L0A、L0B 各 64KB。但编译器自带的 `tilelang/carver/arch/ascend.py:34-43`（`CHIP_SPECS["Ascend910B"]`，单位字节）记 L1 `1024 * 1024`、L0C `512 * 1024`；该表中 Ascend910A 与 Ascend310P 的 L0C 均为 `256 * 1024`，910B 的 512KB 是孤例，疑似把 L1 的值复制到了 L0C。本文**保留文档数值**，实际以 `npu-smi` / 华为官方规格为准；分配是否超限最终以编译报错为准。

## 3. 数据搬运 T.copy

`T.copy(src, dst)`，src/dst 可为 buffer、BufferLoad（起始下标）或 BufferRegion（切片）。合法路径：

| src | dst |
| ----- | ----- |
| GM | L1 / UB |
| L1 | L0A / L0B |
| L0C | GM |
| UB | GM / UB |
| UB | L1（跨 C/V 直通，见下） |
| L0C | UB（跨 C/V 直通，见下） |

**UB 与 L1 之间没有通用直通路径，但源码存在专门的跨 C/V 直通**：`tilelang/language/copy_op.py:197-205` 的 `_is_cross_cv_copy` docstring 原文为 "Check if this is a cross-CV copy (UB→L1 or L0C→UB only)"，即显式支持 **UB→L1**；`copy_cv_experiment`（`copy_op.py:410`）为 **L0C→UB** 的 TMOV 直拷，注释标 "L0C to UB direct copy using TMOV (**PTO A5 only**)"。常规做法仍是 C/V 核间数据经 GM `workspace` 中转，或 Developer 模式 `threads=2` + 片上直连让编译器处理。

尾块用动态切片（不要 host padding），**显式 region 的 extent 必须钳到非负**：

```python
valid_m = T.max(T.min(block_M, M - bx), 0)
valid_n = T.max(T.min(block_N, N - by), 0)
T.copy(A[bx:bx+valid_m, by:by+valid_n], a_ub[0:valid_m, 0:valid_n])
T.copy(b_ub[0:valid_m, 0:valid_n], C[bx:bx+valid_m, by:by+valid_n])
```

N 维 `by < N` 恒成立，故 `N - by` 永不为负；M 维在 `vid` 显式分片下 `bx` 可越过 M 才可能为负。
漏钳位使 extent 变负会报 MTE 越界 507015，且它是**异步**的——kernel 调用本身正常返回，
要到 `torch.npu.synchronize()`（或任何 device 同步点）才抛，真触发条件与实测矩阵见
[constraints.md](constraints.md) §9.1/§9.2。不写显式 region、交给 lowering 自动裁剪时则无此风险。

`pad_value=` 参数可指定越界填充值（如 softmax 用 `-T.infinity(dtype)`）。

**多维切片限制**：`T.copy` 底层是 DataCopyPad，要求每行内连续（行间可有 gap）。切片中“列维”必须是最内维，否则会数据错位（**“静默”即不报错这一半未经证实**）。4D+ 非最内维切片需改布局或分阶段搬运。

## 4. 矩阵计算

`T.gemm_v0(A, B, C, transpose_A=False, transpose_B=False, init=False, kL0Size=128, n_actual=None)`：`C += op(A) @ op(B)`，A/B 在 L1/shared，C 在 L0C/fragment，K 维循环内第一次迭代 `init=True`。`kL0Size` 须为 16 的倍数且 ≤ 4095；源码 docstring（`tilelang/language/ascend.py:418-470`）原文为 "Normally you don't need to change this"，仅在 L0C 利用率不足或想开双缓冲时调优（fp16 + block_M=128/block_N=256 时建议 64）。**「默认 128 与 block_K 不一致会读到未初始化数据」这一理由未证实**（仓库内无依据），故不强制显式传参。

分形限制（必须满足，否则结果错）：

| dtype | L0A/L0B 分形 | 最小维度 |
| ------- | ------------- | --------- |
| fp16/bf16 | 16×16 | M≥16, K≥16, N≥16 |
| fp32 | 16×8 / 8×16 | M≥16, K≥8, N≥16 |
| int8 | 16×32 / 32×16 | M≥16, K≥32, N≥16 |

上表按 dtype 分化的分形**有 Ascend 侧依据**：`testing/python/language/test_tilelang_ascend_language_l1_to_l0.py:39-42` 原文为 "Fractal constraints (M / N >= 16 always; K depends on dtype)"，逐行列出 float16/bfloat16 → L0A、L0B 均 16x16（K ≥ 16）、int8/uint8 → L0A 16x32 / L0B 32x16（K ≥ 32）、int32/float32 → L0A 16x8 / L0B 8x16（K ≥ 8）。通用 L0C 分形 16×16 见 `tilelang/carver/arch/ascend.py:42` 的 `"cube": [16, 16, 16]`。

> ⚠️ **K 下限存在两套上游口径，本文件采信带源码出处的一套。** 上游 TileLang 技能资料另有一处写
> 「L0A `M≥16`/`K≥32`、L0B `K≥32`/`N≥16`」，即不分 dtype 一律 `K ≥ 32`；该说法与本仓
> `test_tilelang_ascend_language_l1_to_l0.py:39-42` 的逐 dtype 表冲突（且与它自己另一处
> "fp16 block_K ≥ 16" 也自相矛盾）。**做法**：按上表取值；若实测编译报分形/对齐错，再把 `block_K`
> 抬到 32 的倍数重试——这是唯一低成本的收敛路径。

L0C 分形固定 16×16，故 block_M、block_N 恒 ≥16。`T.mma` 是更底层指令，实测签名为 `T.mma(A, B, C, init=False, n_actual=None, unit_flag=None, k_actual=None)`（`tilelang/language/customize.py:115`，函数名 `npu_gemm`），**签名本身不含 layout 参数**。用它的前提是自己在 L0A/L0B 上备好操作数；部分场景（如 varlen attention）还需 `T.annotate_layout` 标注 ZN/NZ 布局（`examples/attention_sink/example_gqa_sink_fwd_varlen/example_gqa_sink_fwd_varlen.py:151-165` 标注 L1 buffer 后 `alloc_L0A/L0B` 再 `T.mma`），而 `examples/gemm/example_gemm_intrinsic.py:54-94` 不用标注亦可，故「必须 annotate_layout」表述过强。一般不用 `T.mma`。

实测（CANN 9.1.0）：fp16 主路径 `block_M=128/block_N=256/block_K=64` 在 1024³ 约 29~31 TFLOPS（**经验值/待核**：仓库内无该数字的任何来源，本任务未复现）；fp32 GEMM 该分支无官方示例（`examples/gemm/` 无 fp32 专用示例，`example_gemm.py:21` 默认 `dtype="float16"`），其中「实测不对」一半**未证实**，暂用 fp16/bf16；`T.Pipelined` 预取会越界读尾块，非整除 shape 走 `T.serial`（细节见 op-patterns.md §4）。

## 5. 归约

`T.reduce_sum / reduce_max / reduce_min(buffer, out, dim=-1, clear=True, real_shape=None)`。

- 1D buffer 支持 dim 0/-1；2D 支持 0/1/-1/-2；3D 仅 trailing-tile 轴。
- `clear=False`：merge 到已有输出（sum 累加、max/min 取极值）。**该合并语义只在通用归约路径成立**：本分支两处 lowering 显式拒绝 `clear=false` —— PTO 尾块归约 `src/target/codegen_ascend_pto.cc:3156`（`ICHECK ... "PTO tail_reduce supports only clear=true"`）与窄归约 `src/target/codegen_ascend.cc:2102`（`ICHECK(clear) << "narrow reduce cannot merge into the destination (clear == false); reduce into a scratch and combine."`），均为**编译期致命错误而非静默**。非尾块、非窄归约路径的合并细节未逐条核对。
- 输出 shape：2D `[M,N]` 沿 dim=-1 → `[M]` 或 `[M,1]`；dim=0 → `[N]` 或 `[1,N]`。
- ⚠️ **`dim=0` 作用在只剩一维的 `[rows, 1]` 形状上行为不确定，可能产出 NaN**。多行 tile 的累加式归约
  一律走「循环内逐元素累加 → 循环外只用 `dim=-1` 做两步归约」，见
  [perf-antipatterns.md](perf-antipatterns.md) §12。这里限制的是「归约后只剩一维」的形态；
  对完整二维矩阵做列归约（`[M,N]` → `[1,N]`）不受影响。

## 6. 逐元素与 T.tile 原语

两种范式：

```python
# Developer：T.Parallel + 符号 API（1D/2D 并行，无 if-else 分支）
for i, j in T.Parallel(block_M, block_N):
    c_ub[i, j] = T.exp(a_ub[i, j]) + b_ub[i, j]

# buffer 级 SIMD 原语（两种模式下都可用；惯用于 Expert/混合）
T.tile.exp(c_ub, a_ub)
T.tile.add(c_ub, c_ub, b_ub)
```

### T.tile 常用原语

| 类别 | API |
| ------ | ----- |
| 二元 | `add/sub/mul/div/max/min/pow(dst, src0, src1)`，src1 可为 buffer 或标量 |
| 一元 | `exp/ln/abs/reciprocal/sqrt/rsqrt/relu/sin/cos(dst, src)` |
| 带参 | `leaky_relu(dst,src,slope)`、`axpy(dst,src,a)`、`mul_add_dst(dst,src0,src1)` |
| 激活 | `sigmoid/silu(dst, src)` |
| 广播 | `T.tile.broadcast(dst_2d, src_1d)` |
| 填充/序列 | `fill(buf, val)`、`arith_progression(buf, first, diff, count)`、`createvecindex(buf, first)` |
| 比较 | `compare(dst, src0, src1, mode)`，mode ∈ EQ/NE/GT/GE/LT/LE，结果是 bit mask |
| 选择 | `select(dst, mask, src0, src1, sel_mode)`，sel_mode ∈ VSEL_CMPMASK_SPR / VSEL_TENSOR_SCALAR_MODE / VSEL_TENSOR_TENSOR_MODE（三者均被接受，但 `src1` 与 mode 必须匹配：`src1` 为标量时只许 VSEL_TENSOR_SCALAR_MODE，为 buffer/BufferLoad 时只许另两者，见 `ascend_tile.py:108-158`） |
| 转换 | `cast(dst, src, mode, count)`，mode：CAST_NONE(升)/CAST_RINT(降)/CAST_FLOOR/CEIL/ROUND/TRUNC |
| 数据移动 | `transpose(dst,src)`、`gather(dst,src,off,base)`、`gather_mask(dst,src,pattern)`、`brcb` |
| 原子 | `T.tile.atomic_add(dst_gm, src_local)`（V1 仅 local→GM，dtype 须一致） |
| 排序 | `sort(dst,src,actual_num)`、`merge_sort(dst,s0,s1,...)`、`topk(dst,src,K,actual_num)`（src 大小须为 32 倍数） |

> `pow` 是**二元**原语：实测签名 `pow(dst, src0, src1, *, tmp=None)`（`tilelang/language/ascend_tile.py:2062`），语义为 `dst = src0 ^ src1`，不是一元。

### T.Parallel 限制（Ascend SIMD）

- 支持 1D/2D 并行、serial+parallel 组合；不支持 3D+ 并行。
- 循环边界必须是编译期常量。
- 不支持 `if/else` 分支语句。`T.if_then_else` **能写但不要用**：它无法被 `ascend_lower_parallel` 向量化，
  整个 `T.Parallel` 会**静默退化成串行标量迭代**（每 tile 数千次，性能断崖而无任何报错），部分版本直接拒绝。
  条件逻辑改用 `compare` + `select`；有闭式解时优先做数学等价变换再全用 `T.tile.*`
  （如 `ln(1+exp(x))` → `max(x,0) + ln(1+exp(-|x|))`）。
- 整型窄转换用 `T.tile.cast`（整个 buffer），不用 `.astype()` / `tir.reinterpret`。

### compare/select 要点

- 所有 mode 遇 NaN 返回 False（含 EQ）；`compare(m,x,x,"EQ")` 可检测 NaN。`compare` 接受 EQ/NE/GT/GE/LT/LE 六种 mode（`ascend_tile.py:1839-1950` 的 `assert mode in [...]`）。
- `VSEL_CMPMASK_SPR` 从 64 位寄存器读掩码，N>64 或 int32 时静默错位 → 按 `N<=64 且 dtype!=int32` 编译期选 SPR，否则 TENSOR_TENSOR_MODE。（**硬件行为断言，仓库内查无依据、本任务未证实**，按经验值使用。）
- int32 只有 EQ 有效；其余比较先 `cast` 到 fp32。（**未证实**：Python 层 `compare` 对 int32 无任何限制，是否属 C++ codegen 约束未找到依据。）

### dtype 硬件路径

- `T.tile.transpose` 硬件路径仅 2/4 字节类型（B16：fp16/int16/uint16；B32：fp32/int32），int8 与 bf16 退化为标量实现——`tilelang/language/ascend_tile.py:1618-1645` 的 docstring 原文为 "Supports B16 and B32 via hardware instruction; int8 and bfloat16 fall back to scalar implementation"，且要求 H、W 均满足 32 字节对齐。故 bf16 可用 host 侧 `view(torch.int16)` 零拷贝（仅纯搬数据时）；int8 在 kernel 内 cast 到 fp16；int64 用聚合 DMA 或块 DMA+UB 内重排（**未证实**），禁止逐元素 strided GM。
- 大张量 dtype 转换必须在 kernel 内做，禁止 host 侧 `.to()`/`.contiguous()`。

## 7. 循环与流水线

| API | 用途 |
| ----- | ------ |
| `T.serial(N)` | 普通循环 |
| `T.unroll(N)` | 展开 |
| `T.Parallel(M, N)` | 元素级并行（V 核 SIMD） |
| `T.Pipelined(range, num_stages=N)` | 软件流水线（GEMM/融合，2 级起步） |
| `T.Persistent(domain, wave_size, index)` | 多核均衡/持久化调度 |

## 8. 同步与作用域

| API | 语义 |
| ----- | ------ |
| `with T.Scope("C") / T.Scope("V")` | 指定 Cube/Vector 核执行域（Expert） |
| `T.barrier_all()` | 核内搬运/计算屏障 |
| `T.set_flag(src, dst, eventId) / T.wait_flag(src, dst, eventId)` | 细粒度流水同步。**三个参数均必填**（`ascend.py:233` / `ascend.py:251`）：`src` 为生产者、`dst` 为消费者（均为 pipeline 阶段），`eventId` 为 int。写成单参数 `T.set_flag(pipe)` 会直接 TypeError |
| `T.set_cross_flag(...) / T.wait_cross_flag(...)` | C/V 核间同步（Expert） |
| `T.sync_all()` | 全局同步 |
| `T.printf(fmt, *args)` / `T.dump_tensor(t, desc, size, shape)` | 调试 |

开启 AUTO_SYNC 后不手写 barrier_all；开启 AUTO_CV_COMBINE 后不手写 `T.Scope`（二者冲突会导致编译错误）。

## 9. pass_configs

```python
import tilelang
pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_COMBINE: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_SYNC: True,
}
```

| Key | 底层值 | 默认 | 作用 |
| ----- | -------- | ------ | ------ |
| TL_ASCEND_AUTO_SYNC | tl.ascend_auto_sync | False | 自动插入核内同步 |
| TL_ASCEND_MEMORY_PLANNING | tl.ascend_memory_planning | False | 自动 buffer 复用 |
| TL_ASCEND_AUTO_CV_COMBINE | tl.ascend_auto_cv_combine | False | 自动 C/V 分离 |
| TL_ASCEND_AUTO_CV_SYNC | tl.ascend_auto_cross_core_sync | False | 自动核间同步 |

四个键**默认全为 False**，即"不写就不开"，必须显式打开。

取值口径：`AUTO_SYNC` / `MEMORY_PLANNING` 与算子类型无关，所有算子都开；
`AUTO_CV_COMBINE` / `AUTO_CV_SYNC` 只在**同时含 Cube 与 Vector 工作**的算子上有意义。
**纯 Vector 算子不开这两个键**：实测开与不开输出逐字节相同（无收益），而 kernel 用到 `T.alloc_var`
时存在"定义与使用被分到不同核"的已知风险，排查代价高。详见
[programming-model.md](programming-model.md) §2 的场景表。
