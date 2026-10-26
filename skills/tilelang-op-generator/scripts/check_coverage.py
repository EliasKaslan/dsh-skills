#!/usr/bin/env python3
"""覆盖矩阵静态检查：只读 AST，不 import 被测文件（不需要 NPU / torch / tilelang）。

用法：
    python scripts/check_coverage.py --test custom/{op}/test_{op}.py [--category gemm]

判定依据（写在测试文件顶层的两个模块级字典，见 references/coverage-matrix.md §5）：
    COVERAGE_MANIFEST = {"D-SHAPE-TAIL-1": 1, ...}   # 命中的维度 -> 条数
    COVERAGE_NA       = {"D-SPECIAL-INF": "纯整数算子"}  # 确实不适用 + 理由
可选：CATEGORY = "gemm"（与 --category 等价，命令行优先）

退出码：0 = 通过；1 = 有强制维度缺失；2 = 脚本自身错误（文件读不到 / 语法错 / 参数错）。
"""

from __future__ import annotations

import argparse
import ast
import sys

# 每个维度用"精确 ID"或"前缀模式"（以 * 结尾）表达。
_ALWAYS_MANDATORY = [
    "D-DTYPE-*",
    "D-SHAPE-ALIGNED",
    "D-SHAPE-EDGE",
    "D-SPECIAL-ZERO",
    "D-EXC-DTYPE",
    "D-EXC-SHAPE",
]

_TILED_EXEMPTIBLE = [
    "D-SHAPE-TAIL-1",
    "D-SHAPE-TAIL-MID",
    "D-SHAPE-PRIME",
]

_FLOAT_VALUE_RANGE = [
    "D-VALRANGE-S",
    "D-VALRANGE-M",
    "D-VALRANGE-L",
    "D-VALRANGE-ASYM",
]

_FLOAT_SPECIAL = [
    "D-SPECIAL-INF",
    "D-SPECIAL-NAN",
    "D-SPECIAL-DBOUND",
]

# category -> (mandatory, exemptible)
RULES: dict[str, tuple[list[str], list[str]]] = {
    "activation": (
        _ALWAYS_MANDATORY + _FLOAT_VALUE_RANGE,
        _TILED_EXEMPTIBLE + ["D-SPECIAL-INF", "D-SPECIAL-NAN", "D-SPECIAL-DBOUND",
                             "D-PARAM-*"],
    ),
    "reduction": (
        _ALWAYS_MANDATORY + _FLOAT_VALUE_RANGE
        + ["D-PARAM-dim", "D-SHAPE-TAIL-1", "D-SHAPE-TAIL-MID", "D-SHAPE-PRIME"],
        ["D-SPECIAL-INF", "D-SPECIAL-NAN", "D-SPECIAL-DBOUND"],
    ),
    "normalization": (
        _ALWAYS_MANDATORY
        + ["D-SHAPE-TAIL-1", "D-SHAPE-TAIL-MID", "D-SHAPE-PRIME"]
        + _FLOAT_VALUE_RANGE
        + ["D-PARAM-*", "D-SPECIAL-INF", "D-SPECIAL-NAN"],
        [],
    ),
    "softmax": (
        _ALWAYS_MANDATORY
        + ["D-SHAPE-TAIL-1", "D-SHAPE-TAIL-MID", "D-SHAPE-PRIME"]
        + _FLOAT_VALUE_RANGE
        + ["D-PARAM-*", "D-SPECIAL-INF", "D-SPECIAL-NAN"],
        [],
    ),
    "gemm": (
        _ALWAYS_MANDATORY + ["D-SHAPE-TAIL-1", "D-SHAPE-TAIL-MID", "D-SHAPE-PRIME"],
        ["D-SPECIAL-INF", "D-SPECIAL-NAN", "D-VALRANGE-L", "D-VALRANGE-ASYM"],
    ),
    "fusion": (
        _ALWAYS_MANDATORY
        + ["D-SHAPE-TAIL-1", "D-SHAPE-TAIL-MID", "D-SHAPE-PRIME"]
        + _FLOAT_VALUE_RANGE
        + ["D-SPECIAL-INF", "D-SPECIAL-NAN"],
        [],
    ),
    "integer": (
        ["D-DTYPE-*", "D-SHAPE-ALIGNED", "D-SHAPE-EDGE", "D-SPECIAL-ZERO",
         "D-EXC-DTYPE", "D-EXC-SHAPE"],
        _TILED_EXEMPTIBLE + _FLOAT_VALUE_RANGE + _FLOAT_SPECIAL,
    ),
}

CATEGORY_ALIASES = {
    "norm": "normalization",
    "layernorm": "normalization",
    "rmsnorm": "normalization",
    "matmul": "gemm",
    "elementwise": "activation",
    "reduce": "reduction",
    "generic": "generic",
    "": "generic",
}

# generic：没有类别信息时的保守集合（只保留与类别无关的恒要求维度）
RULES["generic"] = (_ALWAYS_MANDATORY, _TILED_EXEMPTIBLE + _FLOAT_VALUE_RANGE + _FLOAT_SPECIAL)


def _literal(node: ast.AST | None):
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _find_assign(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return node.value
        # 兼容 AnnAssign: NAME: dict = {...}
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return node.value
    return None


def _matches(pattern: str, dim: str) -> bool:
    if pattern.endswith("*"):
        return dim.startswith(pattern[:-1])
    return dim == pattern


def _covered(pattern: str, keys) -> bool:
    return any(_matches(pattern, k) for k in keys)


def _na_reason(pattern: str, na: dict) -> str | None:
    for k, v in na.items():
        if _matches(pattern, k):
            return str(v)
    return None


def _claimed_hits(pattern: str, manifest: dict) -> int:
    """按 manifest 的**值**累加命中条数；0/负数/非整数已在 keys 里被剔除。"""
    return sum(v for k, v in manifest.items()
               if isinstance(v, int) and not isinstance(v, bool) and v > 0
               and _matches(pattern, str(k)))


def _count_cases(tree: ast.Module) -> int | None:
    """尽力统计 test_configs 的字面量用例条数；无法静态求值时返回 None。"""
    node = _find_assign(tree, "test_configs")
    if node is None:
        return None
    val = _literal(node)
    if not isinstance(val, dict):
        return None
    total = 0
    found = False
    for v in val.values():
        if isinstance(v, (list, tuple)):
            total += len(v)
            found = True
    return total if found else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="覆盖矩阵静态检查（不 import 被测文件）")
    ap.add_argument("--test", required=True, help="test_{op}.py 路径")
    ap.add_argument("--category", default=None,
                    help="算子类别：activation/reduction/normalization/softmax/gemm/fusion/integer/generic")
    args = ap.parse_args(argv)

    try:
        # utf-8-sig：吃掉 Windows PowerShell `Set-Content -Encoding utf8` 写的 BOM，
        # 否则 ast.parse 报 invalid non-printable character U+FEFF —— 而 CPython 能正常执行该文件。
        with open(args.test, "r", encoding="utf-8-sig") as fh:
            src = fh.read()
        tree = ast.parse(src)
    except OSError as exc:
        print(f"error: 读不到测试文件: {exc}", file=sys.stderr)
        return 2
    except UnicodeDecodeError as exc:
        # 非 UTF-8（例如 GBK 写的带中文注释的文件）必须给可读结论，不能抛 traceback；
        # exit 1 的契约是"缺维度并打印清单"，编码问题不是缺维度，故归 2（脚本自身错误）。
        print(f"error: 测试文件不是 UTF-8 编码（{args.test}）：{exc}"
              f"\n请转成 UTF-8 再跑，例如：iconv -f gbk -t utf-8 -o out.py in.py", file=sys.stderr)
        return 2
    except SyntaxError as exc:
        print(f"error: 语法错误（{args.test}）: {exc}", file=sys.stderr)
        return 2

    manifest = _literal(_find_assign(tree, "COVERAGE_MANIFEST")) or {}
    na = _literal(_find_assign(tree, "COVERAGE_NA")) or {}
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(na, dict):
        na = {}

    category = (args.category or "").strip().lower()
    if not category:
        declared = _literal(_find_assign(tree, "CATEGORY"))
        if isinstance(declared, str):
            category = declared.strip().lower()
    category = CATEGORY_ALIASES.get(category, category)
    if category not in RULES:
        print(f"error: 未知类别 '{category}'，可选：{', '.join(sorted(RULES))}", file=sys.stderr)
        return 2

    mandatory, exemptible = RULES[category]
    # 记账值必须是正整数：0 / 负数 / 非整数等于"没记账"。
    # 只按键存在就判 PASS 的话，全写 0 的 manifest 也能拿 exit 0（"维度假覆盖"）。
    zero_valued = [str(k) for k, v in manifest.items()
                   if isinstance(v, bool) or not isinstance(v, int) or v <= 0]
    keys = [str(k) for k, v in manifest.items()
            if isinstance(v, int) and not isinstance(v, bool) and v > 0]
    missing: list[str] = [f"{k} <-- 记账值必须为正整数（当前 {manifest[k]!r}）" for k in zero_valued]
    na_used: list[tuple[str, str]] = []
    passed: list[tuple[str, str]] = []

    for pat in mandatory:
        if _covered(pat, keys):
            passed.append((pat, f"got {_claimed_hits(pat, manifest)} (mandatory)"))
        else:
            reason = _na_reason(pat, na)
            if reason is not None:
                # 强制维度不接受 N/A：这正是"用 N/A 绕过覆盖"的常见手法
                missing.append(f"{pat} <-- mandatory，却写在 COVERAGE_NA（理由: {reason}）")
            else:
                missing.append(f"{pat} <-- mandatory，未记账")

    for pat in exemptible:
        if _covered(pat, keys):
            passed.append((pat, f"got {_claimed_hits(pat, manifest)}"))
        else:
            reason = _na_reason(pat, na)
            if reason is None or not reason.strip():
                # 空理由（`"D-X": ""`）不算 N/A：文档要求"必须写清理由"
                missing.append(f"{pat} <-- 未记账，且 COVERAGE_NA 未给出非空理由")
            else:
                na_used.append((pat, reason))

    # 未在规则里出现、但记账了的维度：只做展示，不影响结论
    rule_pats = mandatory + exemptible
    extra = [k for k in keys if not any(_matches(p, k) for p in rule_pats)]

    for pat, note in passed:
        print(f"[PASS] {pat:<22} {note}")
    for pat, reason in na_used:
        print(f"[N/A ] {pat:<22} reason: {reason}")
    for pat in missing:
        print(f"[MISS] {pat}")
    for k in extra:
        print(f"[INFO] {k:<22} 已记账但不在 {category} 的规则集内")

    cases = _count_cases(tree)
    total_claim = sum(v for v in manifest.values()
                      if isinstance(v, int) and not isinstance(v, bool) and v > 0)
    if not manifest:
        print(f"[INFO] 未找到 COVERAGE_MANIFEST（见 coverage-matrix.md §5），"
              f"本类别所有维度都会按未记账处理")
    if cases is None:
        print("[INFO] test_configs 不是字面量，用例数无法静态核对（跳过虚报上界比较）")
    elif total_claim > max(cases, 1) * max(3, len(manifest)):
        # 同一条用例可命中多个维度，所以按维度数量缩放上界，避免合规 manifest 被误判虚报
        print(f"[WARN] MANIFEST 声明合计 {total_claim} 条，而 test_configs 只有 {cases} 条用例"
              f"（上界 {max(cases, 1) * max(3, len(manifest))}），疑似虚报")

    print()
    print(f"COVERAGE: {len(passed)} PASS / {len(missing)} MISS / {len(na_used)} N/A"
          f"  category={category}  cases={cases if cases is not None else 'unknown'}")
    if missing:
        print("-> FAIL (exit 1)")
        return 1
    print("-> PASS (exit 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
