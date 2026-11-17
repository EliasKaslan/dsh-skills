---
name: vllm-ascend-source-install
description: 将指定 checkout 的 vLLM 与 vLLM Ascend 从源码配对构建到已有昇腾环境，控制依赖替换、编译器与 BI 算子产物；适用于源码安装、重编和 build dependency 错误。
whenToUse: 将指定 checkout 的 vLLM 与 vLLM Ascend 从源码配对构建到已有昇腾环境，控制依赖替换、编译器与 BI 算子产物；适用于源码安装、重编和 build dependency 错误。
---

# vLLM Ascend 源码配对构建

## 何时调用

**触发**：源码安装/重编 vLLM 或 vLLM Ascend、build dependency 报错、换 commit 后要重建、需要把 BI 算子产物装进指定环境。

**转交**：CANN/Python/torch/Triton 版本缺口 → [ascend-cann-env](../ascend-cann-env/SKILL.md)；引擎启动与 OOM → [ascend-vllm-serve](../ascend-vllm-serve/SKILL.md)；BI 数值验收 → [batch-invariance-acceptance](../batch-invariance-acceptance/SKILL.md)。

**前置**：目标 vllm-ascend checkout、vLLM commit、目标 Python/CANN 已确定。**后继**：交付版本对、构建选项、包变更、局部旁路 diff 与通过范围。

先保留用户指定的分支、commit 与环境；不为套用历史流程自动升级 main、卸包或去 pin。CANN/Python/torch/Triton 缺口用 `ascend-cann-env`，引擎运行用 `ascend-vllm-serve`。

## 配对与构建

1. 保存两仓 HEAD、dirty diff、submodule status、包清单和实际 Python/CANN。选择目标 vllm-ascend checkout 后读取它的 `.github/vllm-main-verified.commit`；文件缺失时按该 release 的配套文档取 vLLM 版本，不强行套 main 文件。该值会漂，记录完整 SHA。用户若明确测试非认证组合，保留选择并标明偏离。
2. 在独立源码目录或合适当前 checkout 内 fetch 确切 ref/SHA，确认最终 HEAD；不 `checkout -f` 覆盖用户修改。短 SHA 需先从权威仓解析为完整对象，fetch 也受服务端是否允许对象请求限制。初始化该 checkout 的子模块并记录 SHA，注意子模块可能来自 GitCode。
3. 读该版本 build-system、requirements、setup/CMake 和 envs。若复用现有 torch，先使用该 checkout 自带的 use_existing_torch.py（存在且行为已审查时），再解其余依赖；vllm empty target、COMPILE_CUSTOM_KERNELS 等选项先核实当前源码支持。
4. 优先用兼容的 constraints 和安装计划保护已有栈。`--no-build-isolation` 只关闭隔离，不等于“不改依赖”或“不验证依赖”。若确需本地绕过 pin，先证明 ABI/运行兼容并只改指定 dependency 区域，保存精确 diff。不能复用原 strip_torch_pins.py：它会扫描整个 TOML，误改 project.dependencies，异常时也无完整事务回滚。
5. 根据目标头文件/工具链确定 GCC/C++ 标准与 ABI，不把“gcc>=9”当所有 C++20 依赖保证。用 CC/CXX 绝对路径指定工具链，必要时按本版本设置 C_COMPILER/CXX_COMPILER；不把另一个 conda env 的 bin 前置导致 pip 装错环境。
6. 换 torch/CANN/编译器后在本任务构建目录重建受影响产物，清理前核对真实路径与归属。`MAX_JOBS` 按共享资源限制。构建日志管道需 `set -o pipefail` 或保存实际 pip 返回码，不能只看 tee 的退出码或“installed successfully”。

arctic-inference 等依赖是否可省须查目标调用链和功能范围，不能因为旧 .188 编译器落后就默认删掉。未解决的硬依赖冲突应隔离或报告，不笼统称为上游噪声。

## 批次不变性构建

仅当任务需要 BI 才核实并启用相应构建/运行选项。记录本轮实际源码分支、下载产物与哈希、pip/vendor 库路径及真实加载结果；源码宣称支持、mtime 新、HAS 标志为真都不足以单独证明目标算子运行了。

旧经验说 build_batch_invariant_ops.sh “没有 set -e”已不成立：2026-11-16 获取的主线第三行是 `set -euo pipefail`。超时值、download 方式、flag 和 fallback 都查当前脚本，只有证实本轮失败点才定向修复；不无条件改 5→300。构建通过后需目标 BI 路径的执行证据与数值验证，使用已有 `batch-invariance-acceptance` 的判据。

## 交付证据

核对目标解释器的包 metadata、模块路径与 editable 指向，确认 `current_platform` 为目标 NPU。扩展需实际 import/调用；find_spec、backend 目录或新 mtime 只作辅证。区分构建 C++ 扩展和 AscendC kernels 各自的编译器/日志，不用一份 CMakeCache 冒充另一套构建证据。

交付版本对、构建选项/编译器、包变更、局部旁路 diff、实际扩展、失败退出码和通过范围；本地依赖旁路不自动进入上游提交。首次真实模型运行另验权重、设备和端到端行为。

来源：`D:/workspace/share/raw/vllm-ascend-source-install/`，审查日 2026-11-16。动态配对依据：[verified commit](https://github.com/vllm-project/vllm-ascend/blob/main/.github/vllm-main-verified.commit)、[依赖](https://github.com/vllm-project/vllm-ascend/blob/main/requirements.txt)。完整审查在 `D:/workspace/share/codex-review/REVIEW.md`。

## main + 商发 26.2.0（CANN 9.2.0）在 A3 x86_64 上的源码构建链

**适用**：把 vllm-ascend **main** 按「昇腾商发 26.2.0 配套」装到 A3（x86_64）已有环境时。
**不适用**：release 分支或 aarch64 机器（fla_npu 来源不同，未验证）。

### 版本口径

`.github/vllm-main-verified.commit` 给 vLLM commit（本例 `ba15685a…`）；**商发 26.2.0 = CANN 9.2.0 /
torch_npu 2.10.0.post7 / triton-ascend 3.6.0**（依据：`atlas-release/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-a3-…` 镜像标签
与 MindSpeed-Ops 门禁 PR 文案）。main 的 README 写 CANN==9.2.1，实测 9.2.0 **无运行时版本闸门**可跑；
这是对"官方认证组合"的偏离，交付报告里必须单列。基础镜像直接用上面这个 26.2.0 镜像最省事
（CANN、torch、torch_npu、triton 都已就位，避免在纯 `cann:9.2.0` 镜像里再找 cp312 轮子）。

### 构建顺序（实测）

```bash
# 1) vLLM：只取配对的单个 commit，不 --depth 1 拉全历史
git clone --filter=blob:none --no-checkout https://github.com/vllm-project/vllm.git vllm
cd vllm && git fetch --depth 1 origin <verified-commit> && git checkout FETCH_HEAD
pip install setuptools_rust setuptools_scm cmake ninja   # 否则 setup.py 直接报下面的错
VLLM_TARGET_DEVICE=empty pip install -e . --no-build-isolation

# 2) vllm-ascend：先只编 _C，再用官方脚本单独装 BI 算子
cd ../vllm-ascend && git checkout <main-commit>
COMPILE_CUSTOM_KERNELS=0 pip install -e . --no-build-isolation --no-deps
pip install transformers==5.19.0 fastokens memfabric-hybrid==1.3.0 memcache-hybrid==1.3.0
bash csrc/build_batch_invariant_ops.sh ascend910_93     # A3；A2 用 ascend910b，950 用 ascend950
```

BI 脚本会：装 OBS 的 `cann-ops-batch_invariant-<A3|910b|950>-2.0.0-linux.<arch>.run` 到
`$ASCEND_HOME_PATH/opp/vendors/batch_invariant`，再编译 `batch_invariant_ops` wheel（本例 1.0.0）。
自检必须同时为真：

```python
torch.ops.batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant.overloads()  # ['default','out']
hasattr(batch_invariant_ops, "_npu_fused_infer_attention_score_batch_invariant_get_max_workspace")  # True
```

### 坑（都带原文）

- 不带 `--no-build-isolation` 也不会自动有 `setuptools_rust`；`--no-build-isolation` 时 setup.py 直接
  `ModuleNotFoundError: No module named 'setuptools_rust'`（vLLM 侧）。
- **不要在 `vllm/` 源码目录下启动 python**：cwd 的 `vllm/` 目录会被当作 namespace 包，
  报 `ImportError: cannot import name 'ModelRegistry' from 'vllm' (unknown location)`；从 `run/` 之类中性目录启动。
- `vllm_ascend/ops/gdn.py` 在 import 期硬依赖 `fla_npu`，但 requirements 不声明它，缺了直接
  `ModuleNotFoundError: No module named 'fla_npu'`。A3 预编译 fla wheel（`/mnt/share/fla-npu-a3-whl-26.9.0`）只有
  **aarch64**；x86_64 源码 wheel（26.6/26.7.dev）缺 main 需要的 `causal_conv1d_fn / causal_conv1d_update`
  （`ImportError: cannot import name 'chunk_gated_delta_rule' …` / 只有 `causal_conv1d`、`npu_causal_conv1d`）。
  x86_64 的做法：从官方 `quay.io/ascend/vllm-ascend:nightly-main-a3-openeuler` 镜像
  `docker cp` 出 `flash_linear_attention_npu_a3 26.9.1`（含 `opp/` vendor 与 `fla_npu_opp_env.pth`）到目标 site-packages。
- requirements 钉 `triton-ascend===3.6.0.post2`，公网/华为云镜像只有 `3.6.0`：
  `ERROR: Could not find a version that satisfies the requirement triton-ascend==3.6.0.post2 (from versions: none)`；
  镜像内自带 3.6.0 可直接用，别为 `.post2` 卡住。
- pip 下载大包（torch/torch-npu 的 JSON 索引）在容器内可能超时，用 `repo.huaweicloud.com` 镜像（镜像内已配）比 pypi 稳。
