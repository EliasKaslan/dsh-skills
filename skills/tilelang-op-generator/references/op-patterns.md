# 算子配方（按类别直接改写）

> 配方均来自 `tilelang-ascend`（ascendc_pto 分支）`examples/` 验证过的写法。生成时以配方为骨架，替换算子名、shape、计算原语即可；不要凭空造结构。

## 目录

- [0. 通用骨架](#0-通用骨架)
- [1. 逐元素算子](#1-逐元素算子)
- [2. 归约算子](#2-归约算子)
- [3. 归一化算子（softmax/rmsnorm/layernorm）](#3-归一化算子)
- [4. GEMM](#4-gemm)
- [5. 融合算子（GEMM+残差/bias+激活）](#5-融合算子)

## 0. 通用骨架

所有 kernel 文件统一为：

```python
import tilelang
import tilelang.language as T

pass_configs = { ... }   # 按 programming-model.md §2 选择

@tilelang.jit(out_idx=[-1], target="pto", pass_configs=pass_configs)
def {op}(M, N, block_M, block_N, dtype="float16"):
    @T.prim_func
    def main(X: T.Tensor((M, N), dtype), Y: T.Tensor((M, N), dtype)):
        with T.Kernel(T.ceildiv(M, block_M) * T.ceildiv(N, block_N), is_npu=True) as (cid, vid):
            ...
    return main
```

函数名 = 文件名 = 算子名（`from {op} import {op}` 才能工作）。测试文件复制 `assets/test_template.py`，只改 golden 函数与用例。

## 1. 逐元素算子

适用：add/sub/mul/div、relu/gelu/silu、scale、bias 等。纯 V 核 UB 实现。

```python
pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
    # 纯 Vector 不要开 AUTO_CV_COMBINE / AUTO_CV_SYNC：没有 Cube 核可分离，开了无收益；
    # 且 kernel 用到 T.alloc_var 时存在"定义与使用被分到不同核"的已知风险。
    # 若已开且出现异常，先关掉它再排查（不要先去改算法）。
}

@tilelang.jit(out_idx=[-1], pass_configs=pass_configs)
def {op}(M, N, block_M, block_N, dtype="float16"):
    m_num = T.ceildiv(M, block_M)
    n_num = T.ceildiv(N, block_N)

    @T.prim_func
    def main(A: T.Tensor((M, N), dtype), B: T.Tensor((M, N), dtype), C: T.Tensor((M, N), dtype)):
        with T.Kernel(m_num * n_num, threads=2, is_npu=True) as (cid):
            bx = cid // n_num
            by = cid % n_num
            a_ub = T.alloc_shared((block_M, block_N), dtype)
            b_ub = T.alloc_shared((block_M, block_N), dtype)
            c_ub = T.alloc_shared((block_M, block_N), dtype)
            T.copy(A[bx * block_M, by * block_N], a_ub)
            T.copy(B[bx * block_M, by * block_N], b_ub)
            T.tile.add(c_ub, a_ub, b_ub)          # 换成对应原语: mul/sub/max/relu/silu...
            T.copy(c_ub, C[bx * block_M, by * block_N])
    return main
```

- 单目激活：`T.tile.relu/silu/exp/...`（api-reference.md §6）。
- GELU（tanh 近似）无单条原语 → 拆成算术组合：`x → 0.5x(1+tanh(√(2/π)(x+0.044715x³)))`，用 add/mul/pow/tanh 原语组合；tanh 无直接原语时用 `T.Parallel` + `T.tanh(x)` 符号形式或参考仓库 gelu 示例。
- 尾块统一策略：`T.ceildiv` 只决定**块数**（grid 或 `T.serial` 的上界），它**不裁剪 tile 内容**；tile 内容交给
  lowering 按 `min(extent, dim - off)` 自动裁剪。**N 维与 M 维都能靠自动裁剪**：实测 N 尾块
  `(M=64, N=130, block_N=128)` PASS、M 尾块 9 组组合（含 `M < block_M`、余数 1/4/8/16/20/26/36）全 PASS，
  矩阵见 constraints.md §9.1。
- N 维与 M 维的差异在**为什么**：N 维的 `n0 = by * block_N` 受 `T.serial(T.ceildiv(N, block_N))` 约束，
  恒有 `n0 < N`，故 `N - n0` 永远为正；M 维多一层 `vid` 分片，`base_m = bx*block_M + vid*sub_M`
  可以越过 M —— 这才是唯一会变负的一维（也是 constraints.md §9 那条告诫的真正适用范围）。
- 想显式控制就写动态 region，但**必须钳到非负**：`valid = T.max(T.min(block, dim - off), 0)`，输入输出两侧都写。
  漏掉 `T.max(..., 0)`、且最后一个行块的实际行数 `rem` 落在 `0 < rem < block_M/2` 时得到**负 extent**
  → `aicore exception 507015`（实测复现 5 组；判据与矩阵见 constraints.md §9.2）。

## 2. 归约算子

适用：sum/mean/max/min 沿某轴。行内归约用 `T.reduce_*`；跨行归约用 `T.reduce_*` + atomic_add 或多级归约。

```python
# 行内 reduce：[M, N] -> [M, 1]（每 block 一行，V 核各分半行）
@tilelang.jit(out_idx=[1], pass_configs=pass_configs)
def row_sum(M, N, block_M, block_N, dtype="float16"):
    VEC_NUM = 2
    sub_M = block_M // VEC_NUM
    @T.prim_func
    def main(A: T.Tensor((M, N), dtype), S: T.Tensor((M, 1), dtype)):
        with T.Kernel(T.ceildiv(M, block_M), is_npu=True) as (cid, vid):
            bx = cid * block_M + vid * sub_M
            a_ub = T.alloc_ub((sub_M, block_N), dtype)
            acc = T.alloc_ub((sub_M, 1), "float32")
            valid_m = T.min(sub_M, M - bx)
            valid_n = T.min(block_N, N - 0)          # 每行从 0 开始归约整行
            T.copy(A[bx:bx+valid_m, 0:valid_n], a_ub[0:valid_m, 0:valid_n])
            T.reduce_sum(a_ub, acc, dim=-1)
            T.copy(acc[0:valid_m, 0:1], S[bx:bx+valid_m, 0:1])
    return main
```

要点（与 `examples/reduce/` 一致的写法）：

- 输入输出都保持 2D tile 形状（`[sub_M, N]` → `[sub_M, 1]`），`dim=-1` 行归约、`dim=0` 列归约（列归约输出 `[1, N]`）。
- 输出 `[M]` 的算子可让 kernel 直接写 `[M, 1]` 再由 host 侧 `view(-1)`（纯元数据操作）；或在 kernel 内按行 `T.copy` 到 `S[row]`。
- 多 block 分段归约后跨 block 累加：每 block 结果 `T.tile.atomic_add(S_global, local_acc)`，调用前 GM 输出清零。
- `VEC_NUM` 是示例文件内的局部常量（恒为 2），**不是框架 API**；框架侧无该符号。
- `clear=False`（merge 进已有输出）只在通用归约路径成立：PTO 尾块归约与窄归约会直接编译报错（详见 api-reference.md §5）。
- mean = sum / N：`T.tile.div(acc, acc, 1.0/N)` 或先 sum 再乘标量。
- fp16/bf16 输入建议累加到 fp32 buffer（如上 `acc`）。

## 3. 归一化算子

### 3.1 softmax（online 两遍：先 max/sum，再 exp/div）

来自 `examples/softmax/example_online_softmax.py`。核心是「数值稳定的 online softmax」：

```text
第一遍: m_j=max(m_{j-1}, x_j); s_j=s_{j-1}*exp(m_{j-1}-m_j)+exp(x_j-m_j)
第二遍: y_j = exp(x_j - m_N) / s_N
```

```python
pass_configs = {
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
    tilelang.PassConfigKey.TL_ASCEND_AUTO_CV_COMBINE: True,
}

@tilelang.jit(out_idx=[1], pass_configs=pass_configs)
def softmax(M, N, block_M, block_N, dtype="float16"):
    use_f32 = dtype in ("float16", "bfloat16")
    cal = "float32" if use_f32 else dtype
    VEC_NUM = 2
    sub_M = block_M // VEC_NUM

    def cast(dst, src, mode, cnt):
        return T.tile.cast(dst, src, mode, cnt) if use_f32 else T.copy(src, dst)

    @T.prim_func
    def main(A: T.Tensor((M, N), dtype), B: T.Tensor((M, N), dtype)):
        with T.Kernel(T.ceildiv(M, block_M), is_npu=True) as (cid, vid):
            bx = cid
            a    = T.alloc_ub((sub_M, block_N), dtype)
            a_c  = T.alloc_ub((sub_M, block_N), cal)
            mx   = T.alloc_ub((sub_M, 1), cal)
            mx2  = T.alloc_ub((sub_M, block_N), cal)
            prev = T.alloc_ub((sub_M, 1), cal)
            prev2= T.alloc_ub((sub_M, block_N), cal)
            sm   = T.alloc_ub((sub_M, 1), cal)
            prs  = T.alloc_ub((sub_M, 1), cal)
            prs2 = T.alloc_ub((sub_M, block_N), cal)
            tmp  = T.alloc_ub((sub_M, 1), cal)
            T.tile.fill(prev, -T.infinity(cal))
            T.tile.fill(prs, 0.0)

            base_m = bx * block_M + vid * sub_M
            # 第一遍
            for by in T.serial(T.ceildiv(N, block_N)):
                T.copy(A[base_m:base_m+sub_M, by*block_N:(by+1)*block_N], a,
                       pad_value=-T.infinity(cal))
                cast(a_c, a, "CAST_NONE", sub_M*block_N)
                T.reduce_max(a_c, mx, dim=-1)
                T.tile.max(mx, prev, mx)          # m_j = max(m_{j-1}, tile_max)
                T.tile.sub(tmp, prev, mx); T.tile.exp(tmp, tmp)
                T.tile.mul(tmp, prs, tmp)
                T.tile.broadcast(mx2, mx)
                T.tile.sub(a_c, a_c, mx2); T.tile.exp(a_c, a_c)
                T.reduce_sum(a_c, sm, dim=-1)
                T.tile.add(prs, sm, tmp)          # s_j
                T.copy(mx, prev)
            # 第二遍
            T.tile.broadcast(prev2, prev); T.tile.broadcast(prs2, prs)
            for by in T.serial(T.ceildiv(N, block_N)):
                T.copy(A[base_m:base_m+sub_M, by*block_N:(by+1)*block_N], a)
                cast(a_c, a, "CAST_NONE", sub_M*block_N)
                T.tile.sub(a_c, a_c, prev2); T.tile.exp(a_c, a_c)
                T.tile.div(a_c, a_c, prs2)
                cast(a, a_c, "CAST_RINT", sub_M*block_N)
                T.copy(a, B[base_m:base_m+sub_M, by*block_N:(by+1)*block_N])
    return main
```

要点：fp16/bf16 输入用 fp32 中间计算再 cast 回；`pad_value=-inf` 处理尾块；块内并行由 `block_M//2` 行分给两个 V 核。

pass_configs 口径（见 programming-model.md §2）：`AUTO_SYNC` 与 `MEMORY_PLANNING` 与算子类型无关，所有算子都开；
`AUTO_CV_COMBINE` / `AUTO_CV_SYNC` 只在**同时含 Cube 与 Vector 工作**的算子上才有意义。本配方是纯 Vector，
所以只开 3 个键、故意不写 `TL_ASCEND_AUTO_CV_SYNC`。实测纯 Vector 上「开 3 键」与「开 4 键」都编译通过、
都打 `[PRECISION_PASS] l0 ... matched_ratio=1.0000`、退出码均为 0，且输出**逐位相同**（同为 fp16 原始字节
MD5 `3ef0c4ab2479392fd1d24c358ba4ed73`）——即多开 CV 键**无害但无收益**，不必为了「凑齐 4 个」而加。
（进一步实测：纯 Vector 一个 CV 键都不开、只留 `AUTO_SYNC + MEMORY_PLANNING` 也能编译通过并 ratio=1.0000；
「纯 Vector 必须开 AUTO_CV_COMBINE 才能保证只在 AIV 执行」这一说法未获证实，但本次也**未**用 `get_kernel_source()`
核对生成代码的 AIV/AIC 归属，故仍按无收益处理、不主动删键。）

### 3.2 RMSNorm

`y = x / sqrt(mean(x²) + eps) * w`。参照 `examples/normalization/rms_norm.py`：

```python
@tilelang.jit(out_idx=[2], pass_configs=pass_configs)
def rms_norm(M, N, block_M, block_N, dtype="float16"):
    # 每个 block 处理 block_M 行：
    # 1) T.copy 行块到 UB（尾块动态切片）
    # 2) T.tile.mul(a2, a, a)                       # x²
    # 3) T.reduce_sum(a2, ss, dim=-1)               # sum(x²)
    # 4) T.tile.mul(ss, ss, 1.0/N); T.tile.add(ss, ss, eps)
    # 5) T.tile.rsqrt(ss, ss)                       # 1/sqrt(...)
    # 6) T.tile.broadcast(ss2, ss); T.tile.mul(a, a, ss2); T.tile.mul(a, a, w_row)
    # 7) T.copy 回 GM
    ...
```

### 3.3 LayerNorm

`y = (x - mean(x)) / sqrt(var(x) + eps) * w + b`。与 RMSNorm 同构，多一步求 mean（`T.reduce_sum` × (1/N)）和 subtract。参照 `examples/normalization/layer_norm.py`。

## 4. GEMM

来自 `examples/gemm/example_gemm.py`（Expert）与 `example_gemm_pto_developer.py`（混合）。C = A[M,K] @ B[K,N]：

```python
pass_configs = {   # 混合模式：保留自动同步与内存规划
    tilelang.PassConfigKey.TL_ASCEND_AUTO_SYNC: True,
    tilelang.PassConfigKey.TL_ASCEND_MEMORY_PLANNING: True,
}

@tilelang.jit(out_idx=[-1], target="pto", pass_configs=pass_configs)
def matmul(M, N, K, block_M, block_N, block_K, dtype="float16", accum_dtype="float"):
    m_num = T.ceildiv(M, block_M)
    n_num = T.ceildiv(N, block_N)

    @T.prim_func
    def main(A: T.Tensor((M, K), dtype), B: T.Tensor((K, N), dtype), C: T.Tensor((M, N), dtype)):
        with T.Kernel(m_num * n_num, is_npu=True) as (cid, _):
            bx = cid // n_num
            by = cid % n_num
            A_L1 = T.alloc_L1((block_M, block_K), dtype)
            B_L1 = T.alloc_L1((block_K, block_N), dtype)
            C_L0 = T.alloc_L0C((block_M, block_N), accum_dtype)
            for k in T.Pipelined(T.ceildiv(K, block_K), num_stages=2):
                T.copy(A[bx*block_M, k*block_K], A_L1)
                T.copy(B[k*block_K, by*block_N], B_L1)
                T.gemm_v0(A_L1, B_L1, C_L0, init=(k == 0), kL0Size=block_K)
            T.copy(C_L0, C[bx*block_M, by*block_N])
    return main
```

调优起点：`block_M=128, block_N=256, block_K=64`（fp16），`kL0Size=block_K` 显式指定。更大规模可加 `num_stages=3`、双缓冲、`T.Persistent`（见 `example_gemm_persistent.py`）。

实测约束（CANN 9.1.0 + ascendc_pto）：

- **fp16 主路径**：上述配置 1024³ 实测约 29~31 TFLOPS（**经验值/待核**：仓库内无该数字来源，本任务未复现）。
- **fp32 GEMM 未充分验证**：仓库无 fp32 gemm_v0 示例（`examples/gemm/` 无 fp32 专用示例，`example_gemm.py:21` 默认 `dtype="float16"`）；「实测结果 NaN/不对」**未证实**，先用 fp16/bf16。
- **尾块 + 流水线冲突**：`T.Pipelined` 的预取会越界读尾块 → 结果错误。非整除 shape（M/N/K 任一不整除）必须走 `T.serial`（可用 JIT 编译期 `if 整除: Pipelined else: serial` 分支，参照 `example_gemm_tail_block_developer.py`，已实测 530×517×513、100×66×300 通过）。
- 转置 B 用 `transpose_B=True`。

## 5. 融合算子

适用：matmul+残差、matmul+bias+激活、attention 等 C/V 协作。两条路线：

**A. Developer 混合（推荐，先跑通）**：`threads=2` 消 vid，C/V 片上直连，开 4 个 pass（programming-model.md §3）。GEMM 结果 `alloc_fragment` → 片上 `T.copy` 到 `alloc_shared` → 逐元素后处理 → 写 GM。

**B. Expert workspace（兜底/精细控制）**：

```python
@tilelang.jit(out_idx=[-1], workspace_idx=[3], pass_configs=...)
def fused(M, N, K, ...):
    @T.prim_func
    def main(A: T.Tensor((M, K), dtype), B: T.Tensor((K, N), dtype),
             Bias: T.Tensor((N,), dtype), C: T.Tensor((M, N), dtype),
             workspace: T.Tensor((M, N), "float32")):
        with T.Kernel(m_num * n_num, is_npu=True) as (cid, vid):
            # C 核: gemm_v0 -> C_L0 -> T.copy(C_L0, workspace[bx*block_M, by*block_N])
            # V 核: T.copy(workspace[...+vid*sub_M ...], c_ub) -> T.tile.add(c_ub, bias) -> T.copy(c_ub, C[...])
```

铁律：C/V 读写 workspace 用同一索引公式；bias 广播用 `T.tile.broadcast`；融合算子必须开（或手写）核间同步，否则数据竞争。
