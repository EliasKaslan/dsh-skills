# 测试与验证

## 1. 测试文件结构

复制 [assets/test_template.py](../assets/test_template.py) 为 `custom/{op}/test_{op}.py`，然后改 6 处：

| # | 位置 | 改什么 | 漏改的后果 |
| --- | ------ | -------- | ------------ |
| 1 | 全文 `{op}` 占位符 | 换成算子名 | 语法错误，import 阶段即崩（响亮） |
| 2 | `golden_{op}(*inputs)` | 用 PyTorch/NumPy 在 CPU 语义下实现数学公式 | 保持 `raise NotImplementedError` → 每个用例 `[PRECISION_FAIL]`，退出码 1（响亮） |
| 3 | `test_configs["l0"]` / `["l1"]` | 填用例元组 | **留空 = 打印 `[PRECISION_FAIL]` 且退出码 1**（空表被判失败，不再假通过） |
| 4 | `make_inputs(...)` | 构造 CPU 输入，返回 list | 返回空 list → 打印 `[PRECISION_FAIL]` 后**早退**（不调用内核），退出码 1 |
| 5 | `perf_config` | 性能冒烟用例 | `None` → `--level perf` 与 `all` 判失败 |
| 6 | `CATEGORY` / `COVERAGE_MANIFEST` / `COVERAGE_NA` | 按 [coverage-matrix.md](coverage-matrix.md) §2 逐维度记账 | 漏填 → `check_coverage.py` 判每个维度 `[MISS]`，退出码 1，交付门禁卡住 |

用例元组格式：`(dtype, M, N, block_M, block_N)`，kernel 调用一律关键字传参
`{op}(M, N, block_M, block_N, dtype=dtype)`。**不要**按位置传参：实战 kernel 签名形如
`def softmax(M, N, block_M, block_N, dtype="float16")`，dtype 在**末位**且带默认值。
签名不同（如矩阵乘还要 K 与 block_K）时同步扩展用例元组、kernel 调用与 `make_inputs`。

分层约定：

| 层 | 内容 | 标记 | 计入退出码 | 经验规模 |
| ---- | ------ | ------ | ----------- | ---------- |
| L0 | 门槛精度（规则 shape） | `[PRECISION_PASS/FAIL]` | 是 | 3 例，含 1 个 float32 |
| L1 | 功能/不规则（尾块）shape | `[PRECISION_PASS/FAIL]` | 是 | 2 例全尾块 |
| L2 | 负向非法输入 | `[BOUNDARY_PASS/WARN/SKIP]` | 否 | 至少 1 非法 shape + 1 非法 dtype |
| Boundary | 合法极值/特殊值 | `[BOUNDARY_PASS/WARN/SKIP]` | 否 | 浮点算子至少 1 特殊值 + 1 极值 |
| perf | 性能冒烟计时 | `[PERF]` / `[PERF_FAIL]` | 是（`--level perf` 或 `all`） | 1 例，取最大 dtype + 最大 shape |

**L2 / Boundary 的最小集不是"可为空"**：L2 至少要有 1 个非法 shape 与 1 个非法 dtype 用例
（正确拒绝 → `[BOUNDARY_PASS]`；静默接受 → `[BOUNDARY_WARN]`）；浮点算子的 Boundary 至少要有
1 个特殊值（±Inf 或 NaN）与 1 个接近 dtype 上界的极值。整型算子可豁免特殊值，但要在测试文件里
写明豁免理由。

用例确实留空时打 `[BOUNDARY_SKIP]`（明确表示"没测"），**同时在交付说明里记为已知缺口**——
不能因为非阻塞就当成已覆盖。

`l2` / `boundary` 两层的元素是**零参可调用对象**（函数或 lambda），不是 L0/L1 那种元组；
调用时抛异常 = 正确拒绝。例：

```python
"l2": [lambda: {op}(0, 128, 32, 128)],                 # 非法 M，期望抛异常 → [BOUNDARY_PASS]
"boundary": [lambda: run_case("float16", 64, 256, 64, 128, valrange="inf")],
```

往这两层塞元组会在调用处报 `TypeError: 'tuple' object is not callable`，并被吞成
`[BOUNDARY_WARN]`（不阻塞，但等于没测）。

运行：`python test_{op}.py --level l0`（收敛阶段）→ `--level perf` → `--level all`（全量）。
L0/L1 全过且 perf 不失败时打印 `Test Passed!` 且退出码 0 才算通过；任一阻塞层失败打印
`Test Failed!` 且退出码 1。

**覆盖维度是否达标由脚本判，不靠人工数**：

```bash
python scripts/check_coverage.py --test custom/{op}/test_{op}.py --category <gemm|softmax|normalization|activation|reduction|fusion|integer>
```

退出码 0 = 覆盖达标，1 = 有强制维度缺失（会打印缺失清单），2 = 脚本自身错误。
维度定义与各类别最低要求见 [coverage-matrix.md](coverage-matrix.md)。
**覆盖未达标时不得宣称"已完成"**。

`tilelang.disable_cache()` 只在 `main()` 内或 `if __name__ == "__main__":` 之下调用——放在文件顶部
全局位置会连带影响同进程的其它算子，`cache.clear_cache()` 也不要使用。

**反假通过约定**：`test_configs` 的 `l0`/`l1` 为空是**失败**，不是"没测所以通过"。
判定通过时请同时确认日志里出现了对应的 `[PRECISION_PASS]` 行，且**行数等于本次 `--level` 实际执行层
的用例数**（`--level l0` 即 `len(test_configs["l0"])`，`--level all` 即 L0+L1 之和）；
只看退出码不足以区分"跑过了"和"没跑"。

## 2. 精度标准（混合容差双门限）

| dtype | atol | rtol | max_abs_error_limit | required_matched_ratio |
| ------- | ------ | ------ | --------------------- | ------------------------ |
| float16 | 2^-14 | 2^-9 | 1e-1 | 0.99 |
| bfloat16 | 2^-10 | 2^-6 | 1e0 | 0.99 |
| float32 | 2^-16 | 2^-10 | 1e-2 | 0.99 |
| hifloat32 | 2^-16 | 2^-10 | 1e-2 | 0.99 |
| float8_e4m3 | 2^-4 | 2^-2 | 1e0 | 0.99 |
| float8_e5m2 | 2^-3 | 2^-1 | 1e-1 | 0.99 |
| 整数类型 | 0 | 0 | 0 | 1.0（逐元素精确相等） |

后三行（hifloat32 / fp8）取自上游 CANN 的 TileLang 精度口径，**本机未复核**——只有算子真的用这些
dtype 时才会走到，走到时请以实测结果校正后再上库。

**阈值只看 dtype，不看算子类别**：GEMM / Softmax / Normalization / Activation / Reduction / Fusion
统一用本表，不存在"矩阵乘可以放宽"这种例外。

判定：`matched_ratio ≥ required` 且 `max_abs ≤ limit`。**未知 dtype 直接报错**，不得静默
回落到 float16 容差；整型必须 0 误差。表值在 `assets/test_template.py` 的 `get_precision`
与 `assets/compare_common.py` 的 `TOL_TABLE` 中各有一份，必须逐值一致；**未知 dtype
两处都必须抛 `ValueError`**（`get_precision` 与 `get_tolerance` 同语义），不允许一边报错、
一边放行。

NaN/Inf 用例要求位置敏感验证（已在模板与 `compare_common.py` 内实现）：

1. CPU 上固定 seed 生成有限基础值 + 稀疏特殊值 mask（至少一个特殊值 + 一个有限值），
   禁止全 NaN 作为唯一特殊值用例。
2. 比较数值前，先严格比对 actual/golden 的 NaN、+Inf、-Inf 三个 mask 是否完全相等。
3. mask 一致后，只在双方有限位置算 atol/rtol、matched ratio 与 max abs error。

以下四种情况一律判**失败**并打印 `[CHECK_FAIL]`（附原因），不得静默通过：
shape 不一致、空张量（`numel()==0`）、mask 不一致、golden 全为非有限值。

## 3. 运行环境

### 远程昇腾机（需自备，地址与路径不内置）

准备一台可 SSH 登录、已装 CANN 与 TileLang-Ascend 的昇腾机，并把下列值填成目标机的实际路径：

| 环境变量 | 含义 | 示例 |
| ---------- | ------ | ------ |
| `TILELANG_NPU_HOST` | 昇腾机地址（SSH） | `10.0.0.1` |
| `TILELANG_NPU_USER` / `TILELANG_NPU_PORT` | SSH 用户 / 端口 | `root` / `22` |
| `TILELANG_NPU_WORKDIR` | 远程工作目录 | `~/tilelang-work` |
| `CANN_INSTALL_PATH` | CANN 安装路径（含 `set_env.sh`，老布局只有 `bin/setenv.bash` 也认） | `$HOME/Ascend/ascend-toolkit/latest` |
| `TILELANG_ASCEND_PATH` | TileLang-Ascend 仓库路径（含 `set_env.sh`） | `$HOME/tilelang-ascend` |
| `TILELANG_ENV_DIR` | 远程 Python venv 目录 | `$HOME/tilelang-env` |

Python 环境需包含 torch + torch_npu + tilelang，以及写 Triton 基线时所需的 Triton-Ascend
（本 skill 实测组合：torch 2.9.0 + torch_npu 2.9.0 + triton 3.2.0）。

> **Triton-Ascend 的包名与导入名不是一回事**（实测）：发行包名是 `triton-ascend`
> （`pip` 里显示为 `triton_ascend`，版本 3.2.1），但它**没有** `triton_ascend` 这个可导入模块
> —— `import triton_ascend` 报 `ModuleNotFoundError: No module named 'triton_ascend'`。
> 它是覆盖式安装进 `triton` 包里的，落在 `triton/backends/ascend/`，
> 所以**只需 `import triton`**，版本用 `triton.__version__` 核对（实测 3.2.0，
> 此时 `triton` 发行版自身的版本号也是 3.2.0）。
>
> **编译 TileLang-Ascend 需要较新的 gcc**（实测）：Debian 10 自带 gcc 8.3.0 + C++17 下，
> `src/layout/layout.cc` 的 `TVM_REGISTER_GLOBAL("tl.Layout")` 里
> `Array<IterVar>(args[0])` / `PrimExpr(args[2])` 报
> `error: call of overloaded 'Array(tvm::runtime::TVMArgValue)' is ambiguous`
> （`TVMArgValue` 同时可一步转 `int64_t` 与 `ObjectRef`），`make` 直接失败。
> 老发行版可把这三处改成 `args[i].AsObjectRef<Array<IterVar>>()` / `AsObjectRef<PrimExpr>()`
> ——实测改完该 TU 编译通过、全量 make 继续；或直接换 gcc 9+ 的工具链。

选卡：每次运行前先 `npu-smi info` 看哪张卡空闲（Health OK、无进程、HBM 占用低），用 `ASCEND_RT_VISIBLE_DEVICES=0`（填实际空闲卡号）指定；卡异常时可换卡或等其恢复。

每次运行前置（注意首行 PATH 补全，见下方坑位）：

```bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH
source "$CANN_INSTALL_PATH/set_env.sh"      # 标准布局；若无此文件则 source "$CANN_INSTALL_PATH/bin/setenv.bash"
source "$TILELANG_ASCEND_PATH/set_env.sh"
export PATH="$TILELANG_ENV_DIR/bin:$PATH"
```

> 坑位：ssh 非登录 shell 的 PATH 可能缺 `/usr/local/sbin`（npu-smi）与 `/usr/bin`（git，tilelang
> version.py 会调 git），缺了会报 `can not use command: npu-smi info` / `FileNotFoundError: git`。

用脚本一键部署运行（激活前置由脚本注入，`--cmd` 只写要跑的命令）：

```bash
export TILELANG_NPU_HOST=10.0.0.1                        # 昇腾机地址
export CANN_INSTALL_PATH=$HOME/Ascend/ascend-toolkit/latest
export TILELANG_ASCEND_PATH=$HOME/tilelang-ascend        # TileLang-Ascend 仓库路径
export TILELANG_ENV_DIR=$HOME/tilelang-env               # 远程 python venv 路径

python scripts/remote_run.py --deploy custom/{op} \
  --cmd 'ASCEND_RT_VISIBLE_DEVICES=0 python test_{op}.py --level l0'
```

> `remote_run.py` 会把「PATH 补全 + CANN/TileLang-Ascend 激活 + venv PATH 前置」写进远程 bash
> 脚本再执行，因此本地 shell 用什么引号都不会影响 `$PATH` 的展开。环境自检：
> `python scripts/env_check.py`（同样读上述环境变量，可另用 `--host` 等参数覆盖）。

Windows 侧 ssh 只写单行命令：多层引号拼接极易被本地 shell 吃掉，复杂命令一律
「本地写 `.sh` → `scp` 上传 → `ssh bash /tmp/x.sh`」。

### 本地有 NPU 环境

`source $CANN_INSTALL_PATH/set_env.sh`（老布局用 `bin/setenv.bash`）`&& source $TILELANG_ASCEND_PATH/set_env.sh` 后直接 `python test_{op}.py`。

## 4. 数据准备与验证铁律

- 输入随机数、特殊值注入、dtype 转换、golden 物理重排全部在 CPU 完成，再一次性 H2D；验证只 D2H。禁止在 NPU 上 `torch.rand/randint`、in-place random、`.contiguous()`。
- golden 必须在 CPU 或 PyTorch 语义下实现，不得复用被测 kernel 的中间结果。
- 性能冒烟：`perf_smoke` 用 `torch.npu.synchronize()` 包夹 wall-clock，预热 `PERF_WARMUP=3`
  次、计 `PERF_ITERS=20` 次取均值，打印 `[PERF]` 行；正式性能结论用 `msprof op`。
  这两个常数必须与 `assets/compare_common.py` 的 `WARMUP` / `ITERS` 一致，否则 test 的
  "耗时"与 compare 的"比值"不是同一口径。
- **单次 wall-clock 数值不是结论**：同一份代码在同一张卡上重复运行可以差 2 倍以上（同卡
  并发进程尤其明显），所以绝对 us 不能当达标线，跨运行的比值会翻转。测法与实测波动见
  [triton-baseline.md §4](triton-baseline.md)。

## 5. 结果报告

完成时输出结构化摘要：

```text
算子: {op}  状态: PASS/FAIL
文件: custom/{op}/{op}.py, custom/{op}/test_{op}.py
精度: L0 {n} 用例全过 / 失败用例列表
性能: {shape} 下 {时间或GFLOPS}，对比 PyTorch NPU 基线 +/-X%（若测）
已知限制: 未验证项如实列出
```

## 6. Triton 基线对比（同卡互验）

每个算子除 `test_{op}.py` 外，还应产出 `{op}_triton.py`（Triton-Ascend 基线）与 `compare_{op}.py`
（同卡、同数据、同计时协议的精度+性能对比），并把 [assets/compare_common.py](../assets/compare_common.py)
一起部署为 `custom/compare_common.py`（缺它 `compare_{op}.py` 直接 `ModuleNotFoundError`），
部署整个 `custom/` 目录后在 `{op}/` 下运行。`compare_{op}.py` 的 `compare_configs` 必须与
`test_{op}.py` 的 `test_configs["l0"]` + `["l1"]` **逐条同值同序**，脚本开跑前会 import
`test_{op}` 逐条核对，不一致即 `[COMPARE-CONFIG_FAIL]` 退出 1。
对比判定、容差（含 `DIRECT_TOL` 数值）、计时协议、Triton-Ascend 实测坑位
见 [triton-baseline.md](triton-baseline.md)。
