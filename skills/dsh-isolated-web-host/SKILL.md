---
name: "dsh-isolated-web-host"
description: "DSH隔离host入口；独立DSH_HOME、profile与loopback端口启动并验证身份，转总纲隔离host模式。"
whenToUse: "要在不碰真实 profile 的前提下起独立 DSH_HOME/loopback 端口，或要判断 401、端口身份算不算证据时。"
---

# dsh-isolated-web-host

## 何时调用

独立home/profile/workspace/loopback端口；401只属一层证据，不junction整真实profiles。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **隔离host**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
