#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ep_mem_model.py -- Ascend 64GB-HBM MoE memory estimator with Expert Parallelism (EP).

Answers: "truncate MoE LLM to N layers, bf16, EP enabled -> how many 64GB HBM
Ascend cards are needed?"

Every formula in this file carries an `# SRC:` tag pointing at the upstream source
line that justifies it.  The full provenance table (with URLs + pinned commit SHAs)
is in FORMULAS.md next to this file.  Sources were read from:
  vllm         @ f43e4c39e30120abf6250a209a42e5cd4849ca23  (main, 2026-10-09)
  vllm-ascend  @ 12e7e1cb9d5447168d9788e7734beeba219f43f4  (main, 2026-10-09)

Assumptions that are NOT source-backed are tagged `# ASSUMPTION` and are echoed in
the report so they can be replaced by measurements.

Usage examples are at the bottom of the file / in README.md.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field

GiB = 1024 ** 3
MiB = 1024 ** 2


# ----------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------
def gb(bytes_: float) -> float:
    """Report in GiB (what npu-smi / torch.npu.mem_get_info speak)."""
    return bytes_ / GiB


def hdr(t: str) -> str:
    return "\n" + "=" * 78 + "\n" + t + "\n" + "=" * 78


def deep_get(cfg: dict, *names, default=None):
    """Return the first present key, searching cfg then cfg['text_config'].

    Kimi-K3 style configs are multimodal-nested: layer keys live in text_config,
    not at top level.  # SRC lead-verified: moonshotai/Kimi-K3 config.json shape.
    """
    for scope in (cfg, cfg.get("text_config") or {}):
        if not isinstance(scope, dict):
            continue
        for n in names:
            if n in scope and scope[n] is not None:
                return scope[n]
    return default


def need(cfg: dict, *names):
    v = deep_get(cfg, *names)
    if v is None:
        raise SystemExit(
            "config.json is missing required key %s (searched top level and "
            "text_config)" % (names,)
        )
    return v


# ----------------------------------------------------------------------------------
# EP / parallel geometry
# ----------------------------------------------------------------------------------
@dataclass
class Parallel:
    tp: int = 1
    dp: int = 1
    pcp: int = 1
    ep: int | None = None
    eplb: bool = False
    num_redundant_experts: int = 0

    def resolved_ep(self) -> int:
        if self.ep is not None:
            return self.ep
        # SRC vllm/distributed/parallel_state.py:2293-2302
        #   EP group size == DP x PCP x TP
        # SRC vllm/model_executor/layers/fused_moe/config.py:1103-1105, 1221
        #   flatten_tp_size = dp_size*pcp_size*tp_size ; ep_size = flatten_tp_size
        return self.dp * self.pcp * self.tp

    def resolved_tp_for_moe(self) -> int:
        # SRC vllm/model_executor/layers/fused_moe/config.py:1219-1224
        #   "In EP, each device owns a set of experts fully. There is no tensor
        #    parallel update tp_size, tp_rank, ep_size and ep_rank to reflect that."
        #   -> FusedMoEParallelConfig(tp_size=1, ...) when use_ep
        return 1

    def resolved_tp_for_dense(self) -> int:
        # Dense/attention/shared-expert layers keep the *physical* TP group.
        # SRC vllm-ascend/vllm_ascend/ops/fused_moe/shared_experts.py:171-175
        #   "EP rewrites FusedMoEParallelConfig.tp_size to 1 because each routed
        #    expert is local. Shared-expert linears still span the physical TP
        #    group, so their layout must be derived from that group instead."
        return self.tp


# ----------------------------------------------------------------------------------
# model geometry extracted from config.json
# ----------------------------------------------------------------------------------
@dataclass
class Geo:
    n_layers: int
    hidden: int
    vocab: int
    tied_embeddings: bool
    # MoE
    is_moe_model: bool = False
    n_experts: int = 0
    n_shared_experts: int = 0
    moe_intermediate: int = 0
    routed_expert_hidden: int = 0
    first_k_dense_replace: int = 0
    moe_layer_freq: int = 1
    # dense MLP
    intermediate: int = 0
    # MLA
    kv_lora_rank: int = 0
    q_lora_rank: int = 0
    qk_nope_head_dim: int = 0
    qk_rope_head_dim: int = 0
    v_head_dim: int = 0
    n_heads: int = 0
    has_mla: bool = False
    # KDA / linear attention
    kda_layers: list = field(default_factory=list)   # 1-based, per config
    full_attn_layers: list = field(default_factory=list)
    kda_num_heads: int = 0
    kda_head_dim: int = 0
    kda_conv_kernel: int = 0
    kda_gate_head_dim: int = 0                     # f_a shard width (replicated)
    has_kda: bool = False
    # extra
    vision_params: int = 0
    warnings: list = field(default_factory=list)

    def layer_has_moe(self, idx: int) -> bool:
        # SRC vllm/transformers_utils/configs/kimi_linear.py:104  moe_layer_freq
        # SRC vllm/model_executor/models/deepseek_v2.py:1294-1330
        #   MoE is built when n_routed_experts is not None; the dense substitute is
        #   used for the first `first_k_dense_replace` layers.
        if not self.is_moe_model:
            return False
        if idx < self.first_k_dense_replace:
            return False
        if self.moe_layer_freq and idx % self.moe_layer_freq != 0:
            return False
        return True

    def layer_is_kda(self, idx: int) -> bool:
        # SRC vllm/transformers_utils/configs/kimi_linear.py:157-160
        #   def is_kda_layer(self, layer_idx):
        #       return self.linear_attn_config is not None \
        #              and (layer_idx + 1) in self.linear_attn_config["kda_layers"]
        # NOTE: `full_attn_layers` is NEVER read by the modeling code -- do not
        # infer "full attention" from it; "not KDA" is the only safe test.
        return (idx + 1) in self.kda_layers


def load_geo(path: str, layers: int, args) -> Geo:
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)

    n_layers_cfg = int(deep_get(cfg, "num_hidden_layers"))
    hidden = int(deep_get(cfg, "hidden_size"))
    vocab = int(deep_get(cfg, "vocab_size"))
    tied = bool(deep_get(cfg, "tie_word_embeddings", default=False))

    lin = deep_get(cfg, "linear_attn_config") or {}
    kda_layers = list(lin.get("kda_layers") or [])
    full_attn_layers = list(lin.get("full_attn_layers") or [])

    g = Geo(
        n_layers=n_layers_cfg,
        hidden=hidden,
        vocab=vocab,
        tied_embeddings=tied,
        n_experts=int(deep_get(cfg, "num_experts", "n_routed_experts", default=0) or 0),
        n_shared_experts=int(deep_get(cfg, "num_shared_experts", "n_shared_experts",
                                      default=0) or 0),
        moe_intermediate=int(deep_get(cfg, "moe_intermediate_size", default=0) or 0),
        routed_expert_hidden=int(deep_get(cfg, "routed_expert_hidden_size", default=0) or 0),
        first_k_dense_replace=int(deep_get(cfg, "first_k_dense_replace", default=0) or 0),
        moe_layer_freq=int(deep_get(cfg, "moe_layer_freq", default=1) or 1),
        intermediate=int(deep_get(cfg, "intermediate_size", default=0) or 0),
        kv_lora_rank=int(deep_get(cfg, "kv_lora_rank", default=0) or 0),
        q_lora_rank=int(deep_get(cfg, "q_lora_rank", default=0) or 0),
        qk_nope_head_dim=int(deep_get(cfg, "qk_nope_head_dim", default=0) or 0),
        qk_rope_head_dim=int(deep_get(cfg, "qk_rope_head_dim", default=0) or 0),
        v_head_dim=int(deep_get(cfg, "v_head_dim", "head_dim", default=0) or 0),
        n_heads=int(deep_get(cfg, "num_attention_heads", default=0) or 0),
        kda_layers=kda_layers,
        full_attn_layers=full_attn_layers,
        kda_num_heads=int(lin.get("num_heads") or 0),
        kda_head_dim=int(lin.get("head_dim") or 0),
        kda_conv_kernel=int(lin.get("short_conv_kernel_size") or 0),
        kda_gate_head_dim=int(lin.get("gate_head_dim") or lin.get("head_dim") or 0),
    )
    g.is_moe_model = g.n_experts > 0 and g.moe_intermediate > 0
    g.has_mla = g.kv_lora_rank > 0
    g.has_kda = bool(kda_layers) and g.kda_num_heads > 0

    if g.routed_expert_hidden == 0:
        g.routed_expert_hidden = hidden
        g.warnings.append(
            "routed_expert_hidden_size absent -> fell back to hidden_size=%d. For "
            "Kimi-K3 the real value is 3584 (latent MoE). Supply --expert-hidden "
            "or fix the config, otherwise expert params are overstated." % hidden)

    # --- CLI overrides -------------------------------------------------------
    if args.expert_hidden:
        g.routed_expert_hidden = args.expert_hidden
    if args.kda_layers_override:
        g.kda_layers = [int(x) for x in args.kda_layers_override.split(",") if x.strip()]
        g.has_kda = bool(g.kda_layers) and g.kda_num_heads > 0

    if layers is not None:
        if layers > g.n_layers:
            g.warnings.append(
                "--layers %d > config num_hidden_layers %d ; using %d"
                % (layers, g.n_layers, g.n_layers))
        else:
            g.n_layers = layers
    return g


# ----------------------------------------------------------------------------------
# parameter counting
# ----------------------------------------------------------------------------------
@dataclass
class Params:
    """Parameter counts, split by *sharding domain*."""
    expert_total: int = 0        # routed expert weights  -> sharded by EP
    dense_tp_total: int = 0      # TP-parallel dense weights -> sharded by TP
    replicated_total: int = 0    # replicated on every rank (never sharded)
    per_layer_expert: int = 0
    detail: dict = field(default_factory=dict)

    def add(self, key, n, domain):
        self.detail[key] = self.detail.get(key, 0) + n
        if domain == "expert":
            self.expert_total += n
        elif domain == "tp":
            self.dense_tp_total += n
        else:
            self.replicated_total += n

    @property
    def total(self):
        return self.expert_total + self.dense_tp_total + self.replicated_total


def count_params(g: Geo, tp: int) -> Params:
    P = Params()
    H = g.hidden

    # ---- embeddings ---------------------------------------------------------
    # SRC vllm/model_executor/models/deepseek_v2.py:1460  VocabParallelEmbedding
    P.add("embed_tokens", g.vocab * H, "tp")
    if not g.tied_embeddings:
        # SRC .../deepseek_v2.py:1918  ParallelLMHead  (tie_word_embeddings=false
        #     for Kimi-K3 -> lm_head is a separate matrix, NOT shared)
        P.add("lm_head", g.vocab * H, "tp")
    P.add("final_norm", H, "tp")

    # ---- vision tower (multimodal) -----------------------------------------
    if g.vision_params:
        P.add("vision_tower+projector", g.vision_params, "replicated")

    for idx in range(g.n_layers):
        # ---------- attention block ----------
        if g.layer_is_kda(idx):
            # SRC vllm/models/kimi_k3/nvidia/kda.py:600-677
            #   head_dim  = linear_attn_config["head_dim"]
            #   num_heads = linear_attn_config["num_heads"]
            #   projection_size = head_dim * num_heads
            #   in_proj_output_sizes = [projection_size]*4 + [head_dim, num_heads]
            #     -> fused q,k,v,g  (4 projections) + f_a + beta
            #   f_b_proj: ColumnParallelLinear(head_dim, projection_size)
            #   conv1d  : ColumnParallelLinear(conv_size, 3*projection_size), fp32
            #   o_proj  : (projection_size) -> hidden
            Hh, D = g.kda_num_heads, g.kda_head_dim
            Pk = Hh * D
            # gate g is one of the 4 projections -> already full-rank (kda.py:616)
            P.add("kda[%d].in_proj_qkvgfab" % idx, H * (4 * Pk + D + Hh), "tp")
            P.add("kda[%d].f_b_proj" % idx, D * Pk, "tp")
            P.add("kda[%d].conv1d" % idx, 3 * Pk * g.kda_conv_kernel, "tp")
            P.add("kda[%d].o_proj" % idx, Pk * H, "tp")
            P.add("kda[%d].dt_bias+A_log+norm" % idx, 2 * Pk + Hh + H, "tp")
        elif g.has_mla:
            # SRC vllm/model_executor/models/deepseek_v2.py:494-534
            #   q_a_proj            ReplicatedLinear(hidden, q_lora_rank)      :494
            #   q_b_proj            ColumnParallelLinear(q_lora_rank, n_heads*qk_head_dim) :502
            #   kv_a_proj_with_mqa  ReplicatedLinear(hidden, kv_lora_rank+qk_rope_head_dim) :518
            #   kv_b_proj           ColumnParallelLinear(kv_lora_rank, n_heads*(qk_nope+v)) :526
            #   o_proj              RowParallelLinear(n_heads*v_head_dim, hidden) :534
            qk_head = g.qk_nope_head_dim + g.qk_rope_head_dim
            P.add("mla[%d].q_a_proj(REPLICATED)" % idx, H * g.q_lora_rank, "replicated")
            P.add("mla[%d].q_b_proj" % idx, g.q_lora_rank * g.n_heads * qk_head, "tp")
            P.add("mla[%d].kv_a_proj_with_mqa(REPLICATED)" % idx,
                  H * (g.kv_lora_rank + g.qk_rope_head_dim), "replicated")
            P.add("mla[%d].kv_b_proj" % idx,
                  g.kv_lora_rank * g.n_heads * (g.qk_nope_head_dim + g.v_head_dim), "tp")
            P.add("mla[%d].o_proj" % idx, g.n_heads * g.v_head_dim * H, "tp")
            P.add("mla[%d].norms" % idx, g.q_lora_rank + g.kv_lora_rank + 2 * H, "replicated")

        # ---------- MLP / MoE block ----------
        if g.layer_has_moe(idx):
            # SRC lead-verified modeling_kimi_linear.py:795-832 (latent MoE):
            #   gate_proj up_proj: routed_expert_hidden -> moe_intermediate
            #   down_proj        : moe_intermediate -> routed_expert_hidden
            #   => per expert = 3 * routed_expert_hidden * moe_intermediate
            per_expert = 3 * g.routed_expert_hidden * g.moe_intermediate
            if P.per_layer_expert == 0:
                P.per_layer_expert = per_expert
            elif P.per_layer_expert != per_expert:
                raise SystemExit("heterogeneous expert widths are not supported")
            P.add("moe[%d].routed_experts" % idx, g.n_experts * per_expert, "expert")
            # router/gate: replicated on every rank
            # SRC vllm/model_executor/models/deepseek_v2.py:321  GateLinear(...)
            #     (a plain linear over n_routed_experts; neither TP nor EP sharded)
            P.add("moe[%d].gate" % idx, H * g.n_experts + g.n_experts, "replicated")
            if g.n_shared_experts:
                # SRC vllm/model_executor/models/deepseek_v2.py:346-371
                #   DeepseekV2MLP(intermediate_size = moe_intermediate_size
                #                                    * n_shared_experts)
                # SRC vllm-ascend/.../shared_experts.py:171-175 -> TP group, NOT EP
                sh = g.n_shared_experts * g.moe_intermediate
                P.add("moe[%d].shared_experts" % idx, 3 * H * sh, "tp")
        else:
            # dense MLP
            if g.intermediate:
                P.add("mlp[%d]" % idx, 3 * H * g.intermediate, "tp")

    return P


# ----------------------------------------------------------------------------------
# per-card weight bytes
# ----------------------------------------------------------------------------------
def card_weights(P: Params, par: Parallel, dtype_bytes: int):
    ep = par.resolved_ep()
    tp_dense = par.resolved_tp_for_dense()
    n_exp = par.num_redundant_experts

    if ep > 1:
        # SRC vllm/model_executor/layers/fused_moe/expert_map_manager.py:62-69
        #   base_experts = global_num_experts // ep_size
        #   remainder    = global_num_experts %  ep_size
        #   local_num_experts = base_experts + 1 if ep_rank < remainder else base_experts
        #   -> per-card expert weights = ceil(global/ep) for the first `remainder`
        #      ranks, floor(global/ep) for the rest.  NO error, NO fallback to TP.
        #      This is why 896 % EP != 0 is legal (just uneven by 1 expert).
        pass

    # with EPLB the physical expert count is n_experts + n_redundant_experts
    # SRC vllm-ascend docs/source/user_guide/feature_guide/
    #     expert_parallelism_load_balancer.md:357-358
    #   "(num_experts + num_redundant_experts) must make ... divisible by the
    #    expert-parallel size"
    expert_total_with_redundant = P.expert_total + n_exp * _per_expert(P) * _n_moe_layers(P)
    max_local = math.ceil(expert_total_with_redundant / ep)
    min_local = expert_total_with_redundant // ep

    dense = P.dense_tp_total / max(1, tp_dense)
    repl = P.replicated_total

    return {
        "ep": ep,
        "tp_for_dense": tp_dense,
        "expert_max": max_local * dtype_bytes,
        "expert_min": min_local * dtype_bytes,
        "dense_tp": dense * dtype_bytes,
        "replicated": repl * dtype_bytes,
        "non_expert": (dense + repl) * dtype_bytes,
        "total_max": (max_local + dense + repl) * dtype_bytes,
        "expert_params_max": max_local,
        "expert_params_min": min_local,
        "non_expert_params": dense + repl,
    }


def _per_expert(P: Params):
    return P.per_layer_expert


def _n_moe_layers(P: Params):
    return sum(1 for k in P.detail if k.startswith("moe[") and k.endswith("routed_experts"))


# ----------------------------------------------------------------------------------
# KV cache
# ----------------------------------------------------------------------------------
def mla_kv_head_size(g: Geo) -> int:
    # SRC vllm/model_executor/layers/attention/mla_attention.py:479
    #        self.head_size = kv_lora_rank + qk_rope_head_dim
    # SRC .../mla_attention.py:1350-1361  get_kv_cache_spec():
    #        return MLAAttentionSpec(block_size=..., num_kv_heads=1,
    #                                head_size=self.head_size, dtype=..., ...)
    # SRC .../mla_attention.py:1586-1598  customize_spec(): "Per-token-head modes
    #        pack an inline fp32 scale pair after the latent data"
    #        content = head_size * get_dtype_size(spec.dtype) + 2*scale_bytes
    # SRC .../mla_attention.py:1608-1610  get_supported_head_sizes() -> [320,512,576]
    #        (576 = 512+64 corroborates the Kimi-K3 / DeepSeek-V2 dims)
    # WHY MLA is tiny vs MHA: MLA caches ONE shared latent (kv_lora_rank) plus the
    # single shared RoPE key (qk_rope_head_dim) PER TOKEN PER LAYER -- num_heads is
    # absent from the formula.  MHA caches per-head K and V, i.e.
    #    2 * n_heads * head_dim * dtype_bytes per token per layer.
    # For Kimi-K3: MLA 576*2 = 1152 B; a comparable 96-head/128-dim MHA would be
    # 2*96*128*2 = 49152 B -> 42.7x smaller.
    # Returns ELEMENTS per token per layer (multiply by dtype_bytes downstream).
    return g.kv_lora_rank + g.qk_rope_head_dim


def kda_state_bytes_per_seq(g: Geo, tp: int, conv_dtype_bytes: int,
                            recurrent_dtype_bytes: int) -> int:
    # SRC vllm/model_executor/layers/mamba/mamba_utils.py:304-327
    #   kda_state_shape(tp_world_size, num_heads, head_dim, num_k_heads=None,
    #                   head_k_dim=None, conv_kernel_size=4, num_spec=0):
    #       proj_size  = num_heads * head_dim
    #       proj_k_size= num_k_heads * head_k_dim      (default == num_heads/head_dim)
    #       conv_dim   = proj_size + 2*proj_k_size          -> 3*H*D
    #       conv_state_shape      = (conv_dim/tp, conv_kernel_size-1+num_spec)
    #       recurrent_state_shape = (num_heads/tp, head_dim, head_dim)
    # SRC .../mamba_utils.py:132-149  kda_state_dtype():
    #       conv_state_dtype      = kv-cache dtype  (== model dtype when "auto")
    #       recurrent_state_dtype = torch.float32 when mamba_ssm_cache_dtype=="auto"
    # SRC vllm/models/kimi_k3/nvidia/kda.py:564-582, 829-837 -> MambaSpec
    #
    # KEY POINT: this is a PER-SEQUENCE CONSTANT (recurrent state), it does NOT
    # grow with context length.  Only the conv window is finite too.
    H, D = g.kda_num_heads, g.kda_head_dim
    conv_dim = 3 * H * D
    conv_elems = math.ceil(conv_dim / tp) * max(0, g.kda_conv_kernel - 1)
    rec_elems = math.ceil(H / tp) * D * D
    return conv_elems * conv_dtype_bytes + rec_elems * recurrent_dtype_bytes


# ----------------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Ascend 64GB-HBM MoE/EP memory estimator (formulas annotated "
                    "with upstream source lines).")
    ap.add_argument("--config", required=True, help="path to config.json")
    ap.add_argument("--layers", type=int, default=None,
                    help="truncate the model to the first N layers")
    ap.add_argument("--tp", type=int, default=1)
    ap.add_argument("--dp", type=int, default=1)
    ap.add_argument("--pcp", type=int, default=1)
    ap.add_argument("--ep", type=int, default=None,
                    help="explicit EP size; default = DP*PCP*TP (source-matched)")
    ap.add_argument("--enable-eplb", action="store_true")
    ap.add_argument("--num-redundant-experts", type=int, default=0)
    ap.add_argument("--dtype-bytes", type=int, default=2, help="2 = bf16")
    ap.add_argument("--expert-hidden", type=int, default=None,
                    help="override routed_expert_hidden_size")
    ap.add_argument("--kda-layers", dest="kda_layers_override", default=None,
                    help="comma list of 1-based KDA layer indices")
    ap.add_argument("--vision-params", type=int, default=0)
    ap.add_argument("--non-expert-params-override", type=int, default=None,
                    help="replace the modelled non-expert param count (attention/"
                         "KDA/shared/dense/embed/lm_head) with a measured value, "
                         "e.g. from an authoritative param census")
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--batch-size", type=int, default=1,
                    help="concurrent sequences (== max_num_seqs)")
    ap.add_argument("--mla-kv-head-size", type=int, default=None,
                    help="override (kv_lora_rank + qk_rope_head_dim)")
    # hardware / budget
    ap.add_argument("--card-hbm-gib", type=float, default=64.0)
    ap.add_argument("--visible-gib", type=float, default=61.28,
                    help="HBM visible to torch (torch.npu.mem_get_info total)")
    ap.add_argument("--gpu-memory-utilization", type=float, default=0.92)
    ap.add_argument("--hccl-buffer-mb", type=int, default=1024)
    ap.add_argument("--hccl-ep-buffer-mb", type=int, default=2048)
    ap.add_argument("--framework-mib", type=int, default=2048)
    ap.add_argument("--activation-mib", type=int, default=4096)
    ap.add_argument("--activation-per-1k-tokens-mib", type=float, default=0.0,
                    help="extra activation that scales with batch*seq (per 1024 tokens)")
    ap.add_argument("--safety-mib", type=int, default=150)
    ap.add_argument("--assume-all-full-attn", action="store_true",
                    help="treat the 3 KDA layers of the 4-layer package as MLA "
                         "(sensitivity test)")
    ap.add_argument("--json", default=None, help="write machine-readable result")
    args = ap.parse_args(argv)

    g = load_geo(args.config, args.layers, args)
    g.vision_params = args.vision_params
    par = Parallel(tp=args.tp, dp=args.dp, pcp=args.pcp, ep=args.ep,
                   eplb=args.enable_eplb,
                   num_redundant_experts=args.num_redundant_experts)

    P = count_params(g, par.resolved_tp_for_dense())

    modelled_non_expert = P.dense_tp_total + P.replicated_total
    override_delta = None
    if args.non_expert_params_override is not None:
        ov = args.non_expert_params_override
        override_delta = ov - modelled_non_expert
        # preserve the modelled TP-parallel : replicated ratio
        frac_tp = (P.dense_tp_total / modelled_non_expert) if modelled_non_expert else 1.0
        P.dense_tp_total = int(round(ov * frac_tp))
        P.replicated_total = ov - P.dense_tp_total
        P.detail["_OVERRIDE_non_expert"] = ov
    w = card_weights(P, par, args.dtype_bytes)

    # ---- layer-type census --------------------------------------------------
    n_kda = sum(1 for i in range(g.n_layers) if g.layer_is_kda(i))
    n_moe = sum(1 for i in range(g.n_layers) if g.layer_has_moe(i))
    n_dense_mlp = g.n_layers - n_moe
    n_mla = g.n_layers - n_kda

    # ---- KV cache -----------------------------------------------------------
    mla_head = args.mla_kv_head_size or mla_kv_head_size(g)
    mla_per_tok_bytes = mla_head * args.dtype_bytes
    n_mla_eff = g.n_layers if args.assume_all_full_attn else n_mla
    n_kda_eff = g.n_layers - n_mla_eff
    mla_tp = max(1, par.resolved_tp_for_dense())
    # MLA KV cache is NOT TP-sharded in vLLM (num_kv_heads=1, the latent is
    # replicated across TP ranks): SRC mla_attention.py:1355-1361 passes
    # num_kv_heads=1 into MLAAttentionSpec, so every TP rank holds a full copy.
    mla_total = mla_per_tok_bytes * args.seq_len * args.batch_size * n_mla_eff
    kda_per_seq = kda_state_bytes_per_seq(g, par.resolved_tp_for_dense(),
                                          args.dtype_bytes, 4)
    kda_total = kda_per_seq * args.batch_size * n_kda_eff
    kv_total = mla_total + kda_total

    # ---- overheads ----------------------------------------------------------
    activation = args.activation_mib * MiB
    activation += int(args.activation_per_1k_tokens_mib
                      * (args.seq_len * args.batch_size / 1024.0) * MiB)
    comm = (args.hccl_buffer_mb + args.hccl_ep_buffer_mb) * MiB
    framework = args.framework_mib * MiB
    safety = args.safety_mib * MiB

    weights_max = w["total_max"]
    # NOTE: w["expert_min"] is already in BYTES (card_weights applies dtype_bytes).
    weights_min = w["expert_min"] + w["non_expert"]

    used_max = weights_max + kv_total + activation + comm + framework + safety
    used_min = weights_min + kv_total + activation + comm + framework + safety

    visible = args.visible_gib * GiB
    budget = visible * args.gpu_memory_utilization

    # ---- output -------------------------------------------------------------
    out = []
    out.append(hdr("MODEL GEOMETRY  (from %s)" % os.path.abspath(args.config)))
    out.append("scanned layers            : %d" % g.n_layers)
    out.append("hidden_size               : %d" % g.hidden)
    out.append("routed_expert_hidden      : %d" % g.routed_expert_hidden)
    out.append("MoE layers                : %d   dense-MLP layers: %d"
               % (n_moe, n_dense_mlp))
    out.append("KDA (linear-attn) layers  : %d   (kda_layers=%s)"
               % (n_kda, g.kda_layers[:12]))
    out.append("MLA (full-attn) layers    : %d   (full_attn_layers=%s ; NOTE: this "
               "config key is never read by the modeling code)"
               % (n_mla, g.full_attn_layers[:12]))
    out.append("experts/layer             : %d   per-expert params: %s"
               % (g.n_experts, "{:,}".format(P.per_layer_expert)))
    out.append("dtype                     : %d bytes/param (%s)"
               % (args.dtype_bytes, "bf16" if args.dtype_bytes == 2 else "?"))
    out.append("TOTAL PARAMS (this cut)   : %s  = %.3f GB logical"
               % ("{:,}".format(P.total), P.total * args.dtype_bytes / 1e9))
    out.append("  routed experts          : %s (%.3f GB/logical, bf16 %.1f GiB)"
               % ("{:,}".format(P.expert_total),
                  P.expert_total * args.dtype_bytes / 1e9, gb(P.expert_total * 2)))
    out.append("  TP-parallel dense       : %s" % "{:,}".format(P.dense_tp_total))
    out.append("  replicated (every rank) : %s" % "{:,}".format(P.replicated_total))
    out.append("  non-expert subtotal     : %s (%.2f GiB bf16)"
               % ("{:,}".format(P.total - P.expert_total), gb(w["non_expert"])))
    if override_delta is not None:
        out.append("  non-expert OVERRIDDEN by --non-expert-params-override "
                   "(modelled %s, delta %+d = %+.2f%%)"
                   % ("{:,}".format(modelled_non_expert), override_delta,
                      100.0 * override_delta / max(1, modelled_non_expert)))
    for wn in g.warnings:
        out.append("  ! WARNING: %s" % wn)

    out.append(hdr("PARALLEL GEOMETRY  (source-matched)"))
    out.append("--tp %d  --dp %d  --pcp %d  ->  EP SIZE = %d"
               % (args.tp, args.dp, args.pcp, w["ep"]))
    out.append("  SRC vllm/distributed/parallel_state.py:2293-2302   EP group = "
               "reshape(-1, data_parallel_size*pcp*tp)")
    out.append("  SRC vllm/.../fused_moe/config.py:1103-1105,1221     ep_size = "
               "flatten_tp_size = dp*pcp*tp")
    out.append("  SRC vllm/.../fused_moe/config.py:1219-1224          under EP, MoE "
               "tp_size := 1 (each device owns experts fully)")
    out.append("  => MoE experts sharded by EP=%d ; all other layers by TP=%d"
               % (w["ep"], w["tp_for_dense"]))
    out.append("  EP divisibility vs n_experts=%d : %s"
               % (g.n_experts,
                  "EXACT (%d %% %d == 0)" % (g.n_experts, w["ep"])
                  if g.n_experts % w["ep"] == 0 else
                  "UNEVEN -- legal, no error: %d %% %d = %d (some ranks get one "
                  "extra expert)" % (g.n_experts, w["ep"], g.n_experts % w["ep"])))
    if args.enable_eplb:
        ok = (g.n_experts + args.num_redundant_experts) % w["ep"] == 0
        out.append("  --enable-eplb: (n_experts+redundant)=%d %% EP=%d -> %s"
                   % (g.n_experts + args.num_redundant_experts, w["ep"],
                      "OK" if ok else
                      "*** RAISES ValueError: 'EPLB currently only supports even "
                      "distribution of experts across ranks. Got %d experts and %d "
                      "EP ranks.' *** (vllm/.../fused_moe/layer.py:262-267)"
                      % (g.n_experts, w["ep"])))

    out.append(hdr("PER-CARD WEIGHT BREAKDOWN   (EP=%d, TP=%d)" % (w["ep"], w["tp_for_dense"])))
    out.append("  routed experts  max-rank : %10.3f GiB  (%s params)"
               % (gb(w["expert_max"]), "{:,}".format(w["expert_params_max"])))
    if w["expert_max"] != w["expert_min"]:
        out.append("  routed experts  min-rank : %10.3f GiB  (%s params)"
                   % (gb(w["expert_min"]), "{:,}".format(w["expert_params_min"])))
    out.append("  TP-sharded dense (/%d)   : %10.3f GiB  (%s params)"
               % (w["tp_for_dense"], gb(w["dense_tp"]), "{:,}".format(int(w["dense_tp"] / args.dtype_bytes))))
    out.append("  REPLICATED every rank    : %10.3f GiB  (%s params)"
               % (gb(w["replicated"]), "{:,}".format(int(w["replicated"] / args.dtype_bytes))))
    out.append("  ------------------------------------------------")
    out.append("  WEIGHTS per card (max)   : %10.3f GiB" % gb(weights_max))

    out.append(hdr("KV CACHE   (seq_len=%d, concurrent seqs=%d)"
                   % (args.seq_len, args.batch_size)))
    out.append("  MLA  layers=%d : %d B/token/layer  (= kv_lora_rank %d + "
               "qk_rope_head_dim %d, x%d B)"
               % (n_mla_eff, mla_per_tok_bytes, g.kv_lora_rank,
                  g.qk_rope_head_dim, args.dtype_bytes))
    out.append("       SRC mla_attention.py:479 head_size = kv_lora_rank + "
               "qk_rope_head_dim ; :1350-1361 get_kv_cache_spec(num_kv_heads=1)")
    out.append("       SRC mla_attention.py:1608-1610 get_supported_head_sizes "
               "= [320,512,576]  (576 = 512+64 corroborates)")
    out.append("       -> MLA subtotal          : %10.3f GiB   (%s B per sequence)"
               % (gb(mla_total), "{:,}".format(mla_per_tok_bytes * args.seq_len * n_mla_eff)))
    out.append("  KDA  layers=%d : %s B/sequence/layer (CONSTANT, does not grow "
               "with context)" % (n_kda_eff, "{:,}".format(kda_per_seq)))
    out.append("       SRC mamba_utils.py:304-327 conv=(3*H*D/tp, C-1) "
               "recurrent=(H/tp, D, D) ; :132-149 recurrent dtype = float32")
    out.append("       -> KDA subtotal          : %10.3f GiB   (%s B per sequence)"
               % (gb(kda_total), "{:,}".format(kda_per_seq * n_kda_eff)))
    out.append("  ------------------------------------------------")
    out.append("  KV CACHE per card        : %10.3f GiB" % gb(kv_total))

    out.append(hdr("OVERHEAD (source-backed numbers; ASSUMPTIONs marked)"))
    out.append("  activation peak          : %10.3f GiB   [ASSUMPTION %.0f MiB "
               "+ %.3f MiB/1k tokens]  -- replace with the value vllm-ascend logs "
               "('GiB for peak activation', worker.py:915-918)"
               % (gb(activation), args.activation_mib,
                  args.activation_per_1k_tokens_mib))
    out.append("  EP all-to-all + HCCL bufs: %10.3f GiB   = HCCL_BUFFSIZE %d MB + "
               "HCCL_BUFFSIZE_EP %d MB" % (gb(comm), args.hccl_buffer_mb,
                                           args.hccl_ep_buffer_mb))
    out.append("       SRC (official K3 recipe) docs/source/tutorials/models/"
               "Kimi-K3.md:158-159  export HCCL_BUFFSIZE=1024 / "
               "HCCL_BUFFSIZE_EP=2048")
    out.append("       SRC vllm_ascend/utils.py:73,77 _DEFAULT_BUFFER_SIZE=200 MB, "
               "_DYNAMIC_EPLB_BUFFER_SIZE=100 MB (per-process-group hccl_buffer_size)")
    out.append("       SRC (CANN) HCCL_BUFFSIZE default 200 MB -- "
               "hiascend CANN env-var reference")
    out.append("  framework/ACL/CANN ctx   : %10.3f GiB   [ASSUMPTION %.0f MiB]"
               % (gb(framework), args.framework_mib))
    out.append("       (vllm-ascend calls this 'non-torch memory: ACL context, HCCL "
               "buffers, driver layer' -- worker.py:895-896)")
    out.append("  safety margin            : %10.3f GiB   = %d MiB "
               "[SRC worker.py:898 redundancy_buffer = 150 MiB]"
               % (gb(safety), args.safety_mib))

    out.append(hdr("SINGLE-CARD BUDGET"))
    out.append("  card HBM (npu-smi)       : %8.2f GiB  = %.0f bytes  (= %.1f GB "
               "decimal)" % (args.card_hbm_gib, args.card_hbm_gib * GiB,
                             args.card_hbm_gib * GiB / 1e9))
    out.append("  visible to torch         : %8.2f GiB  [measured on A3]"
               % args.visible_gib)
    out.append("       SRC npu-smi shows 65536 MB hardware; torch.npu.mem_get_info() "
               "total = 62748 MB (ascend-vllm-serve skill, measured .188)")
    out.append("  x gpu_memory_utilization : %8.2f  [SRC vllm/config/cache.py:102 "
               "default 0.92]" % args.gpu_memory_utilization)
    out.append("  ---------------------------------------------------------")
    out.append("  ENGINE BUDGET per card   : %8.3f GiB" % gb(budget))
    out.append("  requested_memory = total_memory * gpu_memory_utilization")
    out.append("       SRC vllm-ascend/vllm_ascend/worker/worker.py:454-455")
    out.append("  available_kv = requested - (weights + peak_activation + "
               "non_torch + npugraph)")
    out.append("       SRC worker.py:599-608, 611-612, 624, 899-905")

    out.append(hdr("PER-CARD TOTAL"))
    out.append("  weights (max rank)       : %10.3f GiB" % gb(weights_max))
    out.append("  KV cache                 : %10.3f GiB" % gb(kv_total))
    out.append("  activation               : %10.3f GiB" % gb(activation))
    out.append("  comm buffers             : %10.3f GiB" % gb(comm))
    out.append("  framework                : %10.3f GiB" % gb(framework))
    out.append("  safety                   : %10.3f GiB" % gb(safety))
    out.append("  ================================")
    out.append("  TOTAL per card  (max)    : %10.3f GiB" % gb(used_max))
    out.append("  TOTAL per card  (min)    : %10.3f GiB" % gb(used_min))
    out.append("  budget                   : %10.3f GiB" % gb(budget))
    head = gb(budget) - gb(used_max)
    out.append("  HEADROOM (budget-total)  : %10.3f GiB  (%.1f%% of budget)"
               % (head, 100.0 * head / gb(budget)))

    verdict = "FITS" if used_max <= budget else "DOES NOT FIT"
    out.append("")
    out.append("  VERDICT: %s  with EP=%d over %d card(s)"
               % (verdict, w["ep"], w["ep"]))
    if used_max > budget:
        # what drives it
        parts = [("weights", gb(weights_max)), ("KV", gb(kv_total)),
                 ("activation", gb(activation)), ("comm", gb(comm)),
                 ("framework", gb(framework))]
        parts.sort(key=lambda x: -x[1])
        out.append("  dominant term            : %s (%.3f GiB)" % parts[0])
        need_cards = math.ceil((gb(weights_max) * w["ep"]) /
                               max(1e-9, (gb(budget) - gb(kv_total) - gb(activation)
                                          - gb(comm) - gb(framework))))
        out.append("  minimum cards solving the weight term: EP>=%d" % need_cards)

    # =====================================================================
    # LEGAL-DEPLOYMENT SCAN
    # EP is NOT a free variable: EP == TP*DP*PCP (= the card count N).
    # SRC parallel_state.py:2293-2302 + fused_moe/config.py:1103-1105,1221
    # Additional legality: every head-parallel layer must divide evenly.
    #   SRC vllm/models/kimi_k3/nvidia/kda.py:604  assert self.num_heads % self.tp_size == 0
    #   SRC vllm/model_executor/models/deepseek_v2.py:502,510,526 -> n_heads split by TP
    #   => TP must divide gcd(num_attention_heads, kda num_heads). For Kimi-K3 both are 96.
    # =====================================================================
    head_n = g.n_heads or 0
    if g.has_kda and g.kda_num_heads:
        head_n = math.gcd(head_n, g.kda_num_heads) if head_n else g.kda_num_heads
    legal_tps = [t for t in range(1, head_n + 1) if head_n % t == 0] if head_n else [1]

    out.append(hdr("LEGAL-DEPLOYMENT SCAN  (EP is NOT free: EP = TP x DP x PCP = N cards)"))
    out.append("  Legality rule : TP must divide gcd(num_attention_heads=%d, "
               "kda.num_heads=%d) = %d"
               % (g.n_heads, g.kda_num_heads if g.has_kda else 0, head_n))
    out.append("       SRC vllm/models/kimi_k3/nvidia/kda.py:604 "
               "'assert self.num_heads % self.tp_size == 0'")
    out.append("       SRC vllm/model_executor/models/deepseek_v2.py:502,510,526 "
               "(q_b_proj / q_proj / kv_b_proj are ColumnParallelLinear)")
    out.append("  => legal TP set = %s" % legal_tps)
    out.append("  For each card count N we pick the GOODPUT-OPTIMAL legal split: "
               "max TP (max dense sharding) subject to TP | N and TP | %d. "
               "PCP is left at 1 (DP is the cleaner lever; PCP enters EP identically)."
               % head_n)

    # --- the two overhead budgets -------------------------------------------
    kv_only = kv_total
    # (a) ASSUMPTION budget: activation + comm + framework + safety (as in the
    #     per-card report above).  activation/framework are ASSUMPTIONs.
    oh_assumption = kv_total + activation + comm + framework + safety
    # (b) SOURCED budget: only numbers that have a citation.  No activation and
    #     no framework figure exists in the sources read, so both are ZEROED
    #     rather than guessed.
    #     SRC Kimi-K3.md:158-159  HCCL_BUFFSIZE_EP=2048 MB + HCCL_BUFFSIZE=1024 MB
    #     SRC worker.py:898       redundancy_buffer = 150 MiB
    oh_sourced = (args.hccl_buffer_mb + args.hccl_ep_buffer_mb) * MiB + safety
    out.append("")
    out.append("  overhead budget A (ASSUMPTION) : %.3f GiB = KV %.3f + activation "
               "%.3f[ASSUM] + comm %.3f + framework %.3f[ASSUM] + safety %.3f"
               % (gb(oh_assumption), gb(kv_only), gb(activation), gb(comm),
                  gb(framework), gb(safety)))
    out.append("  overhead budget B (SOURCED)    : %.3f GiB = KV %.3f + comm %.3f "
               "(HCCL_BUFFSIZE %d MB + HCCL_BUFFSIZE_EP %d MB) + safety %.3f "
               "(150 MiB, worker.py:898).  NO activation / framework term exists "
               "in any source read -> set to 0, not guessed."
               % (gb(oh_sourced), gb(kv_only), gb(comm), args.hccl_buffer_mb,
                  args.hccl_ep_buffer_mb, gb(safety)))

    # --- replicated-even-under-TP block (Lead item 5) ------------------------
    mla_repl = 0
    for idx in range(g.n_layers):
        if not g.layer_is_kda(idx) and g.has_mla:
            mla_repl += g.hidden * g.q_lora_rank + g.hidden * (g.kv_lora_rank + g.qk_rope_head_dim)
    out.append("")
    out.append("  REPLICATED EVEN UNDER TP>1 (never sharded, any TP):")
    out.append("    MLA q_a_proj + kv_a_proj_with_mqa = %s params = %.4f GiB bf16"
               % ("{:,}".format(mla_repl), gb(mla_repl * args.dtype_bytes)))
    out.append("       SRC vllm/model_executor/models/deepseek_v2.py:494 q_a_proj = "
               "ReplicatedLinear ; :518 kv_a_proj_with_mqa = ReplicatedLinear")
    out.append("       (plus gate/router, embed_tokens, lm_head, norms: these ARE "
               "TP-sharded, see FORMULAS.md sec.3)")

    out.append("")
    out.append("  %-3s %-4s %-4s %-4s %10s %11s %10s %11s %10s %11s %10s %10s  %s"
               % ("N", "TP", "DP", "EP", "exp GiB", "nonexp GiB", "wts GiB",
                  "afford GiB", "totA GiB", "headA GiB", "totB GiB", "headB GiB",
                  "VERDICT(A/B)"))
    out.append("  " + "-" * 118)
    rows = []
    tp_forced1 = []
    n_scan = list(range(1, 17)) + [18, 20, 24, 32, 48, 64, 96]
    for n in n_scan:
        cand = [t for t in legal_tps if t <= n and n % t == 0]
        if not cand:
            out.append("  %-3d  EXCLUDED: no legal TP divides both N=%d and %d -> "
                       "this card count is NOT ACHIEVABLE for this model with "
                       "DP=PCP=1."
                       % (n, n, head_n))
            continue
        tp = max(cand)
        if n > 1 and tp == 1:
            tp_forced1.append(n)
        dp = n // tp
        p2 = Parallel(tp=tp, dp=dp, pcp=1, ep=n, eplb=args.enable_eplb,
                      num_redundant_experts=args.num_redundant_experts)
        w2 = card_weights(P, p2, args.dtype_bytes)
        wt = w2["total_max"]
        afford = gb(budget) - gb(wt)
        totA = wt + oh_assumption
        totB = wt + oh_sourced
        hA = gb(budget) - gb(totA)
        hB = gb(budget) - gb(totB)
        vA = "FITS" if hA >= 0 else "no"
        vB = "FITS" if hB >= 0 else "no"
        rows.append((n, tp, dp, w2, afford, totA, totB, hA, hB, vA, vB))
        out.append("  %-3d %-4d %-4d %-4d %10.3f %11.3f %10.3f %11.3f %10.3f "
                   "%11.3f %10.3f %10.3f  %s/%s"
                   % (n, tp, dp, n, gb(w2["expert_max"]), gb(w2["non_expert"]),
                      gb(wt), afford, gb(totA), hA, gb(totB), hB, vA, vB))

    fitsA = [r[0] for r in rows if r[9] == "FITS"]
    fitsB = [r[0] for r in rows if r[10] == "FITS"]
    out.append("")
    out.append("  LEGAL-BUT-DEGENERATE card counts (no TP>1 divides N, so TP is FORCED "
               "to 1 and the dense tensors stay fully replicated): N in %s"
               % tp_forced1)
    out.append("       -> for these N the only legal config is TP=1/DP=N, which is "
               "strictly worse than using a nearby N that admits TP>1.")
    out.append("")
    out.append("  'afford GiB' = budget - weights = the MAX overhead (activation + "
               "comm + framework + KV + safety) this card count can tolerate.")
    if fitsA:
        mA = min(fitsA)
        out.append("  MINIMUM LEGAL CARD COUNT, budget A (ASSUMPTION overhead): %d"
                   % mA)
        r = [x for x in rows if x[0] == mA][0]
        out.append("       split TP=%d DP=%d -> EP=%d ; weights %.3f GiB ; total "
                   "%.3f GiB ; headroom %.3f GiB ; affordable overhead %.3f GiB "
                   "(stack is %.3f GiB)" % (r[1], r[2], r[0], gb(r[3]["total_max"]),
                                            gb(r[5]), r[7], r[4], gb(oh_assumption)))
    else:
        out.append("  MINIMUM LEGAL CARD COUNT, budget A: none in scan range")
    if fitsB:
        mB = min(fitsB)
        out.append("  MINIMUM LEGAL CARD COUNT, budget B (SOURCED overhead): %d"
                   % mB)
    else:
        out.append("  MINIMUM LEGAL CARD COUNT, budget B: none in scan range")

    # the specific 4-card question, both TP choices
    out.append("")
    out.append("  4-CARD HEAD-TO-HEAD (the disputed configuration):")
    for tp in [1, 2, 4]:
        if 4 % tp:
            continue
        p3 = Parallel(tp=tp, dp=4 // tp, pcp=1, ep=4)
        w3 = card_weights(P, p3, args.dtype_bytes)
        wt = w3["total_max"]
        out.append("    N=4 TP=%d DP=%d : weights %.3f GiB (exp %.3f + nonexp %.3f)"
                   " -> totalA %.3f GiB headroomA %+.3f ; totalB %.3f headroomB %+.3f"
                   % (tp, 4 // tp, gb(wt), gb(w3["expert_max"]),
                      gb(w3["non_expert"]), gb(wt + oh_assumption),
                      gb(budget) - gb(wt + oh_assumption), gb(wt + oh_sourced),
                      gb(budget) - gb(wt + oh_sourced)))
    out.append("    => the SAME 4 cards flip from FAIL to FIT purely by choosing "
               "TP=4 over TP=1 (dense weights 10.640 -> %.3f GiB)."
               % gb(card_weights(P, Parallel(tp=4, dp=1, ep=4),
                                 args.dtype_bytes)["non_expert"]))

    # recommended
    if fitsA:
        rec = min([n for n in fitsA if n >= 8] or fitsA)
        r = [x for x in rows if x[0] == rec][0]
        out.append("  RECOMMENDED CARD COUNT: %d (TP=%d DP=%d); headroomA %.3f GiB "
                   "(%.1f%% of budget) -- thin headroom at the minimum is why the "
                   "next legal step up is recommended when activation is unmeasured."
                   % (rec, r[1], r[2], r[7], 100.0 * r[7] / gb(budget)))

    print("\n".join(out))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({
                "config": os.path.abspath(args.config),
                "layers": g.n_layers, "ep": w["ep"], "tp": w["tp_for_dense"],
                "params": {"total": P.total, "expert": P.expert_total,
                           "dense_tp": P.dense_tp_total,
                           "replicated": P.replicated_total},
                "per_card_gib": {
                    "weights_max": gb(weights_max),
                    "weights_min": gb(weights_min),
                    "kv": gb(kv_total),
                    "mla_kv": gb(mla_total), "kda_kv": gb(kda_total),
                    "activation": gb(activation), "comm": gb(comm),
                    "framework": gb(framework), "safety": gb(safety),
                    "total_max": gb(used_max), "total_min": gb(used_min),
                    "budget": gb(budget), "headroom": head,
                },
                "verdict": verdict,
                "overhead_assumption_gib": gb(oh_assumption),
                "overhead_sourced_gib": gb(oh_sourced),
                "legal_scan": [
                    {"N": r[0], "TP": r[1], "DP": r[2], "EP": r[0],
                     "expert_gib": gb(r[3]["expert_max"]),
                     "non_expert_gib": gb(r[3]["non_expert"]),
                     "weights_gib": gb(r[3]["total_max"]),
                     "affordable_overhead_gib": r[4],
                     "total_A_gib": gb(r[5]), "headroom_A_gib": r[7],
                     "total_B_gib": gb(r[6]), "headroom_B_gib": r[8],
                     "verdict_A": r[9], "verdict_B": r[10]} for r in rows],
                "min_legal_cards_A": min(fitsA) if fitsA else None,
                "min_legal_cards_B": min(fitsB) if fitsB else None,
            }, fh, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
