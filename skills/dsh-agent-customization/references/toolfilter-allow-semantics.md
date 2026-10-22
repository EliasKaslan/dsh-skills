# `toolFilter.allow` 只筛继承面、own 层注册无条件可见（原 §2.16 原样拆出）

> 从 `dsh-agent-customization/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

### 2.16 `toolFilter.allow` 只筛继承面、own 层注册无条件可见（源码实证；纠正的是运行时 doc comment，**不是本 skill 的旧文**）

> 本节纠正的**不是本 skill 的旧文**（该 skill 里 `toolFilter` / `allow` **0 命中**），而是**运行时 doc comment 这个"唯一权威措辞来源"**：`dsh-tools\lib\index.js:2888-2894` 的 `Restrict global tools` / `global-tool mask` **与实现不符**（`:2891` 的 `scoped registrations remain visible` 与它**自相矛盾**）。

**C9-1｜可机判的结论。** **`toolFilter.allow` 只筛"继承面"（global + 祖先层）；agent 自己 scope 里注册的工具无条件可见，任何 `toolFilter` 都裁不掉。**

- 误判之源（`C:\Users\admin\.dsh\launcher\runtime\node_modules\@deepseek-ai\dsh-tools\lib\index.js:2888-2894`，逐字）：

  ```js
  /**
   * Restrict global tools for the calling agent scope. Empty filters, unknown
   * names, scope-local names, and reserved transport names fail. Restrictions
   * intersect; scoped registrations remain visible.
   * @param filter - global-tool mask: `allow` (keep only) and/or `deny` (remove).
   * @returns the exact disposer that lifts this restriction.
   */
  ```
  `Restrict global tools…` 与 `global-tool mask` 两处措辞会把人带向"**allow 裁的是全局工具名**"——**照注释推必误判**；真相藏在第三行 `scoped registrations remain visible`（`:2891`），它**与首句自相矛盾**、且太隐晦。
- 实现（`view(scope)`，同文件 `:2959-2979`）：
  - `:2963-2965`：`inherited` = `layers.global.tools` + 各祖先层；`if (layer === own) continue;`（`:2964`）⇒ **遍历继承面时显式跳过 own 层**；
  - `:2973`：`if (layers.every((layer) => layer.admits(name))) visible.set(name, definition);` ⇒ **`admits`（allow / deny 过滤）只作用于"继承面"**；
  - `:2975-2978`：`if (own !== void 0) for (const [name, definition] of own.tools.entries()) { knownNames.add(name); visible.set(name, definition); }` ⇒ **own 层直加 `visible`，完全不过 `admits`**。
- 附带解释：`dsh-tools:2907-2908` 报 `names unknown global tool…`（`const unknown = [...allow ?? [], ...deny ?? []].filter((name) => !known.has(name));` + `throw new Error(...)`），校验的是"**可裁名单**"（`restrictableNames`）——**own 层名字根本不在里面**。

**C9-2｜为什么 `explore` 实测 4 个工具而那行 `allow` 只写 3 个**：`modelSelectionSettings` 豁免

- bundle 侧：`artifacts\presets\orchestrator-bundle\cordis.patch.yml:193` 逐字 `modelSelectionSettings: true`（`tool-subagent` 行）。**全 patch 只此一处** ⇒ **`modelSelectionSettings` 1 / 10 条 `tool-subagent*` 行**（实测：patch 共 **36** 条 `- id:`、`- id: tool-` **23** 条、`- id: tool-subagent*` **10** 条）。
  > **口径更正**：早期记录用的是另一个分母（"若干行里只有这一行有该键"）——**"只有这一行有该键"成立**（实测 1 处），但**那个分母已弃用**（复算不出、与实测对不上）⇒ 本节**不写它**，只认上面两种可复算写法。
- 运行时侧（`@deepseek-ai\dsh-tool-subagent\lib\index.js`）：该键触发**逐 agent 安装**分支 ——
  - `:614` `if (agents === void 0) throw new Error("tool-subagent: standing \`modelSelectionSettings\` requires the Agent registry");`
  - `:618-632` `const installScoped = (candidate) => { … const policy = selectForSession(candidate.session); fiber = candidate.ctx.inject(["tools", "subagents", "systemPrompt"], (runtimeCtx) => { install(runtimeCtx, policy); }); }` ⇒ 工具注册进**该 agent 自己的 scope**（`candidate.ctx`）；
  - 注册点 `:398` `disposeTool: runtimeCtx.tools.register(defineTool({ name: toolName, …`。
- 两件事叠加 = 豁免：注册落在 **own 层**（`candidate.ctx`）× own 层**不过 `admits`**（C9-1 的 `:2975-2978`）⇒ **`toolFilter` 裁不掉这个 `subagent` 工具**。这给 `orchestrating-subagents §1` 那句"疑似 provider 在过滤**之后**注入"补上机制（不再是猜测）；**"未经探测的角色不得据此断言工具面"这条纪律保留**。
- 其余 **9** 条 `tool-subagent*` 行（4 个角色行 + `control` / `list-agents` / `fork` / `codex` / `claude-code`）的工具住在**挂载 scope** ⇒ 落在继承面 ⇒ **被 allow 裁掉**。

**C9-3｜"提示词分层"的全貌：子代理侧有现成口子，主 Agent 侧没有一等公民口子**

- 子代理侧四个现成口子：① 子 persona（`@deepseek-ai\dsh-subagent\lib\index.js:517-519` `if (composition.persona !== void 0) childCtx.systemPrompt.section({ order: childCtx.systemPrompt.getSectionOrder("DEPLOYMENT_PERSONA_PREFIX"), …})`）；② `toolFilter`；③ `maxDepth`（`:401` `const childDepth = delegationDepthOf(parent) + 1;` / `:479` `delegationDepth: childDepth`，守卫在 `types\depth.js`）；④ `SUBAGENT_DELEGATION_CONTEXT`（常量 `:487`，注入 `:512-515` `childCtx.systemPrompt.context({ order: childCtx.systemPrompt.getContextOrder("SUBAGENT_DELEGATION"), text: SUBAGENT_DELEGATION_CONTEXT })`；同一注入另见 `types\child-agent.js:159-162`）。**第一手佐证**：`:487` 那个常量**逐字**就是子代理会话里的 `You are a delegated subagent: your permission scope was fixed when you were started …` ⇒ 这条注入路径确实在跑，且**与深度无关**。
- **主 Agent 侧：未发现一等公民口子（负向结论 = "未发现"，不是穷尽证明）**：grep `delegationDepth` 扫 runtime `@deepseek-ai` 全树（1,007 个 `.js/.mjs/.cjs`）⇒ **89 命中 / 34 文件**，逐类归位**全部**落在 ①会话与深度守卫（`dsh-subagent\lib\types\depth.js`、`dsh-session*`）②RPC/schema（各 `typert.host.js`、`dsh-api-*`）③序列化与格式转换——**没有一处是"按 `origin` / `delegationDepth` 拼提示词"的分支**。
- 唯一近似做法及其漏洞：条文写进 **preset persona** ⇒ 只覆盖**写了 `persona:` 的行**：bundle 里 `persona:` 只出现 **5 次**（`cordis.patch.yml:195 / :229 / :247 / :270 / :288`），而 `- id: tool-subagent-fork`（`cordis.patch.yml:303-308`，只有 `provider` / `toolName` / `backgroundMode`）**没有 `persona`** ⇒ **走 `subagent_fork` 的派发会漏掉这段条文**。生效时机也不可混用：preset persona 走 **preset/bundle 冷启动**（§1 例外段），**与 `AGENTS.md` 的热刷新不同层**。
- 第四条机制事实（顺带登记）：`@deepseek-ai\dsh-tool-skill\lib\index.js:207` 按"该 agent 是否看得见 `skill` 工具"**逐 agent 门控**目录：`const snapshot = ctx.tools.get(skillTool.name, agent) === skillTool ? await ctx.skills.snapshot({ cwd: agent.session.header.cwd, signal, scope: agent }) : { skills: [], complete: true };` ⇒ **看不见 `skill` 工具 ⇒ 目录快照恒为空（`{ skills: [] }`）**——这正是 `explore` / `implement` / `verify` 注入 **0 条**目录的直接原因，也与"`allow` 里写不写 `skill` 都不等于有 `skill` 工具"互为印证。

**C9-4｜两条工具陷阱（归本 skill 的坑段，**不是** `pwsh-on-windows` 的坑）**

1. **`grep` 工具跳过点目录、且不跟随 Junction ⇒ "全树 0 命中"可能是假阴性。** 实测：在 `C:\Users\admin\.dsh` **全树** grep `at most 40 lines` 得 **0 命中**，而 `C:\Users\admin\.dsh\.agent-presets\orchestrator\agent.cordis.yml` 里实际有 **6 处**（`:58` / `:238` / `:272` / `:292` / `:313` / `:333`）⇒ **判引用必须显式给绝对路径**（`Select-String -Path <文件>`）。
2. **判"有没有第二份安装副本"不能用全树 grep**，要用 `Get-Item -Force` 看 `LinkType` / `Target`。实测：`C:\Users\admin\.dsh\profiles\web\node_modules\@local\dsh-orchestrator-preset` → `LinkType=Junction`、`Target=D:\workspace\agent\dsh_base\artifacts\presets\orchestrator-bundle` ⇒ 全树 grep 找不到 persona 文本**不是"没有副本"，而是"没跟过去"**。

> **锚点会漂，靠名字找回来**：上面每个源码位置都同时给了**函数名 / 常量名**（`view(scope)` / `admits` / `installScoped` / `SUBAGENT_DELEGATION_CONTEXT`）而不只是行号，行号漂了还能按名字定位（同 §2.15 口径）。`dsh-tools:2888-2894` 的注释与实现不符**本轮不改源码**（不在写域内），只在此登记——如需上游修注释，另派。

