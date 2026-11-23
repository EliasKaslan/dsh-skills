---
name: ascend-conda-env
description: "昇腾Python与conda环境建立、激活和解释器错位排障；冷备兼容入口，正文在 ascend-cann-env。"
whenToUse: "新建/激活conda环境、换Python或pip装错位置时；模型目录走 ascend-cann-env。"
disable-model-invocation: true
warm-triggers: "昇腾conda环境 / pip装错位置 / 解释器错位"
warm-reason: "兼容旧名称；同族触发词已由 ascend-cann-env 覆盖，2026-11-23 降为冷备。"
---

# ascend-conda-env

本入口保留旧技能名，作为冷备兼容路由。具体操作见 [昇腾运行栈](../ascend-cann-env/SKILL.md) 的 Python/torch/Triton 参考，不重复加载全部环境文档。解释器、版本、架构、动态库和设备可见范围以本轮实际环境为准。
