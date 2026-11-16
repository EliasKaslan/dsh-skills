---
name: vllm-ascend-source-install
description: 将指定 checkout 的 vLLM 与 vLLM Ascend 从源码配对构建到已有昇腾环境，控制依赖替换、编译器与 BI 算子产物；适用于源码安装、重编和 build dependency 错误。
whenToUse: 将指定 checkout 的 vLLM 与 vLLM Ascend 从源码配对构建到已有昇腾环境，控制依赖替换、编译器与 BI 算子产物；适用于源码安装、重编和 build dependency 错误。
---

# vLLM Ascend 源码配对构建

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
