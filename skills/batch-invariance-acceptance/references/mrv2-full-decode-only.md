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
