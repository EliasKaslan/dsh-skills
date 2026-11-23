# 容量计算器输入

在 skill 根目录执行 `python scripts/plan_capacity.py input.json`，只读本地 JSON、stdout 输出结果。Python 3.10+，无第三方依赖。输入根含 `evidence` 和 `candidates`。每项证据取 `measured` / `source` / `assumed` / `unknown`；source/measured 必须有可追溯 note，assumed 的结果只可作为假设容量候选。

```json
{
  "evidence": {"model": "revision and census artifact", "runtime": "framework SHA and group definitions"},
  "candidates": [{
    "label": "synthetic example, not a model recipe",
    "tp": 2, "dp": 2, "pcp": 1,
    "num_experts": 8,
    "require_even_experts": true,
    "expert_bytes_total": 8589934592,
    "tp_weight_bytes_total": 2147483648,
    "replicated_weight_bytes": 1073741824,
    "budget_bytes": 8589934592,
    "free_bytes": 8589934592,
    "overheads_bytes": {"kv": 0, "activation": 0, "communication": 0, "framework": 0, "graph": 0, "loading_peak_extra": 0, "safety": 0},
    "evidence": {"weights": {"status": "assumed", "note": "synthetic only"}, "budget": {"status": "assumed", "note": "synthetic only"}, "geometry": {"status": "assumed", "note": "EP=TP*DP*PCP for this example"}, "overheads": {"status": "assumed", "note": "zero only for demonstration"}}
  }]
}
```

每行显式选 tp/dp/pcp，EP 为其乘积；只适用于已确认该公式的同质 EP group。PP、DCP 或多 stage 的异质 rank 需分别建行和预算，工具不自动推断。`expert_bytes_total` 必须包含实际驻留的冗余专家；num_experts 是该驻留总专家数。每专家字节均一且权重均可按所标域切分，工具才适用。TP 列也须已计齐 per-rank padding；不能用平均分片掩盖最坏 rank。

非整除默认 INVALID_GEOMETRY。确实支持不均分时可设 require_even_experts=false，但必须补 `uneven_support_evidence`，按整数个专家取 ceil。未知值写 null 或缺项，结果 INCONCLUSIVE 并列 missing；证据完整且已知分项下界超过预算则 DOES_NOT_FIT。含 assumed 时，超预算和非超预算分别为 CONDITIONAL_DOES_NOT_FIT、CONDITIONAL_CAPACITY_FIT；全 source/measured 的非超预算结果为 CAPACITY_FIT，都不代表部署 PASS。

overheads 的七项需要全部列明且说明零值的依据；profile 中已含通信/图内存时相应独立项可设 0，并在 note 说明避免重复计数。free_bytes 是同一时刻、同一上下文下可用的绝对容量上限；工具检查总占用同时不超引擎预算与 free，不含本轮之后的并发占用。

GB=10^9 B、GiB=2^30 B。62748 MiB×0.92=56.37515625 GiB；先取 61.28 再乘会得到 56.3776，不能把这个舍入值当固定预算。96 GiB=103.079215104 GB，把它当 96 GB 会低估字节数约 6.87%。
