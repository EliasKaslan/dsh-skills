"""基于 {op} 的分层测试模板：L0/L1/L2/Boundary + 性能冒烟 + main(--level)。

用法：复制本文件为 custom/{op}/test_{op}.py，然后按下表改完 6 处。

必须替换 / 实现的位置，以及漏改的后果：

1. 全文所有 `{op}` 占位符 → 算子名。
   漏改 = `from {op} import {op}` 与 `def golden_{op}` 是语法错误，
   import 阶段即崩（响亮，非静默）。
2. `golden_{op}(...)` → 用 PyTorch/NumPy 在 CPU 语义下实现数学公式。
   保持 `raise NotImplementedError` = 每个用例打印 [PRECISION_FAIL] 且退出码 1（响亮）。
3. `test_configs` 的 `"l0"` / `"l1"` 两张表 → 填用例元组。
   **留空 = 立即打印 [PRECISION_FAIL] 并退出码 1**（本模板把"零用例"显式判为失败，
   不会再出现空循环假报 Test Passed! 的假通过）。
4. `make_inputs(...)` → 构造 CPU 输入张量并返回 list。
   返回空 list = 打印 [PRECISION_FAIL] 后**早退**（不调用内核），退出码 1。
5. `perf_config` → 性能冒烟用例。`None` = `--level perf` 与 `--level all` 判失败。
6. `COVERAGE_MANIFEST` / `COVERAGE_NA` / `CATEGORY` → 按 references/coverage-matrix.md
   的类别表逐维度记账。**漏填 = `scripts/check_coverage.py` 判每个维度 MISS 并退出码 1**，
   交付门禁直接卡住。

用例元组的元素顺序 = 本文件 `run_case` 的形参顺序，与 kernel 形参顺序**无关**：

    (dtype, M, N, block_M, block_N)        # dtype 在首位是本模板 run_case 的约定

`l2` / `boundary` 两层不吃元组：每个元素是**零参可调用对象**（函数或 lambda），
调用时抛异常 = 正确拒绝非法输入。例：

    "l2": [lambda: {op}(0, 128, 32, 128)],            # 非法 M，期望抛异常
    "boundary": [lambda: run_case("float16", 64, 256, 64, 128, valrange="inf")],

按 L0/L1 的元组惯例往这两层塞元组，会在调用处报 `TypeError: 'tuple' object is not
callable` 并被吞成 [BOUNDARY_WARN]（不阻塞，但等于没测）。

kernel 调用一律用**关键字**传参：{op}(M, N, block_M, block_N, dtype=dtype)。
不要照元组顺序做位置传参：实战 kernel 签名形如
`def softmax(M, N, block_M, block_N, dtype="float16")`，dtype 在**末位**且带默认值；
写成 `{op}(*cfg)` 会把 dtype 塞到 M 上（TypeError 或荒谬的编译错误）。
若你的算子签名不同（如 matmul 还要 K 与 block_K），同步扩展用例元组、`run_case` /
`run_perf` 形参、kernel 关键字调用与 `make_inputs` 的签名，**不要**退化成位置传参。

分层与退出码：L0/L1 计入退出码（阻塞）；L2/Boundary 不计入（非阻塞）；perf 计入
（`--level perf` 或 `all` 时为阻塞层）。
"""

import argparse
import os
import sys
import time

import tilelang
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from {op} import {op}  # noqa: E402


# ========== Golden 参考实现（精度基准，必须在 CPU 语义下按数学公式实现） ==========
def golden_{op}(*inputs):
    raise NotImplementedError("用 PyTorch/NumPy 实现算子数学公式；禁止复用被测 kernel 的中间结果")


# ========== 用例表（必须填；阻塞层的空表 = 判失败） ==========
test_configs = {
    # L0 门槛精度：规则 shape（各维能被 block 整除），先跑这个收敛。
    # 经验规模：3 例，含 1 个 float32 例。
    # 元组 = (dtype, M, N, block_M, block_N)
    "l0": [],

    # L1 功能/不规则：尾块 shape（例如 M=34 或 N=130 这类非整除值）。
    # 经验规模：2 例，全部为尾块。
    "l1": [],

    # L2 负向（非法输入应被拒绝）/ Boundary 合法极值：非阻塞层，不计入退出码。
    # **这两层填的是零参可调用对象**（函数/lambda），不是一个元组：
    #   抛异常 = 正确拒绝（[BOUNDARY_PASS]）  /  不抛 = 静默接受（[BOUNDARY_WARN]）。
    # 留空则打印 [BOUNDARY_SKIP]（明确表示"没测"，不冒充 PASS）。
    "l2": [],
    "boundary": [],
}

# 性能冒烟用例：(dtype, M, N, block_M, block_N)；None = perf 层判失败。
# 留空不会退回"不测而通过"：--level perf / all 会直接判失败。
perf_config = None

# ========== 覆盖矩阵记账（交付门禁用，见 references/coverage-matrix.md §2/§5） ==========
# CATEGORY 决定 scripts/check_coverage.py 用哪套规则；取值：
# activation / reduction / normalization / softmax / gemm / fusion / integer / generic
CATEGORY = "generic"

# 维度 ID -> 命中的用例条数。**值必须是正整数**：0 或不写 = 该维度未覆盖。
# 键必须覆盖本类别规则里的全部强制维度，漏一个就是 [MISS] + 退出码 1。
# 例（softmax 类别，仅示意）：
#   "D-DTYPE-fp16": 3, "D-SHAPE-ALIGNED": 2, "D-SHAPE-TAIL-1": 1,
#   "D-VALRANGE-M": 2, "D-SPECIAL-NAN": 1,
COVERAGE_MANIFEST = {}

# 确实不测的维度 -> 理由（必须非空字符串；空串等于没写理由，仍判 [MISS]）。
# 强制维度不接受豁免：写进这里会被判 "mandatory，却写在 COVERAGE_NA"。
# 例：COVERAGE_NA = {"D-SPECIAL-DBOUND": "该算子不涉及 dtype 上界饱和"}
COVERAGE_NA = {}

# 性能冒烟计时协议（与 assets/compare_common.py 的 WARMUP/ITERS 保持一致，
# 保证 test 的性能冒烟与 compare 的性能比值同一口径）。
PERF_WARMUP = 3
PERF_ITERS = 20


# ========== 精度标准（混合容差双门限） ==========
# 交叉引用：本函数的容差表与「未知 dtype 报错」语义必须与
# assets/compare_common.py 的 TOL_TABLE / get_tolerance 逐值一致，
# 否则 test 的 [PRECISION_PASS] 与 compare 的 [COMPARE-PRECISION_PASS] 不是同一口径。
INT_DTYPES = ("int8", "int16", "int32", "int64", "uint8")
EXACT_TOL = (0.0, 0.0, 0.0, 1.0)


def get_precision(dtype):
    fp_table = {
        "float16": (2**-14, 2**-9, 1e-1, 0.99),
        "bfloat16": (2**-10, 2**-6, 1e0, 0.99),
        "float32": (2**-16, 2**-10, 1e-2, 0.99),
        # 与 assets/compare_common.py 的 TOL_TABLE 逐值一致（含下面三行）
        "hifloat32": (2**-16, 2**-10, 1e-2, 0.99),
        "float8_e4m3": (2**-4, 2**-2, 1e0, 0.99),
        "float8_e5m2": (2**-3, 2**-1, 1e-1, 0.99),
    }
    if dtype in INT_DTYPES:
        return EXACT_TOL
    if dtype in fp_table:
        return fp_table[dtype]
    # 未知 dtype 直接报错：静默回落 float16 容差会让整型/新类型被错误放行
    raise ValueError(
        f"未定义容差的 dtype: {dtype!r}；已支持 {sorted(fp_table) + list(INT_DTYPES)}。"
        "禁止静默回落到 float16 容差（与 assets/compare_common.py 的 get_tolerance 同语义）")


def _check_fail(reason):
    print(f"[CHECK_FAIL] {reason}")
    return False, 0.0, float("inf")


def check_precision(actual, golden, dtype):
    """混合容差双门限判定，返回 (ok, matched_ratio, max_abs)。

    NaN / +Inf / -Inf mask 先严格比对，再只在双方有限位置算 atol/rtol 与 max_abs；
    空张量与 golden 全为非有限值一律判失败（不得静默通过）。
    """
    atol, rtol, max_abs_limit, required_ratio = get_precision(dtype)
    a, g = actual.detach().cpu(), golden.detach().cpu()
    if a.shape != g.shape:
        return _check_fail(f"shape 不一致: actual={tuple(a.shape)} golden={tuple(g.shape)}")
    if a.numel() == 0:
        return _check_fail("空张量: numel()==0，无可比较元素")
    if atol == 0.0 and rtol == 0.0:
        a, g = a.to(torch.int64), g.to(torch.int64)
        mism = int((a != g).sum().item())
        ratio = 1.0 - mism / a.numel()
        return mism == 0, ratio, (0.0 if mism == 0 else float("inf"))
    a, g = a.float(), g.float()
    for name, ma, mg in (("NaN", a.isnan(), g.isnan()),
                         ("+Inf", a == float("inf"), g == float("inf")),
                         ("-Inf", a == float("-inf"), g == float("-inf"))):
        if not torch.equal(ma, mg):
            return _check_fail(
                f"{name} mask 与 golden 不一致: actual={int(ma.sum().item())} 个, "
                f"golden={int(mg.sum().item())} 个")
    m = torch.isfinite(g)
    if int(m.sum().item()) == 0:
        return _check_fail("golden 全为非有限值，无法计算双门限（禁止全 NaN 作为唯一特殊值用例）")
    abs_err = (a[m] - g[m]).abs()
    ratio = (abs_err <= (atol + rtol * g[m].abs())).float().mean().item()
    max_abs = abs_err.max().item()
    return (ratio >= required_ratio and max_abs <= max_abs_limit), ratio, max_abs


# ========== 输入构造（必须在 CPU 上生成，再一次性 H2D） ==========
def make_inputs(dtype, M, N, block_M, block_N):
    """构造 CPU 输入张量，返回 list（顺序与 kernel 的输入参数一致）。

    多输入算子（如 matmul 需要 a、b 两个张量）改本函数返回多个张量即可。
    禁止在 NPU 上 rand/randint、in-place random 与 .contiguous()。
    """
    if dtype in {"int8", "int16", "int32", "int64", "uint8"}:
        x = torch.randint(-8, 8, (M, N), dtype=getattr(torch, dtype))
    else:
        x = torch.randn(M, N, dtype=getattr(torch, dtype))
    return [x]


# ========== 单用例执行（L0/L1 共用，避免循环体重复展开） ==========
def run_case(dtype, M, N, block_M, block_N, level):
    kernel = {op}(M, N, block_M, block_N, dtype=dtype)
    torch.manual_seed(0)
    inputs = make_inputs(dtype, M, N, block_M, block_N)
    if not inputs:
        print(f"[PRECISION_FAIL] {level} {dtype} ({M},{N}) block=({block_M},{block_N}): "
              f"make_inputs 返回空表，没有输入可喂给内核（不是精度问题）")
        return False
    with torch.no_grad():
        out = kernel(*[x.npu() for x in inputs])
        ref = golden_{op}(*inputs)
    if ref is None:
        print(f"[PRECISION_FAIL] {level} {dtype} ({M},{N}): golden_{op} 返回 None（未实现）")
        return False
    if out is None:
        print(f"[PRECISION_FAIL] {level} {dtype} ({M},{N}): kernel 返回 None")
        return False
    passed, ratio, max_abs = check_precision(out, ref, dtype)
    tag = "PASS" if passed else "FAIL"
    print(f"[PRECISION_{tag}] {level} dtype={dtype} shape=({M},{N}) "
          f"block=({block_M},{block_N}) matched_ratio={ratio:.4f} max_abs={max_abs:.3e}")
    return passed


def _run_level(level, configs):
    """阻塞层的统一入口：空表直接判失败，不留静默假通过通道。"""
    if not configs:
        print(f"[PRECISION_FAIL] {level}: 用例表 test_configs['{level}'] 为空 —— "
              f"空表会让循环空转并假报通过（零用例却退出 0），本模板将空表判为失败。"
              f"请填 (dtype, M, N, block_M, block_N) 元组。"
              f"注意：本行不会打印任何通过标记，grep 通过标记时不应命中这里。")
        return False
    ok = True
    for cfg in configs:
        try:
            ok &= run_case(*(tuple(cfg) + (level,)))
        except Exception as e:
            print(f"[PRECISION_FAIL] {level} {cfg}: {type(e).__name__}: {e}")
            ok = False
    return ok


# ========== L0：门槛精度（规则 shape，先跑这个收敛） ==========
def test_{op}_l0():
    return _run_level("l0", test_configs.get("l0"))


# ========== L1：功能/不规则（尾块）shape ==========
def test_{op}_l1():
    return _run_level("l1", test_configs.get("l1"))


# ========== L2：负向（非法输入应被拒绝；非阻塞，不计入退出码） ==========
# 每个元素是**零参可调用对象**（函数 / lambda）：调用时抛异常 = 正确拒绝。
# 正确拒绝打 [BOUNDARY_PASS]，静默接受打 [BOUNDARY_WARN]（与 acceptance-checklist 3.3 同口径）。
def test_{op}_l2():
    cases = test_configs.get("l2") or []
    if not cases:
        print("[BOUNDARY_SKIP] l2: no negative cases defined (非阻塞层，不计入退出码)")
        return
    for cfg in cases:
        try:
            cfg()
        except Exception as e:
            print(f"[BOUNDARY_PASS] l2: correctly rejected with {type(e).__name__}: {e}")
        else:
            print("[BOUNDARY_WARN] l2: silently accepted (非法输入未被拒绝)")


# ========== Boundary：合法极值/特殊值（非阻塞，不计入退出码） ==========
# 每个元素同样是零参可调用对象；跑通打 [BOUNDARY_PASS]，抛异常打 [BOUNDARY_WARN]。
def test_{op}_boundary():
    cases = test_configs.get("boundary") or []
    if not cases:
        print("[BOUNDARY_SKIP] boundary: no special-value cases defined (非阻塞层，不计入退出码)")
        return
    for cfg in cases:
        try:
            cfg()
            print("[BOUNDARY_PASS] boundary: case accepted as expected")
        except Exception as e:
            print(f"[BOUNDARY_WARN] boundary: {type(e).__name__}: {e}")


# ========== 性能冒烟（wall-clock + torch.npu.synchronize 包夹；正式结论用 msprof op） ==========
def perf_smoke():
    if perf_config is None:
        print("[PERF_FAIL] perf_config 为 None：请在模板里填 (dtype, M, N, block_M, block_N)")
        return False
    dtype, M, N, block_M, block_N = perf_config
    kernel = {op}(M, N, block_M, block_N, dtype=dtype)
    torch.manual_seed(1)
    inputs = make_inputs(dtype, M, N, block_M, block_N)
    if not inputs:
        print("[PERF_FAIL] make_inputs 返回空表，无法计时")
        return False
    dev = [x.npu() for x in inputs]
    try:
        with torch.no_grad():
            torch.npu.synchronize()
            for _ in range(PERF_WARMUP):
                kernel(*dev)
            torch.npu.synchronize()
            t0 = time.perf_counter()
            for _ in range(PERF_ITERS):
                kernel(*dev)
            torch.npu.synchronize()
            avg_us = (time.perf_counter() - t0) / PERF_ITERS * 1e6
    except Exception as e:
        print(f"[PERF_FAIL] {op} {dtype} shape=({M},{N}) block=({block_M},{block_N}): "
              f"{type(e).__name__}: {e}")
        return False
    print(f"[PERF] {op} {dtype} shape=({M},{N}) block=({block_M},{block_N}) "
          f"warmup={PERF_WARMUP} iters={PERF_ITERS} avg={avg_us:.1f} us")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="l0",
                        choices=["l0", "l1", "l2", "boundary", "perf", "all"])
    args = parser.parse_args()

    tilelang.disable_cache()
    torch.manual_seed(0)

    blocking_ok = True
    if args.level in ("l0", "all"):
        blocking_ok &= test_{op}_l0()
    if args.level in ("l1", "all"):
        blocking_ok &= test_{op}_l1()
    if args.level in ("l2", "all"):
        test_{op}_l2()
    if args.level in ("boundary", "all"):
        test_{op}_boundary()
    if args.level in ("perf", "all"):
        blocking_ok &= perf_smoke()

    if blocking_ok:
        print("Test Passed!")
        sys.exit(0)
    print("Test Failed!")
    sys.exit(1)


if __name__ == "__main__":
    main()
