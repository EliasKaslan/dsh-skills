---
name: "dsh-agent-preset-live-verification"
description: "DSH preset 在线验收：从真实请求头取 persona、工具清单与子会话 provider/model，核父 turn/end。"
whenToUse: "已能开会话、要证明 persona/工具/模型路由真生效，或要确认子代理完整跑完时。"
disable-model-invocation: true
warm-triggers: "旧式 preset 的在线会话验收 / 会话日志多帧解压"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dsh-agent-preset-live-verification

## 何时调用

已能开会话时用：证明 persona/工具/路由生效。模式 preset-live；入口[总纲](../dsh-agent-customization/SKILL.md)，取证表[preset-evidence](../dsh-agent-customization/references/preset-evidence.md)。

- 只在隔离 host 用已查 schema 的接口。
- 优先级：请求 header、turn/end.reason.kind > 子会话 config > 模型自述。
- 离线装配归 offline 那份。
