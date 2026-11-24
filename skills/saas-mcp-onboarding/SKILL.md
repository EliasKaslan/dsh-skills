---
name: saas-mcp-onboarding
description: 给Codex/DSH接第三方SaaS的MCP：官方bundle优先、stdio硬条件、云文档厂商实证。适用于"接语雀/飞书/腾讯文档""这个MCP能落地吗"。
whenToUse: 要把一个外部 SaaS（云文档、邮箱、IM、看板）接成 Codex 或 DSH 能用的工具时；或判断某平台宣称的 MCP 支持在 DSH 侧能不能真落地时。
---

# 给 Codex / DSH 接入第三方 SaaS 的 MCP

## 何时调用

要为 Codex CLI 或 DSH 接入一个第三方 SaaS 的 MCP（云文档、邮件、IM、看板），或要判断「某平台说有 MCP 支持」在本机能不能真跑通时用。只管「选哪个 / 能不能落地 / 怎么配」；改插件装配与生效时机另用 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)。

前置：先确认目标 SaaS 有没有官方 bundle，**这一步能省掉全部手写配置**。

## 先查官方 bundle，别急着手写 YAML

DSH 仓库 `packages/connector/` 下已有一等公民：`feishu`、`tencent-docs`、`notion`、`dingtalk`、`wecom`、`linear`。装了 bundle 才拿得到 **OAuth grant**（由 mcp-manager 的 credentials 服务托管）或官方 CLI + 随包 skill。

判断顺序：官方 bundle → 官方 stdio MCP → 社区 MCP。**手写静态行拿不到 OAuth**，这是分流点。

## 静态 `mcp-client` 行的边界（决定能不能落地）

`~/.dsh/cordis.patch.yml` 的 `- insert:` 列表追加一行 `@deepseek-ai/dsh-mcp-client`：

```yaml
    - id: mcp-<name>
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: <name>          # 须匹配 ^[A-Za-z0-9_-]{1,32}$
        transport: stdio
        command: npx
        args: ['-y', '<pkg>']
        env:
          <KEY>: '<value>'
```

工具名是 `mcp__<serverName>__<tool>`。**改完必须重启 DSH 进程**，会话内工具表不热更新。

四条硬边界：

- transport 只有 `stdio` / `streamable-http`，没有 legacy SSE。本机 10 个实例全是 stdio，HTTP 路径零实例验证——别拿 streamable-http 当已证能力。
- **没有 OAuth 流程**：服务返回授权挑战＝普通连接失败＋重连翻腾。强制 OAuth 的只能走 bundle / mcp-manager。
- **没有工具白名单，也没有单工具输出字节上限**：工具多的服务全量注入上下文，大返回只能靠提示纪律。
- `initialize` 的 instructions > **32 KiB** 直接连接失败；单次工具调用默认 **60 s** 超时。

## 供应商硬条件（照这把尺子筛）

1. `npx -y <pkg>` 即起的 **stdio** MCP。
2. 认证走**环境变量或请求头**，不强制 OAuth 浏览器回调。
3. 工具**细粒度**（按 id 的 search / read / write 分开），不是一个大而全工具。
4. instructions ≤ 32 KiB；工具数可控。
5. 单调用 < 60 s，限流返 429 而不是挂起。

**注意两端不对称**：Codex 有 `enabled_tools` / `disabled_tools` / `default_tools_approval_mode` / `output_token_limit`，能收窄；DSH 没有。所以「强制 OAuth / instructions 超限 / 工具大而全」这三类在 Codex 侧还能凑合，在 DSH 侧直接落不了地。

## 国内云文档：谁能被两端真读写（2026-11 实证）

| 平台 | 真 md 读写 | 官方 MCP | DSH bundle | 免费可用 |
|---|---|---|---|---|
| 语雀 | ✅ `format=markdown` 读写 | ✅ `yuque-mcp`（stdio，21 工具含 search / doc versions） | ❌ 手写 8 行 | ❌ 个人 Token 需超级会员 |
| 飞书 | ❌ 块结构，md 仅导入 | ✅ `@larksuiteoapi/lark-mcp` | ✅ `dsh-feishu`（lark-cli + skill） | ✅ |
| 腾讯文档 | ❌ 富文本 | ✅ 远程 `docs.qq.com/openapi/mcp` | ✅ `dsh-tencent-docs`（OAuth） | ✅ 2000 次/天 |
| Notion | ❌ blocks | ✅ `@notionhq/notion-mcp-server`（`NOTION_TOKEN`） | ✅ `dsh-notion` | ✅（数据出境） |

排除项：FlowUs 免费计划 403、WPS 须企业执照、有道 OpenAPI 停申、石墨转商务中台。

## 两个反直觉的坑

- **飞书不能当代理维护的文档库**。官方 `lark-mcp` README 原文：*Direct editing of Feishu cloud documents is not supported (only importing and reading are available)*。md 只能一次性导入（异步任务）。DSH 的 feishu bundle 走 `lark-cli` 而非 `lark-mcp`，写能力**未验证**。
- **语雀的 md 不等于存储格式**。底层是 Lake 富文本，卡片/画板/部分表格不进 md；`yuque_update_doc` 不能在同一次调用里既改 markdown body 又改 title/slug/public，元数据要单独改；`yuque_get_doc` 返回全文无截断，长文会灌爆上下文——先 list 再按需取。

## 验收口径

只在「真实会话里 `mcp__<server>__*` 出现了，且读一次、写一次都能通」时才算接入成功。改了配置文件、插件显示 active、进程还在，都不算。

厂商支持状态会过期（本轮为 2026-11），接入前复核官方仓库与文档页。
