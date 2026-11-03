#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""场景矩阵驱动：把一组 (TP, BS, prompt:max_tokens) 场景逐个跑 bi_equivalence.py 并汇总。

为什么要有这一层：
  - 批次不变性不是"跑一次通过就算过"，它必须在**多个形状**上成立：批维（BS）、
    长度维（长输入/长输出）、并行维（TP）。任一维失效都要能被看见。
  - 每个场景必须独占设备并在子进程里跑：同一进程里换 TP 会残留分布式状态，
    导致下一次 init 抢显存或拿到上一个 TP 的 HCCL 组。

用法：
  python bi_matrix.py --model /path/to/model --preset core --devices 0-7 --out runs/glm51
  python bi_matrix.py --model ... --spec my_scenarios.json --out runs/x

判定口径见 references/acceptance-criteria.md。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EQUIV = HERE / "bi_equivalence.py"

# 每个 preset 是一组场景；prompt_len:max_tokens 记法便于人读
PRESETS: dict[str, list[dict]] = {
    # 冒烟：单卡、短序列、小批。用来先排除"模型根本跑不起来"
    "smoke": [
        {"name": "bs8_128", "tp": 1, "bs": 8, "prompt_len": 128, "max_tokens": 128},
    ],
    # 核心：批维 + 长度维 + 并行维各一条，够给出"这一个模型是否批次不变"的结论
    "core": [
        {"name": "bs64_128", "tp": 8, "bs": 64, "prompt_len": 128, "max_tokens": 128},
        {"name": "long_in_20480", "tp": 8, "bs": 2, "prompt_len": 20480, "max_tokens": 2048},
        {"name": "long_out_8192", "tp": 8, "bs": 2, "prompt_len": 2048, "max_tokens": 8192},
        {"name": "tp1_bs16", "tp": 1, "bs": 16, "prompt_len": 100, "max_tokens": 512},
        {"name": "tp2_bs16", "tp": 2, "bs": 16, "prompt_len": 100, "max_tokens": 512},
        {"name": "tp4_bs16", "tp": 4, "bs": 16, "prompt_len": 100, "max_tokens": 512},
    ],
    # 满配（耗时以小时计）：规范矩阵全量，3 轮
    "full": [
        {"name": "bs64_128", "tp": 8, "bs": 64, "prompt_len": 128, "max_tokens": 128, "rounds": 3},
        {"name": "long_in_20480", "tp": 8, "bs": 64, "prompt_len": 20480, "max_tokens": 2048},
        {"name": "long_out_20480", "tp": 8, "bs": 64, "prompt_len": 2048, "max_tokens": 20480},
        {"name": "tp1_bs16", "tp": 1, "bs": 16, "prompt_len": 100, "max_tokens": 512, "rounds": 3},
        {"name": "tp2_bs16", "tp": 2, "bs": 16, "prompt_len": 100, "max_tokens": 512, "rounds": 3},
        {"name": "tp4_bs16", "tp": 4, "bs": 16, "prompt_len": 100, "max_tokens": 512, "rounds": 3},
        {"name": "tp1_bs32_1k", "tp": 1, "bs": 32, "prompt_len": 1024, "max_tokens": 2048, "rounds": 3},
        {"name": "tp4_bs32_1k", "tp": 4, "bs": 32, "prompt_len": 1024, "max_tokens": 2048, "rounds": 3},
    ],
}


def parse_devices(spec: str) -> list[str]:
    """'0-7' / '0,1,2' / '4' → ['0',...]。昇腾上是 die 号，不是 NPU 卡号。"""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(str(i) for i in range(int(a), int(b) + 1))
        else:
            out.append(part)
    return out


def run_scenario(sc: dict, args, devices: list[str], outdir: Path) -> dict:
    tp = int(sc.get("tp", 1))
    if tp > len(devices):
        return {**sc, "verdict": "BLOCKED_TOO_FEW_DEVICES",
                "detail": f"tp={tp} 但只给了 {len(devices)} 个 die"}
    dev = ",".join(devices[:tp])
    cmd = [
        sys.executable, str(EQUIV),
        "--model", args.model,
        "--tp", str(tp),
        "--bs", str(sc.get("bs", 16)),
        "--prompt-len", str(sc.get("prompt_len", 128)),
        "--prompt-len-variation", str(sc.get("prompt_len_variation", 0)),
        "--max-tokens", str(sc.get("max_tokens", 128)),
        "--temperature", str(sc.get("temperature", args.temperature)),
        "--seed", str(sc.get("seed", args.seed)),
        "--rounds", str(sc.get("rounds", args.rounds)),
        "--json", str(outdir / f"{sc['name']}.json"),
    ]
    for extra in ("load_format", "hf_overrides", "max_model_len"):
        val = sc.get(extra) or getattr(args, extra, None)
        if val:
            cmd += [f"--{extra.replace('_', '-')}", str(val)]
    if args.max_num_batched_tokens:
        cmd += ["--max-num-batched-tokens", str(args.max_num_batched_tokens)]

    env = dict(os.environ)
    # 负控场景显式把开关置 0，其余一律强制 1
    bi = str(sc.get("vllm_batch_invariant", "1"))
    env["VLLM_BATCH_INVARIANT"] = bi
    if bi != "1":
        cmd.append("--allow-non-bi")
    # 场景自带的额外环境变量：负控优先用实现自带的扰动开关，而不是关整个 BI 模式
    env.update({str(k): str(v) for k, v in (sc.get("env") or {}).items()})
    cmd.extend(str(x) for x in (sc.get("extra_args") or []))
    env["ASCEND_RT_VISIBLE_DEVICES"] = dev
    env["PYTHONUNBUFFERED"] = "1"
    env["OMP_NUM_THREADS"] = "1"

    log_path = outdir / f"{sc['name']}.log"
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
        fh.write("CMD: " + " ".join(cmd) + "\n")
        fh.write("ASCEND_RT_VISIBLE_DEVICES=" + dev + "\n")
        fh.write("VLLM_BATCH_INVARIANT=" + bi + "\n")
        for k, v in (sc.get("env") or {}).items():
            fh.write(f"{k}={v}\n")
        fh.write("\n")
        fh.flush()   # 必须先刷盘：子进程直接写同一个 fd，不刷会乱序/被覆盖
        proc = subprocess.run(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT)
    elapsed = round(time.time() - t0, 1)

    text = log_path.read_text(encoding="utf-8", errors="replace")
    verdict, detail, kv = "UNKNOWN", "", {}
    m = re.search(r"^VERDICT: (\S+)$", text, re.M)
    if m:
        verdict = m.group(1)
    else:
        m = re.search(r"^(BLOCKED_[A-Z0-9_]+|SKIPPED_[A-Z0-9_]+)", text, re.M)
        verdict = m.group(1) if m else f"UNKNOWN(rc={proc.returncode})"
    m = re.search(r"BATCH_INVARIANCE_KV_REQUIREMENT: (\{.*\})", text)
    if m:
        try:
            kv = json.loads(m.group(1))
        except json.JSONDecodeError:
            kv = {}
    m = re.search(r"BATCH INVARIANCE FAILURES: (\d+)/(\d+)", text) or re.search(
        r"BATCH_INVARIANCE_FAILURES?: (\d+)/(\d+)", text
    )
    if m:
        detail = f"failures {m.group(1)}/{m.group(2)}"
    if verdict == "FAIL" and not detail:
        m = re.search(r"\[round \d+\] failures=(\d+/\d+)", text)
        detail = f"failures {m.group(1)}" if m else ""

    return {
        "name": sc["name"],
        "tp": tp,
        "bs": sc.get("bs", 16),
        "prompt_len": sc.get("prompt_len", 128),
        "max_tokens": sc.get("max_tokens", 128),
        "rounds": sc.get("rounds", args.rounds),
        "devices": dev,
        "verdict": verdict,
        "detail": detail,
        "max_kv_usage": kv.get("required_kv_tokens") and kv.get("capacity_kv_tokens"),
        "kv_required": kv.get("required_kv_tokens"),
        "kv_capacity": kv.get("capacity_kv_tokens"),
        "elapsed_sec": elapsed,
        "log": str(log_path.relative_to(outdir)),
    }


def stage_verdict(rows: list[dict]) -> tuple[str, str]:
    """场景级结论 → 阶段级结论。口径见 references/acceptance-criteria.md §3。"""
    if not rows:
        return "BLOCKED_NO_SCENARIO", "没有执行任何场景"
    # 负控：期望"能看见差异"。看得见=检查有牙；看不见=要么功能是空操作，要么比对抓不到差异。
    nc = [r for r in rows if r["verdict"].startswith("NEGATIVE_CONTROL")]
    nc_bad = [r for r in nc if r["verdict"] != "NEGATIVE_CONTROL_REJECTED_AS_EXPECTED"]
    bad = [r for r in rows if r["verdict"] == "FAIL"]
    if bad:
        return "FAIL", f"{len(bad)} 个场景不一致：" + ",".join(r["name"] for r in bad)
    if nc_bad:
        return "BLOCKED", ("负控未按预期暴露差异：" + ",".join(r["name"] for r in nc_bad)
                           + "（要么批次不变模式在本栈上是空操作，要么比对逻辑抓不到差异）")
    judged = [r for r in rows if r not in nc]
    passd = [r for r in judged if r["verdict"] == "PASS"]
    skipped = [r for r in judged if r["verdict"].startswith("SKIPPED_")]
    blocked = [r for r in judged
               if r["verdict"].startswith("BLOCKED_") or r["verdict"].startswith("UNKNOWN")]
    if blocked:
        return "BLOCKED", f"{len(blocked)} 个场景无法判定：" + ",".join(
            f"{r['name']}({r['verdict']})" for r in blocked)
    if not passd:
        return "BLOCKED", "没有任何场景通过"
    note = f"（负控 {len(nc)} 个已按预期暴露差异）" if nc else ""
    if skipped:
        return "PASS_PARTIAL", f"{len(passd)} 通过，{len(skipped)} 因资源跳过：" + ",".join(
            r["name"] for r in skipped) + note
    return "PASS", f"{len(passd)}/{len(judged)} 场景逐位一致" + note


def write_summary(rows: list[dict], verdict: tuple[str, str], outdir: Path) -> None:
    cols = ["name", "tp", "bs", "prompt_len", "max_tokens", "rounds", "devices",
            "verdict", "detail", "kv_required", "kv_capacity", "elapsed_sec"]
    with open(outdir / "summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# 场景矩阵结果",
        "",
        f"**阶段结论**：`{verdict[0]}` — {verdict[1]}",
        "",
        "| 场景 | TP | BS | prompt:max_tokens | 轮数 | 设备 | 结论 | 备注 | 耗时(s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['tp']} | {r['bs']} | "
            f"{r['prompt_len']}:{r['max_tokens']} | {r['rounds']} | "
            f"`{r['devices']}` | **{r['verdict']}** | {r['detail']} | {r['elapsed_sec']} |"
        )
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(
        json.dumps({"verdict": verdict[0], "reason": verdict[1], "scenarios": rows},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="批次不变性场景矩阵驱动")
    ap.add_argument("--model", required=True)
    ap.add_argument("--preset", default="core", choices=sorted(PRESETS))
    ap.add_argument("--spec", default="", help="自定义场景 JSON（覆盖 --preset）")
    ap.add_argument("--only", default="", help="只跑名字匹配这些前缀的场景，逗号分隔")
    ap.add_argument("--devices", default="0-7", help="可用 die，如 0-7 或 4,5,6,7")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--load-format", default="")
    ap.add_argument("--hf-overrides", default="")
    ap.add_argument("--max-model-len", type=int, default=0)
    ap.add_argument("--max-num-batched-tokens", type=int, default=0)
    args = ap.parse_args()

    scenarios = json.loads(Path(args.spec).read_text(encoding="utf-8")) if args.spec \
        else PRESETS[args.preset]
    if args.only:
        wanted = [x.strip() for x in args.only.split(",") if x.strip()]
        scenarios = [s for s in scenarios if any(s["name"].startswith(w) for w in wanted)]
    if not scenarios:
        print("没有匹配的场景", file=sys.stderr)
        return 2

    outdir = Path(args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    devices = parse_devices(args.devices)

    rows = []
    for sc in scenarios:
        print(f"\n>>> {sc['name']} (tp={sc.get('tp',1)} bs={sc.get('bs',16)} "
              f"{sc.get('prompt_len',128)}:{sc.get('max_tokens',128)})", flush=True)
        row = run_scenario(sc, args, devices, outdir)
        rows.append(row)
        print(f"    -> {row['verdict']} {row['detail']} [{row['elapsed_sec']}s]", flush=True)

    verdict = stage_verdict(rows)
    write_summary(rows, verdict, outdir)
    print("\n" + "=" * 70)
    print(f"STAGE_VERDICT: {verdict[0]}")
    print(f"REASON: {verdict[1]}")
    print(f"SUMMARY: {outdir / 'summary.md'}")
    print("=" * 70)
    return 0 if verdict[0].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
