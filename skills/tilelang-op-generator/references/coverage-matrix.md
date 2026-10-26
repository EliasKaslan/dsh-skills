# 覆盖矩阵（最低测什么才算测过）

"精度过了"不等于"测过了"。本文件定义每个算子类别**至少**要覆盖的维度，以及缺维度时怎么记账。
判定由 [scripts/check_coverage.py](../scripts/check_coverage.py) 执行，不靠人工数。

## 1. 维度清单

每个维度有稳定 ID，写进测试文件顶部的 `COVERAGE_MANIFEST` 才能被脚本认到。

| ID | 含义 | 记法 |
| --- | ------ | ------ |
| `D-DTYPE-<dt>` | 每个声明支持的 dtype 至少一条用例 | `D-DTYPE-fp16`、`D-DTYPE-bf16`、`D-DTYPE-int8` |
| `D-SHAPE-ALIGNED` | 全维度都是 block 整数倍 | 恒要求 |
| `D-SHAPE-TAIL-1` | 尾块余数 == 1（最易暴露边界 bug） | 有 tiling 的算子 |
| `D-SHAPE-TAIL-MID` | 尾块余数取 block 的中间值 | 有 tiling 的算子 |
| `D-SHAPE-PRIME` | 全维度取质数（完全非对齐） | 有 tiling 的算子 |
| `D-SHAPE-EDGE` | `1×N`、`N×1`、单元素 | 恒要求 |
| `D-SHAPE-RANK-<r>` | 每个支持的 rank 各一条 | rank 范围 > 1 时 |
| `D-VALRANGE-S` | 值域 `[-1, 1]` | 浮点算子 |
| `D-VALRANGE-M` | 值域 `[-10, 10]` | 浮点算子 |
| `D-VALRANGE-L` | 接近 dtype 上界 | 浮点算子 |
| `D-VALRANGE-ASYM` | 非对称值域 `[-5, 10]` | 浮点算子 |
| `D-PARAM-<name>` | 每个关键属性（dim/eps/scale/shift/base）各一条 | 有属性的算子 |
| `D-SPECIAL-INF` | ±Inf 输入 | 浮点算子 |
| `D-SPECIAL-NAN` | NaN 输入 | 浮点算子 |
| `D-SPECIAL-ZERO` | 全 0 / 含 0 输入 | 恒要求 |
| `D-SPECIAL-DBOUND` | dtype 边界值（fp16 ≈ ±65504、fp32 exp ≈ ±88） | 浮点算子 |
| `D-EXC-DTYPE` | 非法/不支持 dtype 被拒绝 | 恒要求（L2） |
| `D-EXC-SHAPE` | 非法 shape 被拒绝 | 恒要求（L2） |

命名规则：`D-DTYPE-` 后的 dtype 用去掉 `torch.` 前缀的短名（`fp16`/`bf16`/`fp32`/`int8`…），
脚本按前缀前缀校验，不校验短名白名单。

## 2. 各类别的最低要求

`强制` = 写进 `COVERAGE_NA` 也判失败；`可豁免` = 可在 `COVERAGE_NA` 里写理由跳过。

| 类别 | 强制维度 | 可豁免维度 |
| ------ | --------- | ----------- |
| Activation（纯 Vector 单步） | `D-DTYPE-*`、`D-SHAPE-ALIGNED`、`D-SHAPE-EDGE`、`D-SPECIAL-ZERO`、`D-EXC-*`、`D-VALRANGE-S`/`M`/`L`/`ASYM` | `D-SHAPE-TAIL-1`/`TAIL-MID`/`PRIME`（无 tiling 边界时）、`D-SPECIAL-INF`/`NAN`/`DBOUND`、`D-PARAM-*` |
| Reduction | `D-DTYPE-*`、`D-SHAPE-ALIGNED`、`D-SHAPE-EDGE`、`D-SPECIAL-ZERO`、`D-EXC-*`、`D-VALRANGE-S`/`M`/`L`/`ASYM`、`D-PARAM-dim`、`D-SHAPE-TAIL-1`/`TAIL-MID`/`PRIME` | `D-SPECIAL-INF`/`NAN`/`DBOUND` |
| Softmax / Normalization | `D-DTYPE-*`、`D-SHAPE-ALIGNED`/`TAIL-1`/`TAIL-MID`/`PRIME`/`EDGE`、`D-VALRANGE-*`、`D-PARAM-*`、`D-SPECIAL-INF`/`NAN`/`ZERO`、`D-EXC-*` | 无 |
| GEMM（纯 Cube） | `D-DTYPE-*`、`D-SHAPE-ALIGNED`/`TAIL-1`/`TAIL-MID`/`PRIME`（**含 K 轴非对齐**）、`D-EXC-*`、`D-SPECIAL-ZERO` | `D-SPECIAL-INF`/`NAN`（矩阵乘溢出语义弱）、`D-VALRANGE-L`、`D-VALRANGE-ASYM` |
| Fusion（CV 融合） | 上表适用的并集，最严格：`D-DTYPE-*`、`D-SHAPE-ALIGNED`/`TAIL-1`/`TAIL-MID`/`PRIME`/`EDGE`、`D-VALRANGE-*`、`D-SPECIAL-ZERO`/`INF`/`NAN`、`D-EXC-*` | 无 |
| 整型/量化 | `D-DTYPE-*`、`D-SHAPE-ALIGNED`/`EDGE`、`D-SPECIAL-ZERO`、`D-EXC-*` | `D-SHAPE-TAIL-1`/`TAIL-MID`/`PRIME`、`D-SPECIAL-INF`/`NAN`/`DBOUND`、`D-VALRANGE-*` |

本表与 `scripts/check_coverage.py` 的 `RULES` 必须逐条一致——**脚本才是门禁**，两处不一致时以脚本
为准并改本表（已按脚本校正过一次：`D-SPECIAL-DBOUND` 与 `D-PARAM-*` 属于可豁免而非强制，
Reduction 不含 `D-SHAPE-TAIL-MID` 之外的可豁免尾块项，GEMM 的 `D-SHAPE-TAIL-MID` 是强制）。
`--category` 未知或不给且没有 `CATEGORY` 时按 `generic` 校验，只查恒要求维度。

## 3. GEMM 的三轴陷阱

**最容易漏的一条**：只把 M 设成非对齐。GEMM 的 M、N、K 三轴各自都会独立触发尾块路径，
K 轴非对齐还会改变 `T.Pipelined` 的收尾逻辑，必须三轴都覆盖：

| 维度 | 最小要求 |
| ------ | --------- |
| `D-SHAPE-TAIL-1` | 至少一条 `M = block_M*k + 1`；再至少一条非对齐 K |
| `D-SHAPE-TAIL-MID` | M 与 N 同时取 block 中间余数 |
| `D-SHAPE-PRIME` | M、N、K 中至少 2 轴取质数 |

## 4. 确定性 shape 配方

不要手挑 shape，按公式生成，保证非对齐必然出现：

```python
def nearest_prime(n: int) -> int:
    """取 <= n 的最大质数，避免超出声明的支持范围。"""
    for c in range(n, 1, -1):
        if all(c % d for d in range(2, int(c ** 0.5) + 1)):
            return c
    return 2


def gen_shapes(block_m: int, block_n: int, k: int = 4) -> dict:
    return {
        "D-SHAPE-ALIGNED":  (block_m * k, block_n * k),
        "D-SHAPE-TAIL-1":   (block_m * k + 1, block_n * k),
        "D-SHAPE-TAIL-MID": (block_m * k + block_m // 2, block_n * k + block_n // 2),
        "D-SHAPE-PRIME":    (nearest_prime(block_m * k), nearest_prime(block_n * k)),
        "D-SHAPE-EDGE":     (1, block_n * k),
    }
```

多维算子：每个 rank 各来一组"ALIGNED + 一条非对齐"。
GEMM：额外补 `K = block_K * k + 1` 与质数 K 各一条。

## 5. 记账方式

在 `test_{op}.py` 顶部（`test_configs` 附近）加两个模块级字典：

```python
# 覆盖记账：ID -> 命中的用例条数（可以小于实际条数，但不能为 0）
COVERAGE_MANIFEST = {
    "D-DTYPE-fp16": 6,
    "D-SHAPE-ALIGNED": 2,
    "D-SHAPE-TAIL-1": 1,
    "D-SPECIAL-ZERO": 1,
    "D-EXC-SHAPE": 2,
    ...
}

# 确实不适用的维度，必须写清理由；类别表里标"强制"的写在这里也会判失败
COVERAGE_NA = {
    "D-SPECIAL-INF": "纯整数算子，无浮点特殊值",
}
```

两条硬规则：

1. **没记账 = 没覆盖**。脚本只认这两个字典，不支持从注释或变量名里猜。
   **值必须是正整数**：写 `0`、负数或非整数的键按"未记账"处理（否则全写 0 的 manifest 也能拿 exit 0）。
   `COVERAGE_NA` 的理由必须是**非空字符串**，`""` 按"没写理由"判 `[MISS]`。
2. **MANIFEST 条数必须能被真实用例支撑**。脚本会与 `test_configs` 的字面量条数做上界比较，
   一旦 `manifest 总量 > 实际用例数 × max(3, 维度数)`（同一条用例可覆盖多维度，故留余量）就告警，
   提示可能虚报；用例表不是字面量时打 `[INFO]` 跳过这条比较。

`test_configs` / `COVERAGE_MANIFEST` / `COVERAGE_NA` 必须写成**字面量**（可被 `ast.literal_eval`
求值）；用 `[(...)] * 3` 这类表达式虽能跑，但脚本数不出用例条数与记账值。

## 6. 运行

```bash
python scripts/check_coverage.py --test custom/{op}/test_{op}.py --category gemm
```

`--category` 省略时读测试文件里的 `CATEGORY` 常量；都没有则按"所有恒要求维度"校验。
退出码 0 = 通过，1 = 有强制维度缺失（打印缺失清单），2 = 脚本自身错误（文件读不到/语法错）。
