---
name: ascend-cann-env
description: 在昇腾 Linux 上搭建或诊断 CANN、conda/Python、torch_npu、triton-ascend 的兼容栈；适用于版本配对、动态库/ABI 错误、解释器错位和 Triton 被覆盖，不负责 vLLM 源码构建。
whenToUse: 在昇腾 Linux 上搭建或诊断 CANN、conda/Python、torch_npu、triton-ascend 的兼容栈；适用于版本配对、动态库/ABI 错误、解释器错位和 Triton 被覆盖，不负责 vLLM 源码构建。
---

# 昇腾运行环境栈

从目标代码和机器约束求兼容组合，保留用户指定的版本。已有工作环境先取证复用；需试新组合则在新前缀验证。旧材料的 A/B 车道与旧版本组合只属于历史案例。

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

## A5/aarch64 个人目录自建「商发 26.2.0 配套」栈

**触发**：目标机只装了 driver（`/usr/local/Ascend` 下没有 toolkit），要在个人/NFS 目录自建一套多 agent 可复用的运行栈。
**实测**：2026-11-20，一台 A5（openEuler 24.03 LTS-SP3，aarch64，8×Ascend950DT 96GB，driver `26.2.0.b020`）。

商发 26.2.0 配套 = **CANN 9.2.0 + torch 2.10.0 + torch_npu 2.10.0.post7 + triton-ascend 3.6.0 + Python 3.12 + numpy 1.26.4**
（依据官方 950 底座镜像名 `mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-950-…-py3.12`，不是推测）。
用户指定「26.2.0 配套」时**不要**被 vllm-ascend README 的 `CANN == 9.2.1` 带跑，偏离要单列。

- 完整命令、run 包位置、activate.sh 模板与验收脚本见 [references/a5-2620-stack.md](references/a5-2620-stack.md)。
- 目录约定：`<根>/env/{cann-9.2.0,py312,wheels,activate.sh}` + `<根>/{src,run,logs,cache,tmp}`。

### 坑（都带原文）

- `conda create -p ... python=3.12` 直接死在
  `CondaToSNonInteractiveError: Terms of Service have not been accepted ... repo.anaconda.com/pkgs/main`
  → 加 `--override-channels -c conda-forge`；不要去 accept ToS。
- `set -u` 下 source nnal 会炸：`nnal/atb/set_env.sh: line 43: ZSH_VERSION: unbound variable`
  → 在 activate.sh 里保存 `$-`、`set +u` 包住 source、再恢复。
- 公网 pypi 镜像速度差一个数量级：`mirrors.aliyun.com` 拉 146MB 的 torch 停在 52 kB/s，
  `repo.huaweicloud.com/repository/pypi/simple` 同包 20 秒级。索引必须**命令行显式** `-i` + `--trusted-host`；
  `~/.config/pip/pip.conf` 的 `[install] trusted-host` 会盖掉 `[global]`，http 索引被静默忽略后只会看到
  `ERROR: No matching distribution found`。同一 venv 一次只允许一个 pip（并发会互相抢带宽并且互相破坏）。
- 公网 pypi 的 `triton-ascend` 只有 3.2.0（仅 cp39/310/311），**没有 cp312 的 3.6.x**
  → 用共享盘预编译 wheel 并按 driver 代次挑（b020 ↔ dev20261029，b030 ↔ dev20261111），
  `pip install --force-reinstall --no-deps <whl>`，再核 `triton.__file__` 落在本环境 site-packages。
- 装完 vLLM 这类上层会把 `numpy` 顶到 2.x，而 triton_ascend 的 METADATA 钉 `numpy==1.26.4`
  → 回钉并重跑 `import triton` + 真机张量。
- 别用「`opp/vendors/` 有没有东西」判断 950-ops 装没装：9.2.0 的 vendors 是**空的**，
  950 算子在 `opp/built-in/op_impl/ai_core/tbe/kernel/ascend950/`。`lib64` 是软链，查库要 `find -L`。
- `import aclnn` 不存在（`ModuleNotFoundError`）：9.2.0 的 aclnn 是对外 C 库 `libopapi*.so`，没有 Python 模块。
