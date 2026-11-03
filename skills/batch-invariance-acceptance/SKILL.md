---
name: batch-invariance-acceptance
description: This skill should be used when the user asks to verify, triage or regression-test batch invariance of a model running on vLLM Ascend, including deciding whether BS=1 and BS=N produce bitwise-identical tokens and logprobs, covering TP matrices, long-input and long-output shapes, operator allowlists, and dataset-level acceptance.
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
