"""TileLang vs Triton 同卡对比的公共工具：容差表、精度判定、计时协议。

部署位置：`custom/compare_common.py`（`custom/{op}/compare_{op}.py` 通过
`sys.path` 上溯一级 import）。本文件与 `assets/test_template.py` 必须成对使用：
两张容差表与计时协议逐值一致，否则"test 过了"与"compare 过了"不是同一口径。

照抄后不要删掉的三条安全前提（都对应曾经的静默假通过）：

1. **未知 dtype 报错，不回落 fp16 容差**。静默回落会让整型算子拿 fp16 容差放行，
   与 references/testing.md「整型必须 0 误差」冲突。整型在 `TOL_TABLE` /
   `DIRECT_TOL` 里显式登记为 0 容差。
2. **空张量、golden 全为非有限值、全非有限互比一律判失败**，不把 `mean()` 作用在
   空张量上（会得到 nan 而静默通过）。
3. **NaN / +Inf / -Inf mask 先严格比对**，再只在双方有限位置算 atol/rtol 与 max_abs。

`bench` 依赖 `torch.npu`，只能在装有 torch_npu 的昇腾环境里调用；在纯 CPU 机器上
只 import 本文件（不调用 bench）是安全的。
"""

import torch

# dtype: (atol, rtol, max_abs_limit, required_matched_ratio)
# 与 references/testing.md §2 的表逐值一致，也与 assets/test_template.py 的
# get_precision 一致。
TOL_TABLE = {
    "float16": (2**-14, 2**-9, 1e-1, 0.99),
    "bfloat16": (2**-10, 2**-6, 1e0, 0.99),
    "float32": (2**-16, 2**-10, 1e-2, 0.99),
    # 下面三行取自上游 CANN 的 TileLang 精度口径，本机未复核：只有算子真的用这些 dtype 时
    # 才会走到；走到时请用实测结果校正后再上库。
    "hifloat32": (2**-16, 2**-10, 1e-2, 0.99),
    "float8_e4m3": (2**-4, 2**-2, 1e0, 0.99),
    "float8_e5m2": (2**-3, 2**-1, 1e-1, 0.99),
}

# 整型：必须逐元素精确相等（atol=rtol=0，matched ratio 必须为 1.0）
INT_DTYPES = ("int8", "int16", "int32", "int64", "uint8")
EXACT_TOL = (0.0, 0.0, 0.0, 1.0)

# 两 kernel 直接互比（同一公式、同 dtype，误差应远小于对 golden 的门限）。
# 数值见 references/triton-baseline.md §2。
DIRECT_TOL = {
    "float16": (2**-12, 2**-8),
    "bfloat16": (2**-8, 2**-5),
    "float32": (2**-15, 2**-9),
}
DIRECT_EXACT = (0.0, 0.0)

# 计时协议：预热 3 次 + 计 20 次取均值（wall-clock）。与 test_{op}.py 的
# perf_smoke 的 PERF_WARMUP / PERF_ITERS 逐值一致。
WARMUP = 3
ITERS = 20


def get_tolerance(dtype):
    """→ (atol, rtol, max_abs_limit, required_matched_ratio)。未知 dtype 直接报错。"""
    if dtype in TOL_TABLE:
        return TOL_TABLE[dtype]
    if dtype in INT_DTYPES:
        return EXACT_TOL
    raise ValueError(
        f"未定义容差的 dtype: {dtype!r}；已支持 {sorted(TOL_TABLE) + list(INT_DTYPES)}。"
        "禁止静默回落到 fp16 容差（那会让整型/未知类型被错误放行）。"
        "交叉引用：assets/test_template.py 的 get_precision 用同一语义（同样报错，同样不回落）")


def get_direct_tolerance(dtype):
    """→ (atol, rtol) 两 kernel 互比容差。未知 dtype 直接报错。"""
    if dtype in DIRECT_TOL:
        return DIRECT_TOL[dtype]
    if dtype in INT_DTYPES:
        return DIRECT_EXACT
    raise ValueError(
        f"未定义互比容差的 dtype: {dtype!r}；已支持 {sorted(DIRECT_TOL) + list(INT_DTYPES)}")


def _check_fail(reason):
    print(f"[CHECK_FAIL] {reason}")
    return False, 0.0, float("inf")


def check_precision(actual, golden, dtype):
    """与 golden（CPU fp32 语义）比较，返回 (ok, matched_ratio, max_abs)。

    逐元素有限值比较，要求 matched_ratio ≥ 表内阈值且 max_abs ≤ 表内上限。
    """
    atol, rtol, max_abs_limit, required_ratio = get_tolerance(dtype)
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
        return _check_fail("golden 全为非有限值，无法计算双门限")
    abs_err = (a[m] - g[m]).abs()
    ratio = (abs_err <= (atol + rtol * g[m].abs())).float().mean().item()
    max_abs = abs_err.max().item()
    return (ratio >= required_ratio and max_abs <= max_abs_limit), ratio, max_abs


def compare_direct(out_a, out_b, dtype):
    """两个 kernel 输出直接互比（TileLang vs Triton），返回 (matched_ratio, max_abs)。"""
    atol, rtol = get_direct_tolerance(dtype)
    a, b = out_a.detach().cpu(), out_b.detach().cpu()
    if a.shape != b.shape:
        print(f"[CHECK_FAIL] 互比 shape 不一致: a={tuple(a.shape)} b={tuple(b.shape)}")
        return 0.0, float("inf")
    if a.numel() == 0:
        print("[CHECK_FAIL] 互比空张量: numel()==0")
        return 0.0, float("inf")
    if atol == 0.0 and rtol == 0.0:
        a, b = a.to(torch.int64), b.to(torch.int64)
        mism = int((a != b).sum().item())
        return 1.0 - mism / a.numel(), (0.0 if mism == 0 else float("inf"))
    a, b = a.float(), b.float()
    for name, ma, mb in (("NaN", a.isnan(), b.isnan()),
                         ("+Inf", a == float("inf"), b == float("inf")),
                         ("-Inf", a == float("-inf"), b == float("-inf"))):
        if not torch.equal(ma, mb):
            print(f"[CHECK_FAIL] 互比 {name} mask 不一致: a={int(ma.sum().item())} 个, "
                  f"b={int(mb.sum().item())} 个")
            return 0.0, float("inf")
    m = torch.isfinite(a) & torch.isfinite(b)
    if int(m.sum().item()) == 0:
        print("[CHECK_FAIL] 互比双方全为非有限值，无法计算比值")
        return 0.0, float("inf")
    abs_err = (a[m] - b[m]).abs()
    ratio = (abs_err <= (atol + rtol * b[m].abs())).float().mean().item()
    return ratio, abs_err.max().item()


def bench(fn, warmup=WARMUP, iters=ITERS):
    """wall-clock + torch.npu.synchronize 计时，返回平均耗时 us。

    与 test_{op}.py 的 perf_smoke 同协议：预热 `warmup` 次、计 `iters` 次取均值
    （两处默认值由 WARMUP / ITERS 统一，口径不同会让"test 的性能数字"与
    "compare 的性能比值"不可比）。两实现共用本函数以保证公平。
    """
    import time
    torch.npu.synchronize()
    for _ in range(warmup):
        fn()
    torch.npu.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    torch.npu.synchronize()
    return (time.perf_counter() - t0) / iters * 1e6
