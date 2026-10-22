---
name: ascend-moe-ep-capacity-planning
description: 昇腾 64GB 卡跑 MoE 大模型前的显存容量与并行几何规划——EP 没有独立开关（EP = TP × DP × PCP），按卡数 N 选型必须随 N 重推 TP；64GB 卡真实预算只有 56.378 GiB，用 64GB 或 64×10⁹ 都会高估；EP 只切 routed experts，其余每卡复制。适用于"这个 MoE 大模型要几张卡才跑得起来 / EP 设多少、TP 设多少 / 专家并行怎么配 / 显存预算怎么算 / 起服务报 OOM 之前先估一遍 / 按卡数扫描怎么选型 / TP 设大了有什么区别"。不适用：服务已经起来要排障或跑推理 → 用 `ascend-vllm-serve`；要装/重装 vllm-ascend → 用 `vllm-ascend-source-install`；只看模型适配没适配 → 用 `ascend-model-adaptation-recon`。
whenToUse: 起服务【之前】决定要占几张卡、EP/TP/DP 怎么配、预算够不够时用。装环境见 vllm-ascend-source-install，运行时报错见 ascend-vllm-serve，上游有没有代码见 ascend-model-adaptation-recon。模型看不到本节。
---

# 昇腾 MoE + EP 起服务前的显存容量规划

实测环境：`192.168.13.188`（A3，8 NPU × 2 die = 16 个 Ascend910_9382，每 die `npu-smi` 报 65536 MB，2026-10-22 复核 16 die 全 `Health OK`）。**其它机器没有实测**：`.190` 2026-10-22 整机不可达、A5（`177.8.21.1`）需先连 A5 VPN 才可达（见 `univpn-vpn`） ⇒ 它们上面的卡数 / HBM 一律 `未采`，本 skill 的数字只能套在 `.188` 上；机器准入状态见 `ascend-env` §1。
对象 = Kimi-K3 类 MoE（`num_experts=896`、`num_experts_per_token=8`、`num_shared_experts=1`、`hidden_size=7168`、`moe_intermediate_size=3584`、KDA 线性注意力 + MLA 混合、`tie_word_embeddings`）。
**这是「起服务之前」的阶段**：本 skill 回答"几张卡 / 怎么配"，`ascend-vllm-serve` 回答"怎么跑起来 / 报错了怎么办"。
配套脚本：本目录 `scripts/ep_mem_model.py`（含 `--help` 全参数、真跑过 `EXIT=0`；含 legal-deployment scan：按 N 重推合法 TP）。下面只留路径与样例命令。
> `FORMULAS.md`（公式→源码行号溯源表，含 pin 的两个 commit SHA）**本轮未复制进本目录**：仍在工作区 `D:\workspace\tmp_new\artifacts\k3-ep-model\FORMULAS.md`。要引用出处行号时读它；要长期留存请把它复制到本目录 `scripts/`。
> 复制采用的是「读源文件 + 逐字重写」，**未做 sha256 逐字节比对**（本写手无 shell 工具、跑不了 `Get-FileHash`）⇒ 首次使用前请用 `python scripts/ep_mem_model.py --help` 与源文件对一次；有差异以 `D:\workspace\tmp_new\artifacts\k3-ep-model\ep_mem_model.py` 为准。

## 何时调用

**加载本 skill 当：**

- 要决定"这个 MoE 模型要占几张卡"，或已有卡数下判断 `FITS / DOES NOT FIT`。
- 要选并行几何（EP / TP / DP）——尤其"`--enable-expert-parallel` 打开了，EP 到底等于几"。
- 起服务前要做一次显存预算，而不是等 `MemoryError` / `value too large` 再回头猜。
- 要解释"为什么 64GB 卡装不下 64GB 的权重"（预算只有 56.378 GiB）。
- 要判断 `EP` 是否必须整除 `num_experts`、`--enable-eplb` 会不会强制均分。

**不要用本 skill（转交）：**

- 服务已经起来要排障（`Engine core initialization failed`、`NnopbaseExecutorDoTiling`、sleep/wake_up、TP=2 起服务） → 用 `ascend-vllm-serve`。
- 要装 / 重装 / 编译 vllm 或 vllm-ascend → 用 `vllm-ascend-source-install`。
- 要判某模型在上游与昇腾侧到底有没有代码 → 用 `ascend-model-adaptation-recon`。
- 模型 / 权重在哪、磁盘该写哪块 → 用 `ascend-server-layout`；本机 PowerShell 的坑 → 用 `pwsh-on-windows`。

**前置**：拿到目标模型的 `config.json`（**多模态模型必须读 `text_config` 子对象**，见坑 4）；有一个 Python 3.10+ 可用。
**后继**：按本 skill 选出的卡数与并行参数去 `ascend-vllm-serve` 起服务；起服务后把真实开销值回填重算（见「验收标准」第 5 条）。

## 前置检查

```bash
# ① 卡上与 HBM 的真实上限（不是 64GB，是 65536 MiB 且其中约 2874 MiB 被驱动吃掉）
ssh -n root@192.168.13.188 "npu-smi info | head -14"
# ② 真正能给引擎的可见总量：实测 62748 MiB ≈ 61.28 GiB
ssh -n root@192.168.13.188 "python -c \"import torch, torch_npu; t,f=torch.npu.mem_get_info(0); print('total_mib', t//1048576)\""
# ③ 预算 = 可见总量 × gpu_memory_utilization（vLLM 默认 0.92）⇒ 61.28 × 0.92 = 56.378 GiB
# ④ 脚本自带全部参数说明
python scripts/ep_mem_model.py --help
```

**判据：所有容量比较一律用 GiB（1024³），并且从 56.378 GiB 起算。** 用 `64` 或 `64×10⁹` 都会高估（后者少算 7.4%）。

## 步骤

### 1 先把「并行几何」钉死：EP 不是一个可以单独设的量

```powershell
python scripts/ep_mem_model.py --config configs/fake_k3_4layer.json --layers 4 --tp 4 --dp 1 --seq-len 8192 --batch-size 16
```

脚本会把推导链打出来，三条事实都要核：

- **`EP size = DP × PCP × TP`**（`--enable-expert-parallel` 只是布尔开关，没有"EP=几"这个参数）。
  出处：`vllm/distributed/parallel_state.py:2293-2302`（EP group = `reshape(-1, data_parallel_size*pcp*tp)`）、
  `vllm/model_executor/layers/fused_moe/config.py:1103-1105,1221`（`ep_size = flatten_tp_size = dp*pcp*tp`）、
  `vllm/engine/arg_utils.py:1260-1264`。
- **EP 下 MoE 的 tp_size 被压成 1**（每个 rank 完整拥有自己的专家）：`fused_moe/config.py:1219-1224`。
- **TP 必须整除 `gcd(num_attention_heads, kda.num_heads)`**（本例 `gcd(96,96)=96` ⇒ 合法 TP ∈ `{1,2,3,4,6,8,12,16,24,32,48,96}`）；**EP size 不必整除 `num_experts`**（见坑 1）。
  出处：`vllm/models/kimi_k3/nvidia/kda.py:604`（`assert self.num_heads % self.tp_size == 0`）、`vllm/model_executor/models/deepseek_v2.py:502,510,526`（MLA 投影是 `ColumnParallelLinear` 铺在 `num_attention_heads` 上）。
  另一道（通常不成约束的）合法性闸门：`moe_intermediate_size % tp_size == 0`（`fused_moe/config.py:1339-1341`；本例 3072 % 4 = 0 ✓）。
- ⚠ **按卡数 N 扫描时必须随 N 重推 TP**（选 `TP | N` 且 `TP | 96` 的最大值，`DP = N/TP`）：EP 与 N 是**同一个量**（`EP ≡ TP×DP×PCP ≡ 卡数`），固定 TP 去变 EP 等于每一行都悄悄假设了不同的错误非专家足迹。**这是本轮被证伪的断言**（见坑 10）。

验证：输出里出现 `--tp N --dp M --pcp K -> EP SIZE = N*M*K` 这一行，且该值与你以为的 EP 一致。

### 2 逐卡权重：把「切」和「不切」分开算

```powershell
python scripts/ep_mem_model.py --config <目标 config.json> --layers <截断层数> --tp 4 --dp 1 --seq-len 8192 --batch-size 16
```

- **切（按 EP）**：只有 routed experts。`每卡专家参数 = 专家总参数 / EP`。
- **不切（每卡整份复制）**：gate/router、MLA 的 `q_a_proj` / `kv_a_proj_with_mqa`、norm。
  出处：`vllm_ascend/ops/fused_moe/shared_experts.py:171-175`（shared experts 的 linear **仍铺在物理 TP 组**上，只是**从不按 EP 切**）、`vllm/model_executor/models/deepseek_v2.py:321-323`（`GateLinear` 不带 tp/ep 参数 = 复制）。
- **连 TP 都不切**：MLA 的 `q_a_proj` / `kv_a_proj_with_mqa` 是 `ReplicatedLinear`（`deepseek_v2.py:494,518`）。
  （`q_b_proj` / `kv_b_proj` 是 `ColumnParallelLinear`、`o_proj` 是 `RowParallelLinear`、`embed_tokens` / `lm_head` 是 `VocabParallelEmbedding` / `ParallelLMHead`、稠密 MLP 是 `MergedColumnParallelLinear` / `RowParallelLinear` —— 这些都**按 TP 切**。）
- ⇒ **TP=1 时"非专家那部分"是卡数硬地板**，EP 再大也不变小。脚本输出的 `repl+TP GB` 列就是它。

### 3 KV cache：按注意力类型分开算

- **MLA（全注意力）**：每 token 每层 `(kv_lora_rank + qk_rope_head_dim) × dtype字节`，`num_kv_heads=1`。
  出处：`vllm/model_executor/layers/attention/mla_attention.py:479`（`head_size = kv_lora_rank + qk_rope_head_dim`）、`:1350-1361`、`:1608-1610`（`get_supported_head_sizes` 含 576 = 512+64）。
- **KDA / Gated-DeltaNet 类线性注意力**：递归状态**每序列常数**、**不随 token 增长**，且递归部分用 fp32。
  出处：`vllm/model_executor/layers/mamba/mamba_utils.py:304-327`（`conv=(3*H*D/tp, C-1)`、`recurrent=(H/tp, D, D)`）、`:132-149`（dtype = float32）。
- ⇒ 混合模型里线性注意力层占比高时，**KV 完全不是瓶颈**：8k 与 128k 上下文实测差异 <1 GiB；把 KDA 层误当 MLA 算，本例总量只从 40.891 → 41.021 GiB（`--assume-all-full-attn` 可一键对照）。

### 4 预算链与开销项（只有带出处的才当数字）

```
npu-smi 65536 MiB  --(驱动基线 2852–3105 MiB/die)-->  mem_get_info 可见 62748 MiB ≈ 61.28 GiB
                    --(× gpu_memory_utilization 默认 0.92)-->  引擎预算 56.378 GiB
56.378 GiB − 每卡权重 − KV − 激活 − 通信缓冲 − 框架/ACL − 150 MiB 安全余量 ≥ 0  ⇒ FITS
```

有出处的开销项：

- `HCCL_BUFFSIZE=1024` / `HCCL_BUFFSIZE_EP=2048`（单位 MB，官方 K3 recipe：`vllm-ascend/docs/source/tutorials/models/Kimi-K3.md:158-159`）；CANN 侧 `HCCL_BUFFSIZE` 默认 200 MB、`vllm_ascend/utils.py:73,77` 另有 200 MB / 100 MB 的 per-group 缓冲。
- 安全余量 **150 MiB** 是硬编码：`vllm_ascend/worker/worker.py:898` `redundancy_buffer = 150 MiB`。
- `requested_memory = total_memory * gpu_memory_utilization`（`vllm_ascend/worker/worker.py:454-455`）；`requested > free` 直接抛 `ValueError`（`worker.py:456-466`）。
- **激活峰值 / 框架开销是假设值**（脚本默认 4 GiB / 2 GiB，`--activation-mib` / `--framework-mib` 可改）——判定要用"可承受开销"列做敏感性分析，别把假设值当实测。

### 5 出结论：最小卡数与推荐卡数分开写

脚本输出的 `EP SWEEP` 表 + `可承受开销 = 预算 − 每卡权重` 列就是结论。本次 4 层包实测（bf16、8k×16 并发）：

| 卡数 | 配置 | 每卡权重 GiB | 总占用 GiB | 余量 GiB | 判定 |
|---:|---|---:|---:|---:|---|
| 3 | TP=3 | 58.721 | 68.299 | −11.922 | ✗ 权重本身就超 56.378 |
| **4** | **TP=4** | 44.059 | 53.637 | **+2.740** | ✓ 最小合法 |
| 4 | TP=1 DP=4 | 51.984 | 61.562 | −5.185 | ✗ 同一批卡，仅因 TP=1 就装不下 |
| 4 | TP=2 DP=2 | 46.701 | 56.279 | +0.099 | ✓ 但 0.1 GiB 余量，实际不可用 |
| **8** | **TP=8** | 22.066 | 31.645 | **+24.733** | ✓ 推荐 |

**卡数没变、权重没变，同一 4 张卡仅因把 TP 从 1 改成 4 就从"装不下"翻成"装得下"。被撑爆的不是卡数，是 TP 的选择。**
`N ∈ {5,7,11,13}` 是"合法但退化"档：没有 >1 的 TP 同时整除 96 与 N，TP 被强制为 1、稠密张量全量复制，比相邻 TP>1 档严格更差。

**⚠ 已被证伪的断言（本轮最该记住的反例）**：**固定 `TP=1` 扫 EP 会得出"最小 5 卡"，随 N 重推 TP 后真值是 4 卡**（TP=4 / DP=1 / EP=4，每卡权重 44.059 GiB，余量 +2.740 GiB）。那张旧表的每一行都隐含 TP=1，是**错误建模撑出来的伪结论**——别把"EP 当自由变量"的扫描结果写进交付。

**两条边界结论（写结论时必须带上）**：

1. **3 卡无论假设怎么调都装不下**：权重 58.721 GiB **本身就 > 预算 56.378 GiB**，属**硬约束**，与开销假设无关。
2. **把假设性开销换成"只留有出处"的口径，判定不翻转**：`HCCL_BUFFSIZE_EP=2048` + `HCCL_BUFFSIZE=1024`（MB）+ `worker.py:898` 的 150 MiB = **3.146 GiB**，激活/框架**无出处则置 0、不猜** ⇒ 4 卡仍 **FITS**，只是余量 2.740 → **9.172 GiB**。⇒ **4 卡结论由权重项主导，对开销假设不敏感**；唯一翻转条件是"激活+框架实测合计 > 12.318 GiB"。

### 6 反查参数口径（防"3.1 TB 权重"这类误判）

不要用 HF `safetensors.parameters` 里的 `U8` 计数当字节数（见坑 3）；也不要拿 `safetensors.total` 与 `.safetensors` 文件总字节互替（**不是同一个量**）。
正确口径：**逻辑参数量 × dtype 字节数**；把普查得到的非专家参数量用 `--non-expert-params-override <N>` 灌进去（本次 Lead 普查值 5,712,517,920，与脚本自算值差 +15.02%，脚本会显式打印这个 delta）。

## 坑与修法

9. **固定 TP 去扫 EP（本轮被证伪的断言，最该记住的一条）**：EP 不是独立可调量，`EP ≡ TP × DP × PCP ≡ 卡数`；按卡数 N 扫描**必须随 N 重推 TP**（选 `TP | N` 且 `TP | gcd(num_attention_heads, kda.num_heads)` 的最大值）。
    → 反例数据：固定 `TP=1` 扫 EP 得出"**最小 5 卡**"；随 N 重推 TP 后真值是 "**4 卡**"（TP=4 / DP=1 / EP=4，每卡权重 44.059 GiB，余量 +2.740 GiB）。**同一 4 卡、同一权重，仅 TP 1→4 就翻转判定**。
    → 修法：扫描表每一行都要显示"这行的 TP/DP 是怎么从 N 推出来的"，别让 EP 当自变量。
10. **"打印的合计"与"各项求和"对不上**（脚本作者自己踩到）：探针函数漏加 `kv_total`，打印头显示 `9.578 GiB`、各项实际求和只有 `9.146 GiB`；修前会把 4 卡总占用**谎报成 53.206 GiB**。
    → 修法：出结论前把输出里的**分项逐条相加**与那个合计行对一遍；只信能对上的一项。
1. **以为 EP size 是独立可设的量** → 它不是：`--enable-expert-parallel` 是布尔量，`EP = DP × PCP × TP`（出处见步骤 1）。
   修法：给 `--tp/--dp`，让脚本自己算 EP；`--ep N` 只用于"假设能设成这么大"的探索，别拿它当部署配置。**反例与真值见坑 9**。
2. **`ValueError: EPLB currently only supports even distribution of experts across ranks. Got 896 experts and 5 EP ranks.`**
   → 原因：**只有 `--enable-eplb` 才强制整除**（`vllm/.../fused_moe/layer.py:258-272`，约束是 `num_experts + num_redundant_experts`）。
   非 EPLB 路径**不均分也合法、不报错**（`vllm/.../fused_moe/expert_map_manager.py:66-69`，余数分给前 remainder 个 rank）。
   → 修法：不开 EPLB 就别为整除改卡数；开了 EPLB 就调 `--num-redundant-experts` 把 `(n_exp + redundant)` 凑成 EP 的倍数（实测 896 % 5 = 1，补 4 个冗余即 900 % 5 = 0）。
3. **把 `safetensors.parameters` 的 `U8` 计数当字节数** → 会误得出"3.1 TB 权重"。
   实测 `{"F32":11122432,"BF16":57179884544,"U8":2722740830208}`：`U8` numel ÷ 剩余可用字节 ≈ **1.882 ≈ 2** —— MXFP4 把 2 个权重打包进 1 个 U8，且 U8 里还混着 per-32 的 scale 字节。
   → 修法：算显存一律"逻辑参数 × dtype 字节数"；要估 MXFP4 **存储量**就另按存储字节算，两者不要混用。
4. **照顶层读多模态 `config.json` → 字段全部 ABSENT，误判成"config 是空壳"**（本轮最大的坑，Lead 与子代理都踩过）。
   → 原因：`torch_dtype` 键**已改名 `dtype`**；MoE 字段是 `num_experts` / `num_experts_per_token` / `num_shared_experts`（**不是** `n_routed_experts` / `num_experts_per_tok` / `n_shared_experts`）；且多模态 config 把语言塔全部参数**嵌在 `text_config` 下**（顶层只有 `architectures` / `dtype` / `tie_word_embeddings` / `text_config` / `vision_config`）。
   → 修法：先 `json.load` 后 `if 'text_config' in d: d = d['text_config']`，再取字段；取不到时先怀疑嵌套与改名，别先怀疑模型。
5. **`find -printf '%s'` 对符号链接报的是 link 长度** → 官方 `model.safetensors.index.json` 显示 **76 B**，几乎被判成空壳，真值 **59,764,096 B**。
   → 修法：一律 `find -L <dir> -printf '%y %s %p -> %l\n'` 判真体积（`-L` 跟随符号链接）。未下载权重时改用 HF cache 元数据，见 `ascend-server-layout` §步骤2。
6. **拿 `createdAt` 当发布日 / 拿大小写差异当"另一个仓" / 按异常文本判 HF 仓不存在** → 见 `ai-vendor-official-source-audit`（本文件只留指针）。
7. **激活峰值是唯一没实测的假设值**：真值从 `vllm serve` 启动日志读（`vllm_ascend/worker/worker.py:908-928` 打印 `N GiB for weights, N GiB for peak activation, N GiB for non-torch memory, N GiB for NPU graph memory`），喂回 `--activation-mib` / `--framework-mib` 重算。
   → 判定要看"可承受开销"余量：4 卡档余量只有 2.740 GiB，所以要往上一档（8 卡，余量 24.733 GiB）；3 卡装不下与开销假设无关（权重自身超预算）。
8. **`HCCL_BUFFSIZE_EP=2048` 是 K3-specific 的硬数字**（官方 recipe），若与 pg_options 的 `hccl_buffer_size` 叠加，估算会低估约 3 GiB。换模型要重新找该模型的 recipe，别照抄。

## 不要做什么

- 不要用 `64 GB`、`64 GiB` 或 `64×10⁹` 当可用预算——**只能从 56.378 GiB 起算**（61.28 × 0.92）。
- 不要拿 `--ep N` 当部署参数，也**不要固定 TP 去扫卡数**（EP ≡ 卡数；两处反例见坑 1 与坑 9）。
- 不要为了凑 EP 整除而改卡数，除非开了 `--enable-eplb`（坑 2）。
- 不要在没把输出里"分项求和"与"打印合计"对上之前就采信那个合计（坑 10）。
- 不要把"无出处的假设开销"当数字用：**没有出处就置 0 并标注，不猜**（步骤 4 与步骤 5 的第 2 条边界结论）。
- 不要把 `U8` numel 当字节、不要把 `safetensors.total` 与 `.safetensors` 文件总字节互替（坑 3）。
- 不要在截断层数上做显存结论后直接上线——**层数变了结论全变**；93 层全量在 bf16 下 `DOES NOT FIT` even at EP=64（实测 2,751,966,453,248 逻辑参数）。
- 不要把假设值（激活 / 框架）当实测值写进结论；不确定的标 `未验证：`。

## 验收标准

1. `python scripts/ep_mem_model.py --help` 能列出全部参数（`--config/--layers/--tp/--dp/--pcp/--ep/--seq-len/--batch-size/--dtype-bytes/--activation-mib/--framework-mib/--non-expert-params-override/--enable-eplb/--num-redundant-experts/--assume-all-full-attn/--json`），退出码 0。
2. 输出里出现 `EP SIZE = DP*PCP*TP` 的推导行与三条 `SRC` 出处行；能口头复述 `shared_experts.py:171-175` 说明"哪些不被切"。
3. 预算行逐字为 `ENGINE BUDGET per card : 56.378 GiB`；**若你的机器 `mem_get_info` 不是 62748 MiB，以现场值为准并同步改算**。
4. 给出**最小卡数**与**推荐卡数**两个数，并附"可承受开销"余量；对最小档说明余量是否够覆盖未实测的激活项。
5. 起服务后从日志抄回 4 个真实开销值，重跑一次脚本，结论方向不变（或明确记录翻转条件，例如"激活+框架合计超过 12.318 GiB 才会重新装不下"）。
6. 每条数字都有出处（文件:行号 / 官方 URL / 实测命令）；假设值单独标注。
7. **扫描表的每一行都写明"这行的 TP/DP 是怎么从卡数 N 推出来的"**（合法 TP 必须整除 `gcd(num_attention_heads, kda.num_heads)`）；出现"固定 TP 变 EP"的行即判不合格（坑 9）。
8. 结论里带上两条边界：**3 卡是权重硬约束下的装不下**（58.721 > 56.378，与开销假设无关）；**把无出处开销置 0 后 4 卡判定不翻转**（余量 2.740 → 9.172 GiB）。
9. 输出的分项逐条求和与打印合计**能对上**（坑 10）。
