#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""算子分诊：拿 profiling 的 op_statistic.csv，判"这份模型图里有没有注定不满足批次不变的算子"。

判决优先级（顺序不能换）：
  1. 强制黑名单（精确名匹配）  → FAIL_BLACKLIST
  2. 芯片白名单                → PASS
  3. 都不在                    → REVIEW_REQUIRED（要么给证据排除，要么做 1e4 条单算子验证）

"关键路径"的口径：按设备耗时占比从高到低累加，覆盖 `--critical-ratio`（默认 0.9）为止。
只看关键路径，是因为占 0.01% 的算子即使不一致也翻不动 top-1；但这只是**缩小范围**，
不等于"非关键路径可以不管"——报告里要列出被排除的算子及其占比。

用法：
  python bi_ops_triage.py --csv op_statistic.csv --chip A3 --json runs/triage.json
  python bi_ops_triage.py --csv-dir profiling/ --chip A3        # 逐 rank 全部文件
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 强制黑名单：这些基础算子本身不满足批次不变，必须走 *BatchInvariant 变体。
# 注意：**只做精确名匹配**。同族融合算子（例如 AddRmsNormBias）不会被匹配到——
# 这是有意的（黑名单宁窄不宽，避免误杀），也是最大的判读盲区。
# ---------------------------------------------------------------------------
BLOCKLIST = [
    "SoftmaxV2",
    "MatMulV2",
    "FusedInferAttentionScore",
    "AddRmsNorm",
    "ReduceSum",
]

# ---------------------------------------------------------------------------
# 白名单：按芯片分区。A2 复用 A3。
# 这是**快照**，随 vLLM-Ascend 版本变化；换版本后应重新采集并更新本表。
# 每条应能回答"为什么它批次不变"：要么是 *BatchInvariant 变体、要么是纯 shape/搬移、
# 要么是逐元素运算（与批形状无关）。
# ---------------------------------------------------------------------------
ALLOWLIST_A3 = [
    # batch invariant 变体
    "FusedInferAttentionScoreBatchInvariant", "SoftmaxV2BatchInvariant",
    "MatMulV2BatchInvariant", "AddRmsNormBatchInvariant", "ReduceSumBatchInvariant",
    "MatMulV3BatchInvariant",
    # shape / 数据搬移：不改变元素值
    "ScatterPaKvCache", "ScatterElementsV2", "Transpose", "Tile", "Slice",
    "ReshapeAndCacheNdKernel", "BroadcastTo", "GatherV3", "GatherV2", "Index",
    "LinearIndex", "Fill",
    # 逐元素 / 比较：与批形状无关
    "SwiGlu", "Sub", "RealDiv", "Neg", "Mul", "MaskedFill", "LogicalNot",
    "LogicalAnd", "Log", "Less", "GreaterEqual", "Cast", "Add", "Abs", "Exp",
    # 归约 / 选择（沿固定轴，不跨批）
    "ReduceMax", "ArgMaxV2",
    # norm
    "RmsNorm",
    # MoE
    "MoeTokenUnpermute", "MoeInitRoutingCustom", "MoeInitRoutingV3", "MoeGatingTopK",
    "GroupedMatmul",
    # 采样随机数：需结合 seed 与采样阶段判断
    "DSARandomUniform",
    # vLLM 自定义 kernel
    "_triton_rope", "_compute_slot_mapping_kernel",
    # 通信：单独出现不代表失败
    "allreduceAicpuKernel", "allgatherAicpuKernel", "hcom_allReduce", "hcom_allGather",
]

ALLOWLIST_A5 = [
    "MatMulV3BatchInvariant", "FusedInferAttentionScoreBatchInvariant",
    "ReduceSumBatchInvariant",
    "GroupedMatmul", "RmsNorm", "Slice", "Add", "SwiGlu", "RealDiv", "Cast",
    "Fill", "Sub",
    "MoeInitRoutingV3", "MoeGatingTopK", "MoeFinalizeRoutingV2",
    "ScatterPaKvCache", "Index", "Tile", "Embedding", "GatherV2", "BroadcastTo",
    "TensorMove", "ScatterElementsV2",
    "ArgMaxV2",
    "_triton_rope", "_compute_slot_mapping_kernel",
]

# 已知的"看着像问题、其实不是"的项：分诊时降级为 INFO，但必须写进报告
KNOWN_BENIGN = {
    "Sort": "top-k 的排序内核（AI_CPU）。同分并列的发射顺序随打包形状变化，"
            "要在比较前做升序规范化；先看 selected-set 是否相同再判失败",
    "SparseFlashAttention": "DSA 稀疏注意力，需按 [T,1,topk] 的 sparse_indices 口径单独验证",
    "LightningIndexer": "稀疏索引选择，tie 顺序敏感；规范化后应 1e4 全过",
    "TransposeBatchMatMul": "shape 搬移 + matmul 融合，与 BatchInvariant 变体不是同一注册名",
    "ConcatD": "拼接，纯搬移",
}


def load_allowlist(chip: str) -> list[str]:
    chip = chip.upper()
    if chip == "A5":
        return ALLOWLIST_A5
    return ALLOWLIST_A3          # A2 复用 A3


def read_csv(path: Path) -> list[dict]:
    """容忍列名差异：OP Type / Op Name 都认；耗时列缺了就按 Count 排序。"""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return rows
        name_key = next((k for k in reader.fieldnames
                         if k and k.strip().lower() in ("op type", "op name", "opname")), None)
        ratio_key = next((k for k in reader.fieldnames
                          if k and "ratio" in k.lower()), None)
        time_key = next((k for k in reader.fieldnames
                         if k and k.strip().lower() == "total time(us)"), None)
        if name_key is None:
            raise SystemExit(f"{path}: 找不到算子名列（应有 'OP Type' 或 'Op Name'）")
        for r in reader:
            name = (r.get(name_key) or "").strip()
            if not name:
                continue
            rows.append({
                "op": name,
                "ratio_pct": float(r.get(ratio_key) or 0) if ratio_key else 0.0,
                "total_time_us": float(r.get(time_key) or 0) if time_key else 0.0,
            })
    return rows


def critical_path(rows: list[dict], ratio: float) -> set[str]:
    ordered = sorted(rows, key=lambda x: x["ratio_pct"], reverse=True)
    picked, acc = set(), 0.0
    for r in ordered:
        if acc >= ratio * 100:
            break
        picked.add(r["op"])
        acc += r["ratio_pct"]
    return picked


def triage_one(rows: list[dict], chip: str, critical_ratio: float) -> dict:
    allow = set(load_allowlist(chip))
    block = set(BLOCKLIST)
    crit = critical_path(rows, critical_ratio)

    verdicts, black_hits, review_hits, benign = [], [], [], []
    for r in rows:
        op = r["op"]
        on_crit = op in crit
        if op in allow:
            v = "ALLOW"
        elif op in block:
            v = "FAIL_BLACKLIST"
            black_hits.append({**r, "on_critical_path": on_crit})
        else:
            v = "REVIEW_REQUIRED"
            review_hits.append({**r, "on_critical_path": on_crit,
                                "note": KNOWN_BENIGN.get(op, "")})
        if op in KNOWN_BENIGN and v == "REVIEW_REQUIRED":
            benign.append(op)
        verdicts.append({**r, "verdict": v, "on_critical_path": on_crit})

    crit_black = [x for x in black_hits if x["on_critical_path"]]
    crit_review = [x for x in review_hits if x["on_critical_path"]]
    crit_benign_only = bool(crit_review) and all(x["op"] in KNOWN_BENIGN
                                                 for x in crit_review)
    if crit_black:
        verdict, code = "FAIL_BLACKLIST", "FAIL_BLACKLIST"
    elif crit_review and not crit_benign_only:
        verdict, code = "REVIEW_REQUIRED", "REVIEW_REQUIRED"
    elif crit_review:
        # 关键路径上的未知算子**全部**是已分析过、判定为良性的那些。
        # 可以进第二阶段，但理由必须在结论里逐条复述——版本一变就要重新判。
        verdict, code = "PASS_WITH_NOTE", "KNOWN_BENIGN_ONLY"
    elif review_hits:
        # 关键路径全清白，但非关键路径仍有未知算子：可以进第二阶段，结论里要写明
        verdict, code = "PASS_WITH_NOTE", "REVIEW_REQUIRED_NON_CRITICAL"
    else:
        verdict, code = "PASS", ""

    return {
        "verdict": verdict,
        "reason_code": code,
        "chip": chip,
        "critical_ratio": critical_ratio,
        "ops_total": len(rows),
        "critical_ops": sorted(crit),
        "blacklist_critical": [x["op"] for x in crit_black],
        "blacklist_all": [x["op"] for x in black_hits],
        "review_critical": [x["op"] for x in crit_review],
        "known_benign_critical": {x["op"]: KNOWN_BENIGN[x["op"]] for x in crit_review
                                  if x["op"] in KNOWN_BENIGN},
        "review_all": [x["op"] for x in review_hits],
        "note": ("关键路径上的未知算子全部属于已知良性集，结论里必须逐条复述其理由；"
                 "换 CANN / vllm-ascend 版本后需重新判定。" if code == "KNOWN_BENIGN_ONLY" else ""),
        "known_benign": sorted(set(benign)),
        "detail": verdicts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="op_statistic.csv → 批次不变性分诊")
    ap.add_argument("--csv", default="", help="单个 op_statistic.csv")
    ap.add_argument("--csv-dir", default="", help="目录，递归找所有 op_statistic*.csv")
    ap.add_argument("--chip", default="A3", help="A2 / A3 / A5（A2 复用 A3 白名单）")
    ap.add_argument("--critical-ratio", type=float, default=0.9)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    files: list[Path] = []
    if args.csv:
        files.append(Path(args.csv))
    if args.csv_dir:
        files.extend(Path(p) for p in glob.glob(
            str(Path(args.csv_dir) / "**" / "op_statistic*.csv"), recursive=True))
    if not files:
        ap.error("需要 --csv 或 --csv-dir")

    results = []
    worst, order = "PASS", ["PASS", "PASS_WITH_NOTE", "REVIEW_REQUIRED", "FAIL_BLACKLIST"]
    for f in files:
        rows = read_csv(f)
        if not rows:
            print(f"{f}: 空文件，跳过", file=sys.stderr)
            continue
        res = triage_one(rows, args.chip, args.critical_ratio)
        res["file"] = str(f)
        results.append(res)
        if order.index(res["verdict"]) > order.index(worst):
            worst = res["verdict"]
        print(f"[{f.name}] {res['verdict']:16s} ops={res['ops_total']:3d} "
              f"black={res['blacklist_all']} review={len(res['review_all'])}"
              f"(critical={res['review_critical']})")

    payload = {"schema": "bi-triage/1", "verdict": worst, "files": results}
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False,
                                              indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
    print(f"TRIAGE_VERDICT: {worst}")
    return 0 if worst in ("PASS", "PASS_WITH_NOTE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
