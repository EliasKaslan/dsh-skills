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
