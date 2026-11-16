---
name: "node-test-false-green-audit"
description: "Node测试与CI假绿、漏跑和断言有效性审查。适用于\"CI绿了却没跑 / 测试数对不上 / cancelled算过吗 / 这条断言会红吗 / 字段改名还绿\"。不适用：PowerShell参数编码故障 → 用 `pwsh-on-windows`。"
whenToUse: "处理Node测试与CI假绿、漏跑和断言有效性审查时加载；模型看不到本节，触发以description为准。"
disable-model-invocation: true
warm-triggers: "CI 绿了但没跑 / 测试数不对 / 变异测试怎么验"
warm-reason: "低频方法论"
---

# Node测试与CI假绿、漏跑和断言有效性审查

## 何时调用

**触发**：CI绿了却没跑 / 测试数对不上 / cancelled算过吗 / 这条断言会红吗 / 字段改名还绿。

**转交**：PowerShell参数编码故障见 [pwsh-on-windows](../pwsh-on-windows/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

使用共享方法的测试发现、执行和变异章节；固定Node版本、CI命令、glob/selector、case和cancelled计数。在实际版本验证unref、fetch/header与平台行为，不套永久结论。先证明客户端真正发出目标数据，再测服务端安全闸门；字段改名须验证存在与类型。

完整方法读取 [prior-agent-artifact-audit](../prior-agent-artifact-audit/SKILL.md)。本入口保留这一具体场景，避免复制共享正文。
