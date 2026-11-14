---
name: batch-invariance-acceptance
description: batch 不变性验收与训推一致性：减层证据、算子级判据、外推六条件、昇腾 BI 白名单审计、验收成本优化（三层锚点+分派同构）。
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

## 声明 vs 能力：行局部性静态审计（同一 backend 在 Ascend 可真、在 CUDA 不可）

## 声明 vs 能力：行局部性静态审计

**触发**：同一 backend/模型在平台 A 上 BI 逐位一致、在平台 B 上被判「不支持」；或 `supports_batch_invariance()` 返回 False，但你怀疑能力其实存在。

**核心判据**：BI 是「(算子, 形状域, kernel 选择)」的性质，不是 backend 类名的性质。类级布尔只能承载一份事实；子类可 override，所以**「未声明」≠「不支持」**。与上文《启动门》一节配套：那节讲门怎么拦，这节讲怎么判能力真伪。

### 三步静态审计（不跑模型）

1. **kernel 选择是否吃批形状**：搜 `num_tokens` / `batch_size` / `num_seqs` / `shape[0]` 参与的条件分支，以及按 M 选配置表的逻辑；吃到就大概率非行局部。
   - 安全例（Ascend GDN）：`vllm_ascend/ops/gdn.py:790-812` 的 `use_fla_gdn_prefill` / `use_fused_chunk` 只看 dtype（bf16）、是否 CPU、`_probe_fused_chunk()`、`pcp_world_size`、硬件能力位；A3 + bf16 + PCP=1 默认走 `device_op.py:883-948` 的 fla_npu 融合算子。
   - 危险例（CUDA GDN）：`vllm/model_executor/layers/mamba/gdn/qwen_gdn_linear_attn.py:1196` 的 `enable=num_tokens <= _BA_PROJ_OVERLAP_MAX_TOKENS` 按本步 token 数开合融合；同文件 `:158` 还有 triton/flashinfer/cutedsl/aiter/sycl 五套 prefill 实现。
2. **chunk 边界是否按序列切**：线性/SSM 类 kernel 必须逐序列，判据是调用处传 `cu_seqlens`，且 chunk 大小是常量（Ascend GDN 全链路 64：`gdn_attn_builder.py:44`、`fla/chunk.py:49,123,207`、`device_op.py:931`；三条 prefill 路径都传 `cu_seqlens`）。若按打包后的总 token 数切 chunk，批组成会改变边界 ⇒ 非行局部。
3. **其余批敏感算子是否被替换**：对照平台 BI 注册表（Ascend：`vllm_ascend/batch_invariant.py:135-154` 的 `mm/matmul/addmm/bmm/softmax/_softmax`、FIA、`npu_add_rms_norm`、`sum`）。清单外算子逐个定性；`grouped_matmul` / routing / swiglu 这类「逐 token 置换 + 逐行点积」通常行局部，但 tiling 是否与 M 无关**未验证**。

### 结论怎么用

- 三步全过 ⇒ **能力为真、只是未声明**：给子类/家族基类加 `@classmethod supports_batch_invariance(cls) -> bool: return True`（父类保持 `False`，CUDA 与插件各自成立），不要去改上游检查。
- 任一步不过 ⇒ **能力为假**：只能补实现或明确拒绝；声明 True 会把「启动失败」换成「静默漂移」。
- 别用端到端 PASS 反推能力：单形状 PASS 只证明该形状，且要先确认 BI 补丁真生效（日志含 `Enabling batch-invariant mode ...`、`torch.ops.batch_invariant_ops.*` 可解析），并做同形状负控。
- 硬前提：BI 下必须关 chunked prefill / prefix caching（`docs/.../batch_invariance.md`）；否则同一 prompt 被切段 prefill，递归状态跨段累进，数值必变。

### 静态审计的四个盲区（必须写进报告的"未验证"）

1. 探针形状可能不覆盖真实头数比例（GDN 探针用 `nk=nv=1, seqlen=64`，真实模型常不同）。
2. 厂商融合算子源码不在仓内时，其内部 tiling 是否随总行数变化**无法静态证明**——这是唯一不闭合的环，只能靠实测。
3. 同一请求在「纯 decode 批」与「P+D 混合批」下送进算子的张量长度不同（conv/state gather 分支），属形状域差异。
4. PCP/DP 等并行维 >1 时存在跨 rank 归约，行局部性默认不成立。

未验证：CUDA GDN 在 H100 上 18/32 不一致的数值机制为推断（未取证到 kernel 级）；Ascend `npu_grouped_matmul` 的 tiling 与 M 无关未取直接证据。

## vLLM-Ascend BI 实现层解剖：五层堆栈、注册表三分支、FIA workspace 断裂（Qwen3.5-35B-A3B 取证）

## vLLM-Ascend BI 实现层解剖（2026-11 取证）

**适用**：要回答「vllm-ascend 到底为 BI 改了哪些代码」「这个模型的 BI 是怎么成立的」「为什么开了 BI 还是漂」，或要给某个混合注意力/MoE 模型做 BI 适配评估。

**基线**：vllm-ascend `origin/main @ 124b477`（2026-11-06），vllm `24420b7a3`（2026-10-30）。行号只对这两个 commit 成立。

### 一、五层堆栈（只有第 3、4 层是 ascend 新增的）

| 层 | 内容 | 关键位置 |
|---|---|---|
| L1 上游契约 | `VLLM_BATCH_INVARIANT` 唯一注入点在 worker 分布式初始化；`supports_batch_invariance()` 基类默认 False | `vllm/v1/worker/gpu_worker.py:1702` → `determinism/batch_invariant.py:1433`；`v1/attention/backend.py:213` |
| L2 ascend 注入 | 同一时机调自己的 init | `vllm_ascend/worker/worker.py:1384` → `init_batch_invariance()`（`batch_invariant.py:166-189`） |
| L3 注册表 | `torch.library.Library("aten","IMPL")` + 自建 `"NPU"` key | `vllm_ascend/batch_invariant.py:124-163` |
| L4 算子 | AscendC wheel（仓外）+ Triton 兜底 | `csrc/build_batch_invariant_ops.sh`；`vllm_ascend/ops/triton/batch_invariant/{matmul,softmax,mean,rmsnorm}.py` |
| L5 模型图 | 只是把调用导向 L3 已 patch 的名字 | 无独立模型文件，走上游模型类 + `patch/worker/*` |

**别搞错路径**：`vllm_ascend/ops/batch_invariant/` **不存在**；真实位置是 `ops/triton/batch_invariant/`。`mean.py` / `rmsnorm.py` 写好了但**没接进注册表**（死代码，只被 UT 直接调）。`softmax.py` 没有 Triton kernel，是 `amax/exp/sum` 组合。

### 二、注册表 13 项 + 三条分支（静默失效的根源）

分支结构（原文 `:134/141/157`）：先 `if HAS_TRITON`（addmm/bmm/softmax/_softmax），再 `if HAS_ASCENDC`（mm/matmul + 4 处 monkey patch）`elif HAS_TRITON`（mm/matmul/linear）。**①② 不互斥，②③ 互斥。**

生效矩阵（这是最容易误判的地方）：

| 探测结果 | 实际生效 | 后果 |
|---|---|---|
| Triton ✓ + AscendC ✓ | 10 项 + 4 patch | 生产形态 |
| Triton ✓ + AscendC ✗ | 7 项 | **FIA / sum / add_rms_norm 全裸奔，但日志照样打印「Enabling batch-invariant mode」** |
| Triton ✗ + AscendC ✓ | 6 处 patch | addmm/bmm/softmax 未替换 |
| 都 ✗ | 0 | 只打 warning（原文有拼写错误：`...not available.skipping...`） |

4 处必须 monkey patch 的原因写在源码注释里（`:144-145`）：`torch_npu.npu_fused_infer_attention_score` 是普通 Python 函数不是 `torch.ops.Operator`，挂不上 dispatch key；`torch.sum` 同理。**代价是这些替换对已存下函数引用的调用点无效** —— 这就是下面 workspace bug 的成因。

`add_rms_norm` 拆分（`:50-62`）：`x_ = x + residual; x_, _ = torch_npu.npu_rms_norm(x_, weight, eps); return x_, None, residual_` —— **rstd 被丢弃**，需要 rstd 做残差重算的下游会拿到 `None`。
`reduce_sum`（`:68-99`）：只有末维（`dim == -1` 或 `x.dim()-1`）、NPU 张量、受支持 dtype 才走 `npu_reduce_sum_batch_invariant`，其余回退 `torch_sum`（`:28` 保存的原始引用，防递归）。非末维会抛 `AclNN_Parameter_Error(EZ1001, "Provided dim only support last dim")`。

### 三、FIA workspace 断裂链（唯一「不改就跑不起来」的坑）

`batch_invariant.py:146-148` 换掉了 `torch_npu.npu_fused_infer_attention_score`，但**没换 `_npu_fused_infer_attention_score_get_max_workspace`**。4 个 v1 调用点仍在按原算子量尺寸：

`attention_v1.py:724`（`full_graph_fia` 里 `get_capture_resource(_FIA_WORKSPACE_KEY, ...)`）、`mm_encoder_attention.py:189/267`、`attention/context_parallel/attention_cp.py:441`。紧随其后的 `register_task(torch_npu.npu_fused_infer_attention_score.out, ...)`（`attention_v1.py:744`）用的是同一份 workspace。

后果：FULL 图首桶报 `EZ1010: Value ... for parameter workspaceSize is invalid ... does not meet the minimum workspace size`，末尾却是 `capture_end ... task group status error` / `error code is 107033`（**报错与真因错位**）。越线幅度 A3+CANN9.2/9.3 约 3.49×、A5 约 2.4×、A3+CANN9.1.0 恰好不越线 → 同一份代码在不同 CANN 上表现不同，最容易被误判成环境问题。

修法：把 `_npu_fused_infer_attention_score_get_max_workspace` 一起重绑（库内应落在 `batch_invariant.py` 的 FIA 补丁旁；应用层只能一行 monkey patch 临时救）。另注意 `full_graph_fia_v2`（`:775`）走 `npu_fused_infer_attention_score_v2`，**注册表只换 v1，v2 无 BI 版**。

### 四、混合批：attention 里唯一的 BI 分支

`git grep VLLM_BATCH_INVARIANT -- vllm_ascend/attention/` **只有 1 行命中**：`attention_v1.py:1058`。语义是 BI 下把混合批（`num_decodes>0 and num_prefills>0`）强制拆成 decode FIA + prefill FIA 两次调用（`_forward_fia_chunked_prefill_split`），A5 靠硬件能力位 `CHUNKED_PREFILL_PHASE_SPLIT` 在非 BI 下也拆。**这不是优化而是语义要求**：合并 FIA 的 tiling 由整批拼出来的 `actual_seq_lengths` 决定，违反「同一条请求的计算结构与邻居无关」。

### 五、GDN 为什么"没有 BI 算子也能逐位一致"

线性注意力的所有 kernel 都按 `[1, T, H, D]` 组织（`ops/gdn.py:327` 注释 "batch size is always 1 here"）——**模型层面没有 batch 维**，N 条请求被拼成一条长 T。BI 于是退化成「打包后的 T 变了，每条请求被切的位置会不会变」：`_GDN_CHUNK_SIZE = 64`（`gdn_attn_builder.py:45`），先按 `cu_seqlens` 分段、再在段内以 64 切，**不跨请求** ⇒ 同一条请求的 chunk 序列只取决于自身长度。

- 三条 prefill 实现，同一模型在不同镜像上可能走不同一条：`gdn.py:814-830` 选择 → A `fla_npu chunk_gated_delta_rule_fwd`（`:831`，A2/A3/A5 默认）/ B `torch_npu.npu_chunk_gated_delta_rule`（`:853`，显式 `.to(bfloat16)` state）/ C 仓库 Triton（`:895`）。
- 另一个形状阈值：`_GDN_SOLVE_TRIL_LARGE_BLOCK_SIZE = 1216`（`:47`）。
- **唯一没闭合的环**：chunk 内 kernel 的 tiling 是否也与总 T 无关。`fla_npu` 源码不在仓库内，只能靠单算子实测。

### 六、其余「按批换实现」的高危点（按危险度）

1. **MoE 通信算法按 token 数选**：`ascend_forward_context.py:161-181` + `select_moe_comm_method`（`:393`），`num_tokens <= mc2_tokens_capacity → MC2`，否则 `ALLTOALL/ALLGATHER`。BS=1 与 BS=64 走完全不同的通信+GEMM 组合。**全仓最脆一环。**
2. **`pa_shape_list` 显式按 batch size 选 kernel**：`attention/utils.py:281-282`（`runtime_shape in pa_shape_list`），配置在 `ascend_config.py:444`（默认空）。填了值 ⇒ PA 与 FIA 混用，**BI 静默失效且无告警**。BI 下应断言该列表为空。
3. GDN 混合批才拆 decode 段走 `causal_conv1d_update`（`gdn.py:550-555/610-628` vs `:634-646`）；三种输出布局（`:678-693`）；单 token 续写 chunk 被重标成 decode（`gdn_attn_builder.py:103-126`）。
4. **绕过 dispatch 的融合算子 BI 管不到**：`sfa_v1.py` 的 `TRANSPOSE_BMM_MAX_SUPPORTED_DIM = 65536` 常量在 `:331`，分支在 **`:1311-1334`**（`_q_proj_and_k_up_proj`）。⚠ 更正本 skill §五之三 的注解：else 侧是 `torch.bmm`（**不是**直接调 `bmm_batch_invariant`，它是靠 `aten::bmm` 的 dispatch 注册被动 BI 化），if 侧 `npu_transpose_batchmatmul` 绕过 aten dispatch ⇒ 不受 BI 约束。`mla_v1.py:1230-1241` 有同构分支。

### 七、声明体系：11 处全 True，但那只管启动门

`git grep -A4 "def supports_batch_invariance" -- vllm_ascend/` = **11 处，全部 `return True`**（`attention_v1.py:85`、`mla_v1.py:116`、`sfa_v1.py:366`、`dsa_v1.py:301`、`dsa_v41.py:1746`、`fa3_v1.py:20`、`indexer.py:146`、`indexer_kpool.py:575/738`、`models/minimax_m3/msa_m3.py:209/712`），注释统一援引 vLLM #60271。注意 `AscendAttentionBackend.get_name()` 返回 `"CUSTOM"` —— 被门拦时的报错会写成 `not supported for CUSTOM.`，别据此去找一个叫 CUSTOM 的类。

MoE 另有**带下划线**的 `_supports_batch_invariance()`（`fused_moe/modular_kernel.py:716`，默认 False）：只实现不带下划线的那个会静默回落非 BI kernel。

配套的 4 处「不叫 BI 但为 BI 服务」的接入点：`utils.py:554-558`（BI 下关自定义算子，注释原文 *"There are some customed operators which aren't implemented with batch invariant in vllm-ascend, we need to disable them."* —— 这是仓库对「部分覆盖」的官方声明）、`sample/sampler.py:96`（退回原生采样）、`platform.py:1720`（FA backend 只服务 A5 的 GLM draft，Qwen3.5 天然走 dense FIA）、`override_envs_for_invariance()`（`:102-113`：`weight_nz_mode=0`、`HCCL_DETERMINISTIC=strict`、`LCCL_DETERMINISTIC=1`、`torch.use_deterministic_algorithms(True, warn_only=True)`）。

### 八、Qwen3.5-35B-A3B 的具体结论（可迁移的判断方法）

- 结构：40 层、`layer_types` 3:1 ⇒ **30 层 GDN + 10 层全注意力**；每层 MoE **256 专家 top-8 + 1 shared**；hidden 2048；bf16 无量化；`attn_output_gate=true`；mrope interleaved `[11,11,10]`；MTP 1 层；ViT 27 层（不参与文本 BI）。
- **点名这个模型的改动只有 3 条**：PR #21176（workspace 重绑，15 行零删除，**未合 main**）、PR #19442（e2e 覆盖，+148/−34 纯测试，4 层切片 + `load_format=dummy`）、PR #18449+#18570（docs Tested Models 加行）。**没有任何为它新写的 BI kernel。**
- 结论强度：A3/TP4/图模式 `FULL_AND_PIECEWISE`/桶{1,2,4,8}/BS≤8/32 步/256 token → token+chosen logprob+top-5 **三项逐位**、3 轮独立引擎复现；同形状负控暴露 6 token+10 logprob ⇒ 有牙。TP=8/BS=16 阶段封顶 `PASS_PARTIAL`。
- 覆盖缺口：GDN 全链、MoE 路由全链、FIA v2、MoE comm 选择，**四者都无 BI 替身** ⇒ 只能报「实测域内成立」，不能报「算子级已证明」。

### 九、取证命令与两个坑

```powershell
$r = '<vllm-ascend 克隆>'
git -C $r log -1 --date=short --format='%H %cd %s' origin/main      # 先锁 commit
git -C $r show origin/main:vllm_ascend/batch_invariant.py | Select-Object -Skip 120 -First 45
git -C $r grep -n "_get_max_workspace" origin/main -- vllm_ascend/
git -C $r grep -n "VLLM_BATCH_INVARIANT" origin/main -- vllm_ascend/attention/
git -C $r grep -n -A4 "def supports_batch_invariance" origin/main -- vllm_ascend/
```

- **别用 `hasattr(torch.ops, "batch_invariant_ops")` 判断装没装**：`torch.ops` 是惰性命名空间，访问任何属性都会当场造空对象，**恒为 True**；`dir(...)` 只返回 `['name']`。唯一判据是逐个 `getattr` 具体算子名。
- **`git grep` 无命中返回退出码 1**，在 `$ErrorActionPreference='Stop'` 下会被当失败；先 `2>$null` 再判 `.Count`。浅克隆会让 `--grep` / pickaxe 给出「引入提交不可达」的假结论（本机 2026-10-11→11-01 有空洞），考古结论必须标「不可考」而不是「没做」。

## DeepSeek-V4.1-Flash bf16 在 A5 跑 BI：三条硬前提与五条错误原文（2026-11-13 实测）

## DeepSeek-V4.1-Flash bf16 在 A5 上做 BI：先过三条硬前提

取证机：`177.11.25.1`（8×Ascend950DT 96 GiB）、镜像 `vllm-ascend:a5-openeuler-20261013-e96110a90739`（CANN 9.1.0）、
env `/mnt/share/g00815994/dsv41_py311`（py3.11.17 / torch 2.10.0+cpu / torch_npu 2.10.0.post4 /
vllm 0.30.1.dev0+gced6857af / vllm-ascend 0.1.dev5793+g6d4339aa1，均为 NFS editable）。
全程未动他人容器，只在自己起的容器里跑。

### 前提一：单机 8 die 装不下全量 bf16（先算再动手，别先加载）

`/mnt/share/g00815994/dsv41/dsv41-flash-bf16` = 525 分片 / 48496 张量 / **1421.66 GiB**。
**遍历全部 525 个分片头部**（`data_offsets` 求和 = 1,526,495,246,152 B，与 index `metadata.total_size` 逐位相等，HEADER_ERRORS=0）得到：

| 族 | GiB |
|---|---:|
| 路由专家（384×3 GMM） | 1012.50 |
| engram.embed（layer 1/14） | 366.22 |
| MTP/nextn | 26.50 |
| 其余（attn/shared/embed/head） | 16.44 |

- engram 全量进 HBM：缺 653.66 GiB。
- **engram `cpu_offload=true` 后 HBM 仍需 1054.85 GiB** ⇒ 8 卡每卡 131.9 GiB，**缺 286.85 GiB**。
- 最小可行：**16 die**（EP16/TP1，关 dspark）；12 die 是零余量理论下限。
- 官方 fp8 原生体（475 GiB）能上 8 卡，靠 **fp4 专家 + engram offload 同时成立**；bf16 版没有这两个折扣。
- **该 bf16 目录的 `config.json` 把 `engram_layer_ids` 清成了 `[]`**（官方体与 `config.json.before-bf16-fix-*` 都是 `[1,14]`）⇒ 那 366.8 GiB 根本不加载，**但这不省 HBM**（瓶颈是非 engram 部分）。用它起的不是完整 V4.1。

判据口径：写 `BLOCKED_INSUFFICIENT_DEVICES`，不要用 `--cpu-offload-gb` 硬跑（每步搬数百 GB，长序列矩阵跑不完，且 offload 本身可能引入额外非确定性）。

### 前提二：A5 的 dsv41 走 packed-cache，需要镜像里的 `ops` DSL 包，而它是 py3.12 绑定

调用链：`dsa_v41.py:763-764` `_device_backend = DeviceOperator.get_dsv41_packed_cache_ops()`
→ `_uses_a5_packed_cache=True` → `dsa_v41.py:1138` 调 `mixed_quant_sparse_flash_mla_metadata`
→ `ops/packaged_attention.py:534/26` `import_module("ops.mixed_quant_sparse_flash_mla_metadata")`。

- `ops` 包只在 `quay.io/ascend/vllm-ascend:v0.32.0rc-a5` / `nightly-main-a5-openeuler` 等新镜像里有（75 MB，11 个 .py + ABI 无关 `.so`）。
- 把它连同 `cannbotdsl` 拷到 NFS 给 py3.11 用，报
  `ImportError: cannot import name 'ir' from 'cannbotdsl._mlir._mlir_libs._mlir' (unknown location)`
  —— `cannbotdsl` 含 **MLIR python 绑定**（py 版本绑定），py3.11 用不了。
- 这些镜像**都不带 vllm/vllm_ascend 实体**（只有 `vllm-0.30.0+empty.dist-info` 之类元数据桩），
  真实 `vllm_ascend` 必须来自 NFS editable 安装。⇒ 想走 packed-cache，**整个 dsv41 环境得搬到 py3.12**。

### 前提三：强制回落到"标准 cache"会撞 CANN 算子 dtype 限制

绕法：让 `DeviceOperator.get_dsv41_packed_cache_ops` 返回 `None`（基类实现本就返回 None，`device_op.py:52-54`）。
用 `sitecustomize.py` + `sys.meta_path` 包一层 loader 改类属性——**必须用 sitecustomize**，
因为 vllm 的 mp worker 是 spawn 起的新解释器，父进程打的补丁不会继承。

patch 生效后再报（8 worker 全报）：

```
RuntimeError: call aclnnScatterNdUpdateSk failed, detail:[PID: ...]
AclNN_Parameter_Error(EZ1001): Tensor varRef not implemented for DT_UINT8,
should be in dtype support list [DT_FLOAT,DT_FLOAT16,DT_BOOL,DT_BFLOAT16,DT_INT64,DT_INT8,DT_INT32,DT_INT16,DT_FLOAT8_E4M3FN,DT_FLOAT8_E5M2,].
```

调用点 `torch.ops._C_ascend.npu_scatter_nd_update_sk(cache, indices, updates)`，cache 是 `uint8`。
CANN 9.1.0 的 aclnn 不支持 uint8 varRef ⇒ 与前提二是同一件事，应当合并到"换 CANN 9.2.1 镜像 + py3.12 env"一次解决。

### 附：三条必踩的启动/产物错误（原文 → 修法）

1. `Value error, DeepSeek V4.1 on Ascend A5 requires Model Runner V2 (VLLM_USE_V2_MODEL_RUNNER=1).`
   ⇒ 所有阶段命令加 `VLLM_USE_V2_MODEL_RUNNER=1`（模型运行前提，非降低判据）。
2. 自己写切片器时：`safetensors._safetensors_rust.SafetensorError: Error while deserializing header: incomplete metadata, file not fully covered`
   ⇒ 不能只预留 8 字节头部占位再写数据（回填头部会覆盖数据区开头）。数据先落临时文件，收尾写 `<8字节长度><header><data>`，
   并校验 `8 + len(header) + max(data_offsets[1]) == filesize`。
3. `ERROR ... min(n): Redundant `--quantization ...` / `ModuleNotFoundError: No module named 'ops'` 之外，
   镜像 py312 版本检查：`batch_invariant_ops_lib.cpython-312-aarch64-linux-gnu.so` 是 **cpython 版本绑定**的，
   py3.11 env 必须自己 build（`csrc/build_batch_invariant_ops.sh ascend950` 会下载 OBS zip，
   里面 `build_and_install.sh` 用 `python setup.py build_ext` 现编；装到独立 `--target` 目录，别改共享 venv）。
   复核判据仍是"逐个 `getattr torch.ops.batch_invariant_ops.<名字>`"，本次 11/11 全解析，
   `reduce_sum(末维)/softmax/log_softmax` 的行局部性 BS=1 vs BS=8/64 逐位通过。

### 附二：dsv41 的 BI 覆盖是结构性缺口，不是调参能补

同一 pin（va `6d4339aa1`）静态审计（`git grep -n supports_batch_invariance -- vllm_ascend/` **零命中**，
Ascend 侧也无 `validate_configuration` 门）⇒ `VLLM_BATCH_INVARIANT=1` **不会启动失败**，只打一行
`Enabling batch-invariant mode ...` 然后**静默不覆盖**。dsv41 主干绕开 `aten::` dispatch 的算子至少 10 类：
`npu_sparse_flash_mla`（`dsa_v41.py:657`）、`npu_grouped_matmul`（`routed_experts.py:231/294`）、
`npu_moe_init_routing`（`token_dispatcher.py:402/679`）、indexer top-k、`npu_add_rms_norm_bias`
（`ops/layernorm.py:93-94`，**BI 补的是 `npu_add_rms_norm`，打错算子名**）、o_proj `npu_transpose_batchmatmul`、
`npu_hc_pre_v3/post`、compressor Triton、`grouped_topk_router.py:269/273` 的 `topk(sorted=False)`。
⇒ 判决只能到 `BLOCKED_OPERATOR_COVERAGE`；要"成立"必须先给这些算子补 BI 实现或证明行局部性。

**切片的上限**：真权重切片（4 层、全 384 专家、剔除 engram/MTP，105.876 GiB）跑通也只能报
`PASS_SLICE_SCOPE_ONLY`；且 dsv41 有跨层引用，砍层必须同时改
`compress_ratios` / `kv_source_layer_ids` / `index_source_layer_ids` / `npu_nextn` / `dspark_target_layer_ids`。

## Qwen3.5-35B-A3B(A5) 实跑：GDN 未声明 BI 的启动门、spawn 与可续跑形态

## Qwen3.5-35B-A3B(A5) 实跑：GDN 声明缺口、spawn 与可续跑形态（2026-11-13 实测）

**适用**：在 A5 上对 Qwen3.5 系列（`Qwen3_5MoeForConditionalGeneration`，3:1 混合 `linear_attention` + `full_attention`）开 `VLLM_BATCH_INVARIANT=1` 时引擎起不来，或要复现「三档 TP 全 PASS + 同形状负控」这一套证据。
**不适用**：纯 decoder-only（无 GDN）模型——它们走 `AscendAttentionBackend`，早已声明 True。

### 栈（本次实测）

镜像 `quay.nju.edu.cn/ascend/vllm-ascend:nightly-releases-v0.32.0rc-a5-openeuler`（image id `be3d1eeee5a3`）：vllm `0.32.0` @`5df63a72`、vllm-ascend `0.19.1rc2.dev3286+gfd4be4dbc`（editable `/vllm-workspace/vllm-ascend`）、torch `2.10.0+cpu` + torch_npu `2.10.0.post7`、CANN `9.2.1`、`batch_invariant_ops 1.0.0`（含 `_npu_fused_infer_attention_score_batch_invariant*_get_max_workspace`，A5 的 FIA workspace 坑已修）。

### 必踩的两个门

1. **GDN 启动门（唯一必须改代码的地方）**。现象：
   `RuntimeError: VLLM batch_invariant mode is not supported for GDN_ATTN.`
   栈：`vllm_ascend/patch/worker/patch_model_runner.py:85` → `vllm/v1/worker/gpu/attn_utils.py:232`（MRv2 必经的门 2），
   报错名来自 `get_name()` 常量，**不是**类名，别去找叫 GDN_ATTN 的类。
   修法（幂等脚本即可，无需重编）：
   ```python
   # /vllm-workspace/vllm-ascend/vllm_ascend/ops/gdn_attn_builder.py
   class AscendGDNAttentionBackend(GDNAttentionBackend):
       @classmethod
       def supports_batch_invariance(cls) -> bool:
           return True
   ```
   声明 True 的依据（静态审计，四条都在本次树里核过）：backend 选择是常量 `gdn.py:407`；prefill 路径只看硬件能力位 + 一次性可用性探针 `gdn.py:827-840`；chunk 恒 64 且按 `cu_seqlens` 逐序列切 `gdn_attn_builder.py:282-300`；GDN 张量是 `[1,T,H,D]` 无 batch 轴 `gdn.py:254-256`。
   **残留风险照旧**：`fla_npu` 内部 tiling 与总 T 的关系、MoE `npu_grouped_matmul` 的 tiling、`causal_conv1d_update` 在本镜像走 PyTorch 回退（日志有 `NPU Triton causal_conv1d_update is unavailable`），三者只有端到端证据。

2. **调度证据正则（不改就永远 BLOCKED）**。`analyze_scheduler_log.py` 写死 `GPU KV cache ...`，Ascend 日志是 `NPU KV cache ...`：
   数值已 `1 passed` 也会被判 `INCOMPLETE: no periodic scheduler statistics were found` → `BLOCKED`。
   修法：`CAPACITY_RE` / `STATS_RE` 改 `(?:GPU|NPU|DEVICE)`。修后同一日志重跑得 `PASS / NO_EVICTION_OBSERVED`。

### TP>1 必须 spawn

`docker exec -e VLLM_WORKER_MULTIPROC_METHOD=spawn`，否则 `RuntimeError: Cannot re-initialize NPU in forked subprocess`。

### 实测结果（A5 = 177.11.27.1，die 4-7，真实 bf16 权重 77 GiB）

| 形状 | TP | BS | 结果 |
|---|---|---|---|
| 100:512 / T=0.6 / eager | 1 | 16 | PASS，KV 612,550/18,432（10.3%），token+logprob 0 不一致 |
| 同上 | 2 | 16 | PASS，4,205,397/18,432（1.5%） |
| 同上 | 4 | 16 | PASS，6,037,588/12,800（0.6%），单轮 12:40 |
| 同上（BI=0 负控） | 2 | 16 | `NEGATIVE_CONTROL_REJECTED_AS_EXPECTED`：16 条里 7 条 token 不一致、7 条 logprob 不一致 |

⇒ 同一形状只改开关，判据从「0/16 不一致」翻到「7/16 不一致」，这是三档 PASS 可信的前提。
成本锚：BS=1 decode ≈14 tok/s、每轮引擎初始化 ≈66 s、BS=16/100:512 单轮 ≈13 min（BS=32 约翻倍）。

### 可续跑形态（共享机上必备）

- 一「格」= 一个 (scenario, TP, BS, prompt_len, max_tokens)，单独一次 `run_phase2_acceptance.sh` 调用；`run_phase2_acceptance.sh` 自己没有 resume，整段调用被中断就全废。
- 外层 driver：跑前 `gate_dies.sh`（die 无进程 且 HBM ≤10%，不满足就写 `BLOCKED_FREE_DEVICE_UNAVAILABLE` 退出 42 不抢卡）；跑后把 `summary.csv` 一行 + `status.json` 落盘；**只跳过 `verdict=PASS`**，所以重跑同一条命令即续跑。
- poller 必须能识别「进程消失」：共享机上别人 `pkill`/`docker kill` 会让 attempt 不带任何退出标记消失（本次实测容器被 `SIGKILL`，`docker inspect` 里 `ExitCode=137`、`OOMKilled=false`），只等 marker 会白等到超时。
- 换机：run root 放 NFS（`/mnt/share/<run>`），`state.json` + append-only `state_transitions.jsonl` 记 `owner_host`/`lease`；新机 `release`+`claim` 后 `docker start` 原容器即可（补丁在容器文件系统里，`docker rm` 才会丢）。

### MATH-500 在 thinking 模型上的坑

`max_tokens=192` 时 500/500 都是 `finish_reason=length`（只有 78 条写出 `\boxed{}`）⇒ accuracy=0.0。BI 判据（逐轮文本逐字节相同）不受影响，但**报告里不能把 accuracy=0 写成「精度通过」**，要么提高 max_tokens，要么明确写「本阶段只证确定性」。

## 训推一致性（train–infer）四仓支持度审计：与批次不变性不是同一件事

## 训推一致性（train–infer）审计：先分清它和批次不变性不是同一件事

**触发**：用户问"verl / FSDPTurbo / vllm / vllm-ascend 对某模型的训推一致性支持到什么程度"、"rollout 和 actor 的 logprob 对不上"、"训练和推理能不能逐位一致"、RL 里 `pearson_corr` / kl 偏大。

**边界**：BI 问的是「同一引擎内，BS=1 与 BS=N 是否同」；训推一致性问的是「训练框架的计算图 与 推理引擎的计算图 是否同」。**裁判对象不同，结论不能互相外推**；BI 全绿也不代表训推一致（本 skill 前文已验证 dsv41 的 BI 判决只能到 `BLOCKED_OPERATOR_COVERAGE`）。

### 1. 先锁树（这一步不做，后面全是错树）

dsv41 的真栈在**一个目录**下，别认错：
```bash
B=/mnt/share/g00815994/dsv41
git -C $B/verl_ds41 log -1 --date=short --format='%H %cd %d %s'   # 训练：fork of menjiantong/verl，branch support_deepseek41
git -C $B/FSDPTurbo  log -1 --date=short --format='%H %cd %d %s'   # 训练内核（模型代码其实在这里，不在 verl）
git -C $B/vllm      log -1 --date=short --format='%H %cd %d %s'    # v0.30.0 pin
git -C $B/vllm-ascend log -1 --date=short --format='%H %cd %d %s'
git -C $B/verl_ds41 status --porcelain | wc -l        # 实测 191 项！
git -C $B/FSDPTurbo status --porcelain                # 5 处，正是实际在跑的数值
```
- **同名副本陷阱**：`z00988734/projects/step5/{verl,FSDPTurbo,vllm,vllm-ascend}` 是 Step5-VL（92 层/16 专家），`j00949742/verl_turbo*` 是第三方变体。判归属看 `config.json` 的 `num_hidden_layers=40` + `n_routed_experts=384`。
- **只看 HEAD 会漏掉真数值**：`.before_*` 未跟踪文件就是 changelog，必须 `git diff HEAD`。
- 训练与 rollout 用**同一份** vllm/vllm-ascend 源码树 + 同一镜像，这是唯一的好消息。

### 2. 六维度矩阵（照这张表填，缺一维就写"未取证"）

| 维度 | 要查什么 |
|---|---|
| D1 结构覆盖 | 两侧都实现了哪些子模块（engram / dspark / MTP / indexer / compressor / mHC / routing）；**MTP 与 DSpark 常是"仅推理"**（训练侧直接 raise） |
| D2 权重与格式 | dtype 是否直通、有无 cast、专家维是否重排、量化形态是否两侧都有 |
| D3 数值路径 | 融合算子清单、fp32-by-design 点位、BI 注册表覆盖、`supports_batch_invariance` 声明 |
| D4 调度/缓存 | 训练有无 KV/cache、推理 KV 是否量化（A5 packed cache = FP4/int4/FP8）、chunked prefill / prefix caching 是否关 |
| D5 采样/logprob | chosen logprob 与 prompt_logprobs 是否同一 kernel、bypass 模式下 old_log_probs ≡ rollout 会假绿 |
| D6 验证设施 | 有无 golden logits / 断言 / CI / e2e 用例；指标是否只落日志 |

判据：**逐位**要求两侧算子与舍入点同源；**统计一致**用 probs 空间 pearson + logprob 偏差分布。

### 3. 已取证的结论（dsv41-flash，2026-11）

- **逐位不可达**，4 条结构缺口：① A5 packed cache 把 KV 压到 FP4/int4/FP8，而训练 KV 是 bf16 环形 buffer 且 `if not self.training` 挡住播种；② 引擎 decode↔prefill 两条通道（0.043–0.19 nats，未做算子级归因）；③ 融合 sparse 核把**未归一化 exp** 舍 bf16、训练 eager 把**归一化 prob** 舍 bf16（舍入对象不同，不是精度高低）；④ MoE 有 ~4× 数学增益（Jacobian，不是 bug）。
- **统计基线**：probs 空间 pooled pearson **0.99456–0.99464** 地板；到 0.999 需总差 ×0.4。
- **主因**：训练侧 `fused_mhc_pre_sinkhorn_premix` 输出 fp32 ⇒ 主流全程 fp32 升格（torch_npu `F.linear(fp32, bf16)` 自动升格），引擎是 bf16 融合核。补丁 `VERL_DSV41_HC_BF16=1` 实测 q 链 ×130，**但从未落盘**（`grep -rn VERL_DSV41_HC_BF16` 在 `verl/`+`fsdp_turbo/` 零命中）。
- **放大在 MoE 不在注意力**：嫁接 MoE 对齐 23×（384 专家 29–42×），注意力仅 2.6×；top-6 专家与压缩索引集合基本零偏差。
- **反直觉但是对的**：训练 head 改 fp32 会让 pearson **变差**（0.99464→0.99403），因为训练侧所有参数都被 cast bf16，bf16 才是同一舍入点。

### 4. 观测与门禁现状（四仓共同的短板）

- 有度量：`verl/utils/debug/metrics.py` 的 `rollout_probs_diff_{mean,max,std}` + `rollout_actor_probs_pearson_corr`。
- 无门禁：无 golden logits、无 CI 断言；带 `--max-k3-kl` 的对拍脚本 `rollout_logprob_diff.py` **不在训练树里**（只在别的副本）。
- **旧 dump 口径偏低**：历史 dump 是 `VLLM_BATCH_INVARIANT=0` 时取的，生产偏差约为 harness 的 2.4×。
- `prompt_logprobs` 走 `torch.logsumexp`，BI 不覆盖 ⇒ 只比 chosen 会漏检。

### 5. 往前推的最小顺序（按性价比）

1. 固化脏树（`git stash create` + tar 快照），否则数字不可复现。
2. 落地 `VERL_DSV41_HC_BF16` → 跑 **1 步 RL** 对照三指标（这是 10 月遗留的待验收项）。
3. 在 BI=1 + 同形状负控下重取 dump；引擎侧试 `VA_V41_OPROJ_FP32_AR=1`（o-proj all-reduce 走 fp32）。
4. 把对拍脚本 + 阈值做成门禁。
5. 只有"共用内核 + 放弃 packed cache"才可能逐位——成本很高，先想清楚是否值得。

**不要做**：在 HC_BF16 落地前反复调 BI —— 已实测 BI on/off 对端到端 pearson 无显著变化，主项不在批组成。

未验证：本文数字来自 2026-10-13~10-21 的工作记录，未在新树上复跑；`cann_ops_transformer.sparse_flash_mla` 与 `torch.ops._C_ascend.npu_sparse_flash_mla` 是否同一二进制内核未取证（签名不同：训练侧无 `cmp_residual`/`mask_mode`）。

## DSV4.1 bf16 权重就位与 4 层切片的可加载性核验（2026-11-14 实测）

**权重就位（A5 四台通用，NFS `172.27.1.1:/Share`）**
- 全量 bf16：`/mnt/share/bi_dsv41/weights/dsv41-flash-bf16`，525 分片 / 1.39 TiB，硬链自 `/mnt/share/g00815994/dsv41/dsv41-flash-bf16`（0 额外空间，inode 相同）。
- 4 层切片：`/mnt/share/bi_dsv41/models/dsv41-bf16-L4`（`weights/` 下有软链），4972 张量 / 105.88 GiB 逻辑 / 113.7 GB 占盘 / 14 分片；保留全 384 专家，剔 engram+MTP。

**切片可加载性的 9 项机械判据（纯标准库、只读 header，约 1 分钟）**
1. 每分片 `8+len(header)+max(data_offsets[1]) == filesize`；偏移不重叠、begin 单调、`end-begin == prod(shape)*dtype_size`。
2. header 键集 == index 键集 == 张量总数；层 id 仅 `<N`；无 `engram` / `mtp.` / `nextn` / `dspark`。
3. 与源逐张量 `(shape,dtype)` 全等，源缺失 0。
4. dtype 计数（BF16/F32 混合要逐个列出，确认源里本就如此，不是切片引入）。
5. `index.metadata.total_size == Σ张量字节 == Σ分片 data 区`；weight_map 分片集合 == 磁盘文件集合。
6. config 逐字段 diff：应改的（层数 / compress_ratios / kv&index_source / num_nextn / dspark / engram）与原样保持的分开列。
7. `tokenizer.json` 可解析、`configuration.json` 与源 sha256 相同；缺 `generation_config.json` 只是 warning。
8. `safe_open(framework="numpy")` 能打开（没有 torch 的 python 也能验）。
9. 核验前后切片目录 mtime 不变（证明只读）。

**`candidate_source_layer_id` 不要"顺手修"**：4 层切片留着源值 20 是**安全**的——`build_layer_plan` 只做 `index_source > candidate_source` 比较，`dsa_v41.py` 有 `0 <= candidate < len(ratios)` 守卫 ⇒ 候选预筛关闭，与全模型（index_source=2 < 20）语义一致。改成 0/1/3 会让比较成立、**打开** candidate 过滤；改成 2 会把 layer 2 标成 candidate source。

**命名能否被认领（静态证据）**：`vllm_ascend/models/deepseek_v41/model.py` 的 `load_weights` 改名表命中切片键族：`.w1/.w2/.w3 → gate_proj/down_proj/up_proj`、`.ffn. → .mlp.`、`.attn. → .self_attn.`、`.attn_norm. → .input_layernorm.`、`.ffn_norm. → .post_attention_layernorm.`、`.gate.bias → .gate.e_score_correction_bias`；`gate.bias_vl` 与 `attn_sink` 有专门特判；`aligner./vision./image_/mtp.` 走 `_DEFERRED_WEIGHT_PREFIXES`。

**未验证**：真实 vllm 加载/前向（P2 blocker 仍是 `No module named 'ops'` + `aclnnScatterNdUpdateSk DT_UINT8`）。CPU 上实例化 V4.1 走不通：nvidia 实现断言 `DeepseekV4 attention requires a CUDA device`，Ascend 实现要平台解析成 npu ⇒ 要拿「模型参数名 − 切片键」差集，只能上空闲 die + `load_format=dummy` 跑同一脚本。

## dummy 权重与 BI：只影响证据强度，不影响性质

**结论**：`load_format=dummy` 不在 BI 的自变量里（BI 判据是「算子实现 × 形状域 × kernel 分派」），所以它**不会**让 BI 失效；但 dummy 下的 PASS 只能算 `SAMPLED_PASS`。

**代码证据（vllm `ffcabb8c`，2026-10-26；三棵 vllm-ascend 树同结论）**
- `vllm/model_executor/determinism/` 三文件里 `load_format` / `dummy` **0 命中**；`dummy.*batch_invarian` 类组合正则在 `vllm/` + `tests/` 全树 **0 命中**。
- BI 唯一入口 `init_batch_invariance()`（`model_executor/determinism/batch_invariant.py:1433`），在 `v1/worker/gpu_worker.py:1690/1699-1701` 的 `init_worker_distributed_environment()` 内、**权重加载之前**调用；实现是 `torch.library.Library("aten","IMPL")` 覆写 `mm/addmm/mm.out/addmm.out/matmul/linear/mean.dim/softmax/_softmax`（:1314-1367）——只看算子 + 形状，看不到权重来源。
- vllm-ascend 侧 `enable_batch_invariant_mode()` 同样 0 命中（0.26 / main / PR 分支均如此）。
- dummy 初值：`initialize_single_dummy_weight`（`model_executor/model_loader/weight_utils.py:1631-1719`）seed 恒 `1234`、浮点默认 ±1e-3、<16bit 浮点 ±1.0、E8M0 scale 固定字节 120、int8/uint8/FP4 用 `random_`；注释明说设计目标是 dequant 后 finite（:1623-1628）⇒ **不会出 NaN**，`torch.empty` 只作 fp16 临时缓冲（:1715-1719）。

**三处真实副作用（这才是"影响"所在）**
1. **非浮点、非 int8/uint8/FP4 的参数直接不写**（:1673-1679，仅 ROCm `zero_()`）→ 保留 `torch.empty` 内容，**跨进程不确定**；有整型 buffer/索引进前向的模型要单独核。
2. **MoE 路由形状域变了**：top-k 由 gate 权重决定，dummy 下专家负载分布 ≠ 真权重，送进 grouped_matmul 的每专家形形状不同；BI 是形状域性质 ⇒ dummy 改的是"被测域"。
3. 附带（代码可推、未实跑）：每次调用都新建 `Generator` 并 seed 1234 ⇒ 同 device/同 shape/同 dtype 的参数拿到**完全相同**的一串值，分布比"随机"更退化。

**证据链现状**
- 上游文档 `docs/features/batch_invariance.md` 对 `weight|dummy|random|load_format` **0 命中**（既不背书也不禁止）。
- 上游 BI 测试全用真权重：`tests/v1/determinism/utils.py:43`（`DEFAULT_MODEL="Qwen/Qwen3-1.7B"`）、`test_batch_invariance.py:180-190`（`LLM(model=TEST_MODEL)`，无 `load_format`）；`tests/v1/determinism/` 里唯一 dummy 在 `test_xpu_batch_invariant_ut.py:67`，只做"量化 + BI"的配置拒绝断言。
- 反例：vllm-ascend main 的 BI e2e 硬编码 `load_format="dummy"` + `num_hidden_layers=2`（`tests/e2e/pull_request/four_card/rlhf/consistency/test_batch_invariant_tp4.py:123-125`），而 `docs/source/user_guide/feature_guide/batch_invariance.md:200-206` 把 Qwen3-30B-A3B 写成 "tested and verified" 且未披露该证据是 2 层随机权重——这就是"dummy 当证据"的实例。

**判据**：dummy 只用于链路/性能/shape 冒烟；dummy 下的 BI 结果报 `SAMPLED_PASS` 并注明「N 层切片 + 随机权重 + 无判别力证据」；要"成立"必须真权重 × 同形状负控（证明尺子有牙），或算子级行局部性 + 分派同构 diff。

## BI + FULL_DECODE_ONLY 在 A5 真开起来：Qwen3.5 实测、A/B 因果取证与 replay/FIA 计数法

## BI + FULL_DECODE_ONLY 在 A5 真开起来之后：Qwen3.5-35B-A3B 实测与三个取证手法（2026-11-14）

**适用**：要回答「开 BI 还能不能开整图」「整图到底有没有生效」「图模式会不会把精度改掉」，或要复现 PR #21176 的前后差异。
**前置**：本 skill《启动门》《五之二 图模式》两节。这里补的是「已经跑起来之后怎么证 + 真实数字」。

### 栈与结论（一句话）

镜像 `be3d1eeee5a3`（vllm 0.32.0@5df63a72 / vllm-ascend 0.19.1rc2@fd4be4db，CANN 9.2.1，torch_npu 2.10.0.post7），
`/mnt/weight/Qwen3.5-35B-A3B`（77 GiB bf16），`VLLM_BATCH_INVARIANT=1` +
`compilation_config={"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,8]}`，TP=1：
**capture 2/2 成功（1.08 GiB）、decode 6.0×、math500 与 eager 逐字节一致**。两个必带补丁：GDN 声明（#19442）+ FIA workspace 重绑（#21176）。

### 手法一：A/B 开关证明「就是这一行让它能开图」

把 PR 的重绑包进 `if os.environ.get("BI_SKIP_WS_REBIND") != "1":`，同一棵树同一 die 跑两腿：

| 腿 | 结果 |
|---|---|
| `BI_SKIP_WS_REBIND=1`（PR 之前） | `aclnnFusedInferAttentionScoreBatchInvariantV5 failed ... Invalid_Argument(EZ1010)` → `capture_end ... error code is 107033` → `EE1018 ... A task group ... started but not ended` |
| 默认（PR #21176） | `Capturing CUDA graphs (FULL): 2/2`、`Graph capturing finished in 1 secs, took 1.08 GiB` |

比"我跑通了"强一个数量级：**没有这行就一定失败**，且失败签名与 PR 描述逐字一致。

### 手法二：replay/FIA 计数证「decode 真在图里」

引擎创建后挂钩 `torch_npu.npu.NPUGraph.replay` 与 `torch_npu.npu_fused_infer_attention_score`（BI 已把它换成 BI 算子），分 prefill/decode 相统计：

| 模式（均 BI=1） | replay/步 | eager FIA/步 | decode tok/s |
|---|---|---|---|
| eager | 0.0 | **10.02** | 16.01 |
| FULL_DECODE_ONLY | **1.0** | **0.02** | 95.52 |

`replay/步=1.0` = 每步重放一次图；`eager FIA/步≈0`（511 步共 ~10 次 = 10 层在 capture 时各一次）⇒ **FIA 被捕获进图**。
**坑**：capture 发生在**引擎初始化**阶段（日志 `Graph capturing finished`），任何在 `LLM(...)` 之后装的钩子都看不到 capture 调用；要统计 capture 就必须在构造引擎**之前**钩 op packet（`torch.ops.batch_invariant_ops.<op>.out`）。

### 手法三：`.out` 形式怎么证（不靠调用计数）

`attention_v1.py` 整图路径两处：`:705` 用 `_npu_fused_infer_attention_score_get_max_workspace` 算 workspace（PR #21176 重绑它）、`:726` `register_task(torch_npu.npu_fused_infer_attention_score.out, ...)`。
BI 下 `torch_npu.npu_fused_infer_attention_score is torch.ops.batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant` → True，
且该 op 的 `overloads()` = `['default','out']` ⇒ **注册进图的就是 BI 算子的 out 重载**。三重证据（注册点 + identity + overload 列表）够用，不必强求调用计数。

### 真实数字（2k 输入 / 2k 输出，bf16，TP=1）

| BS | eager | FULL_DECODE_ONLY | 倍数 |
|---|---|---|---|
| 1 | 16.05 tok/s | 96.43（复现 97.1） | 6.0× |
| 8 | 118.0 tok/s | 650.82（复现 652.85） | 5.5× |

math500（500 题、T=0、seed=1234、`max_tokens=512`、**`enable_thinking=False`**）：eager 2057.2 s vs 图 600.9 s；
accuracy 两侧同为 0.2260，**500/500 预测文本逐字节相同、两份文件 sha256 相同**、discordant 0/0、McNemar p=1.0、配对 t=0、CI[0,0]。
注意 accuracy 0.226 是 512 token 截断（378/500 触顶）导致，不能当模型能力；比较图 vs 不图仍然有效。
> 关思考链是"能比"的前提：不关时 192/512 token 全被 think 段吃掉，两边都会接近 0 分，比不出东西。

### 其它实测坑

- **TP=2 也能开图**（decode 28.97/223.16 tok/s），但该模型 TP>1 时 HCCL 开销压过收益，且与同机他人任务并存时数字不可比；性能结论只认独占 die 的 TP=1。
- `docker exec` 里**别用最小 PATH**（只给 `/usr/local/python3.12.16/bin:/usr/bin:...`）：会丢 CANN/triton 路径，vllm 的 `_prepare_rope_positions_kernel[(grid,)](...)` 退化成普通函数 → `TypeError: 'function' object is not subscriptable`。正确写法是 `export PATH=/usr/local/python3.12.16/bin:$PATH`（在脚本里写 `$PATH` 让它运行时展开，别写 `\$PATH`）。
- 该镜像仍有 `NPU Triton causal_conv1d_update is unavailable ... stalls ACL graph capture at decode-FULL` 警告，但 capture 仍 2/2 成功、decode 确实走图；GDN conv1d 回退是后续性能项，不是开图阻塞项。
- PR #21176 在 `releases/v0.32.0rc` 上 `git apply --3way` 会被拒（rc 与 main 上下文漂移），按 PR 三处改动手工落地即可，务必留 sha256 前后值与落地 diff。
