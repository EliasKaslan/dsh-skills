---
name: "dsh-plugin-market"
description: "DSH插件市场与安装包审查入口；核对索引schema、来源固定、版本匹配及ASAR有界解析。"
whenToUse: "问「有没有某个外部 agent/模型 接入 DSH 的插件」、要按 schema 核对市场索引、或只读解析 app.asar 时。"
---

# dsh-plugin-market

## 何时调用

核对当前市场schema/来源/依赖和ASAR头；导入或安装前审副作用。

加载并遵循 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)，模式为 **市场与安装包**。只执行该模式的前置、步骤与验收，不扩展到无关模式；所需详细reference由该入口给出，工具、权限与认证以本会话 schema 及用户授权为准。

## 社区插件存在性核查（ChatGPT/Codex 类提问）

被问「有没有某个外部 agent/模型 接入 DSH 的插件」时，先拆方向，再取证，最后才回答有/没有。

**判据（顺序不能反）**
1. 官方 vs 社区：官方只认 `deepseek-ai/deepseek-harness` 仓与 `@deepseek-ai/*` 包名。第三方包（`dsh-plugin-*`、`dsh-as-mcp`、`dsh-*-bridge`）一律社区；市场站的 "Verified" 只表示 `dsh plugin add` 能装上并启动，不代表官方、不代表可信。
2. 方向必须分开写：
   - (a) 外部模型当 DSH 的 provider（内建 `openai` 只走 API Key；`openai-codex` 只有 provider id，订阅 OAuth 未接线）；
   - (b) DSH 被外部当子代理/MCP server 调用（官方无 MCP server，出口只有 ACP / SDK stdio JSON-RPC / HTTP Web）；
   - (c) DSH 驱动外部 agent 当子代理（官方 on-demand bundle：`@deepseek-ai/dsh-subagent-codex`、`-claude-code`、`-acp`、`-dsh-sdk`，默认 `availability: missing`，需 `dsh plugin add`）。
   三者结论互不等价，答 (a) 不能顺带当成 (b)。

**取证命令**
- 包真伪：`GET https://registry.npmjs.org/<pkg>/latest` → 200/404（例：`@deepseek-ai/dsh-llm-openai` = 404，官方 OpenAI 支持在 `llm-pi-ai` 里）。
- 本机官方 bundle 表在 `D:\tools\dsh\resources\app.asar`（2026-11-23 为 209MB 单文件，含 349 个 `@deepseek-ai/*` 包）。按二进制读全文 `count`/`find` 取上下文；`app.asar.unpacked` 只有原生模块与资源、无包源码，`Get-ChildItem ...\packages` 一定扑空。

**坑**
- 不带 `/latest` 的 registry 请求返回全部历史版本，几十 KB 起、直接打爆上下文；`deprecated` 字段要读（有包被标 `broken: incomplete package`）。
- ASAR 里 `Sign in with ChatGPT` 命中的是文档示例（`https://auth.example/start`），不等于订阅 OAuth 已实现。
- 关键词计数只在 `dsh-*` 包内可信；`azure` / `oauth` 的高计数多来自第三方依赖。
- 本机 `dsh` CLI 不在 PATH（2026-11-23 实测），别用它取版本；版本读 asar 内 `package.json`。
- 桥接类包常钉死 DSH 版本（例：某 bridge 只 targets 一个 rc），装前先核对 peer/targets。
