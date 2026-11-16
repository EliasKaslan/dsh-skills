---
name: ascend-cann-env
description: 在昇腾 Linux 上搭建或诊断 CANN、conda/Python、torch_npu、triton-ascend 的兼容栈；适用于版本配对、动态库/ABI 错误、解释器错位和 Triton 被覆盖，不负责 vLLM 源码构建。
whenToUse: 在昇腾 Linux 上搭建或诊断 CANN、conda/Python、torch_npu、triton-ascend 的兼容栈；适用于版本配对、动态库/ABI 错误、解释器错位和 Triton 被覆盖，不负责 vLLM 源码构建。
---

# 昇腾运行环境栈

从目标代码和机器约束求兼容组合，保留用户指定的版本。已有工作环境先取证复用；需试新组合则在新前缀验证。旧材料的 A/B 车道、True 16 253、Python 3.12、CANN 9.1 只属于历史案例。

## 先确定组合

记录主机、CPU 架构、OS/glibc、driver/firmware、目标源码 SHA、CANN 实际 source 路径、Python ABI/wheel tag、torch/torch_npu、triton/triton-ascend、编译器与 C++ ABI。选定目标 checkout 后检查 requirements/pyproject 和官方版本矩阵；包在索引可下载、官方支持配套、真机冒烟通过是三种结论。

按缺口读取：

- CANN 安装、组件和动态库：[references/cann.md](references/cann.md)。
- 解释器、依赖、共享 Triton 树：[references/python-torch-triton.md](references/python-torch-triton.md)。

## 分层验收

1. 驱动：`npu-smi info` 的设备、健康与预期可见范围一致。
2. CANN：在当前 shell 显式 source 后，检查真实环境路径、`import acl` 和设备型号；仅目录存在或 `/etc/Ascend` 安装记录不能证明当前进程使用它。
3. torch：在已准入空闲设备上，用目标解释器 import torch/torch_npu，记录版本、路径、available/count/name，跑小张量并同步、核对结果。count 受设备映射影响，不固定为 16，soc API 也按当前版本核查。
4. Triton：同时记录 distribution metadata、`triton.__file__`/版本、C 扩展和 backend 来源，实际编译运行小 kernel；目录和 dist-info 存在不足以通过。

每层失败就定位该层，不用重装整栈。单个加法通过不证明所有算子、性能或数值一致性。包冲突逐项判定：区分 CANN 的 PYTHONPATH 注入包与环境真实依赖，不能笼统忽略 `pip check`。检查所需任务是否触及冲突，再决定修复、隔离或明确记录限制。

沉淀依据：原 ascend-env、ascend-cann-env、ascend-conda-env、ascend-torch-npu、ascend-triton-ascend；2026-11-16 快照及本轮取舍见 `D:/workspace/share/codex-review/REVIEW.md`。源码构建转 `vllm-ascend-source-install`，数值一致性任务使用已有 `batch-invariance-acceptance`。
