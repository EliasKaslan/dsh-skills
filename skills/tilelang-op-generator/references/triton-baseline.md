# Triton 基线对比（TileLang vs Triton-Ascend）

为验证 TileLang 算子的正确性与性能水平，skill 提供与 Triton-Ascend 同卡、同数据、同计时协议的对比机制。
已验证环境：`triton.__version__ == 3.2.0`（发行包 `triton-ascend` 3.2.1 覆盖式安装进
`triton/backends/ascend/`，**`import triton_ascend` 会 ModuleNotFoundError，只需 `import triton`**；
详见 [testing.md §3](testing.md)），与 TileLang 共用同一 Python env（即 testing.md 的
`TILELANG_ENV_DIR`，torch 2.9.0 + torch_npu 2.9.0）。

## 1. 产物约定（每个算子）

| 文件 | 来源 | 内容 |
| ------ | ------ | ------ |
| `custom/{op}/{op}_triton.py` | 手写 | Triton 基线 kernel + Python wrapper（同公式、同 dtype 语义） |
| `custom/{op}/compare_{op}.py` | 复制 [assets/compare_template.py](../assets/compare_template.py) | 对比入口：精度（各自对 golden + 逐点互比）+ 性能 |
| `custom/compare_common.py` | 复制 [assets/compare_common.py](../assets/compare_common.py) | 公共工具：容差表、`check_precision`、`compare_direct`、`bench` |
| `custom/{op}/test_{op}.py` | 复制 [assets/test_template.py](../assets/test_template.py) | 被测实现的 L0/L1 用例表（compare 用它做一致性校验） |

`compare_common.py` 是**必需产物**：`compare_{op}.py` 文件开头（模板第 50 行）的
`from compare_common import ...` 就依赖它，缺文件直接
`ModuleNotFoundError: No module named 'compare_common'`。它放在 `custom/` 下，
`compare_{op}.py` 用两次 `sys.path.insert` 上溯一级 import。

运行（部署整个 `custom/` 目录后）：

```bash
cd {op} && ASCEND_RT_VISIBLE_DEVICES=0 python -u compare_{op}.py
```

`compare_{op}.py` 里的 `torch.npu.set_device(0)` 与 `ASCEND_RT_VISIBLE_DEVICES` 掩码配合：
掩码后逻辑卡 0 就是被指定的那张卡，所以这里是 `set_device(0)` 而不是真实卡号。

## 2. 判定口径

**精度**：两实现各自对 CPU golden 必须过 [testing.md §2](testing.md) 的混合容差双门限
（`TOL_TABLE`，与 `test_{op}.py` 的 `get_precision` 逐值一致）。

**逐点互比**：两实现输出直接比，要求 `matched_ratio ≥ 0.99`（即 `compare_template.py` 的模块级常量
`DIRECT_REQUIRED_RATIO`），容差用 `DIRECT_TOL`（比 golden 门限更严）：

| dtype | DIRECT_TOL atol | DIRECT_TOL rtol |
| ------- | ----------------- | ----------------- |
| float16 | 2^-12 | 2^-8 |
| bfloat16 | 2^-8 | 2^-5 |
| float32 | 2^-15 | 2^-9 |
| 整数类型 | 0 | 0（逐元素精确相等） |

**性能**：`bench` 用 wall-clock + `torch.npu.synchronize()`，默认预热 `WARMUP=3` 次、
计 `ITERS=20` 次取均值（与 `test_{op}.py` 的 `perf_smoke` 的 `PERF_WARMUP` / `PERF_ITERS`
同值，两处改一处必须改另一处）；输出 `TileLang/Triton` 比值，大于 1 表示 TileLang 更快。
正式结论仍以 `msprof op` 为准。

**用例一致性**：`compare_configs` 必须与 `test_{op}.py` 的 `test_configs["l0"]` + `["l1"]`
逐条同值同序；`compare_{op}.py` 开跑前会 import `test_{op}` 逐条核对，不一致或两边都为空
即打印 `[COMPARE-CONFIG_FAIL]` 并退出 1。不允许"注释说与 test 对齐、实际只测 2 个用例"。

**marker 与退出码**：逐用例打 `[COMPARE-PRECISION_PASS]` / `[COMPARE-PRECISION_FAIL]`
（三个判定：TileLang 对 golden、Triton 对 golden、TL 与 TR 互比），性能打 `[COMPARE-PERF]`；
全部通过打印 `Compare Passed!` 且退出码 0，任一失败打印 `Compare Failed!` 且退出码 1。
`PERF_CASE` 为 `None` 时直接判失败（不静默跳过性能对比）。

**失败须响亮的四种输入**：未知 dtype（`ValueError`，不回落 fp16 容差）、shape 不一致、
空张量、双方或 golden 全为非有限值 —— 一律 `[CHECK_FAIL]` 且判失败（空张量上取
`mean()` 会得到 nan 而静默通过，故必须先拦）。

## 3. Triton-Ascend 实测坑位 ⚠️

1. **`% M` 回绕加载不可用**：经典 Triton matmul 用 `(pid_m*BM + arange) % M` 免 mask 加载；
   在 Ascend 后端尾块会读到脏数据导致结果错（曾测出 max_abs=3e2）。必须显式
   `tl.load(..., mask=..., other=0.0)`，且 K 维尾块也要 mask（`offs_k < K - k*BLOCK_K`）。
2. **`~/.triton/cache` 与 torch 版本强绑定**：升级 torch 后旧 launcher .so 报
   `undefined symbol: _ZNK3c1010TensorImpl15incref_pyobjectEv`，`rm -rf ~/.triton/cache` 重编即可。
3. **aicore 异常直接终止进程**：越界/非法配置（如 softmax BLOCK_N=4096 单块、elementwise 超大 block）
   触发 `aicore exception` 时是 C++ 层 terminate，Python `try/except` 捕获不到，
   后续同进程所有 NPU 操作全部失败。调参扫描必须**每个危险配置单独进程**跑，并加 `python -u` 保留已有输出。
4. **num_warps 语义是 AI Core 数**：小 BLOCK 配大 num_warps 反而慢；
   elementwise BLOCK=2048/num_warps=2、softmax 分块 2048/num_warps=8 为 910 上实测甜点。
5. **计时协议必须统一**：`torch.npu.Event` 包夹会包含 TileLang JIT wrapper 的 host 发射开销
   （曾测出 gelu 136us vs wall-clock 50us 的假差距）；两实现对比一律用 wall-clock + synchronize。

## 4. 性能怎么测、怎么比（绝对数字不可当达标线）

**方法（这部分是稳定的，照做即可）：**

1. 同一张卡、同一份输入数据、同一 dtype，两实现共用 `compare_common.bench`；
2. 先 `npu-smi info` 确认卡空闲并**独占**跑，跑之前确认没有别的进程在用同一张卡；
3. 至少重复 3 次，报**中位数与范围**，不要只报一次的数；
4. 只把**同一次运行内**的 `TileLang/Triton` 比值当结论；跨运行、跨机器的绝对 us 不作数；
5. 正式性能结论一律用 `msprof op`，Python 计时只用于冒烟与同轮互比。

**为什么绝对 us 不能作数（本 skill 在 .190 卡 1 实测，softmax fp16 shape=(256,4096)
block=(32,512)，wall-clock，预热 3 次 / 计 20 次）：**

| 条件 | 实测 TileLang | 实测 Triton |
| ------ | --------------- | ------------- |
| 独占，同进程内 `perf_smoke` 路径 | 95.9 / 91.7 / 92.3 us（另一次运行 95.9 / 93.7 us） | — |
| 独占，同进程内 `compare_common.bench` | 94.3 / 92.5 / 94.8 / 101.4 us | — |
| 复刻 compare 顺序（先跑 5 个精度用例含 Triton） | 122.8 / 96.4 / 299.6 us（同进程内就波动） | 140.9 / 35.7 us（同进程内就波动） |
| 两个进程同时跑同一基准 | 236.8 ~ 440.2 us | — |
| 三次完整的 `compare_softmax.py` | 99.5 / 95.4 / 98.0 us | 40.8 / 157.0 / **1231.3** us |
| 同一轮的 `test_{op}.py --level perf` | 95.1 / 97.8 / 102.7 us | — |

最后两行是重点：**同一份代码、同一 shape、同一台机**，三次完整对比给出的比值分别是
**0.41x / 1.65x / 12.57x**（翻转来自 Triton 侧 40.8 / 157.0 / 1231.3 us，TileLang 一直是 95~103 us）；
同一轮里 `[PERF]`（test 的 `perf_smoke`）与 `[COMPARE-PERF]`（compare 的 `bench`）TileLang 侧相差
在 5% 以内（102.7 对 98.0、97.8 对 95.4）。同轮其他评测者在同一台机上还测到过 0.17x 与 0.41x
（他们的 `[PERF]` 104.2 us 对 `[COMPARE-PERF]` 79.5 us）。合计同一 shape 出现过的比值：
**0.17x / 0.41x / 0.62x / 1.65x / 12.57x**。

**判断与依据**：这不是"test 与 compare 两个脚本计时协议不同"造成的。两条路径是同一段代码
（`torch.npu.synchronize()` 包夹 → 预热 3 次 → `time.perf_counter()` → 计 20 次 → 再 `synchronize()`），
在独占、同进程顺序测量下两者相差约 5%（95.9/91.7 对 94.3/92.5）。真正的原因是**这张卡被多个
进程共用**：两个进程同时跑同一基准时实测膨胀到 2.5 ~ 4.6 倍；即使只有一个进程，只要同卡上
其他进程在跑 kernel，单个计时窗口也会冒出 299.6 / 538.1 / 1231.3 us 这类离群值。
因此"同协议"只保证**同一次运行内**两实现可比，不保证两个脚本、两次运行的数字能对上；
看到两个脚本或两次运行差 1.5 倍以上时，先查同卡并发与离群窗口，而不是去改计时公式。

**历史参考值（特定机器 + 特定配置的当时记录，不是达标线）**：下表来自更早的一次实测记录，
本次在同一台 .190 上**逐条复测未能复现**（softmax 复测为 92~101 us，表中记 51.2 us）。
本次只复测了 softmax，gelu / matmul 两行**未复测**，仅作数量级直觉：

| 算子 | shape | TileLang | Triton | TL/TR |
| ------ | ------- | ---------- | -------- | ------- |
| gelu | (1024,2048) | 50.1 us @ block(128,256) | 41.5 us @ BLOCK=2048,nw=2 | 0.83x |
| softmax | (256,4096) | 51.2 us @ block(32,512) | 31.8 us @ BLOCK_N=2048,nw=8 | 0.62x |
| softmax | (512,1024) | 284.5 us @ block(64,128) | 51.1 us @ BLOCK=1024（默认 num_warps） | 0.18x |
| matmul | 1024³ | 54.6 us (39.4 TFLOPS) | 83.1 us (25.8 TFLOPS) | 1.52x |

> 第 3 行是 2026-10-26 在 **.188**（`ascendc_pto` commit `43b0b69`）按 `op-patterns.md §3.1`
> 配方跑出的 `compare_softmax.py` 单次结果；同一 shape 在该机 `test_{op}.py --level perf`
> 里量到 165.8 us，与 compare 的 284.5 us 差 1.7 倍 —— 正是上面"绝对 us 不作数"的又一例证，
> 只把 0.18x 这个**同一次运行内**的比值当结论。

由上表得出的"Cube 类算子 TileLang 占优、纯 Vector 算子 Triton 略快"是**待复测的判断**，
不要当结论引用。可复用的方法仍然是：纯 Vector 算子先扫 block 大小（TileLang）与
BLOCK/num_warps（Triton），两边都调到各自最优再比；扫描时对候选 block / `VEC_NUM` 组合
做单进程小批量扫描，每个危险配置独立进程跑（见 §3 坑位 3）。

## 5. 写 Triton 基线的要求

- **同公式**：与 TileLang 版用同一数学表达式（如 gelu 用 sigmoid 形式而非 tanh 形式），减小逐点差异便于互比。
- **同 dtype 语义**：fp16/bf16 输入一律升 fp32 计算再降回（`acc`/reduce 用 fp32）。
- **尾块安全**：所有维度显式 mask，禁止回绕技巧（见坑位 1）。
- **matmul 参考配置**：`BLOCK_M=64, BLOCK_N=64, BLOCK_K=32, GROUP_M=8, num_warps=1, num_stages=1`。
- **签名对齐**：`compare_template.py` 的默认签名是 2D 单输入；矩阵乘类算子必须同步改
  `make_inputs`（返回两个张量）、`golden_{op}(a, b)`、`run_case` / `run_perf`（加 K 与 block_K）
  以及 `compare_configs` / `PERF_CASE` 元组。
