---
name: "dsh-plugin-market"
description: "DSH插件市场与安装包审查入口；核对索引schema、来源固定、版本匹配及ASAR有界解析。"
whenToUse: "DSH插件市场与安装包审查入口；核对索引schema、来源固定、版本匹配及ASAR有界解析。 模型触发仍以description为准。"
---

# dsh-plugin-market

## 何时调用

核对当前市场schema/来源/依赖和ASAR头；导入或安装前审副作用。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **市场与安装包**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
