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
