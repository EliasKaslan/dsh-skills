#!/usr/bin/env python3
"""Explicit per-rank homogeneous EP-group budget; no model-specific defaults."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

OVERHEADS = ("kv", "activation", "communication", "framework", "graph", "loading_peak_extra", "safety")
STATUSES = {"source", "measured", "assumed", "unknown"}

def number(value, name, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(f"{name} must be a {'positive' if positive else 'nonnegative'} integer")
    return value

def evaluate(item):
    if not isinstance(item, dict):
        raise ValueError("candidate must be an object")
    tp, dp, pcp = (number(item.get(key), key, True) for key in ("tp", "dp", "pcp"))
    ep = tp*dp*pcp
    experts = number(item.get("num_experts"), "num_experts", True)
    result = {"label": item.get("label", ""), "tp": tp, "dp": dp, "pcp": pcp, "ep": ep}
    even = item.get("require_even_experts", True)
    if type(even) is not bool:
        raise ValueError("require_even_experts must be boolean")
    if experts % ep and (even or not item.get("uneven_support_evidence")):
        result.update(verdict="INVALID_GEOMETRY", reason="expert count not divisible by EP; uneven backend support not established")
        return result
    evidence = item.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("candidate evidence must be an object")
    missing, assumed = [], []
    for key in ("weights", "budget", "geometry", "overheads"):
        entry = evidence.get(key, {})
        if not isinstance(entry, dict):
            raise ValueError(f"evidence.{key} must be an object")
        status = entry.get("status", "unknown")
        if status not in STATUSES:
            raise ValueError(f"invalid evidence status: {key}")
        if status == "unknown" or not entry.get("note"):
            missing.append("evidence."+key)
        elif status == "assumed":
            assumed.append(key)
    def value(key, source):
        v = source.get(key)
        if v is None:
            missing.append(key)
            return 0
        return number(v, key)
    expert_bytes = value("expert_bytes_total", item)
    tp_bytes = value("tp_weight_bytes_total", item)
    replicated = value("replicated_weight_bytes", item)
    if expert_bytes % experts:
        raise ValueError("expert_bytes_total must describe equal-size integral-byte experts")
    if tp_bytes % tp:
        raise ValueError("TP bytes must account for integral per-rank padding")
    local_experts = (experts+ep-1)//ep
    parts = {"expert_weights": (expert_bytes//experts)*local_experts,
             "tp_weights": tp_bytes//tp, "replicated_weights": replicated}
    overheads = item.get("overheads_bytes", {})
    if not isinstance(overheads, dict) or set(overheads)-set(OVERHEADS):
        raise ValueError("unsupported overhead keys")
    for key in OVERHEADS:
        parts[key] = value(key, overheads)
    budget = value("budget_bytes", item)
    free = value("free_bytes", item)
    available = min(budget, free)
    total = sum(parts.values())
    # Missing budgets are unknown, not zero-valued capacity limits.
    known_limits = [item[key] for key in ("budget_bytes", "free_bytes") if item.get(key) is not None]
    exceeds_known = bool(known_limits) and total > min(known_limits)
    evidence_missing = any(x.startswith("evidence.") for x in missing)
    verdict = ("INCONCLUSIVE" if evidence_missing else
               "CONDITIONAL_DOES_NOT_FIT" if exceeds_known and assumed else
               "DOES_NOT_FIT" if exceeds_known else "INCONCLUSIVE" if missing else
               "CONDITIONAL_CAPACITY_FIT" if assumed else "CAPACITY_FIT")
    result.update(verdict=verdict, local_experts_max=local_experts, parts_bytes=parts,
                  total_lower_bound_bytes=total, limit_bytes=available if len(known_limits)==2 else None,
                  headroom_bytes=available-total if len(known_limits)==2 else None,
                  missing=missing, assumptions=assumed,
                  scope="arithmetic capacity only; topology, kernels and service execution NOT VERIFIED")
    if result["headroom_bytes"] is not None:
        result["headroom_gib"] = result["headroom_bytes"]/1024**3
    return result

def plan(data):
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list) or not data["candidates"]:
        raise ValueError("nonempty candidates list is required")
    if not isinstance(data.get("evidence"), dict) or not data["evidence"].get("model") or not data["evidence"].get("runtime"):
        raise ValueError("root evidence.model and evidence.runtime are required")
    return {"evidence": data["evidence"], "candidates": [evaluate(item) for item in data["candidates"]]}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json")
    args = ap.parse_args(argv)
    try:
        data = json.loads(Path(args.input_json).read_text(encoding="utf-8-sig"),
                          parse_constant=lambda x: (_ for _ in ()).throw(ValueError("non-finite JSON")))
        result = plan(data)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0  # Evaluation success; individual candidates carry explicit verdicts.

if __name__ == "__main__":
    sys.exit(main())
