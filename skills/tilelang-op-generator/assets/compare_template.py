"""{op}：TileLang vs Triton 同卡、同数据、同计时协议对比（模板）。

用法：复制本文件为 custom/{op}/compare_{op}.py，然后按下表改完 4 处。

必须替换 / 实现的位置，以及漏改的后果：

1. 全文所有 `{op}` 占位符 → 算子名。
   漏改 = `from {op}_triton import {op}_triton` 是语法错误，import 阶段即崩（响亮）。
2. `golden_{op}(...)` → 在 CPU 语义下按数学公式实现，必须与 test_{op}.py 的 golden 一致。
   保持 `raise NotImplementedError` = 首个用例抛异常，被捕获成
   [COMPARE-PRECISION_FAIL]，退出码 1（响亮）。
3. `compare_configs` → 与 test_{op}.py 的 `test_configs["l0"]` + `["l1"]` **逐条同值同序**。
   本文件在开跑前会 import test_{op} 逐条核对，不一致直接 [COMPARE-CONFIG_FAIL] 退出 1；
   留空同样判失败 —— 不会再出现"注释说与 test 对齐、实际只测 2 例"或
   "零用例却打印 Compare Passed!"。
4. `PERF_CASE` → 性能对比用例；`None` = 判失败（不会静默跳过性能对比）。

输出约定（grep 请用这些逐字 marker）：

- `[COMPARE-PRECISION_PASS]` / `[COMPARE-PRECISION_FAIL]`：单个用例的三项判定
  （TileLang 对 golden、Triton 对 golden、两实现逐点互比）。
- `[COMPARE-PERF]`：性能对比（两实现耗时 us 与 TileLang/Triton 比值）。
- 退出码：全部 PASS 为 0，任一失败为 1。

用例元组的元素顺序 = 本文件 `run_case` 的形参顺序，与 kernel 形参顺序**无关**：

    (dtype, M, N, block_M, block_N, level)   # dtype 在首位是 run_case 的约定
    kernel 调用一律用关键字传参：{op}(M, N, block_M, block_N, dtype=dtype)

不要照元组顺序做位置传参：实战 kernel 的 dtype 在**末位**且带默认值，
`{op}(*cfg)` 会把 dtype 塞到 M 上。

矩阵乘类算子（多输入 + K 维）必须改签名，改法：
`make_inputs` 返回 `[a, b]` 两个张量、`golden_{op}(a, b)`、`run_case` 与 `run_perf`
增加 `K` / `block_K` 形参，并同步扩展 `compare_configs` 与 `PERF_CASE` 元组。
"""

import os
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tilelang  # noqa: E402
import triton  # noqa: E402  导入名就是 triton：Triton-Ascend 覆盖式装进 triton/backends/ascend/
from {op} import {op}  # noqa: E402
from {op}_triton import {op}_triton  # noqa: E402
from compare_common import (  # noqa: E402
    ITERS, WARMUP, bench, check_precision, compare_direct, get_tolerance)

# 与 ASCEND_RT_VISIBLE_DEVICES 掩码配合：掩码后逻辑卡 0 即是指定卡（见 testing.md §3）
torch.npu.set_device(0)


# ========== Golden 参考实现（必须与 test_{op}.py 的 golden 一致） ==========
def golden_{op}(*inputs):
    raise NotImplementedError("用 PyTorch/NumPy 实现算子数学公式；禁止复用被测 kernel 的中间结果")


# ========== 用例表（必须与 test_{op}.py 的 L0/L1 逐条同值同序） ==========
# 元组 = (dtype, M, N, block_M, block_N, level)
# 填法示例（取自一次已实测跑通的 softmax 用例，仅供参照数值规模）：
#   ("float16", 128, 256, 32, 256, "l0")
#   ("float16", 256, 512, 32, 256, "l0")
#   ("float32", 128, 256, 32, 256, "l0")
#   ("float16", 34, 130, 32, 128, "l1")     # 尾块
#   ("float16", 17, 300, 32, 128, "l1")     # 尾块
compare_configs = []

# 性能对比用例：(dtype, M, N, block_M, block_N)；None = 判失败
PERF_CASE = None

# 两实现逐点互比要求的 matched_ratio 下限。与 compare_common.DIRECT_TOL 分工不同：
# DIRECT_TOL 给的是逐点容差 (atol, rtol)，本常量给的是"达标点占比"门限，
# 两者合起来等价于 triton-baseline.md §2 的「matched_ratio ≥ 0.99」。
DIRECT_REQUIRED_RATIO = 0.99


# ========== 输入构造（CPU 上生成，再一次性 H2D） ==========
def make_inputs(dtype, M, N):
    """构造 CPU 输入张量，返回 list。矩阵乘类算子在此返回 [a, b] 并补 K 维。

    注意签名与 test_{op}.py 的 make_inputs 不同：这里只有 (dtype, M, N)，
    因为 compare 不需要 block 信息就能造出同样的数据（数据只由 dtype 与 shape 决定）。
    """
    torch_dtype = getattr(torch, dtype)
    if dtype in {"int8", "int16", "int32", "int64", "uint8"}:
        return [torch.randint(-8, 8, (M, N), dtype=torch_dtype)]
    return [torch.randn(M, N, dtype=torch_dtype)]


# ========== 用例一致性校验（防止 compare 与 test 的用例表悄悄漂移） ==========
def _expected_configs():
    import test_{op} as t
    l0 = [tuple(cfg) + ("l0",) for cfg in (t.test_configs.get("l0") or [])]
    l1 = [tuple(cfg) + ("l1",) for cfg in (t.test_configs.get("l1") or [])]
    return l0 + l1


def _check_aligned_with_test():
    try:
        expected = _expected_configs()
    except Exception as e:
        print(f"[COMPARE-CONFIG_FAIL] 无法 import test_{op} 读取用例表: {type(e).__name__}: {e}")
        return False
    actual = [tuple(c) for c in compare_configs]
    if actual != expected:
        print("[COMPARE-CONFIG_FAIL] compare_configs 与 test_{op}.py 的 L0/L1 不一致：")
        print(f"  期望（来自 test_{op}.py）: {expected}")
        print(f"  实际（本文件）          : {actual}")
        return False
    if not actual:
        print("[COMPARE-CONFIG_FAIL] test_{op}.py 的 L0/L1 用例表为空，没有任何用例可比")
        return False
    return True


# ========== 单用例：两实现各自对 golden + 两实现逐点互比 ==========
def run_case(dtype, M, N, block_M, block_N, level):
    get_tolerance(dtype)  # 未知 dtype 立即报错，不静默回落 fp16 容差
    kernel = {op}(M, N, block_M, block_N, dtype=dtype)
    torch.manual_seed(0)
    inputs = make_inputs(dtype, M, N)
    if not inputs:
        print(f"[COMPARE-PRECISION_FAIL] {level} {dtype} ({M},{N}): "
              f"make_inputs 返回空表，没有输入可喂给两实现（不是精度问题）")
        return False
    dev = [x.npu() for x in inputs]
    with torch.no_grad():
        out_tl = kernel(*dev)
        out_tr = {op}_triton(*dev)
        ref = golden_{op}(*inputs)
    if ref is None:
        print(f"[COMPARE-PRECISION_FAIL] {level} {dtype} ({M},{N}): golden_{op} 返回 None（未实现）")
        return False
    if out_tl is None or out_tr is None:
        print(f"[COMPARE-PRECISION_FAIL] {level} {dtype} ({M},{N}): "
              f"kernel 返回 None (TileLang={out_tl is None}, Triton={out_tr is None})")
        return False

    ok_tl, r_tl, e_tl = check_precision(out_tl, ref, dtype)
    ok_tr, r_tr, e_tr = check_precision(out_tr, ref, dtype)
    ratio_ab, err_ab = compare_direct(out_tl, out_tr, dtype)
    ok_ab = ratio_ab >= DIRECT_REQUIRED_RATIO
    ok = ok_tl and ok_tr and ok_ab
    tag = "PASS" if ok else "FAIL"
    print(f"[COMPARE-PRECISION_{tag}] {level} dtype={dtype} shape=({M},{N}) "
          f"block=({block_M},{block_N}) | "
          f"TileLang: ratio={r_tl:.4f} max_abs={e_tl:.3e} ({'PASS' if ok_tl else 'FAIL'}) | "
          f"Triton: ratio={r_tr:.4f} max_abs={e_tr:.3e} ({'PASS' if ok_tr else 'FAIL'}) | "
          f"TL vs TR: matched={ratio_ab:.4f} max_abs={err_ab:.3e}")
    return ok


# ========== 性能对比（两实现共用 compare_common.bench，协议一致） ==========
def run_perf(dtype, M, N, block_M, block_N):
    """两实现计时对比。

    返回值语义（调用方**必须**判 None，否则会出现"打了 [COMPARE-PERF_FAIL]
    却打印 Compare Passed! 并退出 0"）：
    - 成功 → `(us_tl, us_tr)` 两个平均耗时（us）
    - 失败 → `None`（例如 `make_inputs` 返回空表）
    """
    kernel = {op}(M, N, block_M, block_N, dtype=dtype)
    torch.manual_seed(1)
    inputs = make_inputs(dtype, M, N)
    if not inputs:
        print("[COMPARE-PERF_FAIL] make_inputs 返回空表，无法计时")
        return None
    dev = [x.npu() for x in inputs]
    us_tl = bench(lambda: kernel(*dev))
    us_tr = bench(lambda: {op}_triton(*dev))
    speedup = us_tr / us_tl if us_tl > 0 else float("inf")
    print(f"[COMPARE-PERF] {op} {dtype} shape=({M},{N}) block=({block_M},{block_N}) "
          f"warmup={WARMUP} iters={ITERS} triton={triton.__version__} | "
          f"TileLang={us_tl:.1f} us | "
          f"Triton={us_tr:.1f} us | TileLang/Triton={speedup:.2f}x (>1 表示 TileLang 更快)")
    return us_tl, us_tr


def main():
    tilelang.disable_cache()
    if not _check_aligned_with_test():
        print("Compare Failed!")
        sys.exit(1)

    ok = True
    for cfg in compare_configs:
        try:
            ok &= run_case(*cfg)
        except Exception as e:
            print(f"[COMPARE-PRECISION_FAIL] {cfg}: {type(e).__name__}: {e}")
            ok = False

    if PERF_CASE is None:
        print("[COMPARE-PERF_FAIL] PERF_CASE 为 None：请填 (dtype, M, N, block_M, block_N)")
        ok = False
    else:
        try:
            res = run_perf(*PERF_CASE)
        except Exception as e:
            print(f"[COMPARE-PERF_FAIL] {PERF_CASE}: {type(e).__name__}: {e}")
            res = None
        if res is None:
            # 必须在这里落地成失败：run_perf 的失败路径只打印 marker，
            # 不判返回值就会"有 FAIL 标记还退 0"
            print("[COMPARE-PERF_FAIL] run_perf 未返回耗时，性能对比不成立")
            ok = False

    print("Compare Passed!" if ok else "Compare Failed!")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
