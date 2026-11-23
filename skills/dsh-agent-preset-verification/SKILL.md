---
name: "dsh-agent-preset-verification"
description: "DSH preset/overlay 离线核查：声明行是否进组合树、Config 语义与工具策略；不取会话证据。"
whenToUse: "改完 preset 声明行要判断装配结果，或要核 Config 未知键与语义时。"
disable-model-invocation: true
warm-triggers: "旧式 .agent-presets 目录的离线校验"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dsh-agent-preset-verification

## 何时调用

只查磁盘用。模式 preset-offline；入口[总纲](../dsh-agent-customization/SKILL.md)，取证表[preset-evidence](../dsh-agent-customization/references/preset-evidence.md)。

- 记 base→bundle→patch→最终 row 的 id/来源/enabled/配置，止于源码行。
- `.agent-presets/` 已不被读，目录不是装配证据。
- `Config` 类型校验 ≠ `resolveConfig` 语义校验；会话行为转 live 那份。
