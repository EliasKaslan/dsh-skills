---
name: "mindspeed-ops-whl-build"
description: "MindSpeed-Ops wheel构建与独立环境验收。适用于\"打Ops的whl / CMake报错 / 编译器太旧 / SOC怎么选 / 验证wheel\"。不适用：只配置CANN运行环境 → 用 `ascend-cann-env`。"
whenToUse: "处理MindSpeed-Ops wheel构建与独立环境验收时加载；模型看不到本节，触发以description为准。"
---

# MindSpeed-Ops wheel构建与独立环境验收

## 何时调用

**触发**：打Ops的whl / CMake报错 / 编译器太旧 / SOC怎么选 / 验证wheel。

**转交**：只配置CANN运行环境见 [ascend-cann-env](../ascend-cann-env/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

优先读取共享方法的 references/build.md。固定源码/工具链/SOC与ABI，保存构建rc；检查wheel成员/ELF/依赖与来源，在独立环境离开源码树后验收真实调用。SOC变量未设不必然失败，实际自动检测与纯Python产物按目标构建代码核实；不能把zip检查或CPU安装称NPU可用。

完整方法读取 [mindspeed-ops-smoke](../mindspeed-ops-smoke/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。

## 判某 ACLNN 算子是否支持 A5（ascend950/arch35）

## 判某 ACLNN 算子是否支持 A5（ascend950/arch35）

两处都要满足，缺一即"不支持"：

1. `mindspeed_ops/csrc/<op>/op_host/<op>_def.cpp` 的 `this->AICore().AddConfig(...)` 必须含 `ascend950`。
2. `mindspeed_ops/csrc/build_aclnn.sh` 的 `^ascend950` 分支 `CUSTOM_OPS_ARRAY` 必须列出该算子；为空时安装期打印 `no custom ACLNN ops configured; skip build` 并 `exit 0`，A5 产物（`mindspeed_ops/_cann_ops_custom`）里就没有它。

一次性取证：

```bash
git grep -n "AddConfig" <rev> -- 'mindspeed_ops/csrc/*/op_host/*_def.cpp'
git show <rev>:mindspeed_ops/csrc/build_aclnn.sh | sed -n '14,32p'
```

坑：

- `op_host/*_tiling.h` 里的 `SocVersion::ASCEND950` 只是 `CompileInfo` 默认值，不能当支持证据。
- 有目录、有 `api/aclnn/npu_*.py` 不等于已打包：master 用 `triangle_multiplicative_update`（各 stage `_def.cpp` 只声明 `ascend950`）承担 A5，`add_rms_norm_bias` 在 master 仍只有 910b/910_93。
- `pytest.mark.skipif(not hasattr(torch.ops.mindspeed_ops, ...))` 会静默跳过，A5 上"UT 全绿"可能是一个用例都没跑。
