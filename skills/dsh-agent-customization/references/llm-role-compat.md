# OpenAI 兼容网关把 system 写成 developer：判据与修法

## 症状

切到某个推理模型后，本轮**第一个**请求即失败：

```
400: {"message":"developer is not one of ['system', 'assistant', 'user', 'tool', 'function']","type":"invalid_request_error","code":"invalid_parameter_error"}
```

此时会话里还没有任何工具增删事件，所以与 DSH 的 `developer/message` 无关（那条在 pi-ai 适配器里会被转成 system 消息，见 dsh-llm-pi-ai 的 `appendDeveloper`）。

## 根因（0.2.2-rc.5 实读，2026-11-23 复核）

- `@earendil-works/pi-ai/dist/api/openai-completions.js`（asar 内 `dsh/node_modules/` 下，该版 65,602 字节）：
  `const instructionRole = model.reasoning && compat.supportsDeveloperRole ? "developer" : "system";`
  system 指令按这个角色 push 进 messages。
- 同文件 `detectCompat()`：`supportsDeveloperRole: isOpenRouterDeveloperRoleModel || (!isNonStandard && !isOpenRouter)`。
  非标准名单按 provider 或 baseURL 命中：nvidia / cerebras / xai(api.x.ai) / together / chutes.ai / deepseek / zai / moonshot / opencode / cloudflare Workers AI / cloudflare AI Gateway / ant-ling。
  openrouter 走单独分支：只有 `anthropic/`、`openai/` 前缀的模型才允许 developer，其余为 system。
  自定义 provider 名（如 huoshan）+ 自建/中转 baseURL → 两条都不命中 → **默认 true**。
- 模型带 `reasoningEfforts` 时 `model.reasoning = true`（dsh-llm-pi-ai `resolveReasoning`），两者相乘 → developer。
- DashScope compatible-mode 只接受 system/assistant/user/tool/function，于是 400。

## 修法

profile 的 `cordis.patch.yml`，在**该模型**条目下：

```yaml
- id: dashscope/kimi-k3.1-pro
  ...
  compat:
    supportsDeveloperRole: false
```

- 模型级优先：同网关的另一模型可能能接受 developer，不要顺手在 provider 级一起关。
- `compatProfile` 是 schemastery 部分对象：单键合法；实测 `{supportsDeveloperRole:false}` 原样保留、`{}` 通过、类型错才报 `expected boolean`。
- `openai-completions` 的 `COMPLETIONS_COMPAT_GATE.supportsDeveloperRole` 为 `"offer"`，不会被「not configurable」拒绝；`withhold` 字段才拒绝。
- 生效：loader 不 watch `cordis.patch.yml`，需重启 DSH 重新装配 profile。

## 验证

1. 定性（不动配置）：对同一 baseURL 发最小请求，只改角色——`system` → 200，`developer` → 400 同一句错误；再带 `max_completion_tokens` / `store` / `reasoning_effort` 各发一条，均 200，排除其他字段。
2. 改后：用 python/pyyaml 解析该文件确认结构与 compat 键；重启 DSH 后切到该模型真跑一轮。

未验证：重启后的整轮请求本机未实测（只验证到配置层与网关层）。
