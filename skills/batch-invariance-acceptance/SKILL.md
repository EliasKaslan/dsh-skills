---
name: "batch-invariance-acceptance"
description: "昇腾批次不变性与训推数值一致性适配、定位、验证。适用于\"验批次不变性 / 训推logprob对不上 / prefill和decode不同 / 梯度怎么验证 / 更新后不同步\"。不适用：仅启动推理服务→ascend-vllm-serve。"
whenToUse: "处理昇腾批次不变性与训推数值一致性适配、定位、验证及知识归档时加载；模型看不到本节，触发以description为准。"
---

# 昇腾训推一致性

## 何时调用

**触发**：验模型批次不变性 / 训推logprob对不上 / prefill和decode不同 / 梯度怎么验证 / 更新后不同步。

**转交**：仅启动推理服务见 [ascend-vllm-serve](../ascend-vllm-serve/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

把“训推不同”转成可复现、可归因、可验证的数值问题。保留用户指定的模型、框架、精度、并行策略和任务边界；从已有源码、resolved config 与失败证据开始，选择当前最有区分力、成本最低的实验。可以从中途定位或已有回执复核进入，不要求每次从环境搭建重跑整条链路。

## 不可混淆的判据

- 比较对象必须是同一有效策略、相同 token 历史、位置、mask 和评分语义。先区分 raw logprob 与经温度、penalty、top-k/top-p 处理后的 logprob；不能把概率差、KL 或 token 相同称为 logpdiff=0。
- bitwise 目标比较原始 dtype 的位模式及非空有效 token；NaN/Inf、缺 rank、未命中目标分支和空 mask 不能通过。不能降精度、取整、调宽阈值、屏蔽失败 token 或复制另一侧结果制造通过。误差预算任务按事先约定的指标单独验收。
- 推理自身 BI/PD、训练自身重复性、跨框架前向、独立梯度验证、真实更新/同步、质量和性能是不同结论。只完成其中一项时，其他项注明未覆盖。
- PyTorch/torch_npu 的 NPU 开发与验证进程显式调用 `torch_npu.npu.set_deterministic_level(3)`，包括各 rank、推理 worker 和新建子进程；用当前版本真实的查询接口核对实际等级。不因上游案例或性能原因悄悄降级。非 torch_npu 后端核对其原生确定性机制，不能用另一个进程设置 torch_npu 冒充本后端保证；若任务强制要求该 API 而后端不支持，明确说明兼容性缺口。
- 证据绑定实际执行的源码、算子产物、配置、权重与状态。换了候选实现就重跑受影响的比较，历史 PASS 不自动继承。
- 遵守本轮授权的设备、工作目录和时间窗口。大模型实验前估算训推共存、offload、workspace 和同步峰值；只清理本任务资源。旧案例的设备、账号、窗口不构成新授权。

## 按证据选择入口

| 现象 | 优先区分什么 | 可选材料 |
|---|---|---|
| 同侧相同输入重复也不同 | 状态/RNG、异步错误、实际算子、归约/编译路径 | [运行时与生命周期](references/runtime-and-updates.md) |
| 单独相同、混批/换位置不同 | 调度、packing、通信选择、行数/tiling、上下文游标 | [实验设计](references/validation-design.md)、[算子方法](references/numerical-methods.md) |
| decode 与 prefill 不同 | position/mask、KV 精度和布局、chunk/page 边界、状态更新 | [算子方法](references/numerical-methods.md) |
| 两侧分别稳定，交叉不同 | 参数/模型语义、cast/归约顺序、离散选择、scorer | [算子方法](references/numerical-methods.md) |
| old-logprob 相同，真实训练前向不同 | grad/train 分支、重计算、分片与训练专用算子 | [实验设计](references/validation-design.md) |
| logits 相同，logprob 不同 | 实际 scorer、词表分片归约、温度与处理顺序 | [算子方法](references/numerical-methods.md) |
| 首次相同，更新或 sleep/reload 后不同 | master→导出→接收→派生权重、版本/别名/cache/Graph | [运行时与生命周期](references/runtime-and-updates.md) |
| 新模型含类似结构或症状 | 检索带适用条件的历史案例，再验证本轮假设 | [知识索引](knowledge/index.md) |

这些是选路提示，不是根因判定或固定执行顺序。资源错误与数值差异分开记录；受污染设备上下文中的数值证据不可信。原场景失败而缩小场景通过时，先确认是否丢掉触发条件。

复用旧 DSH 验收脚本、用减层模型外推，或设计关闭 BI 的负控时，按需读 [旧验收方法的补充核查](references/dsh-acceptance-lessons.md)，避免请求漏项、空集通过、符号零和同构外推造成的假证据。

## 开发时保留的最小信息

维护一份可更新的任务契约：本轮目标与覆盖范围、实际运行环境、评分语义、有效权重版本、主要并行/状态路径、资源限制、性能/质量要求。先从现有资料恢复信息，只询问无法恢复且确实影响选择的缺项；不为参考资料中的固定审批点再增加确认流程。

给修改明确归属：现有实现复用、框架 glue、数值契约适配、真正新增的前向/反向 kernel。优先保持原生训练入口与参数容器，复用相同 forward primitive；共享 kernel 后仍核对 caller 的 dtype、布局、metadata、compile boundary 和状态。新增 backward/STE 必须写明数学契约并独立验证，不能用 forward=0 或“梯度有限非零”代替梯度正确性。

每轮只保存与待检假设有关的最小 trace；先层边界，再模块边界，最后在完全相同算子输入上复现首个差异。修复后回到原失败用例和受影响矩阵。最终结论来自交付实现实际执行的路径，不能用诊断替代路径的结果代替。

## 文档与知识沉淀

实现过程中持续写修改文档，重点说明算子：差异证据、修改前后公式及舍入点、dtype/shape/stride/ABI、前后向与保存状态、源码位置/指纹、原失败用例复测、耗时和未覆盖范围。完整原始数据留在任务目录，报告区分 PASS、FAIL、INVALID/INCONCLUSIVE、NOT RUN，不将 skip 当成通过。

适配结束或形成可复用结论后，按 [knowledge/index.md 的维护约定](knowledge/index.md) 和 [案例模板](knowledge/case-template.md) 更新 `knowledge/`。已通过的案例写清通过范围；失败尝试和待验证假设保留各自状态。不要把案例参数提升为通用开关，也不要写入凭据、大权重或全量 dump。

本 skill 提供方法，不依赖特定训练框架、推理框架、芯片代际或外部状态机。参考来源、借鉴范围与未继承的约束见 [sources.md](references/sources.md)。

## 旧脚本入口

原4份BI脚本已在同路径改为失效退出，避免被历史调用静默判PASS。读取 [脚本状态](references/legacy-tool-status.md)；实际实验按本入口的方法编写和验证当前任务工具，不能把失效退出当数值不通过或自动尝试旧副本。

## 需求验收报告怎么写：五段骨架、被测树口径与配对检验

## 需求验收报告怎么写：五段骨架、被测树口径与配对检验

**适用**：要给上游/客户交一份「需求验收报告」（功能支持 + 性能 + 精度三段），尤其是 BI + 整图这类特性验收。
**不适用**：只想内部记一笔验证结论 → 直接写运行目录里的 `*_report.md` 就够，不必套正式骨架。

### 骨架（按需裁剪，但这五段别少）

1. `# 需求描述`：背景、需求详细表（模型/序列/精度/数据集/卡数/质量目标）、验收标准与本轮结论对照表。
   需求模板里的模型名与实际被测模型不一致时，加一句「模型口径」说明，别让评审自己去猜。
2. `# 环境配套`：固定五列 `| 配套软件 | 配套版本 | 链接 |`，行必须覆盖 **CANN / pta(torch_npu) / ta(triton-ascend) / vllm(commit) / vllm-ascend(commit)**；
   表下补运行镜像、算子包、硬件、Python。
3. `# 测试脚本`：引擎配置代码块（两模式唯一差异要显式写出）、脚本清单表（用途/脚本/关键点）、可直接复制的复现命令、原始产物目录。
4. `# 性能验收`：测量方法（如何剔除 prefill/加载）、结果表（基线 vs 目标 + 倍数）、**图真在跑的证据**、A/B 因果、扩展项。
5. `# 精度验收`：数据集与采样参数、结果表、配对检验表、说明与边界。

### 三条硬纪律（写报告前先做，做不了就降级措辞）

1. **先锁被测树，再决定报告里写哪个 commit**。顺序：
   `get_pull_request` 看 `merged_at` / `merge_commit_sha` → 取目标分支 HEAD（`list_commits` perPage=1）→
   在**该 HEAD** 上直接 `get_file_contents` 或 `search_code` 确认关键改动在位（例如 `batch_invariant.py` 的 workspace 重绑、
   `gdn_attn_builder.py` 的 `supports_batch_invariance`）。
   若实测是在合入前的树上叠加 PR head 完成的，报告里必须加「版本口径」脚注：写清实测树 + 合入后 main 的等价性核验，
   **不许把没跑过的 main 写成"已跑"**。
2. **版本从运行容器里取**，不抄镜像名、不靠记忆：CANN 看 `ASCEND_HOME_PATH`，pta/ta/vllm 走 `python -c import` + `pip show`，
   commit 走 `pip show` 的版本后缀或 git。
3. **性能和精度都要"带牙"的证据**，不能只给结论：
   - 性能：`Capturing CUDA graphs (...) N/N`、`Graph capturing finished ...` 日志行 + `NPUGraph.replay`/步 +
     该被换实现的算子 eager 调用/步（基线对照必须明显不同）；
   - 精度：同一批样本两模式**配对**——不一致对 b/c、McNemar 精确检验、配对 t 与 95% CI、逐字节文本一致数 + 文件 sha256。

### 常见坑

- **只写"分数一样"不够**：要区分"都答对了"与"都没答出来"。`max_tokens` 太小导致大面积截断时，两侧同分只是同样的截断，
  报告里必须点明截断条数、并说明为何该对比仍然有效（同配置、同截断位置），同时声明绝对分数不代表模型能力。
- **sha256 别手抄**：64 位十六进制手抄必错，写前缀 + 给出可复核命令，或直接从文件取值粘贴。
- **性能数字同机波动**：同机其他租户任务会造成 5% 级抖动，报告里注明测量重复次数与波动范围，别把单次数字写成规格。
- **别把"能开图"写成"性能达标"**：功能（capture 成功）、性能（收益/无劣化）、精度（配对无差异）是三个独立判据，分开写、分开给证据。

未验证：本骨架按「特性验收（BI + 整图）」整理，是否直接适用于纯性能需求或纯功能需求的交付评审，未验证。

## 用 vllm bench 做 BI+整图性能验收 + 同模式对照与分数级判据

## 用 `vllm bench` 做「BI + 整图」性能验收 + 同模式对照

**适用**：需求只要求"跑 vllm bench 看吞吐提升"，或手里出现"图模式与 eager 生成文本不一致"想下结论时。

### 最小配方：两模式只差一行 CLI

`vllm bench throughput` 吃通用 engine 参数，但**没有** `--cudagraph-mode` 这个 flag，必须走 JSON：

```bash
# 基线（不图）
--enforce-eager --compilation-config {"cudagraph_mode":"NONE"}
# 整图
--no-enforce-eager --compilation-config {"cudagraph_mode":"FULL_DECODE_ONLY","decode_cudagraph_capture_request_sizes":[1,8]}
```

共同部分：固定 `--seed`、`--max-model-len`、`--max-num-seqs`、`--gpu-memory-utilization`、`--input-len/--output-len`；
环境必须带 `VLLM_BATCH_INVARIANT=1`、`VLLM_WORKER_MULTIPROC_METHOD=spawn`、`VLLM_ENABLE_V1_MULTIPROCESSING=0`。
检查 `vllm bench throughput --help=<flag>` 可逐项确认参数名（`--help` 分组输出里能看到 `--compilation-config`）。

### 指标口径：别把 decode-only 倍数写成端到端倍数

`vllm bench` 的 elapsed **包含 prefill**，所以同一 shape 下端到端吞吐的提升通常只有 1.x 倍，
而 decode-only 速率（用 `max_tokens=1` 与 `max_tokens=N` 的差值量）可以到 5~6 倍。报告里必须写清用的是哪个指标，
两者不能互换。判据：整图组出现 `Capturing CUDA graphs (FULL): N/N` + `Graph capturing finished`，基线组不得出现；两组各跑两次看抖动。

### 同模式对照：判断"图 vs eager 文本不一致"的唯一可靠办法

某些模型上 `temperature=0` 的整图与 eager 逐样本文本会大面积不同，但评分类似。**先别下"图模式改了数值"或"脚本有问题"的结论**，
先做同模式重复对照：同一模式连跑两次（独立进程、独立 die、同一批题、同 seed）。

| 对照结果 | 结论 |
|---|---|
| 同模式两次逐样本 100% 相同 | 脚本/采样是确定性的 ⇒ **跨模式差异真实存在**，可写进报告 |
| 同模式两次也不同 | 先修 harness（seed、采样参数、请求顺序、并行 die 干扰），别急着归因 |

归因方向（**未验证**）：整图路径的 FIA 走 `.out` 重载（`attention_v1.py` 用 `register_task(torch_npu.npu_fused_infer_attention_score.out, ...)`），
eager 走默认重载，两者 workspace / 内存布局不同 ⇒ 微小数值差，被 `temperature=0` 的贪心解码放大成不同 token；
MoE / MoE-comm 侧是否也有份未取证。纯全注意力（GQA）模型比混合 GDN 模型更容易暴露这种差异。

### 报告口径（两条不能混）

- 验收判据是**分数级**：同一批样本两模式配对，看不一致对 + McNemar 精确检验 + 配对 t/CI。p 大 ⇒ 无显著差异 ⇒ 无劣化。
- "图模式与 eager 逐位一致"是**另一条独立要求**。用"分数没差"去暗示"数值逐位一致"是错误写法；
  反过来，文本不同也不能直接判验收失败，除非需求明确要求逐位。

## MRv2 下开 FULL_DECODE_ONLY：capture 参数与「图在跑」的取证口径

**适用**：vllm-ascend main（vLLM 0.33 / model runner V2）上验收「BI + FULL_DECODE_ONLY 整图」，需要给出
capture 成功、图确实在跑、性能不劣化三类证据时。**不适用**：V0/V1 runner 或 release 分支（口径不同，未验证）。

### 1. `cudagraph_capture_sizes` 在 MRv2 已改名改义，照旧写会出「假无收益」

MRv2 把抓图预算拆成 prefill token 与 decode request 两类，旧的 `compilation_config.cudagraph_capture_sizes`
被解释为 **prefill token** 尺寸。写 `{"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,8]}` 仍然会打印

```text
Capturing CUDA graphs (FULL): 100%|##########| 2/2
Graph capturing finished in 1 secs, took 1.93 GiB
```

但抓到的是 2 个 8-token 的 prefill 图，**decode 全部退回 eager**，表现就是「开了图和没开图吞吐一模一样」。
正确写法：

```python
compilation_config={"cudagraph_mode": "FULL_DECODE_ONLY",
                    "decode_cudagraph_capture_request_sizes": [1, 8],
                    "cudagraph_mm_encoder": False}
```

引擎日志可见 `decode_cudagraph_capture_request_sizes=[1, 8]  max_decode_cudagraph_capture_requests=8`。
另有 `prefill_cudagraph_capture_token_sizes` / `max_decode_cudagraph_capture_requests` 两个新键，按模式选。

### 2. 「图在跑」的取证：TP>1 时进程内 hook 全部失效

- `NPUGraph.replay`、`torch_npu.npu_fused_infer_attention_score` 的 hook 只在**模型与解释器同进程**（TP=1）时有效；
  TP=4 时模型跑在 `VLLM::Worker_TP*` 子进程，父进程计数恒为 0（实测 replay/step=0、fia/step=0，eager 腿也是 0）。
- 可靠办法：`LLM(..., cudagraph_metrics=True)`（这是 EngineArgs 字段；传 `observability_config={...}` 会
  `TypeError: EngineArgs.__init__() got an unexpected keyword argument 'observability_config'`）。
  引擎按日志周期打印：

```text
| Unpadded Tokens | Padded Tokens | Num Paddings | Runtime Mode | Count |
| 8               | 8             | 0            | FULL         | 122   |
| 1               | 1             | 0            | FULL         | 89    |
```

  decode 行为 `FULL` 才算图在跑；同脚本 `enforce_eager=True` 时该列必须是 `NONE`（基线对照）。
- 备选：同进程 hook `vllm.v1.worker.gpu.cudagraph_utils.CudaGraphManager.run_fullgraph`。

### 3. A/B 因果：没有 BI 版 workspace 查询就一定 capture 失败

用 `sitecustomize.py` 只改一件事（BI 启用后把 `torch_npu._npu_fused_infer_attention_score_get_max_workspace`
换回非 BI 版本，模拟旧 `batch_invariant_ops`），其余不变，capture 立即失败：

```text
RuntimeError: capture_end:../torch_npu/csrc/core/npu/NPUGraph.cpp:238 NPU function error:
c10_npu::acl::AclmdlRICaptureEnd(capture_stream_, &model_ri), error code is 107033
Invalid_Argument_API_Call_Sequence(EE1018): Stream end capture failed. Reason: A task group
in the model (model_id=49) has been started but not ended.
current working operator name is aclnnFusedInferAttentionScoreBatchInvariantV3
```

一行同时证明两件事：图里跑的是 **BI FIA 算子**（`aclnnFusedInferAttentionScoreBatchInvariantV3`），
且「BI workspace 查询 + `.out` 注册」是 capture 成功的前提。shim 要注意 `PYTHONPATH=<shim 目录>:$PYTHONPATH`，
**不能覆盖** PYTHONPATH——CANN 的 `acl` 模块靠它注入，覆盖后 worker 直接 `ModuleNotFoundError: No module named 'acl'`。

### 4. 共享机纪律

图 vs 不图的 A/B 必须**同一组空闲 die 连续完成**。另一租户中途占同一组 NPU 时，会得到 ~5× 的假劣化
（实测 BS=8 从 ~100 掉到 ~21 tok/s），随后初始化直接 `Free memory on device (4.88/61.27 GiB) on startup is less than
desired GPU memory utilization`。测量前后都核对 `npu-smi` 进程表与进程启动时间，发现他人进程就把该批数据作废、换 die 重测。
