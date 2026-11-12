---
name: batch-invariance-acceptance
description: batch 不变性验收：减层证据、算子级判据、外推六条件、昇腾 BI 白名单审计、验收成本优化（三层锚点+分派同构）。
version: 1.0.0
domain: inference-model
function: batch-invariance-validation
tags: [batch-invariance, vllm-ascend, determinism]
author: mindspeed-agent
---

# 批次不变性验收

## 何时调用

**适用于**"验一下这个模型的批次不变性 / BS=1 和 BS=64 的 logprob 对不上 / 帮我出一套批次不变性验收矩阵 / 这个算子会不会破坏逐位一致 / 换了 TP 就不一致了 / 上一轮验收判了 BLOCKED 怎么办 / 批次不变性该验收哪些场景 / 怎么证明这个 PASS 是可信的"。

**不适用**：
- 只想把服务起起来跑通推理 → 用 `ascend-vllm-serve`
- 只想装或重编 vllm-ascend → 用 `vllm-ascend-source-install`
- 只想知道某模型在昇腾上适配到什么程度 → 用 `ascend-model-adaptation-recon`
- 只想算显存/并行几何够不够 → 用 `ascend-moe-ep-capacity-planning`

**触发词**：batch invariance / 批次不变性 / BS=1 与 BS=N 不一致 / 逐位一致 / 确定性推理 / logprob 对不上 / token 序列漂移 / 复现结果不稳定。

**一句话定义**：同一条请求的输出，不能因为"批里还有别人"而改变。
形式上：对任意 `i`，`generate([p_i])` 与 `generate([p_1..p_N])[i]` 必须给出**完全相同的 token 序列**和**按位相同的 chosen-token logprob**。

**为什么必须零容差**：这不是"精度够不够"的问题，而是"归约顺序有没有被批形状影响"。昇腾上的 matmul 归约、all-reduce 分块、attention 的 softmax 规约都可能按 batch/seq 切分而变化，1e-7 的差异经过几十层残差会翻转 top-1，尤其在 temperature>0 采样时。所以判据是 `torch.equal`，不是 `allclose`。

**三个阶段，三种问题**：

| 阶段 | 回答的问题 | 典型耗时 |
|---|---|---|
| 1 算子 | 模型图里有没有"注定不满足"的算子？ | 分钟级（看 profiling）+ 小时级（单算子 1e4 用例） |
| 2 功能 | 端到端 token / logprob 是否逐位一致？ | 十几分钟到几小时（取决于场景） |
| 3 数据集 | 换 500 道题跑 10 轮，分数和生成文本是否完全一致？ | 小时级（真权重 + 全量评测） |

**三者是"与"关系**，但**只有阶段 2 是主战场**：阶段 1 用来把"注定失败"提前挡掉并定位到算子，阶段 3 用来证明"在实际业务负载上也没漂移"。时间不够时，宁可把阶段 2 做全，不要三段都做一半。

---

## 一、先想清楚三件事

### 1. 我在验什么

不是"模型准不准"，也不是"性能好不好"，是**"输出是否与批形状无关"**。所以：

- BS=1 与 BS=N 必须用**同一份 prompt token id**、**同一 seed**、**同一采样参数**；
- 两边都必须生成**恰好** `max_tokens` 步（`ignore_eos=True`），否则长度差异会被误读成不变性差异；
- 温度可以泛化（`0` 或 `0.6` 各出一份结论），但**一次对比内不许变**。

### 2. 什么算"过"

三层各自成立且都留下了证据，才算"这个模型批次不变"。任一层的结论都**不能**外推到另一层：

- 算子层通过 ≠ 端到端不变（还有调度、KV、通信）；
- 某个 TP 通过 ≠ 所有 TP 通过（TP 改变了 all-reduce 分块）；
- 短序列通过 ≠ 长序列通过（长 prefill 会触发不同的切分与 chunk）。

### 3. 什么算"没法判"

**必须把"失败"和"判不了"分开**，否则报告会给出错误结论：

| 情形 | 结论 | 不许写成 |
|---|---|---|
| 权重装不进卡（加载期 OOM） | `SKIPPED_TP_RESOURCE_UNAVAILABLE` | PASS，或 FAIL |
| KV 需求 > KV 容量 | `BLOCKED_EVICTION_UNSUPPORTED` | FAIL（此时"差异"是驱逐造成的） |
| 缺调度统计 / 探测不到算子 | `BLOCKED_*` | PASS |
| 真出现 token 或 logprob 不一致 | `FAIL` | BLOCKED（不许用"环境问题"掩盖） |

---

## 二、五分钟跑通第一条链路

```bash
# 0) 环境：CANN + vllm + vllm-ascend 就绪，且必须显式指定 die
source /usr/local/Ascend/ascend-toolkit/set_env.sh

# 1) 环境准入（包/算子/芯片分类）
python scripts/bi_preflight.py --json runs/env.json

# 2) 冒烟：单卡、短序列、小批。这一步只回答"模型能不能跑起来"
VLLM_BATCH_INVARIANT=1 ASCEND_RT_VISIBLE_DEVICES=0 \
  python scripts/bi_equivalence.py --model <MODEL> --tp 1 --bs 8 \
         --prompt-len 128 --max-tokens 128 --rounds 1 --json runs/smoke.json

# 3) 看最后两行
#    BATCH_INVARIANCE_RESULT: {...}
#    VERDICT: PASS
```

冒烟 `FAIL` 就直接进 [失败定位](references/failure-triage.md)，别急着上大场景。
冒烟 `PASS` 也不代表什么——它只证明链路通。

---

## 三、四步验收流程

### Step 0 · 环境准入

`scripts/bi_preflight.py` 只做四件**能机械判定**的事：

1. `vllm` / `vllm-ascend` 的版本与 commit（`git_commit` 优先，detached HEAD 无分支名是正常的，**不要据此判失败**）；
2. `batch_invariant_ops` 这个 python 包能否 import；
3. 自定义算子动态库 `.so` 是否存在且能加载（**注意它可能不在包目录里**，要去 dist-info 的 `RECORD` 找）；
4. 五个能力项（`attention` / `matmul` / `reduce_sum` / `softmax` / `add_rms_norm`）**是否能在任一命名空间解析到具体名字**。

> **这里有两个"永远为真"的陷阱，两个都会让你得出相反结论**（实测见 [算子分诊](references/operator-classification.md) §1）：
>
> 1. `hasattr(torch.ops, "batch_invariant_ops")` **恒为 `True`**——`torch.ops` 是惰性命名空间，访问任何属性都会当场造一个空对象。用 `hasattr` 判断"算子包在不在"等于没判。
> 2. `dir(torch.ops.batch_invariant_ops)` 只给 `['name']`——**枚举不出已注册的算子**。用遍历来"发现算子"会得到"一个都没有"的错觉。
>
> 唯一可靠的判据是**逐个 `getattr` 具体算子名**（不存在会抛 `AttributeError`）。而且探之前必须先 `import batch_invariant_ops`，否则连 python 层的那批函数都看不到。

芯片分类由脚本给定（A2/A3/A5），**不要**拿原始型号字符串去和 `A2/A3/A5` 直接比较。A2 复用 A3 的白名单。

判据：四项全通过 → `PASS`；缺包/缺 SO/缺注册 → `BLOCKED_OPERATOR_INSTALLATION`；芯片识别失败 → `BLOCKED_CHIP_DETECTION`。

### Step 1 · 算子层

**目的**：把"注定不满足"的算子提前挡掉，并把端到端失败定位到具体算子。

1. 采一次 profiling，拿到每个 rank 的 `op_statistic.csv`（要求见 [算子分诊](references/operator-classification.md)）；
2. `python scripts/bi_ops_triage.py --csv <op_statistic.csv> --chip A3 --json runs/triage.json`；
3. 按判决处理：

| 判决 | 含义 | 下一步 |
|---|---|---|
| `PASS` | 关键路径算子全在白名单 | 进 Step 2 |
| `FAIL_BLACKLIST` | 关键路径命中强制黑名单（`SoftmaxV2` / `MatMulV2` / `FusedInferAttentionScore` / `AddRmsNorm` / `ReduceSum`） | 先确认**实际跑的是不是** `*BatchInvariant` 变体，再决定是否要改代码 |
| `REVIEW_REQUIRED` | 白名单外、黑名单外 | 对每个算子做 1e4 条单算子验证（见 reference） |

> **黑名单只做精确名匹配**，这是它有意的设计，也是它最大的坑：`AddRmsNorm` 黑了，但同族的融合算子 `AddRmsNormBias`（名字不同）不会被匹配到。同理 `torch.sum` 被替换了，但 `Tensor.sum` 走的是另一个注册名。**白名单外算子命中黑名单后，不要急着改代码——先看实际调用路径。**

> **拿不到 `op_statistic.csv` 就别硬采**（2026-11-03 实测 torch_npu 2.10.0.post4 + CANN 9.2.1）：`torch_npu.profiler` 这一版**没有** `analyse`/`analysis` 分析入口（`torch_npu.profiler.analysis` 下只有 `prof_bean/prof_common_func/prof_config/prof_parse/prof_view`），`msprof` 离线导出对 `ASCEND_PROFILER_OUTPUT` 报 `does not have PROF dir`、对 rank 目录只产出 `api_statistic.csv` / `task_time.csv` / `trace_view.json` / `analysis.db` / `ascend_pytorch_profiler.db`，**始终没有** `op_statistic.csv` / `op_summary.csv`。此时正确结论是 `BLOCKED_MISSING_OP_STATISTIC` 并把已产出的目录列进证据，别反复重采浪费几小时。

**采不到 ≠ 交白卷：Phase 1 的两步替代取证**（同一天在同一台机上真跑过，30 分钟内出结果）

```python
# ① 真实前向的算子清点：TorchDispatchMode 拦 aten/npu 调用，不需要 profiler
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"   # 同进程跑，省掉 /dev/shm
os.environ["VLLM_BATCH_INVARIANT"] = "1"
from torch.utils._python_dispatch import TorchDispatchMode
class Census(TorchDispatchMode):
    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        key = str(func)                      # e.g. vllm.unquantized_gemm.default
        COUNT[key] = COUNT.get(key, 0) + 1
        return func(*args, **(kwargs or {}))
with Census():
    llm.generate(prompts, SamplingParams(temperature=0, max_tokens=8))
```

```bash
# ② 树内自带的 BI 分支命中计数（真正的"BI 有没有生效"证据）
grep -o "\[glm-bi\] op hits: {[^}]*}" <engine log | tee>
# GLM-5.x 实测: {'gating': 0, 'routing': 9, 'grouped_matmul': 18, 'sfa': 32,
#               'indexer': 24, 'tbmm': 0, 'add_rms_norm_bias': 72}
```

两条铁律，否则会把结论读反：

- **dispatch 名字看不出实现是否被换成 BI 版**。vllm-ascend 是在**同一 op 名**下换实现（`vllm.unquantized_gemm` / `vllm.mla_forward` 名字不变），所以"命中黑名单名字"≠"没走 BI"，"没命中"也≠"走了 BI"。判 BI 是否生效只看 ②，不看 ①。
- ① 的合法用途是**列热路径算子族**（本例：`aten.slice` 759 / `copy_` 247 / `add` 96 / `npu_rms_norm` 72 / `unquantized_gemm` 48 / `mla_forward` 32 / `npu_swiglu` 24），据此判断该查哪个 BI 分支；不要拿它算耗时占比，那需要 profiler。

报告里怎么写：`status` 仍是 `BLOCKED_MISSING_OP_STATISTIC`，但 `artifacts` 挂上 `op_census.csv/json` + `census.log`，并写一句算子层结论（例："SFA / indexer / grouped_matmul / routing / add_rms_norm_bias 均非零 ⇒ BI 替换集确实生效且被调用，因此端到端分叉不能归因于'算子没装上'"）。这一句是后续排障的岔路口，比一张空表值钱得多。

### Step 2 · 功能层（主战场）

**目的**：端到端证明 token 序列与 chosen-token logprob 按位一致。

**先测吞吐，再定矩阵。** 这是最容易翻车的一步：矩阵的成本几乎全在 BS=1 那一侧——要跟 BS=N 比，就得把 N 条请求**逐条**跑一遍。所以一个场景的耗时约等于 `BS × (prompt_len / prefill速度 + max_tokens / decode速度)`，随 BS 线性涨。

实测（Qwen3-30B-A3B，TP=8，共享机 load≈280）：`BS=16 / 256:64 / 2 轮` 约 25 分钟；同样配置下 `BS=64 / 20480:2048` 需要**几十小时**。照抄大矩阵会得到一个永远跑不完的验收。

做法：先跑一格小场景（`BS=2 / 32:32`）量出 prefill / decode 速度，再用上面的公式估算，把矩阵裁到时间预算内，并**在报告里写明裁剪依据**。

规范矩阵（这是"过"的完整定义，缺一条就只能报 `PASS_PARTIAL`）：

| 场景 | TP | BS | prompt : max_tokens | 轮数 |
|---|---|---|---|---|
| 负控（先跑） | 8 | 32 | 512 : 128 | 1 |
| 批维 | 8 | 64 | 128 : 128 | 1 |
| 长输入 | 8 | 64 | 20480 : 2048 | 1 |
| 长输出 | 8 | 64 | 2048 : 20480 | 1 |
| 并行矩阵 | 1 / 2 / 4 | 16、32 | 100 : 512、1024 : 2048 | 3 |

时间不够时按**横向优先**裁剪：先保证每个被测模型都拿到"批维"这一格，再加深场景，而不是把一个模型的所有组合跑完。理由是一格 PASS 加一格负控已经能支撑"这个模型在当前形状下满足批次不变性"，而"某模型只跑了一个 TP" 比"某模型完全没数据"有价值得多。

```bash
python scripts/bi_matrix.py --model <MODEL> --preset full \
       --devices 0-7 --out runs/phase2
```

时间不够时用 `--preset core`（每个维度各一条），并在报告里**明确写清哪些组合没跑**——这比"跑了但没说"安全得多。

`max_model_len` 必须 ≥ `20480 + 50 + 2048 = 22578`（`50` 是逐条随机长度增量上界）。设成 22528 会让最长的那条请求直接撞 `BLOCKED_PROMPT_LENGTH_EXCEEDS_MODEL_LIMIT`。

### Step 2.5 · 负控：先证明你的检查有牙

在相信任何 `PASS` 之前，用**同一个比对**跑一次关掉开关的负控：

```bash
VLLM_BATCH_INVARIANT=0 python scripts/bi_equivalence.py ... --allow-non-bi
```

| 负控结果 | 含义 |
|---|---|
| `NEGATIVE_CONTROL_REJECTED_AS_EXPECTED` | 比对能看见差异，且批次不变模式在这条路径上确实起作用 |
| `NEGATIVE_CONTROL_INCONCLUSIVE` | 关掉开关后输出仍逐位一致 → 要么这个形状本来就不受批影响，要么开关没接上，**此前的 `PASS` 可能是空过** |

`INCONCLUSIVE` 不能当通过，必须换更大形状或换模型重试。没有负控的 `PASS`，说服力只有一半。

**硬规则：负控必须和正式场景同形状，且负控 `INCONCLUSIVE` 时该形状的 `PASS` 一并作废。**

理由很直接：负控回答的是"这个场景**能不能**看见差异"，不是"批次不变有没有生效"。如果关掉开关都看不出差别，那这个形状对差异是**钝的**，拿它测出来的 `PASS` 只能说明"钝的尺子量不出东西"，不能说明"没有东西"。这时正确做法是把该场景降级重报（`INCONCLUSIVE` / 不可用），而不是留着 `PASS` 好看。

本轮就撞上了这个：GLM 缩层模型在 `TP=8 / BS=16 / 256:64` 上关掉开关，输出**仍然逐位一致**（`NEGATIVE_CONTROL_INCONCLUSIVE`），所以同为该形状的 `PASS` 不能算证据；而 Qwen3-30B-A3B 在同一台机器上换到 `TP=8 / BS=32 / 512:128` 就稳定暴露差异（32/32）。**同一台机器、同一套代码，换个形状判别力完全不同**——所以负控不能只做一次就套用到所有场景。

负控要用**足够大的形状**才有效：实测在 TP=1 / BS=4 / 64:32 上关掉开关，输出仍然逐位一致（`INCONCLUSIVE`）；换到 TP=8 / BS=32 / 512:128 才稳定暴露差异（32/32 请求不一致，其中 6 个 token 不同、26 个只有 logprob 不同）。

> **这就是为什么必须比 logprob**：只比 token 的话，那 26 个真实差异会被判成"通过"。

如果实现自带扰动开关（例如 GLM-5.x 的 `VLLM_BI_GLM_SELFTEST=perturb`），优先用它——它按批大小注入扰动，且保证扰动在 routing 归一化后仍然存活，比自造的负控可靠。

另外还有一步**不需要模型**的自检，改完比对器先跑它：

```bash
python scripts/bi_equivalence.py --selftest
```

它会用合成数据对四条判决分支逐条注入（含 1 ULP 的 logprob 差异），必须全部命中。

### Step 3 · 数据集层

**目的**：在真实负载上证明"分数不漂、生成文本不漂"。

- `temperature=0`、固定 seed、关 prefix caching / chunked prefill / async scheduling；
- Math500 全量 **10 轮**，每轮 500 条全部成功；
- 每轮 accuracy 必须**完全相同**，且逐样本原始生成文本必须**完全相同**；
- 阈值与轮数必须**执行前固定**，禁止跑完再按结果回填。

**必须有真实权重**。没有真实权重时这一步只能报 `BLOCKED_MISSING_REAL_WEIGHTS`，不得用减层/随机权重蒙混——那验证的不是这个模型。

**没有 `ais_bench` 就自己搭最小闭环**（2026-11-03 在 A3 上真跑通）。`ais_bench` 不在 PyPI（`pip download ais_bench` → `No matching distribution found`），但这一步的判据只是"10 轮 ×500 题的分数与文本是否逐位相同"，不需要那个框架：

```bash
# ① 数据集：hf-mirror 直取，比 huggingface.co 稳（后者能连也可能 307 到 cache 失效）
curl -sfL https://hf-mirror.com/datasets/HuggingFaceH4/MATH-500/resolve/main/test.jsonl -o math500_test.jsonl
wc -l math500_test.jsonl          # 必须 500；字段 problem / answer / solution / subject / level / unique_id
```

```python
# ② 10 轮 ×500，每轮立刻落盘（中途被打断也留得下证据），轮间比 token 序列
llm = LLM(model=..., tensor_parallel_size=1, max_model_len=4096, enforce_eager=True,
          enable_prefix_caching=False, enable_chunked_prefill=False,
          max_num_seqs=64, max_num_batched_tokens=8192, seed=1234)   # VLLM_BATCH_INVARIANT=1
sp = SamplingParams(temperature=0.0, max_tokens=192, ignore_eos=False)
prev = None
for r in range(1, 11):
    outs = llm.generate(prompts, sp)
    tk = [list(o.outputs[0].token_ids) for o in outs]
    rec = {"round": r, "accuracy": grade(outs), "token_identical_to_prev": tk == prev}
    open(f"round_{r:02d}.jsonl", "w").write(...)   # 逐样本 text + token_ids
    prev = tk
```

- 判据：`len({round accuracy}) == 1` **且** 每一轮 `token_ids` 与上一轮逐位相同；两者不满足任一条就是 FAIL，与 accuracy 高低无关。
- 评分用最后一段 `\boxed{...}` 与 `answer` 规范化后精确比（去 `$`、`\left/\right`、空白）；答案常被截断时 accuracy 会很低，**这不影响判据**，报告里写清 `max_tokens` 即可。
- `temperature=0` 但**必须固定 seed**；`ignore_eos=False` 让答案自然停，截断位置才是确定性的。
- 成本：A3 单 die、4 层切片、TP=1、`max_tokens=192` 下 500 题约 35 分钟/轮（主机同时压着 4 个作业）；`max_tokens=512` 会掉到 4 倍以上，**先用 192 试一轮再决定**，别一上来就 512。

---

## 四、判据红线

1. **`VLLM_BATCH_INVARIANT` 必须严格等于 `1`**。未设置时 vLLM 不会走批次不变路径，此时"一致"是无意义的巧合。
2. **零容差**：先比 token 序列，**只有 token 全同才比 logprob**；logprob 用 `torch.equal`（float32 逐位）。
3. **长度精确**：每条 prompt 的实际 token 数必须等于"基准 + 本条随机增量"，日志要能证明这一点；近似长度不算证据。
4. **KV 需求 > 容量 → `BLOCKED`**，不是 `FAIL`。此时出现的差异是换出/重算造成的，与不变性无关。
5. **`SKIPPED` 不是 `PASS`**，也不阻塞整体；但**不许**用别的 TP 的结果外推它。
6. **不许缩小 TP/BS 后宣称通过**。资源不够就报 `SKIPPED`/`BLOCKED` 并保留原始报错。

---

## 五、常见误判

| 现象 | 真因 | 处置 |
|---|---|---|
| 探不到算子 / 判"算子缺失要重编 CANN" | 用了 `hasattr`（恒真）或 `dir`（枚举不出），或没 `import batch_invariant_ops` | 逐个 `getattr` 具体算子名，见 [算子分诊](references/operator-classification.md) §1 |
| 每次跑都 `INCOMPLETE` / `BLOCKED_SCHEDULER_EVIDENCE` | 日志里 KV 行是 `NPU KV cache ...`，正则只认 `GPU` | 正则兼容 `(GPU\|NPU\|DEVICE)` |
| 测试明明 `1 passed` 却被判 `BLOCKED` | 判定顺序错：先看调度证据再看 pytest | 先判 pytest，调度证据降级为并列记录 |
| `LightningIndexer` 偶发不一致，但选中的 index 集合相同 | 同分并列的发射顺序随打包形状变化 | 按该 token 自身分数升序规范化后再比；判失败先看 multiset 是否相同 |
| 减层/随机权重下"通过"了 | 验证的不是目标模型 | 只能报 `BLOCKED_MISSING_REAL_WEIGHTS`，不许当通过 |
| 长序列场景 OOM | `max_num_batched_tokens` 太小导致一次性打包 | 显式给 `131072`，它只影响单步预算，不改变 KV 容量要求 |
| 每个 FAIL 都被判成 `EVICTION_UNSUPPORTED`（`reasons` 里写"test emitted ..."但日志里搜不到那次真发射） | `analyze_scheduler_log.py` 用**裸子串**匹配 eviction marker，而 pytest 失败的 traceback 会把 `test_batch_invariant.py` 源码原样回显，源码里就含这个字面量 | 改成"marker 后必须能 `json.loads` 出 payload"再置位（真发射一定带 JSON）。修完同一份日志复核：`status=PASS / NO_EVICTION_OBSERVED`，而 token 不一致仍然如实报 FAIL |
| 共享机上 TP=8 起不来：`Free memory on device (8.32/61.27 GiB) ... less than desired GPU memory utilization (0.9, 55.14 GiB)` | `test_batch_invariant.py` 把 `gpu_memory_utilization=0.9` **写死**，没有环境变量可降档 | 别指望降档；要 TP=8 就得 8 张卡同时各留 ≥0.9×卡容量。凑不齐就报 `SKIPPED_TP_RESOURCE_UNAVAILABLE` 并保留原始报错，不许换小 TP 顶替 |
| 只有 TP=1 起不来，TP=2/TP=4 同一台机全过：`RuntimeError: Insufficient space in /dev/shm for shared-memory allocation: 160 MiB required, 4 MiB free` | 该主机的 `/dev/shm` 是个 **4 MB 的 devtmpfs**（`df -h /dev/shm` → `devtmpfs 4.0M`），而 TP=1 引擎每次启动要一条 160 MiB 的 `ShmRingBuffer`；TP>1 不走这条路径，所以"大显存"和"卡够不够"全是无关变量 | 先 `df -h /dev/shm` 再谈资源；`VLLM_ENABLE_V1_MULTIPROCESSING=0` **无效**（日志确认已生效，仍报同一错）。要过就得让容器带 `--shm-size=4g` / `--ipc=host`，或协调后 `mount -t tmpfs -o size=4g tmpfs /dev/shm`（会挡住别的租户正在持有的 shm 文件，共享机上**不要自己动**）。判据词用 `BLOCKED_SHM_TOO_SMALL`，与"显存不够"分开记 |
| 图模式 + BI 一起开，引擎在 capture 阶段就起不来 | 报错末尾是 `capture_end ... task group status error` / `error code is 107033`，**真因却是前面那条 workspace 不足**（见 §五之二） | 先把 workspace 查询换成 BI 版再看图捕获 |

---

## 五之二、图模式（ACL graph）+ FIA：A5 实测 2026-11-03

以下每条都在 A5（`177.8.21.1`，8×Ascend950DT）+ 容器 `vllm-ascend:v0.30.0-a5-openeuler`（vllm 0.30.0 `ced6857` / vllm-ascend v0.30.0 `c09d3e20b`）+ `Qwen3-30B-A3B`（48 层 MoE）上真跑过：

- **`VLLM_BATCH_INVARIANT=1` + `enforce_eager=False` 默认必崩**：FULL 图第一个 bucket 就报 `call aclnnFusedInferAttentionScoreBatchInvariantV5 failed ... EZ1010: Value 203456512 for parameter workspaceSize is invalid. Reason: ... does not meet the minimum workspace size 487327744`。根因是 `attention_v1.py: full_graph_fia()` 用 `torch_npu._npu_fused_infer_attention_score_get_max_workspace` 算 workspace，而 `batch_invariant.py` 只把 **FIA 调用**换成了 BI 版、没换**这个查询** ⇒ 按非 BI 算子分配、喂给 BI 算子（AutoContiguous 路径要求更大）。A3 上没炸只是同一 bug 没越线，不代表 A3 安全。
- **修法一行**（应用层即可，放脚本最前面）：`torch_npu._npu_fused_infer_attention_score_get_max_workspace = batch_invariant_ops._npu_fused_infer_attention_score_batch_invariant_get_max_workspace`。修后 FULL 4/4 + PIECEWISE 4/4 捕获成功，TP=1 / TP=2（fork 起 worker，补丁被继承）都过。根治要落在 `vllm_ascend/batch_invariant.py` 的 FIA 补丁旁。
- **只有 FULL 图才算"FIA 进图"**：图模式下 `full_graph_fia` 计数 = 层数 × FULL bucket 数（30B/48 层 × 4 = 192）；`cudagraph_mode=PIECEWISE` 时该计数为 0、FIA 全部在图层间 eager（`forward_fused_infer_attention` eager 计数 = 层数 × 前向步数）。decode 期 eager FIA 计数必须为 0，这是"decode 真走图"的硬证据。
- **重放计数认 `torch_npu.npu.NPUGraph.replay`**：0.30.0 的重放走 `vllm_ascend.compilation.acl_graph`（`entry.aclgraph.replay()`），vllm 自己的 `ModelCudaGraphManager.run_fullgraph` 计数恒 0（patch 了也抓不到），别拿它下结论。
- **判"图模式有没有改数值"用 PIECEWISE 当对照**：PIECEWISE 下 FIA eager、其余在图层里；它与 FULL 图的 BS=1 refs **逐位相同** ⇒ 把 FIA 捕进图不改变数值。FULL/PIECEWISE 与"全 eager"的差异（token 全同、logprob 有确定性差，本机 max|Δ|≈0.107）来自**非注意力算子**，既不是 FIA 也不是 BI。
- **验收口径要分开写**：BI 判据是"同一模式内 BS=1 vs BS=N"；"图模式必须与 eager 逐位相同"是另一条要求，A5 + 0.30.0 **不满足**（30B 实测 token 0/8 不同、logprob 8/8 有差）。把两者混成一条判决，会把一个正常的 BI 结果判成 FAIL，或把真实的跨模式漂移放过。

---

## 五之三、长 prompt 的断点在哪：20480 就断，跟 TP 和 prefill 切步都无关（A3 实测 2026-11-03）

GLM-5.1 / GLM-5.2 的 4 层真实权重切片（保留全部 256 experts，无 dummy），vllm 0.31.0 + vllm-ascend `365692e2`，`VLLM_BATCH_INVARIANT=1`，`temperature=0.6`，`max_num_batched_tokens=131072`：

| 形状 | TP | BS | 结果 |
|---|---|---|---|
| 100:512 | 2 / 4 | 16、32 | **PASS**，3/3 轮 token 与 logprob 全位一致 |
| 1024:2048 | 2 / 4 | 16、32 | **PASS**，3/3 轮 |
| 20480:2048 | 8 | 64 | **FAIL** 64/64 prompts，`TOKEN_MISMATCH`，首个不一致在 **position 0** |
| 20480:2048 | 4 | 64 | **FAIL** 64/64，同样 position 0 |
| 20480:2048 | 2 | **4** | **FAIL** 4/4，position 0/3 |

结论与用法：

- **断点跟着 prompt 长度走**：≤1024 全过，20480 必断。别把"短序列 PASS"外推到长序列（§一.2 已经说了，这里是实测坐实）。
- **不是 TP 的锅**：TP=2/4/8 都断，所以"换个 TP 再试"救不回来。
- **不是 prefill 切步的锅**：BS=4 时 4×20500 = 82K < 131072，**一个 prefill 步**装得下，照样 4/4 断；BS=64 要 10 步，也断。所以定位方向是**长序列 attention/MoE 在批维上的归约**，不是调度切分。
- **不一致出现在 position 0** 意味着 **prefill 的 hidden state 就已经不同**，不是 decode 累积漂移；查的时候直接比 prefill 末位 logits，别从采样器查起。
- 同一台机、同一份权重、关掉 BI 的负控（TP=1、BS=8、temperature=0、64 tokens）：**logprob 8/8 不一致、token 2/8 不一致** ⇒ 尺子有牙，上面的 PASS 不是空过。注意负控里 token 只差 2/8 而 logprob 差 8/8——再次说明只比 token 会漏掉大部分真实差异。

---

## 六、交付什么

一份报告 + 一个运行目录。报告按 [验收标准](references/acceptance-criteria.md) §5 的骨架写，运行目录必须能让人**不看报告也能复核**：

```
runs/
  env.json                 # 准入结果（含芯片分类、版本 commit）
  triage.json              # 算子判决
  phase2/
    summary.csv|md|json    # 每场景：TP/BS/长度/轮数/判决/KV 需求与容量/耗时
    <scenario>.log         # 完整 stdout，含 VERDICT 与失败明细
    <scenario>.json        # 结构化结果
  phase3/
    phase3_acceptance.json # 10 轮 accuracy 与逐样本文本一致性的判定
```

**报告里每个结论都要能指到上面某个文件**。指不到的就不要写。

---

## 七、什么时候读哪份 reference

| 你现在的处境 | 读这个 |
|---|---|
| 不知道某个算子该不该放行、单算子怎么造用例 | [算子分诊](references/operator-classification.md) |
| 判据要写进报告、要跟人解释"凭什么算过" | [验收标准](references/acceptance-criteria.md) |
| 已经 `FAIL` 了，不知道从哪查 | [失败定位](references/failure-triage.md) |

脚本都可以直接读一遍再改：`bi_equivalence.py` 是判定核心（约 380 行，注释写的是"为什么"，不是"做了什么"），`bi_matrix.py` 是场景驱动，`bi_preflight.py` / `bi_ops_triage.py` 是准入与分诊。

## 减层模型能否作为 BI 证据：算子级判据与外推条件（含 §五之三 归因更正）

## 减层模型能否作为 BI 证据（2026-11-12 增补）

### 先更正一条已被证伪的归因

本 skill 前文 §五之三 把"20480 长 prompt 必断"归因为"长序列 attention/MoE 在批维上的归约"。**该归因不成立。**
真因是 `vllm_ascend/attention/sfa_v1.py` 里按"单步打包 token 总量 T"切换 kernel（2026-11-12 main 仍在）：

```python
# sfa_v1.py:331  TRANSPOSE_BMM_MAX_SUPPORTED_DIM = 65536
if q_nope.dtype in [torch.float16, torch.bfloat16] and hasattr(torch_npu, "npu_transpose_batchmatmul") \
   and q_nope.shape[0] < TRANSPOSE_BMM_MAX_SUPPORTED_DIM:      # T < 65536
    ql_nope = torch_npu.npu_transpose_batchmatmul(...)          # 路径 A：未 BI 化
else:
    ql_nope = torch.bmm(q_nope.transpose(0, 1), self.W_UK_T).transpose(0, 1)   # 路径 B：已被换成 bmm_batch_invariant
```

两条路径差约 1 个 bf16 ULP ⇒ **判据是"单步打包量 T 是否跨 65536"，与单请求长度、请求条数、TP 都无关**；BS=1 基线 T<65536 走 A、BS=N 打包后 T≥65536 走 B，同一 prompt 的 logits 就不逐位相同。所以要复现/回归这个缺陷，构造 `T = 65535 / 65536 / 65537` 三种打包即可，不必上 20480 长 prompt。

### 结论：减层模型证伪有力、证真无力

BI 不是"模型深度"的性质，而是"计算图里每个算子在某形状域上是否**逐行局部**"的性质。

- 定义：算子 `f` 行局部 ⟺ 对任意批 `B`、任意行 `i`，`f(B)[i] ≡ f({B_i})[i]`（逐位）。
- 正向定理：每个算子行局部 + 打包/调度不改变算子实参（dtype / shape 语义 / **kernel 选择** / layout）⇒ 整图 BI。证明是对计算图拓扑序做归纳，**与层数无关**。
- 推论：缩层切片 `S` 只覆盖 `Ops(S) ⊆ Ops(M)` 与 `Shapes(S)`。`S` FAIL 且失败路径全模型也走 ⇒ 全模型 FAIL（可信）；`S` PASS ⇒ 只说明切片内 op 实例在切片形状上恰好一致。
- 层数只通过三件事影响结论：**出现哪些算子族**、**出现哪些形状**、**KV 容量允许跑到多大的 T/BS**（容量大 ⇒ 更容易触发 shape 分叉，检出能力反而更强）。

推论：**真要证明全模型 BI，证明对象是"算子集 × 形状域"，缩层不是必需品**；一旦把缩层当证明手段，说明还没定位到算子级性质。

### 外推前必须补齐的六项（缺一只能写 PASS_SLICE_SCOPE_ONLY）

1. **算子族覆盖**：`Ops(切片) ⊇ Ops(全模型)`（族级）。做法：切片与全模型各跑一次 `TorchDispatchMode` 计数（不需要 profiler），对集合做差；差集非空即不足。
2. **形状域覆盖**：跨过每个算子的分叉边界（T=65536、`linear_persistent` 的 M<256/256~1024 BLOCK 分支、block_size、图桶、num_seqs）。"BS=1 vs BS=N"只覆盖一条嵌套对，生产是连续批处理、批组成每步变。
3. **无层号数值依赖**：`layer_idx` 不得进 kernel 参数（本项目唯一入口是 per-layer c8 量化 scale）。
4. **负控有牙**：同形状关掉 `VLLM_BATCH_INVARIANT` 必须能看见差异；`INCONCLUSIVE` ⇒ 该形状 PASS 作废。dummy/随机权重 + `load_format=dummy` 的 PASS 一律作废。
5. **调度域一致**：block_size=128、禁 chunked prefill / prefix caching / preemption，TP/EP、图模式、量化一致。
6. **白名单外算子逐个定性**：要么给行局部性单测，要么承认该区域未验证。

### 昇腾 BI 白名单怎么审（当前实现范式）

BI 是**进程级全局 patch + 白名单**，不是"整模式"。审的时候只看两处：

- `vllm_ascend/batch_invariant.py` 的 `enable_batch_invariant_mode()` 注册表：`aten::mm/matmul/addmm/bmm/softmax/_softmax/sum`（仅末维）+ `npu_add_rms_norm` 拆分 + `npu_fused_infer_attention_score`（仅稠密 FIA）。
- `vllm_ascend/utils.py` 的 `_CUSTOM_OP_ENABLED=False`：仓库自认"有些自定义算子没有 BI 实现，必须关掉"——这是**部分覆盖**的官方声明，不是补全。

白名单之外、且 GLM/DeepSeek-DSA 类模型的**主干**：`npu_grouped_matmul`、gating top-k、`npu_swiglu`、`npu_moe_init_routing/token_permute`、`npu_quant_matmul`、indexer / sparse attention 那套（`dsa_v1` / `dsa_v41` / `indexer.py`，走独立 impl，连被 patch 的 FIA 都不经过）。这些只要在 dispatch 集合里，就必须单独定性。

配套 vllm 侧的对照原则值得抄：**kernel 配置必须与批形状解耦**（`determinism/batch_invariant_configs.py`：每个 expert 形状只取一个 fused MoE 配置、对所有 M 复用；`BLOCK_K` 只由形状/dtype 定）。昇腾侧 `ops/triton/batch_invariant/matmul.py` 的 `matmul_persistent` 固定 128/128/64 是好例子，而 `linear_persistent` 的 `BLOCK_M/N` 随 M 变——设计上仍逐行，但属需单算子实测确认的风险项，不能假设。

### 判决词

新增两档，避免把"没测到"写成"通过"：`PASS_SLICE_SCOPE_ONLY`（切片范围通过，须附形状域声明）、`BLOCKED_OPERATOR_COVERAGE`（白名单外算子族未定性）。

## 验收成本优化：三层锚点 + 分派同构 diff（把 70 小时压到 5 小时）

## 把 BI 验收从 70 小时压到 5 小时（保绝对性）

适配对象：MindSpeed-Agent `skills/inference-model-skills/batch-invariance-validation`（master `7cb5678`）。结论：**贵不在测得多，在把端到端当证明**。

### 时间账（先算再改）

单场景成本 ≈ `加载 + Σ_BS1[prompt/ρ_prefill + max_tokens/ρ_dec_single] + max_tokens/ρ_dec_batch`。
BS=1 是**逐条串行**跑，所以成本 ∝ BS；默认矩阵（长输出 20480、长输入 20480、矩阵 36 组合 ×3 轮、38 次加载）≈ 70~82 h，其中 **94~96% 在 BS=1 那一侧**。模型加载 38 次约 1.9 h；BS=N 批跑 + 调度解析 <3%。

### 三个反模式（见到就改）

1. **P0 自伤**：`--auto-install` 默认开 + 构建与注册检查共用 `--timeout=120s` ⇒ 真构建必超时 ⇒ 判 BLOCKED ⇒ 整套复检。修：默认关、超时分离、OPP 路径按 SOC_VERSION 解析、结果按 `(pip freeze, SO SHA, SOC_VERSION, commit)` 缓存。
2. **P1 唯一通道**：要求逐 rank `op_statistic.csv` 且"不得用其他文件替代"，而本栈采不到 ⇒ 恒 BLOCKED 且每次先白耗数小时。修：改成 `op_statistic.csv` **或** 真实前向 `TorchDispatchMode` 计数二者其一。
3. **P3 同构重放**：10 轮同 seed/temperature=0/同顺序/同 max_num_seqs ⇒ 第 3~10 轮只是重放，证明不了批组成敏感。修：500 题 × 2 轮，第 2 轮**打乱顺序 + 改 max_num_seqs**；判据补 token id 级比较，`len(set(acc))==1` 要加"分数非退化"。

### 三层锚点（严格性不降，成本 ÷10~20）

端到端本来就只是抽样（`∀批组成` 给不出），所以把"BS=1 全量 64 条"换成：

- **P1 首步锚点（全量）**：每条单独跑 `max_tokens=1`，与 BS=N 的第 0 步比 logprob。T 差异最大，最容易撞分叉阈值，成本秒级。
- **P2 全长锚点（K=2~4 条）**：跑满 `max_tokens`，护住 decode 累积与 `ignore_eos` 步数断言。
- **P3 双打包互比（其余 N−K）**：`BS=N` vs `BS=max(1,N//8)` 或**逆序提交**，比公共子集。顺序维度现在完全没测。

必须保留"unbatched vs batched"这条轴（否则 `batch>1` 才出现的融合 kernel 漏网），但不必全量保留。

### 新增 A2：分派同构 diff（这才是"绝对性"）

在两次打包的 run 里挂 `TorchDispatchMode`，记录 `(op 名, 逐行 shape 签名)`，diff 两个序列：

```python
with DispatchCensus() as c:
    llm.generate(prompts, sp)          # BS=N
# 再跑 BS=max(1,N//8)，diff
assert not (c_big.multiset() - c_small.multiset())   # 例：npu_transpose_batchmatmul vs aten::bmm
```

在 A1（算子级行局部性）成立的前提下，执行图同构 ⇒ 输出逐位相同。这让 PASS 可解释，而不是碰巧。
**盲区**：同名换实现（`aten::mm` → BI kernel）trace 里同名，A2 抓不到，必须由 A1 单测覆盖——这条要写进 skill，否则会误以为 A2 万能。
配套 CI lint：`attention/**`、`ops/**`、`models/**` 里 `shape[0] <`、`num_tokens`、`num_seqs` 参与实现选择的，命中即要求说明"为什么与批无关"。

### 分档门禁（替代"每次都跑验收矩阵"）

- G0 静态扫描 + 缓存预检：<2 min
- G1 算子级（A1 单算子 ≥200/算子按分叉阈值取 shape + A2 diff）：<20 min，**不过不许进端到端**
- G2 功能快档（1 TP × 2 BS × 128:128、100:512）：≈1 h
- G3 完整验收（长输入/长输出/TP 矩阵，1 轮换序）：4~6 h，多 die 并行 2~3 h

### 报告口径（防止"抽样写成证明"）

A1+A2+A3 全过 → 可写"BI 成立（声明域内）"；只有端到端一致 → `SAMPLED_PASS` 并写清锚点数；A2 有 diff → `FAIL_DISPATCH_NOT_INVARIANT`；无算子证据 → `BLOCKED_OPERATOR_COVERAGE`。
K 条锚点要写"K 条全长严格 + N−K 条打包一致"，不许写"N 条全过"。

## 启动门：supports_batch_invariance 的三道门与「自派 backend」陷阱（#60271）

## 启动门：supports_batch_invariance 的三道门与「自派 backend」陷阱（#60271）

**适用**：`VLLM_BATCH_INVARIANT=1` 时引擎启动即抛 `RuntimeError: VLLM batch_invariant mode is not supported for XXX.`，尤其发生在 hybrid/线性注意力（GDN/KDA）或硬件插件自接 backend 的模型上。

### 三道门，只有第三道是「必经」

| 门 | 位置 | 何时触发 | 谁能绕过 |
|---|---|---|---|
| 0 平台 block-size 探测 | `vllm/platforms/interface.py:684-702`（`:699 layer.get_attn_backend()`） | `load_model()` 后 `update_block_size_for_backend()` | 层自派 backend 时不过 selector，但**仍会调 get_attn_backend()** |
| 1 mamba 选择器 | `vllm/v1/attention/selector.py:245`（#40193 引入） | `MambaBase.get_attn_backend()` → `get_mamba_attn_backend(mamba_type)`（`model_executor/layers/mamba/abstract.py:93-95`） | 插件 monkey-patch 掉层的 `get_attn_backend()`，直返类对象 |
| 2 逐层 attn group | `vllm/v1/worker/gpu/attn_utils.py:233-241`（#60271 新增） | `init_attn_backend()` 遍历每个 KV cache group 的 layer | **无**（V2/MRv2 必经；MRv1 无此检查） |

判据：门 1 会拒 CUDA 上的 GDN 模型（上游 issue #48613，早于 #60271 两个月）；**门 2 才是「自派 backend」的唯一出口闸**，因为 `MambaSpec`（`vllm/v1/kv_cache_interface.py:1094`）没有 override `has_layer_views`（基类 `:329` 为 True），GDN 组不会被 `attn_utils.py:221` 的 `continue` 跳过。全树只有 `HiSparse*Spec` 返回 False。

### 症状与归因的三个易错点

1. **「backend 没有 supports_batch_invariance 方法」通常不成立**：方法在 `vllm/v1/attention/backend.py:213-215` 基类上、默认 `False`，子类只是没 override。真缺属性会是 `AttributeError`；看到 `RuntimeError ... not supported for X.` 就应按「未声明」处理。
2. **报错里的名字来自 `get_name()`**，通常是父类常量（GDN 家族一律 `GDN_ATTN`），不是插件类名——别据此判断「这是上游的问题」。
3. **数值可 BI ≠ 启动门放行**：门只读声明，不读测量。反过来，「声明 True」也不等于真 BI（上游 #45819 评论：flag-only 必要但不充分，H100 上 18/32 不一致）。

### 定位步骤（不用跑模型）

```bash
# 1) 该 backend 家族有没有声明？
git grep -n "supports_batch_invariance" -- <repo>/vllm_ascend/attention <repo>/vllm_ascend/ops
# 2) 家族基类是谁、继承链上是否有 override
git grep -n "class .*<BackendName>" -- <repo>
# 3) 层是自派还是走选择器？
git grep -n "get_attn_backend" -- <repo>/<patch dir>
# 4) 插件是否直调上游 init_attn_backend（= 门 2 生效）
git grep -n "init_attn_backend" -- <repo>
```

坑：回归测试常按目录组织（只扫 `attention/`），而 GDN 这类 backend 放在 `ops/`，于是「10 个 backend 全绿」但缺口仍在——审清单时要按**类家族**核，不按目录。

### 修复范式（先证据后声明）

1. 在**家族基类**加 `@classmethod supports_batch_invariance(cls) -> bool: return True`（子类自动继承；`is_ssm()` / `get_name()` 不动）。
2. 把家族（含插件子类）加入 backend 声明回归 UT。
3. 声明前补数值证据：BS=1 vs BS=N 的 token + chosen-token logprob 逐位（含同形状负控）；单形状 PASS 只能算 `SAMPLED_PASS`。
4. 硬件/版本有差异时按能力位条件返回（例如某代卡未验证就不要无条件 True）。
5. 反面做法：只在某层包一层跳过检查，或裸声明 True 不做验收——前者重造「静默非 BI」，后者让后续 BI 报告失真。

未验证：本条为 2026-11 的静态溯源结论，未在真机复现。
