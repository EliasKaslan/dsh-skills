---
name: "dingxiang-slider-captcha"
description: "顶象滑块验证码的合法交互与故障识别入口；转登录流程的人工交接模式，保留加载/iframe观察，停止脚本绕过。"
whenToUse: "顶象滑块验证码的合法交互与故障识别入口；转登录流程的人工交接模式，保留加载/iframe观察，停止脚本绕过。 模型触发仍以description为准。"
disable-model-invocation: true
warm-triggers: "顶象滑块验证码 / dx_captcha_basic / adb 拖滑块"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# dingxiang-slider-captcha

## 何时调用

只识别验证码/加载状态并交给用户正常完成；不执行SDK伪造、图像定位或自动拖动绕过。

加载并遵循 [login-credential-autofill](../login-credential-autofill/SKILL.md)，模式为 **验证码人工交接**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出。当前工具、权限和认证均以本会话实际DSH schema及用户授权为准。
