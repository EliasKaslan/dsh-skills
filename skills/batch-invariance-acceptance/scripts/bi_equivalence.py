#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""批次不变性最小判定：同一批请求，BS=1 逐条跑 vs 一次整批跑，逐位比对。

判定链（顺序不能换，换一步就会给出错误结论）：
  1. 步数一致           —— 两边都必须正好生成 max_tokens 步（ignore_eos=True）
  2. token ID 序列一致  —— 不一致就是 FAIL，且**不再比 logprob**（路径不同，比了没意义）
  3. chosen-token logprob **按位**一致 —— float32 逐元素 torch.equal，容差 0

为什么必须零容差：批次不变性的定义就是"同一条请求的输出不随批内其它请求变化"。
任何"接近但不相等"都说明归约顺序或增量累加被批形状影响了，1e-7 的差异在长序列上会放大成不同的 token。

用法：
  python bi_equivalence.py --model /path/to/model --tp 8 --bs 64 --prompt-len 128 --max-tokens 128
  python bi_equivalence.py ... --rounds 3 --json out/bs64_tp8.json

依赖：目标机已装 vllm + vllm-ascend，且已 source CANN 的 set_env.sh。
本脚本是**参考实现**：跑之前先读一遍，确认与本机 vLLM 版本的 API 对得上。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time

# ---------------------------------------------------------------------------
# 环境准备必须在 import vllm 之前完成
# ---------------------------------------------------------------------------
# VLLM_BATCH_INVARIANT 由 vLLM 在 import 期读取一次；import 之后再设无效。
# 注意：vLLM 的 enable_batch_invariant_mode() 走的是 CUDA 专用路径，在昇腾上会失败，
# 所以这里只认环境变量，不调用那个函数。
_BI_MODE = os.environ.get("VLLM_BATCH_INVARIANT", "")
_ALLOW_NON_BI = "--allow-non-bi" in sys.argv   # 仅供负控：故意走非批次不变路径
_SELFTEST = "--selftest" in sys.argv           # 只验比对逻辑，不需要模型
if _BI_MODE != "1" and not _ALLOW_NON_BI and not _SELFTEST:
    print(
        "BLOCKED_BATCH_INVARIANT_MODE_DISABLED: 必须用 VLLM_BATCH_INVARIANT=1 启动本脚本；"
        "否则测的不是批次不变性。若确实要跑负控，加 --allow-non-bi。",
        file=sys.stderr,
    )
    raise SystemExit(2)
if _BI_MODE != "1" and not _SELFTEST:
    print(
        "NEGATIVE_CONTROL: VLLM_BATCH_INVARIANT 不是 1（实际=%r），本次结果是负控，"
        "**不能**当作批次不变性通过证据。" % _BI_MODE,
        file=sys.stderr,
    )

os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")

import torch  # noqa: E402

torch.use_deterministic_algorithms(True, warn_only=True)

# vLLM 只在真正要跑推理时才导入：preflight / selftest 不需要它，
# 而在没有 source CANN 环境的机器上 import vllm 会直接崩。
LLM = SamplingParams = cleanup_dist_env_and_memory = None  # 在 main 里赋值


# ---------------------------------------------------------------------------
# prompt 构造：长度必须**精确**等于目标 token 数
# ---------------------------------------------------------------------------
# 不能用 "重复同一句话直到够长" 的写法：那样不同请求的 token 分布过于一致，
# 掩盖真实场景；但长度又必须可控，否则 BS=1 与 BS=N 的实际形状不可比。
_TEMPLATES = [
    "Question: What is the capital of France?\nAnswer: The capital of France is",
    "Q: How does photosynthesis work?\nA: Photosynthesis is the process by which",
    "User: Can you explain quantum mechanics?\nAssistant: Quantum mechanics is",
    "Once upon a time in a distant galaxy, there lived",
    "To implement a binary search tree in Python, first we need to",
    "Climate change is caused by several factors including",
]
_FILLER = "This is an interesting topic that deserves more explanation."


def build_prompts(tokenizer, target_len: int, count: int) -> list[list[int]]:
    filler = tokenizer.encode(_FILLER, add_special_tokens=False)
    if not filler:
        raise RuntimeError("tokenizer 对填充文本返回了空序列，换一段填充文本")
    out = []
    for _ in range(count):
        ids = list(tokenizer.encode(random.choice(_TEMPLATES), add_special_tokens=False))
        ids = ids[:target_len]
        remain = target_len - len(ids)
        if remain:
            ids.extend((filler * (math.ceil(remain / len(filler))))[:remain])
        if len(ids) != target_len:
            raise RuntimeError(f"prompt 长度构造失败：{len(ids)} != {target_len}")
        out.append(ids)
    return out


def chosen_logprobs(request_output):
    """取出 generated token 序列与**被选中 token** 那一路的 logprob。"""
    outputs = getattr(request_output, "outputs", None)
    if not outputs:
        return None, None
    inner = outputs[0]
    token_ids = list(inner.token_ids)
    lps = getattr(inner, "logprobs", None)
    if not lps:
        return None, None
    # lps[i] 是第 i 步的候选表，取其中被选中那个 token 的 logprob
    vals = [lps[i][tid].logprob for i, tid in enumerate(token_ids)]
    return torch.tensor(vals, dtype=torch.float32), token_ids


def compare(bs1: list[tuple], bsN: list[tuple]) -> dict:
    """bs1/bsN: [(logprob_tensor, token_ids), ...] —— 逐条成对比较。"""
    stats = {
        "total": 0,
        "step_mismatch": 0,
        "token_mismatch": 0,
        "logprob_mismatch": 0,
        "failures": [],
    }
    for idx, ((lp1, tk1), (lpN, tkN)) in enumerate(zip(bs1, bsN)):
        stats["total"] += 1
        if len(lp1) != len(lpN):
            stats["step_mismatch"] += 1
            stats["failures"].append(
                {
                    "prompt_idx": idx,
                    "failure_type": "step_mismatch",
                    "reason": f"{len(lp1)} steps (BS=1) vs {len(lpN)} steps (BS=N)",
                }
            )
            continue
        if tk1 != tkN:
            pos = next((i for i, (a, b) in enumerate(zip(tk1, tkN)) if a != b), -1)
            stats["token_mismatch"] += 1
            stats["failures"].append(
                {
                    "prompt_idx": idx,
                    "failure_type": "token_mismatch",
                    "diff_position": pos,
                    "bs1_token": tk1[pos] if pos >= 0 else None,
                    "bsN_token": tkN[pos] if pos >= 0 else None,
                }
            )
            continue
        if not torch.equal(lp1, lpN):
            diff = (lp1 - lpN).abs()
            stats["logprob_mismatch"] += 1
            stats["failures"].append(
                {
                    "prompt_idx": idx,
                    "failure_type": "logprob_mismatch",
                    "first_mismatch_position": int(
                        (diff > 0).nonzero()[0].item()
                    ),
                    "max_abs_diff": float(diff.max().item()),
                    "max_diff_position": int(diff.argmax().item()),
                }
            )
    return stats


def kv_check(llm, prompt_lens: list[int], max_tokens: int) -> dict:
    """先算 KV 需求再开跑：需求超容量时"跑出差异"其实是驱逐/换页造成的，不是不变性问题。"""
    cache_config = llm.llm_engine.vllm_config.cache_config
    block_size = int(getattr(cache_config, "block_size", 128))
    capacity = getattr(cache_config, "kv_cache_size_tokens", None)
    required = sum(
        math.ceil((n + max_tokens) / block_size) * block_size for n in prompt_lens
    )
    return {
        "block_size": block_size,
        "capacity_kv_tokens": capacity,
        "required_kv_tokens": required,
        "overflow": bool(capacity is not None and required > capacity),
    }


def selftest() -> int:
    """比对逻辑自检：不需要模型，纯合成数据。

    为什么必须有这一步：如果 compare() 本身写错了（例如把 logprob 用 allclose 比、
    或者 token 不一致时提前 continue 掉），端到端跑出来的 PASS 全部无效。
    这里对四条分支逐条注入，必须每条都被抓到。
    """
    cases = []

    # 1) 完全一致 → 应无 failure
    lp = torch.tensor([-1.0, -2.0, -3.0], dtype=torch.float32)
    cases.append(("identical", [(lp, [1, 2, 3])], [(lp, [1, 2, 3])], None))

    # 2) 步数不同 → step_mismatch
    cases.append(("step", [(lp, [1, 2, 3])],
                  [(torch.tensor([-1.0], dtype=torch.float32), [1])], "step_mismatch"))

    # 3) token 不同 → token_mismatch
    cases.append(("token", [(lp, [1, 2, 3])], [(lp, [1, 2, 4])], "token_mismatch"))

    # 4) logprob 差 1ulp → logprob_mismatch（这正是 allclose 会漏掉的）
    lp_tiny = lp.clone()
    lp_tiny[1] = torch.nextafter(lp_tiny[1], torch.tensor(float("-inf")))
    assert not torch.equal(lp, lp_tiny), "nextafter 没造出差异，自检无效"
    cases.append(("logprob_1ulp", [(lp, [1, 2, 3])], [(lp_tiny, [1, 2, 3])],
                  "logprob_mismatch"))

    ok = True
    for name, a, b, expect in cases:
        stats = compare(a, b)
        got = stats["failures"][0]["failure_type"] if stats["failures"] else None
        good = got == expect
        ok &= good
        print(f"  [{'ok' if good else 'FAIL'}] {name}: expect={expect} got={got}")
    print(f"SELFTEST: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="批次不变性最小判定（BS=1 vs BS=N）")
    ap.add_argument("--model", default="", help="模型路径（--selftest 时不需要）")
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--bs", type=int, default=64, help="整批请求数（也就是 BS=N 的 N）")
    ap.add_argument("--prompt-len", type=int, default=128)
    ap.add_argument("--prompt-len-variation", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--rounds", type=int, default=1, help="整轮重复次数；>1 时额外检查跨轮一致")
    ap.add_argument("--max-model-len", type=int, default=0, help="0 = prompt+max_tokens 自动")
    ap.add_argument("--max-num-batched-tokens", type=int, default=0, help="0 = 自动")
    ap.add_argument("--load-format", default="", help="无真实权重时用 dummy")
    ap.add_argument("--hf-overrides", default="", help='JSON，如 {"num_hidden_layers":8}')
    ap.add_argument("--json", default="", help="结果写入该文件")
    ap.add_argument("--allow-non-bi", action="store_true",
                    help="负控专用：允许 VLLM_BATCH_INVARIANT!=1 运行，结果不得作为通过证据")
    ap.add_argument("--selftest", action="store_true",
                    help="只跑比对逻辑自检（不需要模型，不需要 NPU）")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.model:
        ap.error("--model 必填（除非只跑 --selftest）")

    global LLM, SamplingParams, cleanup_dist_env_and_memory
    from vllm import LLM as _LLM
    from vllm import SamplingParams as _SP
    from vllm.distributed import cleanup_dist_env_and_memory as _cleanup

    LLM, SamplingParams, cleanup_dist_env_and_memory = _LLM, _SP, _cleanup

    if args.prompt_len_variation and args.prompt_len_variation < 0:
        ap.error("--prompt-len-variation 不能为负")

    random.seed(args.seed)
    max_model_len = args.max_model_len or (
        args.prompt_len + args.prompt_len_variation + args.max_tokens + 256
    )
    if args.prompt_len + args.prompt_len_variation + args.max_tokens > max_model_len:
        print(
            "BLOCKED_PROMPT_LENGTH_EXCEEDS_MODEL_LIMIT: prompt+variation+max_tokens "
            f"> max_model_len({max_model_len})",
            file=sys.stderr,
        )
        return 2

    max_num_batched_tokens = args.max_num_batched_tokens or min(
        131072,
        max(max_model_len, (args.prompt_len + args.prompt_len_variation + 101) * args.bs),
    )

    hf_overrides = json.loads(args.hf_overrides) if args.hf_overrides else None
    llm_kwargs = dict(
        model=args.model,
        tensor_parallel_size=args.tp,
        # 下面三个开关**必须**这样设：任何"按批形状改变执行路径"的优化都会污染结论
        enforce_eager=True,             # 不吃图融合带来的形状特化
        enable_chunked_prefill=False,   # 不让长请求被切段（切段会改变归约切分）
        enable_prefix_caching=False,    # 不让共享前缀命中缓存（命中与否随批变化）
        async_scheduling=False,
        block_size=128,
        max_num_seqs=args.bs,
        max_model_len=max_model_len,
        max_num_batched_tokens=max_num_batched_tokens,
        dtype="bfloat16",
        gpu_memory_utilization=0.9,
        distributed_executor_backend="mp",
        disable_log_stats=False,        # 保留统计行，便于外部核对 KV 用量
    )
    if args.load_format:
        llm_kwargs["load_format"] = args.load_format
    if hf_overrides:
        llm_kwargs["hf_overrides"] = hf_overrides

    print("BATCH_INVARIANCE_MODEL_OVERRIDES: " + json.dumps(
        {"load_format": args.load_format or None, "hf_overrides": hf_overrides},
        sort_keys=True,
    ), flush=True)

    t0 = time.time()
    try:
        llm = LLM(**llm_kwargs)
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        low = text.lower()
        if any(m in low for m in ("out of memory", "failed to allocate",
                                  "no available memory for the cache blocks")):
            print("SKIPPED_TP_RESOURCE_UNAVAILABLE: " + json.dumps(
                {"tp": args.tp, "bs": args.bs, "error": text[:800]}, ensure_ascii=False))
            return 3
        print("BLOCKED_MODEL_LOAD_FAILED: " + text[:800], file=sys.stderr)
        return 2

    sp = SamplingParams(
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        seed=args.seed,
        logprobs=1,
        ignore_eos=True,   # 长度必须固定，否则步数差异会被误判成不变性问题
    )

    tokenizer = llm.get_tokenizer()
    prompt_lens = [
        args.prompt_len + random.randint(0, args.prompt_len_variation)
        for _ in range(args.bs)
    ]
    token_id_lists = []
    for n in prompt_lens:
        token_id_lists.extend(build_prompts(tokenizer, n, 1))
    prompts = [{"prompt_token_ids": ids} for ids in token_id_lists]

    kv = kv_check(llm, [len(x) for x in token_id_lists], args.max_tokens)
    print("BATCH_INVARIANCE_KV_REQUIREMENT: " + json.dumps(kv, sort_keys=True), flush=True)
    if kv["overflow"]:
        # 需求超容量 → 必然发生换出/重算，此时比对结果没有意义
        print("BLOCKED_EVICTION_UNSUPPORTED: " + json.dumps(kv, sort_keys=True))
        _shutdown(llm)
        return 3

    rounds = []
    round_signatures = []
    for r in range(args.rounds):
        print(f"\n===== round {r + 1}/{args.rounds} =====", flush=True)
        bs1 = []
        for i, p in enumerate(prompts):
            outs = llm.generate([p], sp, use_tqdm=False)
            lp, tk = chosen_logprobs(outs[0])
            if lp is None:
                print("BLOCKED_LOGPROB_UNAVAILABLE: RequestOutput 没有 logprobs，"
                      "检查 SamplingParams(logprobs=1) 是否被版本吞掉")
                _shutdown(llm)
                return 2
            if len(lp) != args.max_tokens:
                print(f"BLOCKED_STEP_COUNT: prompt {i} 生成 {len(lp)} 步，"
                      f"期望 {args.max_tokens}（ignore_eos=True 未生效？）")
                _shutdown(llm)
                return 2
            bs1.append((lp, tk))
        outsN = llm.generate(prompts, sp, use_tqdm=False)
        bsN = [chosen_logprobs(o) for o in outsN]

        stats = compare(bs1, bsN)
        stats["round"] = r + 1
        rounds.append(stats)
        # 跨轮签名：同一配置重复跑，BS=1 的逐条输出必须逐轮完全相同。
        # 这一条独立于 BS1-vs-BSN 比对，专门抓"运行间不确定"（另一类缺陷）。
        round_signatures.append([(lp.tolist(), tk) for lp, tk in bs1])
        print(f"[round {r + 1}] failures={len(stats['failures'])}/{stats['total']} "
              f"(step={stats['step_mismatch']} token={stats['token_mismatch']} "
              f"logprob={stats['logprob_mismatch']})", flush=True)

    # 跨轮一致：只在前面的比对全过时才值得看，否则噪音太多
    cross_round_identical = all(sig == round_signatures[0] for sig in round_signatures)
    if not cross_round_identical:
        rounds.append(
            {
                "round": 0,
                "check": "cross_round",
                "failures": [
                    {"failure_type": "nondeterministic_across_rounds",
                     "reason": "同一配置重复运行得到不同输出"}
                ],
            }
        )

    _shutdown(llm)

    total_fail = sum(len(r["failures"]) for r in rounds)
    is_negctl = _BI_MODE != "1"
    if is_negctl:
        # 负控的意义：关掉批次不变模式后，同一个比对**必须**能看见差异。
        # 看得见 → 说明这套检查确实有牙，同时也说明 BI 模式在这里不是空操作；
        # 看不见 → 两种可能：BI 模式在本栈上没起作用，或者比对逻辑抓不到差异。都要单独报。
        verdict = ("NEGATIVE_CONTROL_REJECTED_AS_EXPECTED" if total_fail > 0
                   else "NEGATIVE_CONTROL_INCONCLUSIVE")
    else:
        verdict = "PASS" if total_fail == 0 and cross_round_identical else "FAIL"
    result = {
        "schema": "bi-equivalence/1",
        "verdict": verdict,
        "negative_control": is_negctl,
        "batch_invariant_mode": _BI_MODE or "<unset>",
        "model": args.model,
        "parallel": {"tp": args.tp},
        "scenario": {
            "bs": args.bs,
            "prompt_len": args.prompt_len,
            "prompt_len_variation": args.prompt_len_variation,
            "max_tokens": args.max_tokens,
            "temperature": args.temperature,
            "seed": args.seed,
            "rounds": args.rounds,
            "max_model_len": max_model_len,
            "max_num_batched_tokens": max_num_batched_tokens,
            "enforce_eager": True,
            "enable_chunked_prefill": False,
            "enable_prefix_caching": False,
            "load_format": args.load_format or None,
            "hf_overrides": hf_overrides,
        },
        "kv": kv,
        "rounds": rounds,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    print("BATCH_INVARIANCE_RESULT: " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    print(f"VERDICT: {verdict}")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    if is_negctl:
        return 4 if verdict == "NEGATIVE_CONTROL_INCONCLUSIVE" else 0
    return 0 if verdict == "PASS" else 1


def _shutdown(llm) -> None:
    """显式关引擎并清分布式内存，否则同一进程里连跑多个 TP 会互相抢显存。"""
    try:
        core = getattr(getattr(llm, "llm_engine", None), "engine_core", None)
        shutdown = getattr(core, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown(timeout=60)
            except TypeError:
                shutdown()
    except Exception as exc:  # noqa: BLE001
        print(f"BATCH_INVARIANCE_CLEANUP_WARNING: engine shutdown: {exc}")
    try:
        cleanup_dist_env_and_memory()
    except Exception as exc:  # noqa: BLE001
        print(f"BATCH_INVARIANCE_CLEANUP_WARNING: distributed cleanup: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
