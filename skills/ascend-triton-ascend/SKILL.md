---
name: ascend-triton-ascend
description: "昇腾Triton同名文件覆盖、版本来源与真实kernel验证；冷备兼容入口，正文在 ascend-cann-env。"
whenToUse: "安装、修复或比较triton-ascend版本，或怀疑Python/C扩展混合时；模型目录走 ascend-cann-env。"
disable-model-invocation: true
warm-triggers: "triton-ascend被覆盖 / triton版本来源 / 真实kernel是否生效"
warm-reason: "兼容旧名称；同族触发词已由 ascend-cann-env 覆盖，2026-11-23 降为冷备。"
---

# ascend-triton-ascend

本入口保留旧技能名，作为冷备兼容路由。具体操作见 [昇腾运行栈](../ascend-cann-env/SKILL.md) 的 Python/torch/Triton 参考，不重复加载全部环境文档。解释器、版本、架构、动态库和设备可见范围以本轮实际环境为准。
