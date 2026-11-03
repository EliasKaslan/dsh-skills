#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""环境准入：判定"能不能开始验"，不做任何测量。

只回答四个能机械判定的问题：
  1. vllm / vllm-ascend 是什么版本、什么 commit
  2. batch_invariant_ops 这个 python 包在不在
  3. 自定义算子动态库 .so 在不在、能不能 dlopen
  4. 必需算子是否已注册到 torch.ops.batch_invariant_ops

用法：
  python bi_preflight.py                       # 人读输出
  python bi_preflight.py --json runs/env.json  # 落盘
  python bi_preflight.py --detect-chip         # 只读芯片型号（不检查包）

退出码：0 全通过；2 缺件（BLOCKED_OPERATOR_INSTALLATION）；3 芯片识别失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# 必需能力（按**语义**列，不按名字列）。
#
# 为什么不能硬编码算子名：同一份能力在不同构建里以三种形态出现，名字完全不同——
#   (a) `torch.ops.batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant`
#   (b) python 函数 `batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant`
#   (c) 被 patch 进 `torch.ops.npu.*` 的原算子
# 实测（2026-11，CANN 9.2.0 + vllm 0.31.0 源码构建）(a) 和 (b) **同时存在**，但探测这件事
# 本身有两个恒为真/恒为空的陷阱：
#   hasattr(torch.ops, <任何名字>) 恒为 True —— torch.ops 是惰性命名空间，访问属性就现造一个
#   dir(torch.ops.batch_invariant_ops) 只给 ['name'] —— 枚举不出已注册算子
# 所以下面所有探测一律走"逐个 getattr 具体名字"，两个命名空间都试。
REQUIRED_CAPABILITIES = {
    "attention": ("fused_infer_attention_score_batch_invariant",),
    "matmul": ("matmul_batch_invariant", "mm_batch_invariant"),
    "reduce_sum": ("reduce_sum_batch_invariant",),
    "softmax": ("softmax_batch_invariant", "log_softmax_batch_invariant"),
    "add_rms_norm": ("add_rms_norm_batch_invariant",),
}


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)


def chip_class() -> dict:
    """原始型号 → A2 / A3 / A5。只按脚本给的规则判，不要拿原串直接比 A2/A3/A5。"""
    rc, out = run(["npu-smi", "info"])
    model = ""
    if rc == 0:
        m = re.search(r"(910[A-Za-z0-9_]*|Ascend\s*\S+)", out)
        model = m.group(1) if m else ""
    low = model.lower()
    if "950" in low:
        cls, build = "A5", "ascend950"
    elif "910b" in low or "a2g3" in low:
        cls, build = "A2", "ascend910b"
    elif "910" in low:
        cls, build = "A3", "ascend910_93"
    else:
        cls, build = "", ""
    return {"raw_model": model, "class": cls, "build_platform": build,
            "npu_smi_ok": rc == 0, "npu_smi_head": out.splitlines()[:3]}


def pkg_info(name: str) -> dict:
    try:
        from importlib.metadata import distribution

        dist = distribution(name)
        info = {"installed": True, "version": dist.version}
        # git commit 优先看 direct_url，其次看包内 _version.py
        direct = dist.read_text("direct_url.json")
        if direct:
            try:
                info["vcs_url"] = json.loads(direct).get("url", "")
            except json.JSONDecodeError:
                pass
        return info
    except Exception:  # noqa: BLE001
        return {"installed": False}


def vcs_commit(pkg_name: str) -> str:
    """从包内 _version.py 里抠 commit；取不到就 unavailable，不要据此判失败。"""
    try:
        mod = __import__(pkg_name)
        base = Path(mod.__file__).resolve().parent
        for candidate in (base / "_version.py", base / "version.py"):
            if candidate.is_file():
                txt = candidate.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"[0-9a-f]{40}", txt)
                if m:
                    return m.group(0)
    except Exception:  # noqa: BLE001
        pass
    return "unavailable"


def check_ops() -> dict:
    """先 import 包，再枚举它**实际**暴露了什么。两种命名空间都探。"""
    result = {
        "import_ok": False,
        "so_paths": [],
        "so_dlopen": False,
        "python_entrypoints": [],
        "torch_ops_namespace": False,
        "torch_ops_registered": [],
        "capabilities": {},
        "missing_capabilities": [],
    }
    try:
        import batch_invariant_ops as bio

        result["import_ok"] = True
    except Exception as exc:  # noqa: BLE001
        result["import_error"] = str(exc)[:400]
        return result

    # 1) python 函数形态（实测形态）
    entries = sorted(
        a for a in dir(bio) if not a.startswith("_") and "batch_invariant" in a
        and callable(getattr(bio, a, None))
    )
    result["python_entrypoints"] = entries

    # 2) torch.ops 命名空间形态。
    #    注意：hasattr(torch.ops, X) 恒为 True（惰性命名空间），dir() 也枚举不出
    #    已注册算子（实测只给 ['name']）。所以这里**不报**"命名空间存不存在"这种
    #    永远为真的信号，只报"每个具体算子名取不取得到"。
    import torch

    ns = getattr(torch.ops, "batch_invariant_ops", None)
    resolved = {}
    for cap, candidates in REQUIRED_CAPABILITIES.items():
        for cand in candidates:
            for prefix in ("", "npu_"):
                full = prefix + cand
                try:
                    getattr(ns, full)          # 取不到会抛 AttributeError
                    resolved.setdefault(cap, []).append("torch.ops:" + full)
                except Exception:  # noqa: BLE001
                    continue
    result["torch_ops_resolved"] = resolved
    result["torch_ops_note"] = (
        "hasattr(dir) 均不可用作判据：torch.ops 惰性造命名空间，dir() 只给 ['name']")

    # 3) 动态库：可能不在包目录里，去 dist-info 的 RECORD 找
    pkg_dir = Path(bio.__file__).resolve().parent
    candidates = sorted(pkg_dir.rglob("*.so"))
    try:
        from importlib.metadata import distribution

        record = distribution("batch_invariant_ops").read_text("RECORD") or ""
        site = Path(bio.__file__).resolve().parents[1]
        for line in record.splitlines():
            name = line.split(",")[0]
            if name.endswith(".so"):
                p = site / name
                if p.is_file():
                    candidates.append(p)
    except Exception:  # noqa: BLE001
        pass
    seen: set[str] = set()
    result["so_paths"] = [str(p) for p in candidates
                          if not (str(p) in seen or seen.add(str(p)))]
    if result["so_paths"]:
        import ctypes

        try:
            ctypes.CDLL(result["so_paths"][0])
            result["so_dlopen"] = True
        except OSError as exc:
            result["so_dlopen_error"] = str(exc)[:400]

    # 4) 能力覆盖：语义名对不上任何一个具体实现就算缺
    resolved_names = {x.split(":", 1)[-1].lower()
                      for group in result["torch_ops_resolved"].values() for x in group}
    haystack = set(entries) | resolved_names
    for cap, needles in REQUIRED_CAPABILITIES.items():
        hit = next((n for n in needles if any(n in h for h in haystack)), None)
        result["capabilities"][cap] = hit or ""
        if not hit:
            result["missing_capabilities"].append(cap)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--detect-chip", action="store_true")
    args = ap.parse_args()

    chip = chip_class()
    if args.detect_chip:
        print(json.dumps(chip, ensure_ascii=False))
        return 0 if chip["class"] else 3

    report = {
        "schema": "bi-preflight/1",
        "chip": chip,
        "vllm": {**pkg_info("vllm"), "commit": vcs_commit("vllm")},
        "vllm_ascend": {**pkg_info("vllm-ascend"), "commit": vcs_commit("vllm_ascend")},
        "batch_invariant_ops": check_ops(),
        "visible_devices": os.environ.get("ASCEND_RT_VISIBLE_DEVICES", "<unset>"),
    }

    ops = report["batch_invariant_ops"]
    checks = {
        "chip_classified": bool(chip["class"]),
        "vllm_importable": bool(report["vllm"].get("installed")),
        "vllm_ascend_importable": bool(report["vllm_ascend"].get("installed")),
        "ops_package": ops["import_ok"],
        "ops_so_loaded": ops["so_dlopen"],
        "ops_capabilities": not ops["missing_capabilities"],
    }
    report["checks"] = checks
    if not checks["chip_classified"]:
        report["verdict"], report["reason_code"] = "BLOCKED", "BLOCKED_CHIP_DETECTION"
    elif not (checks["ops_package"] and checks["ops_so_loaded"] and checks["ops_capabilities"]):
        report["verdict"], report["reason_code"] = "BLOCKED", "BLOCKED_OPERATOR_INSTALLATION"
    elif not (checks["vllm_importable"] and checks["vllm_ascend_importable"]):
        report["verdict"], report["reason_code"] = "BLOCKED", "BLOCKED_PACKAGE_MISSING"
    else:
        report["verdict"], report["reason_code"] = "PASS", ""

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    print(f"PREFLIGHT_VERDICT: {report['verdict']} {report['reason_code']}".rstrip())
    return 0 if report["verdict"] == "PASS" else (3 if report["reason_code"] ==
                                                  "BLOCKED_CHIP_DETECTION" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
