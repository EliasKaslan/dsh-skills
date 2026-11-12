---
name: dsh-agent-preset-verification
description: DSH agent preset 离线静态校验（$DSH_HOME/.agent-presets/<id>/agent.cordis.yml）——不起会话也能验挂载：scanRoot 权威健康检查、逐行 Config/resolveConfig 报错原文、maxDepth 语义与 toolFilter 挂载期不校验的陷阱、坏 row 静默不服务的回滚要求。适用于"preset 到底挂载对没对 / 改完 preset 先离线确认能不能挂 / preset 没生效但看不出哪错了 / 委派工具一调用就报错是不是配置键写错 / maxDepth 写 0 为什么让工具全废 / 部署实验插件行前先看失败长什么样"。不适用：已起会话要验运行时真相（persona、工具裁剪、委派） → 用 `dsh-agent-preset-live-verification`；只是要个干净实验环境（起隔离 host） → 用 `dsh-isolated-web-host`；不知改 DSH 哪层、何时生效、怎么撤 → 用 `dsh-agent-customization`。
whenToUse: 离线（还没起会话）校验 preset 能不能挂载、哪个配置键或工具名写错时用；已起会话要验 persona、工具裁剪与委派请转 live 版。
disable-model-invocation: true
warm-triggers: 旧式 .agent-presets 目录的离线校验
warm-reason: 0.2.2-rc.1 已不读 .agent-presets，仅作历史参考
---

# 离线校验自定义 agent preset

> 本 skill 是总纲 `dsh-agent-customization` 的子 skill：只负责「离线静态校验」这一段；DSH 的分层、生效时机与上线纪律见总纲。

## 何时调用

**加载本 skill 当：**

- 刚写了 / 改了 `$DSH_HOME/.agent-presets/<id>/agent.cordis.yml`，想在起 host 之前知道它能不能挂载。
- preset 看起来"没生效"、或某个委派工具一调用就报错，需要区分是**配置键写错**、**深度策略写错**、还是**工具名写错**。
- 准备往 patch 里加实验插件行，需要先知道失败会长什么样。
- 还没起会话（或不想起会话），只想要"这份 preset 静态上到底对不对、能不能挂载"的结论。

**不要用本 skill（转交）：**
- 已经起了会话，要验运行时真相（system prompt persona 原文、真实工具裁剪、委派是否跑通、`turn/end`） → 用 `dsh-agent-preset-live-verification`。
- 只是要一个干净的隔离实验环境（重定向 `DSH_HOME`、401 判就绪、taskkill 收尾） → 用 `dsh-isolated-web-host`。

**前置**：能在可解析到 `@deepseek-ai/*` 的目录里跑 node（如 `C:\Users\admin\.dsh\profiles`），否则 `import` 直接失败。 ／ **后继**：静态结论为"能挂载"后，进 `dsh-agent-preset-live-verification` 做在线会话级验收。

## 前置检查

结构（缺一不可）：

```
$DSH_HOME\.agent-presets\<id>\agent.cordis.yml   # 组合文件（COMPOSITION_FILE）
$DSH_HOME\.agent-presets\<id>\preset.yml         # 展示元数据（METADATA_FILE）
```

- `<id>` 必须匹配 `^[a-z0-9][a-z0-9-]*$`，不匹配的目录直接跳过（`dsh-agent-presets/lib/types/discovery.js:293`）。
- 目录**每次读取都重扫**，新建目录 / 改文件**无需重启 host**。
- `preset.yml` 只读 `name` / `description` / `order` 三个键，**其余键静默忽略**（`dsh-agent-presets/lib/types/metadata.js:61-70`）；YAML 语法坏掉也只在展示层回退到 id，不影响挂载（`:50-57`）。

离线校验**必须在能解析到 `@deepseek-ai/*` 的目录里跑 node**，否则 `import` 直接失败：

```powershell
cd C:\Users\admin\.dsh\profiles
```

## 步骤

1. **权威健康检查 —— 用 `scanRoot`**。

   `scanRoot` / `discoverPresets` 已从包根 re-export，**正常用包名即可，不需要绝对路径 file URL**（见坑 1）：

   ```powershell
   node --input-type=module -e "import { scanRoot } from '@deepseek-ai/dsh-agent-presets'; const rows = await scanRoot({ path: 'C:/Users/admin/.dsh/.agent-presets', trust: 'user' }, 'file:///C:/Users/admin/.dsh/profiles/node_modules/@deepseek-ai/dsh/'); for (const r of rows) console.log(r.id, '|', 'broken' in r ? 'BROKEN: ' + r.broken : 'healthy');"
   ```

   - 验证：**健康条目没有 `broken` 字段**，失败条目才有（`discovery.js:297-306`）。
   - 实测 healthy 行形状：

     ```
     {"id":"orchestrator","trust":"user","path":"C:\\Users\\admin\\.dsh\\.agent-presets\\orchestrator\\agent.cordis.yml","name":"编排模式","description":"...","order":2}
     ```

   - 实测 broken 行原文（把 root 指向一个只有目录、没有组合文件的树即可复现，例如 `C:/Users/admin/.dsh/skills`）：

     ```
     the composition file agent.cordis.yml is missing — the directory still occupies the id; delete it or restore the file
     ```

   - `scanRoot({ path, trust }, harnessBase)`：`harnessBase` 传 dsh 包的 file URL 即可（上面那条），它用于解析 row 里 `name:` 写的包名。

2. **逐行校验 config**。分三类，不要一律用 `Config`：

   **a) 有 `Config` 导出的包**（实测 `dsh-tool-subagent` 的 exports = `Config,apply,inject,name`；另有 `dsh-persona` / `dsh-mcp-client` / `dsh-llm-retry` 等一批）：

   ```powershell
   node --input-type=module -e "import { Config } from '@deepseek-ai/dsh-tool-subagent'; console.log(Config({ provider:'spawn', toolName:'explore', maxDepth:1 }));"
   ```

   **b) 导出 `resolveConfig` 的包** —— `dsh-compaction-tool-result-pruner` 与 `dsh-plan-mode`。**这才是能做完整校验的入口**：

   ```powershell
   node --input-type=module -e "const p = await import('@deepseek-ai/dsh-compaction-tool-result-pruner'); try { p.resolveConfig({ thresholdChars: 100, headChars: 90, tailChars: 20 }); } catch (e) { console.log('BUDGET:', e.message); } try { p.resolveConfig({ thresholdChars: 8192, nope: 1 }); } catch (e) { console.log('KEY:', e.message); }"
   ```

   - 实测错误原文：

     ```
     ToolResultPruneConfig: headChars + marker + tailChars (149) must be at most thresholdChars (100)
     ToolResultPruneConfig: unknown key "nope" (allowed: thresholdChars, headChars, tailChars)
     ```

   - 标记串 `PRUNE_MARKER` 是 `"\n\n[... tool result middle pruned ...]\n\n"`（`dsh-compaction-tool-result-pruner/lib/index.js:8`），约束是 `headChars + 39 + tailChars ≤ thresholdChars`（`:43-44`）。

   **c) 什么都不导出的包** —— `dsh-compaction-basic` 只导出 `BasicCompactionEngine` + default。实测三个包的 exports：

     ```
     dsh-compaction-basic               => BasicCompactionEngine, default
     dsh-compaction-tool-result-pruner  => DEFAULTS, PRUNE_MARKER, ToolResultPruner, codePointLength, default, resolveConfig
     dsh-plan-mode                      => EXIT_PLAN_MODE, PlanModeController, default, planProjectionDefinition, resolveConfig
     ```

     所以 **`dsh-compaction-basic` / `dsh-compaction-tool-result-pruner` / `dsh-plan-mode` 都不导出 `Config`**；compaction-basic 只能读源码核对键名与约束。

3. **compaction-basic 的键集与约束（按源码，不要只记 5 个键）**：

   ```
   thresholdRatio / retainRatio / retainTokens / summarizationProvider / summarizationModel
   / maxTokens / compactionRetries / maxOverflowRetries / modelPolicies / auto
   ```

   - 出处：`POLICY_CONFIG_KEYS`（`dsh-compaction-basic/lib/index.js:20-27`）+ `modelPolicies`/`auto`（`:30-34`）+ `Config` schema（`:766-777`）。
   - 真校验在 `resolveConfig`（**不导出**，由构造函数调用，`:58-64, 785`）：未知键报错 `BasicCompactionConfig: unknown key "<k>"`（`:186`）；`retainRatio >= thresholdRatio` 报 `BasicCompactionConfig: retainRatio (0.9) must be less than the resolved thresholdRatio (0.7)`（`:135`）；`retainRatio` 与 `retainTokens` 互斥（`:169`）；比值须 ∈ (0,1]（`:201`）。

4. **确认组合树**（只证明 row 进了树，**不证明能加载**）：

   ```powershell
   node C:\Users\admin\.dsh\profiles\node_modules\@deepseek-ai\dsh\lib\bin.js --profile web --dump-config
   ```

   - 它能打印组合后的树，可确认 patch rows 确实进了树；但它**不导入模块**，所以**抓不到坏 row**（见"坑与修法"最后一条）。

5. **settings 里指定默认 preset**：

   ```yaml
   agent-presets:
     default: orchestrator
   ```

   - 命名空间 `agent-presets`，schema 仅 `{ default: z.string() }`（`dsh-agent-presets/lib/index.js:1145,1151`）。

## 坑与修法

- **`Config()` 只是类型层，通过 ≠ 能挂载**。实测 `BasicCompactionEngine.Config({ thresholdRatio: 0.7, retainRatio: 0.9, nope: 1 })` **不抛错**，未知键 `nope` 原样留在结果对象里（`keys = ['thresholdRatio','retainRatio','modelPolicies','nope']`）。
  → 原因：schemastery 的 `z.object` 不剥离未知键；键名与跨字段校验在 `resolveConfig` / 构造函数里。
  → 修法：能拿到 `resolveConfig` 就用它（pruner / plan-mode）；拿不到（compaction-basic）就按源码键集核对。**不要只跑 `Config()` 就宣称校验通过**。

- **`maxDepth` 语义陷阱（最容易写错的一条）**：`maxDepth` 限制的是**子代理自身的深度**，不是"父代理能否委派"。
  → 机制：`resolveChildDepth(parent, maxDepth)` 算 `delegationDepthOf(parent) + 1`，`childDepth > maxDepth` 抛 `SubagentDepthError`，消息 `subagent depth <attempted> exceeds maxDepth <max>`（`dsh-subagent/lib/types/child-agent.js:32-40`）。
  → 顶层调用者深度为 0 → 它的子代理深度为 1，所以 **`maxDepth: 0` 会让该工具的每一次调用都失败**；**`maxDepth: 1` 才是"叶子角色"**（子代理能跑，但它自己再委派会被拒）。
  → 而且 `Config({ maxDepth: 0 })` **不抛错**（实测通过），所以离线校验抓不到，只有第一次委派才炸。
  → `maxDepth: 'provider-managed'` 也被接受（实测），用于 codex / claude-code 这类外部 provider。

- **`toolFilter.allow` 里写的是全局工具名，且挂载期不校验**。实测 `Config({ provider:'spawn', toolName:'explore', toolFilter:{ allow:['reed'] } })` **通过**，拼错的 `reed` 原样保留。
  → 原因：`restrict()` 在**子代理创建时**才执行（`dsh-tool-subagent/lib/index.js:554` 附近的 `runtimeCtx.subagents.start`），挂载期不校验。
  → 修法：写完后手工把 `allow` 列表与当前会话实际可见的工具名逐一对照，别指望启动时报错。

- **静态 `agentOptions` 会绕过 `allowedModels` 策略**：该策略只约束"模型主动发起"的选择（`dsh-tool-subagent/lib/index.js:209-212` 的 `subagent/model-selection-policy`）。在 row 里写死 `agentOptions.provider/model` 就等于把这条策略绕过去了，别把它当成模型路由的兜底。

- **部署坏 row 是致命且无声的**。实测：patch 里放一个指向不存在包的 row，host 进程**仍然存活、stdout/stderr 全空、永远不打印 token URL、端口不监听**——即**静默不服务**。
  → 后果：没有报错可看，很容易误判成"还在启动中"而一直等。
  → 修法：必须有**独立于 host 的回滚手段**——部署前备份 patch，在 host 之外轮询端口判活，超时自动还原备份。不要指望从 host 日志里看出问题。

- **`--dump-config` 不是加载测试**：它打印组合树但不 `import` 模块，所以坏 row 在 dump 里看起来完全正常。树对了不等于能跑。

- **改 preset 不需要重启 host**：目录每次读取都重扫。反过来，改了没生效要先怀疑 id 不合法（`^[a-z0-9][a-z0-9-]*$`）或文件不在 `<id>/agent.cordis.yml`。

## 不要做什么

- 不要只跑 `Config()` 就宣称 preset 校验通过。
- 不要用 `--dump-config` 判断插件能不能加载。
- 不要在用户真实 `~/.dsh` 上试坏 row（静默不服务 + 无回滚 = 用户环境挂掉）。
- 不要把 `maxDepth: 0` 当成"禁止这个工具委派"——它是"禁止创建子代理"，会让工具彻底不可用。
- 不要以为改了 preset 要重启 host。
- 不要在没有备份 patch、没有 host 外探活的情况下部署实验插件行。

## 验收标准

- `scanRoot` 输出里目标 id 那一行**没有** `broken` 字段。
- 每个 row 都跑过一遍对应入口：有 `Config` 的跑 `Config(cfg)`，有 `resolveConfig` 的跑 `resolveConfig(cfg)`，两者都没有的按源码键集人工核对，且全部不抛错。
- `--dump-config` 里能看到预期的 row（仅作为"进树"证据，不作为"能加载"证据）。
- 部署实验 row 前：patch 已备份、host 外的端口轮询判活已就绪、失败还原路径明确。
