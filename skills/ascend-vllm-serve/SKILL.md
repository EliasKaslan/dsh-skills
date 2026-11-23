---
name: ascend-vllm-serve
description: 在已安装的昇腾 vLLM 环境中做离线推理、启动 OpenAI 服务及定位 OOM/初始化失败，并验证 sleep、唤醒与权重更新；不负责源码安装或训练数值一致性适配。
whenToUse: 在已安装的昇腾 vLLM 环境中做离线推理、启动 OpenAI 服务及定位 OOM/初始化失败，并验证 sleep、唤醒与权重更新；不负责源码安装或训练数值一致性适配。
---

# 昇腾 vLLM 运行与生命周期

先核实实际 Python、两仓 SHA/包路径、CANN source、目标权重版本和 NPU 平台。保留用户已有启动方式；环境未过分层验收时定位环境，不急着运行大模型。源码构建用 `vllm-ascend-source-install`。

## 最小复现到实际服务

- 用 `ascend-server-layout` 的工具核实完整权重与存储 dtype，再检查目标架构 registry、Ascend patch、并行/量化后端。registry 有名只证明注册，不能保证目标硬件组合可跑。
- 选已准入且当前无人使用的物理卡，在 import 前设置 ASCEND_RT_VISIBLE_DEVICES，记录 logical 映射；不通过初始化所有 NPU 来挑剩余 HBM 最大的卡。TP/EP 的几何、权重/KV/通信/graph 峰值先预算，用户目标超资源时明确缺口。
- 审查 env 脚本的隐藏开关。普通服务不从历史环境无意继承 BI；用户需要 BI 时保留并核实实际路径。不要继承已不存在的 VLLM_USE_V1 等变量，也不在技能里指定永久禁用名单。
- 用目标版本 `vllm serve --help` 和实际源码确认参数。诊断场景可用短上下文、少并发、eager、真实小模型或减层包，明确其覆盖限制；用户验收仍回到原模型、图模式、并行和上下文。dummy 只验机制，不能验真实权重质量。
- 离线生成先覆盖引擎/算子，再按需求启动 HTTP。诊断服务默认 bind 127.0.0.1，记录本任务 PID、唯一端口和日志，轮询 readiness 并设置截止时间。端口瞬时空闲不保证 launch 时无竞争。
- HTTP 验模型名、响应结构、非空输出及 finish_reason。思考型模型 token 截断可有 reasoning 而无最终答案：区分服务可用、任务完成和质量，不用固定 max_tokens=1000 或非空文本替代任务正确性。吞吐只在实际相同设置下比较。

OOM 应分权重、KV、激活/通信、非 torch 和图池；`gpu_memory_utilization` 预留空间并不等于让多个任务共享别人的卡。定位时保存首个底层异常，缺 GLIBCXX/acl、Triton 失配、权重 LFS 指针与 NPU fork 初始化分开处理。需要 spawn 时在子进程启动前配置并使用 main guard。

## Sleep 与更新

仅在任务涉及此能力时读 [references/sleep-and-update.md](references/sleep-and-update.md)。生产服务不得因技能调用自动暴露 dev 管理端点。数值一致性、梯度或真实训练更新任务用已有 `batch-invariance-acceptance`。

## 收尾与证据

一次性冒烟结束或失败时，按已记录 PID/进程组只停止本任务；如果用户要求持续服务，保持运行并交付端口、PID、日志和停止方式。用端口释放、本任务 worker 消失、目标 HBM 回落共同复查，不能盲目 pkill/reset/prune。HBM 未回落说明还需定位，不等于有权重置设备。

来源：原 ascend-vllm-serve 与关联 layout/env，沉淀日 2026-11-16；具体模型大小、toks/s 与历史环境不作为新任务默认值。审查见 `D:/workspace/share/codex-review/REVIEW.md`。

## 日志行号指纹与"看起来卡住"的判定

vLLM 日志前缀 `[文件名:行号]` 的行号是 `logger.xxx(` 的**调用行**（多行调用取首行，Python 3.12 实测），可直接反推版本：`entrypoints/chat_utils.py:397`≈v0.8.5、`:470`≈v0.10.1；`renderers/hf.py:548`≈v0.23–v0.29、`:648`≈v0.32、`:736`≈v0.33.0、`:743`≈v0.34。报出某行先去该 tag 的 raw 源码核对调用行，再谈阶段。

`Detected the chat template content format to be 'string'. You can set --chat-template-content-format to override this` 是**良性 info_once**，不是错误：`resolve_chat_template_content_format()` 解析 Jinja AST，模板把 `message.content` 当纯字符串（而非 OpenAI 多段 list）即判 `string`，只影响 chat 接口多段/多模态 content 的解析；文本 prompt 或脚本自己用 HF tokenizer 渲染时结果无关。

位置才是判据：v0.33.0 由 `LLM.__init__` 末尾 `renderer.warmup()` 渲染一条 dummy chat 触发，此时引擎已 READY——权重加载、显存 profile、KV cache、`compile_or_warm_up_model`/图捕获全部完成。所以"停在这行之后长时间无输出"**不是**加载卡住，而是首个请求阶段。别用"最后一行日志"定位阶段，先看它是否出现在三行之后（权重耗时、KV cache 大小、init engine took）。

静默常由脚本造成：离线脚本同时传 `disable_log_stats=True` 与 `generate(..., use_tqdm=False)` 时整轮零输出，只在轮次结束打印。判定顺序：`npu-smi info` 看 HBM 与 aicore（持续 0% 才是疑似死等）、`py-spy dump --pid <pid>` 看栈（`VLLM_ENABLE_V1_MULTIPROCESSING=0` 时单进程）、`ASCEND_PROCESS_LOG_PATH` 下 plog 看设备侧真错、输出目录文件 mtime 是否推进。HCCL 建链失败会静默等到 `HCCL_CONNECT_TIMEOUT`（脚本常设 1200s）才报错，多网卡机器要显式指定 `HCCL_SOCKET_IFNAME`。
