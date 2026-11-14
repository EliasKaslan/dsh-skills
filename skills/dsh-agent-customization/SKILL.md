---
name: dsh-agent-customization
description: DSH 改造入口总纲：五层生效时机、插件 bundle、上线纪律与回滚。适用于"改 DSH 行为该改哪一层 / 插件行坏了怎么回滚 / MCP 怎么挂 / 恢复后会话打不开 / 自己写 host 插件"。
whenToUse: 要改 DSH 自身行为（行为宪法 / 流程 skill / agent 组合 / 默认 preset / 插件行与 patch），或要判定改动何时生效、怎样回滚、上线前还差哪一步时，先加载本总纲。模型看不到本节。
---

# DSH「改造 agent 行为」总纲

本 skill 是**入口**：先在这里定"改哪一层、怎么生效、怎么撤、上线还差什么"，具体动作交给对应子 skill。
**单一归属**——每一步的详细命令、错误原文只写在子 skill 里，本总纲只写入口与纪律，不复制正文。

## 何时调用

- 触发信号：用户说"改 DSH 的行为 / 让它以后都这样 / 新写一个 skill / 换个 agent 组合 / 加一个插件行"，或你正要动 `~/.dsh` 下的任何一层配置。
- 触发信号：用户说"把某个 MCP server 挂给 DSH / MCP 工具用不了 / 这个 MCP 挂上去要占多少上下文"，或你正要往 patch 里写一行 MCP 插件（先读 **2.7 / 2.8 / 2.9**）。
- 触发信号：host 起了但页面打不开、改了配置不知何时生效、改完想回滚。
- 转交边界：只验 preset 静态可挂载 → `dsh-agent-preset-verification`；已起会话验 persona / 工具 / 委派 → `dsh-agent-preset-live-verification`；只搭干净环境 → `dsh-isolated-web-host`；把跑通的流程写成新 skill 的协议 → `sedimenting-skills`；skill 集合的定期体检（重复 / 失效指针 / 预算）→ `dsh-skill-self-audit`；MCP 工具的实际用法（接管 Outlook.com 邮箱、设备码登录） → `outlook-mailbox-control`。
- 前置：知道 `DSH_HOME`（默认 `~/.dsh`）与当前 host 的端口；**改自己正跑在里面的那个 host 前，先读完第 2 节**。 ／ **后继**：按第 3 节阶梯顺序走，最后回到第 2.6 节确认回滚路径。

## 1. 三个可改层 + 生效时机（实测）

| 改什么 | 位置 | 何时生效 |
|---|---|---|
| 行为宪法 | `~/.dsh/AGENTS.md` | 会话**首个请求**时加载；**文件被改动后 harness 会检测到并热刷新注入**（实测：改完当轮即收到 `Updated instructions from: ~/.dsh/AGENTS.md — This file changed after it was loaded.` 并用新正文替换旧正文）→ **无需重启**；但刷新时机由 harness 的变更检测决定，别假设"改完对所有正在跑的会话都立刻生效" |
| 流程 skill | `~/.dsh/skills/<name>/SKILL.md` | **写入即可被发现**，无需重启（实测两次）；first-party `write`/`edit` 会让 skill provider 失效并重发目录 |
| agent 组合 | `~/.dsh/.agent-presets/<id>/` | roster **每次读取都重扫**（改文件 / 加目录都不用重启）；但**只有空会话能切换 preset**，已建会话不换；新建会话采用 settings 里的默认 |
| 默认 preset / 模型路由 | `~/.dsh/settings.yaml` | 每次**新建会话**时读取（改完对已存在的会话无效） |
| 插件行 / patch | `<profile>/cordis.patch.yml` | **热重载**——但热重载的成败判据与冷启动完全不同，见第 2.1 节 |

**这一节的反直觉结论**：上面这些层**大多是热生效的**，所以"改完立刻观察到了变化"**证明不了这个改动是安全的**。真正需要**重启**才能验证的是插件行 / patch 的**冷启动正确性**（第 2.1 节）——"现在没坏"不等于"下次还能起来"。

补充：**给 DSH 挂 MCP server 就是"插件行 / patch"层**（没有独立 MCP 配置文件，唯一入口是 patch 里一行 `@deepseek-ai/dsh-mcp-client`）——落点、能力边界与**三种**失败形态见 **2.7**，接入前必须先量的"工具面注入量"见 **2.8**，`env` 传值保真的量法见 **2.9**。

补充（实测）：`.agent-presets` 的 roster 重扫是**每次读取**都重扫，所以改 preset 后连 host 都不用重启；反过来"改了没生效"要先怀疑 id 不合法（`^[a-z0-9][a-z0-9-]*$`）或文件不在 `<id>/agent.cordis.yml`。

## 2. 上线纪律（本总纲最重要的一节）

### 2.1 热重载 ≠ 冷启动，失败模式完全不同（实测）

同一个**坏 row**（指向不存在的包）在两种路径下表现截然不同。**"坏 row"其实有三种形态，别当成一种**（下表前三行，形态 ①② 是冷启动的两个分支、③ 是解析期）：

| 路径 | 现象 | 致命性 |
|---|---|---|
| **冷启动 · 形态①**（row 校验合法，但 MCP server 起不来） | 进程**不挂**：host **照常起来并服务**（不带 token 的 HTTP GET **401**），只有那个 MCP server 子进程起不来 → **工具静默缺席** | **最危险**：唯一可见迹象是子进程 stderr 一行（实测 `command` 指向不存在的可执行文件时，GBK 解码原文：`'npx-definitely-not-a-real-binary-3f9a' 不是内部或外部命令，也不是可运行的程序或批处理文件。`）；host 侧**没有任何报错** |
| **冷启动 · 形态③**（YAML 语法错误） | 进程直接 **`EXITED code=1`**，stderr 原文 `Error: dsh: failed to parse patches …\cordis.patch.yml: YAMLException: can not read an implicit mapping pair; a colon is missed (16:20)`（`dsh-app-boot/lib/index.js:1197`，解析在 `:1149`；同一位置的读文件失败见 `:1147`） | **不致命**：硬退出 + 报错可见（依据：YAML 在插件树之前解析，promise 没人 await → 未捕获 → 退出码 1）——**这一形态不静默** |
| **冷启动 · 形态②**（host 正常起来了、新工具却没注册上） | host 打得开（**401** 照常通过），工具面里就是没有它 → 仍**静默** | **危险**：`401` **不算**接入成功。**本次未取证**（无实跑日志）——仍必须防，判据见 2.7 |
| **热重载**（同一个坏 row） | host **继续服务**（保留旧树），但坏 patch **留在盘上** | **非致命**，但**下一次重启才会静默挂掉**——当场看不出问题，这是最危险的形态 |
| 合法 rows 冷启动 / 热重载 | 继续服务（实测最差连续失败次数 **0**）；冷启动形态是 stdout 打印启动 URL 一行、stderr **0 字节** | 安全 |

**冷启动失败 vs 成功的判据**（实测）——要只有两条：

- **进程是否存活**：`Get-Process -Id <pid>` 有输出 = 没硬退出（形态③ 为 `EXITED code=1`，进程已没）。
- **HTTP 探针**：不带 token 的 GET **401** = 服务在跑（2.4）。
- **不要**把"端口不监听"当判据：本机端口枚举是**盲的**（`netstat` / `Get-NetTCPConnection` 恒空），"端口不监听"**永远成立，是恒真空断言** → 正文见 `dsh-isolated-web-host`（坑「整机端口枚举是盲的」），本 skill 不复制。
- 两个判据都过**也证不了工具在**（形态②）。三条判据齐全才是"接入成功"。

→ 铁律：**"现在没坏"不等于"安全"**。部署任何插件行 / patch 改动前，必须先在**隔离环境冷启动**验证**同一组合**。"组合相同"指的是：**同样的 profile 文件 + 同样的 `node_modules`**（不是"差不多的配置"）。

### 2.2 改的是"自己正跑在里面的那个 host"时，必须有 host 之外的看门狗

一旦 host 挂了，**你（被这个 host 服务的 agent）就同时失去了回滚能力**——你不能靠一个已经死掉的宿主去救它自己。实测：`Start-Process` 启的**分离进程能存活于发起 shell 退出之后**，所以看门狗可以独立于 host 存在。

看门狗模式（五段，缺一段都不算）：

1. **守卫**：patch 必须是已知的裸数组 `[]`，否则**拒动**（防止在别人的定制上盲写）。
2. **备份**：备份原文件，**不覆盖已有备份**（避免二次故障时把好备份覆盖成坏的）。
3. **应用**：写入新 row / patch。
4. **盯端口**：每 **3 秒**一次，**连续 3 次失败（≈9 秒）才算死**——热重载期间会有短暂闪烁，单次失败不能判死。
5. **失败则回滚 + 用显式 `DSH_HOME` / `--port` / `--no-open` 重启 host**；并且**始终留 marker 文件**，写清结论与回滚命令。

### 2.3 安全网自己必须先被测

**真实教训**：第一版看门狗的重启命令写成了 `node <bin> web`，**漏了端口和 `DSH_HOME`** → 一旦触发回滚，它会去**抢用户的真实端口**、指向**错误的 home**——**安全网自己制造了故障**。这个 bug 只有靠"**模拟 host 崩溃**"实测才暴露出来。

→ 铁律：**没被真正触发过的安全网不算安全网**。回滚 / 看门狗类脚本必须用**人为杀掉 host** 来实跑它的**回滚 + 重启分支**，否则你拥有的只是一个"看起来像安全网"的字符串。同理：**重启命令里必须显式带 `DSH_HOME`、`--port`、`--no-open`**——省掉任何一个，安全网都会打到错误的目标上。

### 2.4 就绪判据

- **不带 token** 请求返回 **HTTP 401 = 服务已就绪**——这是 token 围栏在生效，**不是故障**；带 token 才是 **200**。
- 启动时会打印 `dsh web: http://127.0.0.1:<port>/?token=…`。**没有打印**这一行**不能**直接判"起不来"——按 2.1：形态①② 的 host 可能照常服务，形态③ 才是硬退出（那一形态另有 `EXITED code=1` + YAML 解析报错可见）。所以先看进程存活 + 401 探针，再排查 stderr。

### 2.5 已知地雷

`@deepseek-ai/dsh-experimental-agent-team` + `-tool-agent-team` 一旦挂载，**所有普通子代理委派都会失败**（`TEAM_NOT_MEMBER`），且**没有任何配置级绕法**。

→ 本总纲只给一条纪律：**先别挂**；确实要挂，先看子 skill `dsh-agent-preset-live-verification`（有机制溯源、错误原文、上游修法与对照组做法）。

**更新（2026-11-12，0.2.2-rc.2 实测，上面这条已被部分证伪）**：`dsh-experimental-agent-team*` 三个包已改名为 `dsh-agent-team` / `dsh-tool-agent-team` / `dsh-client-ui-agent-team`，由 `dsh-base` / `dsh-web-app` **默认挂载且 `enabled=true`**（`plugin_manager list_plugins` 里两个 `include:*` 行都是 `active`）。在这种默认开启状态下，本会话成功派发了两个 `subagent` ⇒ **`TEAM_NOT_MEMBER` 在 0.2.2-rc.2 未复现**；该地雷只对 0.2.1-era 的 `dsh-experimental-*` 包名成立。注意团队模式**默认关闭**（新 Session 默认关），所以普通会话的工具面里看不到任务工具——那是设计，不是故障。判定"为什么插件页没有它了"见本文末尾那节。

### 2.6 生效 / 回滚矩阵（每层都要能一句话说清"怎么撤"）

| 层 | 怎么撤 | 撤完何时生效 |
|---|---|---|
| `AGENTS.md` | 改回原段落 / 删掉新增段 | 下一次变更检测热刷新（同第 1 节） |
| skill | 删 `<name>/SKILL.md` 或改回原文 | 下一轮目录重发即生效，无需重启 |
| agent preset | 删 `~/.dsh/.agent-presets/<id>/`；若它是默认，同时删/改回 settings 里的 `agent-presets.default` | roster 每次重扫立即生效；但**已建会话不能换 preset**，要新会话才看到 |
| settings | 改回原值（默认 preset、模型路由） | 新建会话生效 |
| 插件行 / patch | 用备份还原（`[]` 或原数组） | 热重载立即恢复服务树；**还原后仍要重启一次验证冷启动**，因为热重载成功不代表干净 |

### 2.7 MCP 接入层（本层的一个特例，实测）

要给 DSH 挂一个 **MCP server** 时，它**不是新的一层**——它就是第 1 节里的**"插件行 / patch"层**，落点仍然只有 `cordis.patch.yml`。

**先删掉错误的心智模型**（实测）：

- **没有**独立的 MCP 配置文件、**没有** `mcpServers` 键、**没有** `~/.dsh/mcp/*.json` 这类声明文件（该目录可以是空的）。**唯一的声明入口 = patch 里的一行 cordis 插件**，插件固定是 `@deepseek-ai/dsh-mcp-client`。
- patch 文件的形状是**单一顶层 `- insert:` 列表**，每个 server 一行、**4 空格缩进**，与既有插件行同级追加即可。
- 文件顶部注释逐字写着：**Requires restarting `npx @deepseek-ai/dsh web` to take effect.** → 与 2.1 一致（改完必须**冷启动**验证）。
- 行定位靠 `id:`（自取唯一名）；工具对模型暴露为 **`mcp__<serverName>__<tool>`**。
- 能力边界（决定"这条路走不通"要在第 3 节之前就判）：**只支持 `stdio` 与 `streamable-http`，没有 `sse`**；**只桥 tools，不桥 resources / prompts**。

**上线纪律按 2.1 / 2.2 / 2.3 全套走**，只补两条 MCP 专属的：

1. **在隔离 host（重定向 `DSH_HOME`）冷启动验证"同一组合"**——实测成功那组的形态是：`stdout` 只有一行 `dsh web: http://127.0.0.1:<port>/?token=…`、`stderr` **0 字节**。判据是"**打印了 URL 那一行**"，不是"进程还活着"。
2. **失败形态有三种，都要单独判**：① **合法 row、但 server 起不来**（host 照常服务、无 token GET 照样 **401**，工具**静默缺席**——见 2.1 形态①，唯一痕迹是子进程 stderr 一行；"无 token 401"**不算**接入成功）；② **host 正常起来了、新工具却没注册上**（**同样静默**，`401` 会照样通过；**本次未取证**，但仍必须防）；③ **YAML 语法错误**（**不是静默**：进程直接 `EXITED code=1` + 解析报错，见 2.1 形态③）。⇒ 无论走哪一条，都必须再去会话的工具面里**点名核对那个新工具是否存在**（`mcp__<serverName>__<tool>`）。

**可选字段的语义与默认值**（`@deepseek-ai/dsh-mcp-client`，本次新增）：

| 字段 | 默认 | 语义 | 依据 |
|---|---|---|---|
| `toolCallTimeoutMs` | **60000** | 单次 `tools/call` 的超时（ms），透传到 `callTool(...,{timeout: opts.toolCallTimeoutMs})` | `lib/index.js:728`（`const DEFAULT_TOOL_CALL_TIMEOUT_MS = 6e4;`）、schema `:750` / `:758`（`z.number().default(...)`）、用法 `:101-104`、`README.md:61` |
| `failOnStartupError` | **false** | 默认 `registrationFailure: "contain"`（连接 / 工具同步失败**被吞**，host 照常起）；置 true 换成 `"throw"`，在 `outcome.error !== void 0` 时抛 `mcp-client(<serverName>): initial connection or tool synchronization failed` | schema `lib/index.js:751` / `:759`、语义 `:520` 与 `:524-526`、抛错 `:788`、`README.md:62` / `:70` |

**判据（结论）：两个都建议保持默认。** `failOnStartupError: true` **只**把"形态①的静默缺席"升级成"**整个 host 起不来**"，对**形态③（YAML 解析错误）买不到任何保护**——那种情况本来就已经硬退出并报错；把它开成 true 等于让**一个 MCP server 的抖动变成整个 DSH 起不来**，是用更大故障换更响的报错。

### 2.8 接入任何 MCP server 前，先量一次"工具面注入量"

**为什么必须先量**：MCP 工具的 schema 属于 **request header**，**每一轮请求都要重发**——挂上去的成本是**每轮线性付**，不是一次性。

**DSH 侧的实现事实**（`@deepseek-ai/dsh-mcp-client`）：桥接时 `createDefinition(..., tool.description ?? "", tool.inputSchema, ...)` **原样透传 `description` 与 `inputSchema`，无截断、无长度上限、无字段裁剪**；工具名按 `mcp__${serverName}__${rawName}` 拼装。

**可复用的量法**（三个 server 都适用，别只看包体积）：

1. 让 server 起来、抓它自己的 **`tools/list`** 原始响应（`initialize` → `notifications/initialized` → `tools/list`）。
2. 只按 DSH **真正会发的字段**算字符数：`{type:"function", function:{name, description, parameters}}`，其中 `parameters` 就是原始 `inputSchema`、`name` 用 `mcp__<serverName>__<tool>` 形态；用紧凑 JSON（`separators=(',',':')`、`ensure_ascii=False`）量。
3. 与**已经挂着的 server 做基线对比**，得到"这一个要花掉几个基线"。

**经验事实（判据，不是某 server 的结论）**：

- `tools/list` 原始响应里**不进上下文**的字段（`title` / `annotations` / `outputSchema` / `execution` 等）**不要计入**——原始响应体积 ≠ 注入量（实测口径：原始响应里约一半不是发送字段 + pretty-print 缩进）。
- **成本几乎全在 `inputSchema`**（实测口径：一个 51 工具的面里 `description` 约 10%、`inputSchema` 约 **88%**、工具名约 1%）。所以"工具 description 写得短"根本不是优化点，**砍 schema 才是**。
- 很多 server 提供 **`--discovery` 类开关**（只暴露少数 discovery/utility 工具，真实工具藏在 catalog 里按名直调）或**工具白名单开关**。**二者未必能叠加**：有的实现把白名单当作**隐藏 catalog 的过滤器**——结果是**暴露的工具数不变、字符数不降，但被过滤掉的工具在运行时以 `Tool not found` 静默失败**，属**白付代价**（省不到上下文，还丢了能力）。⇒ **叠加前必须做对照实验**（两个开关分别单开、一起开，三组比"工具数 + 字符数 + 目标工具能否真调用"）。
- 走 discovery / 按名直调路线的代价要一并算：参数 schema **不在上下文里**，参数写错只在**调用期**暴露（错误形如 `Tool not found: <name>`），所以配方必须**写进 skill 或 prompt 让模型照抄**，别指望模型回忆。
- 量法脚本与三组对照的原始产物**留在报告的 bundle 目录，不进本 skill**。

### 2.9 `env:` 传值保真怎么量（YAML → config → spawn → `process.env` 四跳）

**问题**：配置里的 `env:` 要过 YAML → mcp-client config → 子进程 spawn → Node `process.env` **四跳**，非 ASCII（emoji 等）会不会被损坏，**光看配置文件看不出来**。

**量法（自建探针 MCP server，可复用）**：

1. 写一个**最小 stdio MCP server**：只回显 `process.env` 的**指定键**（`initialize` → `notifications/initialized` → 一个 echo 工具，返回该键的 presence + 原样字符串）。
2. 用**一条临时插件行**把探针桥进**隔离 host**（`dsh-isolated-web-host`），**绝不污染真实 `~/.dsh`**。
3. 在会话里调 `mcp__<probeServerName>__<echoTool>`，把值取回来。
4. **断言口径**：比对 **codepoints 数组** + **utf8 hex**（`值.encode('utf-8').hex()`）+ **紧凑 JSON 原文**（`separators=(',',':')`、`ensure_ascii=False`）三样，**不要眼看**。
5. 本次跑通的口径可作验收模板：返回体是 `{present, codepoints, utf8hex, json}` 四元组，**emoji 与尾随空格零损坏**判据 = `utf8hex` 与源串逐字节相等、`codepoints` 与源码点逐项相等。

**边界**：探针 server 必须跑在**隔离 host**（`dsh-isolated-web-host`）；取值的会话 RPC 细节（`session/create|page|prompt` 的参数要包一层 `{"request":{…}}`、`throughSeq` 必须 ≤ 游标否则 `past cursor N`）**单一归属在 `dsh-agent-preset-live-verification`**，本 skill 只留这条指针、不复制。探针那侧的具体变量名属**会话专属证据**，留报告，不进本 skill。

> 会话专属证据（隔离 home 的实际路径、端口、URL、各 server 的字符数）留报告，不进本 skill。


## 3. 阶梯顺序（编排入口）

```
设计  →  离线校验（dsh-agent-preset-verification）
      →  起隔离 host（dsh-isolated-web-host）
      →  在线会话验收（dsh-agent-preset-live-verification）
      →  安全上线（本总纲第 2 节那一套）
```

**为什么不能跳：**

- **离线只证配置层**：证明 YAML / 配置键 / 发现层没问题，能挂载。它**不 import 运行期**，所以 apply 期错误、工具裁剪、模型路由都看不到。
- **在线才证运行时**：persona 原文、真实工具清单（服务端权威，别信模型自述）、委派是否真跑通，只能在真会话里核对。
- **上线纪律才证"下次重启还能起来"**：前三步全绿也只说明"现在能用"，而 2.1 的坏 row 恰恰是**当场无感、重启才死**。跳过第 2 节 = 把故障推迟到用户下次重启时才引爆。

**顺序不可交换**：没起隔离 host 就没有在线验收的场地；没离线过就上在线，会把配置层错误当成运行期问题查（浪费一轮且结论不可信）。

## 不要做什么

- 不要在**用户真实 `~/.dsh`** 上直接试实验插件行——坏 row 冷启动**分三形态**（2.1）：解析错误那一种会**硬退出并报错**（可见、可回滚），真正危险的是**形态①的静默缺席**（host 照常 401、工具没了）与**形态②**（未取证但必须防）。**风险不对称** ⇒ 没想好回滚就不要动用户环境。
- 不要把 **401** 当成启动失败，也**不要**当成 MCP 接入成功（形态①/② 下 401 照样通过）。
- 不要用"**端口不监听**"当冷启动失败 / 清理判据——本机端口枚举恒空，那是**恒真空断言**（正文与实测见 `dsh-isolated-web-host`）。
- 不要把"热重载后页面还能打开"当成部署成功——换的是冷启动的账。
- 不要在没有 **host 之外**的看门狗时，改自己正跑在里面的那个 host。
- 不要提交一个**没被真实故障触发过**的回滚/看门狗脚本，也不要让重启命令漏掉 `DSH_HOME` / `--port` / `--no-open`。
- 不要把 **401** 当成启动失败。
- 不要挂 `dsh-experimental-agent-team` + `-tool-agent-team`（除非已读过 `dsh-agent-preset-live-verification` 并用对照组确认委派仍可用）。
- 不要把 `failOnStartupError` / `toolCallTimeoutMs` 改离默认值——`failOnStartupError: true` 只把"形态①的静默缺席"升级成"整个 host 起不来"，对形态③（YAML 解析错误）**买不到任何保护**（2.7 表）。
- 不要**去找**"MCP 的配置文件"或写 `mcpServers` 键——DSH 没有那一层，唯一入口是 patch 里的一行 `@deepseek-ai/dsh-mcp-client`（2.7）；也不要指望 `sse`，它只支持 `stdio` / `streamable-http`，且**不桥** resources / prompts。
- 不要在**没量过**工具面注入量之前就把 MCP server 挂上去——工具 schema 每轮重发，成本按轮线性付（2.8）；也不要先假定"`--discovery` 类开关 + 工具白名单能叠加"，**必须三组对照实测**（单开 / 单开 / 同开），否则可能白付"能力消失"的代价。
- 不要把"隔离 host 打得开（401）"当成 MCP 接入成功——**形态①/②都**是 host 正常但工具没来，**必须点名核对工具**（2.1 / 2.7）。
- 不要在本总纲里找具体命令——按第 3 节进对应子 skill；本总纲不复制它们的正文。

## 验收标准

1. 能一句话说出本次改动**属于哪一层**、**何时生效**、**怎么撤**（第 1、2.6 节）。
2. 若动了插件行 / patch：已在**隔离环境冷启动**验证**同一组合**（同 profile 文件 + 同 `node_modules`），并观察到启动 URL + 401。**挂了 MCP server 时再加一条**：新工具名**点名**核对过（`mcp__<serverName>__<tool>` 真的出现）——host 打得开**不算**过（2.7 的形态①/②就是"host 正常、工具没了/静默缺席"）；并对该 server 量过一次**工具面注入量**、与已挂 server 做过基线对比（2.8）；有非 ASCII `env:` 时另按 2.9 用探针 server 验一次保真（判据 = codepoints + utf8 hex 逐项相等）。
3. 若动的是自己正跑着的 host：看门狗**已用人为杀 host 实测过**回滚与重启分支，且重启命令显式带 `DSH_HOME` / `--port` / `--no-open`，marker 文件已落盘。
4. 按第 3 节阶梯留下证据：离线校验结论 → 隔离 host 就绪（401）→ 在线 `agentPreset`/persona/工具/`turn/end` → 上线后的冷启动证据。
5. 子 skill 与总纲的交叉引用双向齐全（总纲 → 子 skill；子 skill description 的"不适用 → 用 `dsh-agent-customization`"）。

## 恢复 DSH home 时：文件名版本段必须以文件内 header 为准

> 这一节不新增层：恢复 `~/.dsh` 备份仍是“改一个正在跑的环境”，第 2.2 / 2.3 节的纪律（外围看门狗、安全网要实测）照样适用。区别只在失败形态——它不是静默，而是**整个会话列表一起挂**。

### 硬约束：`session.vN.jsonl.zstd` 的 N 必须等于 header 的 `version`

会话日志的落盘路径是：

```
<项目目录>/<session-id>/session.vN.jsonl.zstd
```

**文件名里的版本段必须等于该日志第一行（header）的 `version` 字段**——不是“当前 DSH 的最新版本”。从空闲簇 / 旧副本重建、或从旧版迁移时，这一步最容易整体写错。

命名规则（`@deepseek-ai/dsh-session-format/lib/index.js:472`）：

| header `version` | 合法文件名 | 备注 |
|---|---|---|
| `v0` | `session.jsonl` | **没有**版本段；`.v0.` 非法 |
| `vN`（N ≥ 1） | `session.vN.jsonl` | 大写 `V3`、前导零 `v03` 都不被识别 |
| 压缩存储 | 上面任一种再加 `.zstd` | 后缀按压缩方式追加 |

### 写回日志必须**多帧**：第 1 帧只放 header 行；单帧写回会让会话**静默消失**

压缩日志是**多个 zstd 帧拼接**：第 1 帧装 header 行，后续帧装追加的事件行。所以**读要跨帧**——`zstandard.ZstdDecompressor().stream_reader(f, read_across_frames=True)`；Node 的 `zlib.zstdDecompressSync()` 只解第一帧（实测一个 505 字节的日志只得到 244 字节 header，很容易误判“日志是空的”）。读全的完整配方**单一归属在 `dsh-agent-preset-live-verification`**（§6），本节只写**写回**约束。

**写回铁律**：重压缩写回时**至少两帧，且第 1 帧只放 header 这一行**，其余全部事件行放进后续帧。若压成**单帧**写回——**内容完全正确，不报错，也没有任何损坏提示**，但 `session/list` 里那个会话**直接消失**。实测：把 10 个日志改成单帧 → 列表 **234 条掉到 224 条**；同一内容改回「第 1 帧 = header 行 + 第 2 帧 = 其余全部行」→ 该会话**立刻回到列表**。⇒ 它不是坏了，是被“自己的修复”藏起来了。（只剩 header 的日志怎么处理**未验证**。）

**这条改了排查方向**：「备份恢复后某些会话不见了」**先别怀疑内容坏了**，先查帧布局。

判定（三步，可复用）：

1. **比数量**：`session/list` 的条数 **<** `sessions/` 下的日志文件数 ⇒ 命中了“静默不可见”。
2. **验内容**：把疑似缺失的那条**跨帧解压**，能解出完整 JSONL（header + 事件行齐全）⇒ 内容没坏，问题在**帧布局**。
3. **修法**：按「第 1 帧 = header 行、第 2 帧 = 其余全部行」重写成两帧，再拉一次 `session/list` 核对该会话是否回来。

### 不一致 = 硬失败，会拖垮整个 listing

不是“跳过这一条”，而是**抛错**——`@deepseek-ai/dsh-session-persistence-jsonl/lib/index.js:3159`，消息形如：

```
session generation filename identifies v<文件名版本>, but its header identifies v<header 版本>
```

同文件的 `listArtifacts` **只在 `unsupported` / `corruption` 时跳过**（`:3115`），这条错不在跳过之列 → 冒泡成 `dsh-session-query` 的 **`SESSION_QUERY_PERSISTENCE_FAILED`**（`dsh-session-query/lib/index.js:290`）→ 依赖会话列表的下游全部挂：workspace controller、手机桥的 task index。用户侧体感就是“**会话列表 / 工作区打不开**”。

⇒ **一条坏日志 = 整块功能不可用**。只要恢复过 `sessions/`，就必须**全量逐条校验**，不能抽查。

### 根因的典型形态

一批日志被**统一改名成最新版本**（例如全写成 `session.v4.jsonl.zstd`），但内容 header 还是 v3 / v0——“按当前版本批量重写文件名”的迁移 / 重建就是这样坏的。

实测样本（一次恢复）：230 条里 **48 条**被写坏（42 个 header 是 v3、6 个是 v0），约两成。⇒ **“文件数对上了”不能证明恢复成功**，恰恰最容易给出假 OK。

### 恢复后的自证：让**真消费者**打一行日志

别用“数文件 / 看目录结构”验收，找一个**真的调 listing** 的消费者。最低成本：手机桥插件 `~/.dsh/plugins/dsh-mobile-bridge` 启动时就会 `sessionQuery.listSessions()`：

- 成功 → `[info] task index loaded <N> sessions from <N> rows`
- 失败 → `[error] task index load failed ...`（看到这条就回上面全量查）

### 同场景的两个可复用手法

1. **不启动 host 校验 patch 组合**：`dsh --profile <自定义名> --dump-config`。`desktop` profile 被 Electron 独占、不能这样起；**自定义 profile 名可以**。
2. **`storages/workspace.json` 会被内存旧版覆盖**：它**启动时读进内存**（`dsh-storage-json` 无文件监听）。运行中改写文件不影响当前进程；而进程下次做**工作区级写操作**时会把内存旧版**写回磁盘、覆盖你的恢复结果**。⇒ 改完**必须重启**，且**重启前别在 GUI 里动工作区**。

### 恢复流程（按此顺序）

1. 只铺文件，**先不启动 host**。
2. **全量校验**：逐条读第一行 header，断言 `文件名版本段 == header.version`；不一致的**以 header 为准改文件名**（`v0` → 去掉版本段的 `session.jsonl`；压缩的一律保留 `.zstd`；大小写 / 前导零按上表归一）。
3. 启动，看「自证」那一行日志：`loaded <N> sessions` 且 N 与预期一致才算过。
4. **最后**才改 `storages/workspace.json`，改完**重启一次**让索引从磁盘重读（手法 2）。

### 坑

| 坑 | 现象 | 修法 |
|---|---|---|
| 只数文件数 | 230 条都在 → 判“恢复成功”，实际 48 条坏 | 全量断言版本段；用自证日志验收 |
| 以为坏日志会被跳过 | 期望“少几条会话”，实际整个列表 500 | 单条错即 listing 全挂，必须全量修 |
| 把 v0 也写成带版本段 | `session.v0.jsonl.zstd` → 解析侧不认 | `v0` 永远没有版本段 |
| 改完没重启 | 当前进程行为没变；下次工作区写回把旧版写回磁盘 | 改完必重启，重启前别动 GUI |

> 会话专属证据（本次会话数、坏日志条数、具体项目目录名）留报告，不进本 skill；这里只留可复用的判据与顺序。

## 第三方双半插件（host + client）——实测 2026-11-10，DSH 0.2.2-rc.1

**客户端半不是独立行。** host 行 active 后，宿主读该包 manifest；`dsh.client.platform === "web"` 且 `exports["./client"]` 存在才进 boot graph。注册 id = 包名。

- 包布局：`main: lib/index.js`（host ESM，`@deepseek-ai/*` 保持 external）+ `exports["./client"]: lib/client.js`（**预构建自注册 CJS factory**：`window.__ModuleLoader__.load({id, factory:(require)=>{…; return module.exports}})`；只 require 平台 seed：react / react-dom / react/jsx-runtime / cordis / dsh-client-store / dsh-client-ui-primitives / dsh-client-ui-slots / dsh-client-ui-dockkit）。非平台依赖写 `dsh.client.external`；手写 ESM 必失败（宿主原样拼接）。
- bundle 安装：`dsh.bundle.patch: "./cordis.patch.yml"` 让插件管理器可装；patch 里 `- insert: - id: <id> name: '<包名>'`。手工安装 = profile `node_modules` 放 junction + profile patch 加同一行。
- 生效：profile patch 改动热重载；**实测只改 profile patch 可能不唤醒 watcher → touch `~/.dsh/cordis.patch.yml` 触发一次重组合**；改插件自身 `package.json` 清单需重启。
- 验证（不带 token）：`GET /plugins/events` 首帧 graph 里按 `id` 找行——**注意这条只对 host+client 双半插件成立**；纯 host-only bundle 在客户端图里**恒为 0**（实测：真实 host 里已发布两次的 host-only 插件同样是 0 命中），拿它判缺席会得到假阴性（**不要**用 pluginInventory，它只投影宿主行）；`GET /plugins/??<pkg>/client.js&rev=<rev>` 200，旧 rev 404。`/plugins/*` 免令牌，`/` 401 只是 token 围栏。
- RPC：宿主 service 继承 `TypertRemoteService`（`super(ctx,'<svc>',{namespace:'<ns>'})`）+ 原型 marker `@deepseek-ai/dsh-typert-protocol/remote-methods`；无 strict 描述符时网关走 SRC 兜底（参数名从 `Function.prototype.toString()` 解析，**signal 必须字面量最后一位**）。client 最省事走 `ctx.connection.rpc.call('/api','<ns>/<method>',{args},signal)`，返回 `{ok,value}|{ok:false,error}`，**免 zod / 免 $mount / 免 generator**。
- 验收：隔离 host 冷启动 + boot graph + bundle 200；真会话验 UI；只读用主会话 `session.vN.jsonl.zstd` 的 size/mtime 不变做证据。
- 完整示例与细节：`D:\workspace\agent\dsh-sidecar`（README 的 How it works / Development）。

## host-only 插件 bundle：peerDependencies 解析与 defineTool 契约（实测 0.2.2-rc.1）

host-only bundle 不需要 client 半、不需要构建，三个文件就够：`package.json`（`type: module`、`exports: {".": "./index.js"}`、`dsh.bundle.patch`）+ `cordis.patch.yml`（`- insert: - id: <id> name: '<包名>'`）+ `index.js`（`export function apply(ctx, config)`，可选 `export const inject` / `export const Config`）。

**三个必踩的坑（错误原文逐字）**

1. `Cannot find package '@deepseek-ai/dsh-tools' imported from …\index.js`
   → profile 插件对 dsh 自带包的解析走 app-boot 的拦截层，而拦截层只对**在该包 `package.json` 的 `peerDependencies` 里声明过的名字**生效（`routeLinked` → `readPeerNames`）。在插件清单里声明 peer（本例：`@deepseek-ai/dsh-tools` / `dsh-llm` / `schemastery`）即可，**不要**往插件目录里 vendored 副本。
2. `JsonSchemaError: unsupported JSON schema: schema.required is not supported by the value schema DSL`
   → `defineTool` 用自定义 DSL：`required: true` 写在**属性节点**上，不能写 JSON-Schema 的 `required: [...]` 数组；`type` 为 object 的节点要显式 `additionalProperties`；**`output` 是必填字段**（漏了 register 时抛 TypeError）。
3. `session append cannot reenter while another append is being published`
   → 在 `turn/end` 的 append 发布过程中直接 `agent.followup()` 必炸。改在 `agent/turn-stopping`（异步 serial 派发，此时没有 append 在发布）里排队：该消息会落在 loop 收尾的 inbox 检查之前，被当成新的一轮继续跑；非 `completed` 的轮次在 `turn/end` 里用 `agent.inbox.remove(messageId)` 撤回并回滚计数。

**系统提示段只给顶层 agent**：`ctx.systemPrompt.section({ name, order, text })` 的 `text(context)` 里判 `context.agent.session.header`——`origin === 'subagent'`、`parentSession !== undefined`、`delegationDepth > 0` 任一成立就返回 `""`（子代理不该继承顶层治理规则）。

**写盘类工具必须自带回读自检**：写完立刻 `fs.readFile` 回读，断言 frontmatter 可切分、`name` 与目录名一致、`description` 单行且 ≤480、路径形状 `<name>/SKILL.md`，并把结果作为 `checks[]` 回给模型；判据与 `sedimenting-skills` 的契约保持一致。

**手工安装（等价于 plugin_manager）**：`<profile>/node_modules/<包名>` 放 junction → profile `package.json` 的 `dependencies` 加 `link:<绝对路径>`、`dsh.profile.bundles` 追加包名 → touch `~/.dsh/cordis.patch.yml` 触发重组合。不需要手改 profile patch：bundle 自带的 patch 会插入 row。

**验收"真的加载了"**：派一个子代理让它如实回报函数清单，看新工具名是否在里面（工具是全局注册的），再让它调一次验 execute 护栏。**不要靠日志**——headless 下 `ctx.logger.info` / `logger.warn` 的输出去向不可靠（本次实测 stderr 全空，插件却已生效）。

## 第三方客户端 UI 插件「装了没反应」的静默降级诊断

## 症状

从第三方市场装的**纯客户端**插件（`dsh.client.platform: web`，`lib/index.js` 是空 `apply(){}`）装上、启用、重启后，界面上**完全没有反应，控制台也不报错**。这类插件的作者通常写了「静默降级」：数据取不到就 `return null`，整条链被 `?.` 和 `try-catch` 吞掉。

血证（dsh-plugin-node-time@0.1.2 → DSH 0.2.2-rc.1）：

```js
// 插件 client.js:54 —— 期望列表快照里有 current
next = sessions.list?.getSnapshot?.()?.current;   // 恒为 undefined
// 插件 client.js:255 —— 拿不到会话就直接 return，不抛错
function resolveTiming(snapshot, element) {
  if (snapshot === void 0 || snapshot === null) return null;
```

## 定位顺序（先证「行生效」，再证「契约」，最后才怀疑浏览器）

1. **行生效没生效**：`plugin_manager` → `set_plugin` / `enabled: true`，`target` 用 `include:<rowId>`。
   - `application: applied` + `changed: false` = 行已存在且启用（幂等，可安全重复调用）。
   - `error.code: unknown-plugin` = 行不存在，或刚改完 patch 宿主还没重建索引 → **等 2 秒重试一次**，不要急着改配置。
   - 这比 `list_plugins` 便宜得多：后者返回 200+ 条，前者一行 JSON。
2. **契约还在不在**：读插件的取数代码，把它的字符串/字段/服务名当清单，到当前 `app.asar` 里逐项验。
   - DOM 钩子（`data-*`）、客户端服务名（`sessions`、`timer`、`slots`）、时间字段（`callTime` / `stepStartTime` / `firstTokenTime` / `completedTime`）都是可全文搜的字面量。
   - **数据结构定义**最省事：`@deepseek-ai/dsh-cordis-client-runner` 的客户端 bundle 里内嵌了 `.d.ts` 原文（`declaration: "export interface ..."`），直接 grep 就能拿到当前真实形状。
3. 比对了才发现断的是取数路径，不是 DOM：`data-disclosure-row` / `data-chat-call-id` / `data-chat-anchor-key` / `data-sample` 在 0.2.2 全都还在。

## 已证伪的断言（别再按这些写插件）

| 旧写法（0.1.x） | 0.2.2 实际 |
| --- | --- |
| `sessions.list.getSnapshot().current` | 不存在。`SessionListState = { ids, byId, phase, projectionsBySession }` |
| `session.getSnapshot().chat.nodes/order` | 不存在。chat 改成了 binding target |
| 符号 `ToolChatData` / `AssistantChatData` | 全 asar 0 命中；但**形状**仍在（`data.root` / `data.subCalls` / `data.finalNode.timing`） |

## 读 asar（本机固定路径 `D:\tools\dsh\resources\app.asar`）

头部 16 字节是 `uint32 4 | uint32 headerLen | uint32 payloadLen | uint32 jsonLen`，**JSON 从偏移 16 开始**，数据区从 `8 + headerLen` 开始。

```python
n0, header_len, n2, json_len = struct.unpack('<IIII', f.read(16))
f.seek(16); hdr = json.loads(f.read(json_len).decode('utf-8'))
# 每条目: {offset, size} 或 {files:{...}}（目录）或 {link} / unpacked（无 offset，必须跳过）
```

坑：`v['offset']` 对 symlink/unpacked 条目不存在，不判断就 `KeyError`；脚本往 stderr 打状态行会被 Windows PowerShell 当错误（命令尾部加 `2>$null`）。

## 官方自带的不漂替代

要「每步时间」这类能力，优先用 app 自带的官方包，用 profile patch 加一行即可（`- insert:` 包一层，module 名用 `@deepseek-ai/...`）：

```yaml
- insert:
    - id: ui-stats
      name: '@deepseek-ai/dsh-experimental-client-ui-stats'
```

`@deepseek-ai/dsh-experimental-client-ui-stats` 贡献 `conversation.view` 的「统计」页签：展开步骤行给该步开始时间戳 `MM-DD HH:MM:SS.mmm`、模型/工具耗时、TTFT、缓存命中、输出速度，且**不受** `developerTools` 开关限制。手改 patch 后 row 立刻 live，只需刷新页面（客户端模块图每次页面加载重建），不必重启宿主。

## 本机 DSH 取证入口（源码 / 会话日志）

何时用：要确认「DSH 内部到底怎么做的」（上下文压缩、注入、工具表），或回看某次会话到底发生了什么。方向是**只读取证**，不改配置——要改配置回总纲的「五层」那一节。

### 1) 源码不在 runtime context 给的那个路径上

runtime context 里的 `D:\tools\dsh\resources\app.asar\dsh\` 是 asar **包内**虚拟路径，磁盘上没有这个目录：

```
Get-ChildItem : 找不到路径"D:\tools\dsh\resources\app.asar\dsh"
rg: IO error for operation on D:\tools\dsh\resources\app.asar\dsh: 系统找不到指定的路径。 (os error 3)
```

真实布局：

- `D:\tools\dsh\resources\app.asar` —— 打包体（本机约 213 MB）
- `D:\tools\dsh\resources\app.asar.unpacked\dsh\node_modules\` —— 只解包了原生依赖，源码仍压在 asar 里
- asar 头（本机实测）：offset0 `u32=4`，offset4 `u32=headerSize`（本机 `0x57b5a4`），其后是 Chrome pickle `{u32 payloadSize}{u32 jsonLen}{json}`，文件数据在头之后；JSON 的 files 树给出每个文件的 offset/size
- 本机**没有** `@electron/asar` 模块，要 grep 源码必须先自己按上面的头解析、把目标文件 dump 出来

未验证：解包成可 grep 的目录树、以及 dump 后能否命中具体实现——本次只确认了路径与头部格式，没有跑通提取。

### 2) 会话日志

- 位置：`%DSH_HOME%\sessions\<工作区 slug>\**\session.v3.jsonl.zstd`（部分为 `session.v4.jsonl.zstd`），按工作区目录分桶，每会话一个文件
- 解压：node v24.18 有 `require('zlib').zstdDecompressSync`；python 有 `zstandard 0.25.0`；本机**没有** `zstd.exe`
- 每轮 token / TTFT / 缓存命中也能从界面拿：profile 的 `cordis.patch.yml` 里声明 `ui-stats` 插件后，统计页签按轮、按步给出这些数

### 3) 配置在哪、默认值从哪来

- 机器级：`C:\Users\admin\.dsh\cordis.patch.yml`
- profile 级：`C:\Users\admin\.dsh\profiles\<profile>\cordis.patch.yml`（本机 profile = `desktop`）
- 两层都**没有**压缩 / 上下文相关条目 ⇒ 该行为走内置默认；想调必须先从包里挖出默认键名，别假设有现成开关
- **先确认 `DSH_HOME` 环境变量再拼路径**：本机是 `C:\Users\admin\.dsh`，不是 `C:\Users\Administrator`；按用户名猜路径会扑空（`Test-Path` 返回 False，且不会报错）

## host-only 插件 bundle：安装、生效判定与免启动验证（实测 2026-11-12）

## 用 `plugin_manager` 装本地 link bundle（省掉手工三步）

`install_bundle` 的 `target` 直接收 `link:<绝对路径>`：

```
plugin_manager install_bundle target='link:D:\workspace\agent\<你的插件目录>'
```

成功返回 `{"stage":"enable","target":"<包名>","enabled":true,"changed":true,"application":"applied"}`，它一次做完：建 `node_modules` junction → 写 profile `package.json` 的 `dependencies`（`link:D:/...`）→ 追加进 `dsh.profile.bundles` → 跑 pnpm。

- **pnpm 的 peer 警告是噪音，不是故障**：link 形态必然打
  `The linked in dependency will not resolve the peer dependencies from the target node_modules`，
  而 peer 实际由 app-boot 的拦截层按插件 `peerDependencies` 解析（见本 skill 上面那节），实测不影响加载。
- **不要在 link 形态下往插件目录 vendored 一份 `@deepseek-ai/*`**，那会绕开拦截层。
- 幂等复查用 `set_plugin target='include:<rowId>' enabled=true`：返回 `application: applied` + `changed: false` 就是行已在且启用。

## 改了插件源码 ≠ 已经生效；"行到底挂没挂"也别猜

**先纠正一条本 skill 早前的错误断言**：此前写的是"bundle 目录里的源码不会被热重载"。**已被实测证伪**——
同一个插件在真实 host 里，改 `lib/*.js` 之后 `publish.log` **确实出现过新的 `loaded(...)` 行**（两次，间隔 17 秒）。

实测（2026-11-12，真实 host）：

| 我做了什么 | 运行期有没有跟着变 |
|---|---|
| 改 `lib/*.js` | **有**——日志里出现两条新的 `loaded(...)` |
| 同一轮里再改 `index.js` | 数分钟内**没有**任何新行 |

⇒ 结论不是"会不会热重载"，而是**"无法预判"**。唯一判据是**运行期痕迹**：在 `apply()` 开头自己写一行落盘日志
（不要只靠 `ctx.logger`，它不进 stderr），改完看有没有新行。有新行 = 新代码在跑；没有 = 仍是旧版，重启 host。
**文件 mtime 不是证据**，`401` 更不是（见下一节）。

## 判"插件行到底挂没挂"：唯一可靠判据是插件自己的副作用

三组对照（隔离 host，0.2.2-rc.1，同一个 host-only 插件）：

| 组 | 改动 | 无 token `GET /` | stderr | 插件副作用 |
|---|---|---|---|---|
| A | 原样 | 401 | 空 | `<stateDir>/<plugin>.log`，config = profile 覆盖后的值 |
| B | 把 row 的 `name` 改成不存在的包名 | 401 | 空 | 痕迹改用**默认** config（`enabled=true repo=<默认路径>`） |
| C | 把 bundle 从 `dsh.profile.bundles` 里删掉 | 401 | 空 | 两个 state 目录**都不生成** |

两条反直觉结论：

- **`401` 对"行挂没挂"是恒真断言**：三种状态码、`stdout`、`stderr` 全都一模一样。判据只能是插件自己写出的副作用（状态文件 / 日志文件）。
- **B 组：坏 `name` 不会让行消失**。它把整段 patch（**连 `config`**）静默丢弃，插件**退回 bundle 自带的默认配置照常挂载**。
  所以"好像加载了但配置没生效"要优先怀疑 `name` 拼错或包名不存在。反过来这也是最便宜的判据：
  **在 `apply()` 里把关键 config 值打进那行日志**，值不对就是 profile 的覆盖根本没吃上。

## 不启 host 也能验接线（比冷启动便宜得多）

把插件目录复制到一个桩目录，造两个最小 peer 包，然后用 `ctx` 桩直接调 `apply()`：

```js
// 桩：node_modules/@deepseek-ai/dsh-tools/index.js
export const defineTool = (o) => o
// 桩：node_modules/@deepseek-ai/schemastery/index.js  —— 每个类型返回 {default:()=>d, parse:v=>v}
```

```js
const regs = []
const ctx = {
  logger: { info() {}, warn() {} },
  effect: (fn, label) => { const d = fn(); if (typeof d !== 'function') throw new Error('no disposer: ' + label) },
  on: (evt) => regs.push('on:' + evt),
  tools: { register: (def) => regs.push('tool:' + def.name) },
}
mod.apply(ctx, cfg)   // 断言 regs === ['tool:...','tool:...','on:session/event']
```

它能一次证掉四件事：`exports` 面（`name` / `inject` / `Config` / `apply`）、**注册的工具名清单**、
**订阅的事件名清单**、以及 `ctx.effect` 的回调**真的返回了 disposer**（返回 `undefined` 会在真 host 里埋泄漏）。
`node --check` 只能证语法，证不了这些。

## 两个事件/定时器事实（0.2.2-rc.1）

- **`turn/end` 不是 cordis 事件**，`ctx.on('turn/end', …)` 收不到（全 asar 搜 `turn/end` 只命中会话日志的 append）。
  它是会话日志类型，必须走：`ctx.on('session/event', (session, event) => { if (event?.type !== 'turn/end') return; … })`。
- cordis **没有** `ctx.setInterval`；用 Node 全局包在 effect 里，并 `unref()` 否则 host 退不掉：

```js
ctx.effect(() => {
  const t = setInterval(tick, ms)
  if (typeof t.unref === 'function') t.unref()
  return () => clearInterval(t)
}, '<plugin>: poll timer')
```

- 同理 **`ctx.on('dispose')` 也不存在**：清理一律走 `ctx.effect(() => disposer)` 或让 `apply` 返回函数。

## 写盘类插件的"可审计"底线

发布/同步类插件（把文件推出去的那种）除了自带回读自检（写完 `readFile` 断言），还要**把删除动作留痕**：
把本次删掉的路径写进状态文件（例：`state.json` 的 `deleted[]`）。否则"发布后少了文件"只能靠事后
`git diff <old> <new>` 反推——而那一刻你往往已经不知道 `<old>` 是哪个 sha 了。

## 自己写「行内装饰」型客户端插件（手写 bundle + 取数链 + 免重启安装）

## 自己写「行内装饰」型客户端插件（实测 0.2.2-rc.1）

用户要「对话每一行常显这步的开始时间」这类**逐行装饰**需求时，先排除 slots：`conversation.chat.node` 是接管式槽（`entryKey: kind`，fallback 才是默认渲染），`tool.call.toolview` 同样是接管式（`dsh-diff-stat` 就靠它重画 diff，代价是自己渲染整个工具视图）。要在**每行加一枚小标签**而不管宿主怎么渲染，只能做 DOM 装饰。

### 包与 bundle 契约（手写即可，不需要构建）

- `package.json`：`"exports": { "./client": "./lib/client.js" }` + `"dsh": { "client": { "platform": "web", "inject": [] } }`。
- `lib/client.js` 用宿主同款信封，**零 `require`** 就是「纯 bundle」（宿主有 bundle purity gate，外部 specifier 会抛）：
  ```js
  window.__ModuleLoader__.load({ id: '<pkg>', factory: function () { /* ... */ return { apply: apply, inject: [] }; } });
  ```
- `lib/index.js` 只要 `export function apply() {}`（无宿主行为）。

### 已验证的取数链

```js
const sessionId = el.closest('[data-conversation-session]')?.getAttribute('data-conversation-session');
const binding   = ctx.sessions.binding(sessionId);
const chat      = ctx.uiConversation.binding(binding).target('chat');   // 返回 { getSnapshot, subscribe }
const node      = chat.getSnapshot().nodes.get(el.getAttribute('data-chat-node-key'));  // nodes 是 Map
const t0 = node.kind === 'tool-call'  ? node.data.root.callTime                 // 运行中只有 time
         : node.kind === 'assistant-step' ? node.data.finalNode.timing.stepStartTime
         : node.data.time;
```

- 会话 id 的 DOM 锚点是 `data-conversation-session`（渲染在包住 chat 区的容器上）；**没有** `data-session-id`。
- `data-chat-node-key` 的值形如 `${kind.length}:${kind}${id}`（例如 `9:tool-call<callId>`）——**只当 map key，不要解析**。
- 稳定性排序（从稳到脆）：`target('chat')` → `nodes.get()` → `node.data.*` 字段名。把这三层各写成一个可替换的适配器，升级时只动一层。

### 一个必踩的坑：双角标

`[data-disclosure-row]` 是工具行**内部的折叠头**、不带身份；真正带 `data-chat-call-id` 的元素（`callRow`）才是工具行容器。两个选择器都装饰 → 同一行出现两枚角标。规则：先装饰 `[data-chat-call-id]`，再装饰 `[data-disclosure-row]`/`[data-sample]` 时跳过 `closest('[data-chat-call-id]')` 命中的；flow item 一律「最内层获胜」（内含 `[data-chat-node-key]` 或 `[data-chat-group-key]` 的跳过）。

### 安装：本机不要碰 pnpm

`pnpm.ps1` 被执行策略拦（`无法加载文件 ... 因为在此系统上禁止运行脚本`）。两步即可，且**热生效不用重启**：

1. `cmd /c mklink /J %USERPROFILE%\.dsh\profiles\desktop\node_modules\<pkg> <源码目录>`
2. profile 的 `cordis.patch.yml` 追加 `- insert:` → `- id: <rowId>` / `name: '<pkg>'`

反例：把同样内容写成包的 `dsh.bundle.patch`，需要重启宿主才应用（bundle 列表只在启动时读）。行是否生效用 `plugin_manager set_plugin target=include:<rowId>` 验，`application: applied` 即为已挂载。

### 单测不需要 jsdom

手写极简 DOM（元素 + `attributes` + `children` + `parentElement` + `parentNode` + `querySelector(All)`，选择器只需支持 `[a]` 与 `[a="b"]`、以及逗号分隔），把 bundle 源码用 `eval` 跑在注入了假 `window.__ModuleLoader__` 的全局里，即可验证：适配器命中、两种时间来源、缺服务不抛错、dispose 清干净、服务晚到后重扫能补上。这套假 DOM 能抓出真 bug——例如插件里用了 `parentNode`/元素级 `querySelector` 而假 DOM 没实现（真宿主有，属于测试缺口，但要补上才能继续跑）。

## 行内装饰客户端插件的自审清单（DOM 装饰 + 订阅型数据源）

写完这类插件后按表过一遍，每条都是实测踩过的：

| 症状 | 修法 |
| --- | --- |
| 流式输出时页面发涩 | **订阅必须按快照引用去重**：`if (snap === lastSnap) return;`，再按 rAF 合并一次 pass。订阅在流式 token 上高频触发，每通知一次全量重建索引是长会话的主要卡点 |
| 每帧扫全文档 | `document.querySelectorAll` 换成 `root.querySelectorAll`，root = `[data-conversation-session]` 容器 |
| 控制台每帧一条报错 | rAF 回调整段包 `try/catch`：一次意外 DOM 形状不该打死 observer，也不该每帧刷日志 |
| 服务缺失时 CPU 飙 | 适配器重试要退避（如 1s），不要每帧试 `sessions.binding()` / `target('chat')`——它们失败时会造异常对象 |
| 某些行的时间明明有却不显示 | 别写 `map.get(k) \|\| null`：开始时间为 `0` 会被判成"无数据"。用 `=== undefined` 判断 |
| 折叠区里的行被白装饰、展开后不刷新 | 跳过带 `hidden` 属性的祖先；展开本身会触发 MutationObserver，下一帧自然补上 |
| 装配早于 `<body>` 就永不生效 | `document.body === null` 时 `setTimeout` 重试并返回取消句柄，不要 `return` |
| 切会话后旧数据还挂着 | 视图卸载（容器属性没了 / sessionId 变空）时 `detach()`：退订 + 清索引 |
| 角标样式突然丢 | 每 pass 检查 `styleTag.parentNode === null`，被 HMR 的样式簿记收走就重新注入（样式标签务必打 `data-plugin` 标记，否则会被邻近插件认领清理） |
| 读屏把每个时间念一遍 | 装饰性角标加 `aria-hidden="true"`；再配 `pointer-events:none` + `user-select:none` |
| 切到后台回来角标不更新 | 不要用 `setInterval` 主驱动；rAF 在隐藏页不跑，回前台自动补一帧 |

死代码自检（一行）：用 python 统计 `function NAME(` 声明名在全文的出现次数，`==1` 即只声明未调用。注意**以函数表达式放进数组的适配器**（`ADAPTERS = [function a(){}, ...]`）只会出现一次，属合法，不要误删。

验收顺序固定：`node --check` → `node test/run.mjs` → `plugin_manager set_plugin target=include:<rowId>` 看 `application: applied`。前两步过了再谈浏览器效果，别用"刷新试试"当验收。

## DOM 装饰的锚点选择：块级行容器 vs flex 折叠头

## DOM 装饰的锚点要按「布局角色」选，不能按「带身份属性的元素」选

**症状**：同一个装饰在 A 类行出现在左上角，在 B 类行却跑到行内行首（跟标题同一行）。

**原因**：装饰是「插成锚点的第一个子节点」，而锚点的 `display` 决定了你怎么排布——
`[data-disclosure-row]`（折叠头）是一行横排 **flex**，插进去的子节点变成第一个 flex 项目，于是跟标题并排；而 `[data-chat-node-key]`（flow item）、`[data-chat-call-id]`（工具行）是普通 **block** div，插进去就独占一行、自然落在左上角。

**规则**：身份属性 ≠ 锚点。

1. 锚点只选**块级行容器**：节点行走 flow item，工具行走 call row。
2. **绝不**往折叠头 / 标题行 / 任何 `display:flex` 的元素里插装饰。
3. 拿不到块级锚点时，退到「该元素的**父容器**」，并用「祖先已有的装饰」去重：
   ```js
   function hasBadgeAbove(el, root) {
     for (var cur = el; cur && cur !== root; cur = cur.parentElement) {
       if (ownBadge(cur) !== null) return true;   // ownBadge = 只看直接子节点
     }
     return false;
   }
   ```
   这条兜底同时挡住「有锚点的行被重复装饰」。
4. 别为了让位置好看去给宿主元素加 `position:relative` 再绝对定位：那会改变宿主自己的定位上下文，行内浮层/菜单的锚点可能被带偏。

**反推锚点的技巧**：如果旧实现「能显示出内容」，说明它取数所依赖的身份祖先**一定存在**（取数要先找到那个属性），据此就能判定该把它装饰在哪个块级容器上，而不用猜 DOM 结构。

**验收方式**：给行类型各写一条断言，并且**成对写**「该有」和「不该有」——
`Think 行角标在 flow item 上` + `折叠头里没有角标`；`兜底行角标在父容器上` + `折叠头本身干净` + `整行只有一枚`。只写「有角标」会漏掉这种位置错误。

## 插件状态异常：先读 bundle 的 error，最常见是 overlay 写成 // 注释

**先看 bundle 级 `error`，不要预设是哪个插件。**
`plugin_manager list_bundles` 的每个条目都可能带 `error: { code, diagnostic }`，
`diagnostic` 里通常直接写着**文件路径、行号和解析原因**。用户报"某个插件异常"时，
先用它定位到底是哪一个——实测出现过用户以为是 A 插件，实际是 B 插件的情况。
交叉判据：被怀疑的插件若 `/health` 正常、且它的 bundle 条目没有 `error`，它就不是故障源。

**最高频的一类：overlay 的 YAML 注释写成了 `//`。**
bundle 的 `cordis.patch.yml`（loader overlay）是 **YAML**，注释只能用 `#`。
写成 JS 风格的 `//` 会让解析器在那一行直接失败，报
`YAMLException: end of the stream or a document separator is expected (n:1)`，
**整份 overlay 作废** → 该 bundle 在插件列表里显示异常、它的 row 也不注册。
这类错误与 DSH 版本升级无关（任何版本的 YAML 都不接受 `//`），不要往升级上归因。

**修法与核对**
- `link:` 形态的 bundle，`<profile>/node_modules/<name>` 是软链，改**源目录**即可，
  改完核对两处首行一致（`Get-Content -TotalCount 1`）。
- 复验用 `list_bundles` 带 `offset` + `limit:1` 精读那一条，确认 `error` 消失、
  `rows` 重新出现——整份列表输出很大，不要整份重拉。
- 只修故障本身；原本 `enabled: false` 的插件**不要顺手打开**，那是用户的意图。

**通用纪律**：插件"状态异常"时先读诊断字段，再动手；诊断字段里往往已经有答案，
凭猜测去改代码或重装，成本高且容易把故障带到别处。

## 升级后判定插件行是否还在：fiberPhase 与 unaddressable 的区别

## 升级后判定插件行是否还在：看 fiberPhase，别看 set_plugin 成败

**症状**：DSH 升级后，对自建插件行跑 `plugin_manager set_plugin` 得到：

```
{"application":"failed","error":{"code":"unaddressable"},
 "nextStep":"This entry has no unique profile patch target; tell the user to edit the profile patch file directly."}
```

很容易据此误报"升级把插件弄坏了"。

**真相**：`unaddressable` 是**寻址**分类，不是加载状态。判加载只看 `list_plugins` 里的 `enabled` + `fiberPhase`：

| 结果 | 含义 |
| --- | --- |
| `application: applied` | 行存在、管理器能改、已生效 |
| `error.code: unaddressable` + 表里 `fiberPhase: active` | **行正常加载**，只是管理器不能再开关它（需直接改 patch 文件） |
| `error.code: unknown-plugin` | 行不存在；若刚改过 patch，索引可能未重建 → **等 1~2 秒重试一次** |

**根因**：由 profile patch 的 `- insert:` 直接插入的行**没有 `patchId`**；bundle 带进来的行有。新版本会把无 `patchId` 的行标成 `readOnlyReason: "unaddressable"`（同表的 `dsh-*-native` 等内置插入行同样如此）。

**想让管理器重新能开关它**：把包做成 bundle —— `package.json` 里声明 `dsh.bundle.patch`，profile 的 `dsh.profile.bundles` 登记包名，然后**删掉**手写的那段 `- insert:`（否则会重复注册）。代价：bundle 列表只在启动时读取，改动需要重启宿主才生效。

**廉价取证：只取表的尾部。** profile patch / bundle 插入的行排在 roster 最后，用 `list_plugins(offset = total - 25)` 一屏就能看到它们，不必拉全表（大版本里常有 200+ 条）。

### 另一个会骗人的取证陷阱：压缩串里的引号形式会变

宿主客户端 bundle 是压缩产物，同一符号的**引号样式可能随版本改变**。实例：同一个 seam 在 A 版本是

```js
ctx.uiConversation.binding(binding).target("chat")
```

在新版本变成

```js
ctx.uiConversation.binding(binding).target(`chat`)
```

按 `"chat"` / `target("chat")` 做字面量 grep 会得到 **0 命中**，从而误判"seam 被删了"。对策：

1. 搜**调用点**而不是字面量：`\.target\(`、`faceOf\(`、`nodes\.get\(` 这类结构模式；
2. 命中后读上下文 70~140 字符，确认实参的**语义**（id 是否仍是同一个字符串）；
3. 批量比对多个符号时，先把引号掩码掉（统一成 `'` 或去掉）再匹配。

同理，`"chat",` 这种"字符串 + 逗号"的字面量也会因压缩换行/空格而失配，不要用它当证据。

### 升级核对顺序（配合 `dsh-doc` 的 upgrading.md）

1. 取新版本号（`app.asar` 里任一 `@deepseek-ai/dsh-*` 的 `package.json.version`）。
2. 读官方 `docs/upgrade-guide/v<旧版本>/` 那一节，逐条对照插件**实际用到的面**（服务、事件、slot、DOM 契约、包字段、patch 方言）；报告"用到的"与"跳过的及理由"。
3. 再按上面的办法扫契约字符串 + 看 `fiberPhase`，两者都过才算兼容。
4. 单测只能证明插件自身逻辑不回归，**不能**证明宿主契约没变；反之契约在也不等于画面对，最终仍需浏览器里一行 `__<plugin>` 自检。

## 跨版本升级兼容性核查：定版本、取指南、用冒烟定论

用户说"升级了 DSH，检查某插件有没有兼容性问题"时，**先定版本、再取指南、最后用冒烟定论**——不要凭印象或只读代码。

## 1 定版本与指南（只读）

- 运行版本：`<DSH_INSTALL_DIR>/package.json` 的 `version`；`DSH_PROFILE=desktop` 表示桌面 profile。
- 指南索引：`<DSH_INSTALL_DIR>/docs/upgrade-guide/README.md`，每个 `## v<T>` 一节描述"从 vT 升到下一个版本"要改什么。
- **先只打印章节标题**（一行一条），按"用户从哪个版本升上来"选最近几段，再按需读具体 `guide.md`。整份索引很长，别整份读。

## 2 在 ASAR 里读东西的正确姿势（本机必踩）

- 必须用 `$env:DSH_NODE_EXECUTABLE`（Electron 本体）+ 环境变量 `ELECTRON_RUN_AS_NODE=1` 启动，普通 node 读不进 `app.asar`。
- **PowerShell 5.1 没有 `ProcessStartInfo.ArgumentList`**（PS7 才有）：用它必然报 `不能对 Null 值表达式调用方法`。
  做法：把探针写成 `.cjs` 文件，然后 `$start.Arguments = '"' + $probe + '"'`。
- **判"某 API 还在不在"不要拼目录猜**：`DSH_INSTALL_DIR` 指向 `@deepseek-ai/dsh` 包内部，其 `node_modules/@deepseek-ai` 与 app 层 hoisted 的依赖**不是同一处**；
  直接拼 `<root>/node_modules/@deepseek-ai/<pkg>` 会全部 MISSING（实测四个包全 MISSING，与事实相反）。
  正确姿势：`require.resolve('<pkg>/package.json', { paths: [process.env.DSH_INSTALL_DIR] })` 拿真实目录再扫。

## 3 用"冒烟"而不是"考古"定论

读指南只用来**缩小怀疑面**；最终判据是实测：

1. 对改动过的高频表面做**代码级 grep**，命中数为 0 就是"未使用"的硬证据（比"我觉得它没用到"可靠）；
2. 重载插件看启动日志：服务是否**逐个 `service bound`**、索引是否加载成功、健康端点是否返回、中继是否 online；
3. 升级前是否已有**成功的功能调用**记录（例如一次真实请求的响应日志）——有，说明那条链路在目标版本上已经工作过。

## 4 报告纪律

必须写清：用了哪些指南、跳过了哪些**及原因**、以及"无兼容问题"的依据是"命中 0 + 冒烟通过"，而不是"看起来没问题"。

## 5 顺带体检

第三方 bundle 若 `package.json` 里既无 `engines.dsh` 也无 `peerDependencies`，
升级时**不会有任何兼容性预警**：未来的不兼容会以"静默失效"出现。
发现这种情况要主动指出（是否加约束由用户决定）。

## 把兼容性结论落成可核对的文档（含 engines 的边界与远端核实）

兼容性结论写进仓库时，**不要只写一句"支持 DSH X.Y"**——那种句子无法被核对，也无法在下次升级时产生作用。按下面的结构写，才对下一个人（和下一个自己）有用。

## 文档结构（六段，缺一不可）

1. **已验证版本**：写具体版本号 + profile + 平台，并列出**实测通过的项**（哪些服务绑上了、哪条读取链路跑通、哪个外部连接建立）。
2. **依赖的表面清单**：一张表，逐个列出用到的 API/服务及其用途。这是升级时的对照清单。
3. **明确不涉及的表面**：显式列出"不用"，否则读者会以为要逐项审查全部变更。
4. **免于影响的依据**：给出代码级证据——对本次升级指南里的改动表面做 grep，命中数为 **0**。写"命中 0"而不是"我觉得没用到"。
5. **异常排查线索**：把"失效长什么样"写成可执行的判据，例如
   `service bound: <name>` 缺失 ⇒ 该服务接口变了；
   索引类日志数量归零/报错 ⇒ 持久化格式变了；
   外部连接正常但功能异常 ⇒ 问题在数据面不在链路。
6. **未验证范围**：显式标注哪些版本没验证过，别让下界声明被读成"永久兼容"。

## `engines` 的语义边界

在 `package.json` 里声明 `engines.dsh` 等约束是**好事，但它只是一个下界声明**：
它表达"已验证到这个版本"，**拦不住未来的破坏性变更**（服务改名/签名变化仍会在运行时炸）。
所以约束必须与第 5 段的排查线索配套；只加 `engines` 而不写判据，等于把"静默失效"包装成"看起来有保障"。

## 远端核实：抓不到就用 SHA 等价

改完文档要确认远端真的带上，别只看 `git push` 返回 0：
- 能抓 raw 的（如 GitHub）直接抓原文匹配关键串；
- **反爬导致 403 的（如 GitCode raw）不要反复换抓法**——直接比两端的 `main` 提交 SHA：
  git 对象是内容寻址的，**同 SHA 即同树**，README 字节必然一致。这是比"再试一次"更硬的证据。

## 何时 bump 版本

纯文档 / 清单改动（无运行产物变化）**不 bump 版本**，只移动 tag；
版本号留给"运行时可感知的变化"，否则用户按版本号判断"要不要刷新"会失效。

## unaddressable 的真正条件：同一模块被声明两次

## `unaddressable` 的真正条件与修复（同一模块被声明两次）

> 更正：上一节把 `unaddressable` 归因于「patch `- insert:` 的行没有 patchId」，**不准确**。同样是 patch insert 的 `ui-stats` 就带着 `patchId`。真正的判定在管理器源码里：

```js
const rows = flatten(composeEntries([readProfilePatches("dsh", this.profile)]));
const candidates = rows.filter((row) => row.id === actual?.options.id);
if (candidate === undefined || candidates.length > 1
    || candidate.name !== entry.moduleName
    || actual?.parent.tree.ctx.fiber.entry?.id !== "include")
  return { ...entry, readOnlyReason: "unaddressable" };
return { ...entry, patchId: candidate.id };
```

即行可寻址需同时满足：**唯一命中** `id`、`name` 与模块名一致、父 fiber 是 `include`。

### 最常见死因：声明了两次

一个本地插件如果**既登记进 `dsh.profile.bundles`，又在 `cordis.patch.yml` 里手写 `- insert:`**，`candidates.length > 1` → 立刻 `unaddressable`。此时插件**仍然正常 active**（角标照画），只是管理界面里开关不了、`set_plugin` 报错，很容易被误读成"升级把它弄坏了"。

### 修复：只保留一份声明

| 想要 | 保留 | 代价 |
| --- | --- | --- |
| 改动**热生效**、不用重启 | 手写 `- insert:`；从 `dsh.profile.bundles` 去掉那次登记（`dependencies` 的 `link:` 保留，解析照常） | 行没有 bundle 语义 |
| 管理器**可开关**、把它当正式 bundle | 登记进 `dsh.profile.bundles`，删掉手写 insert（包内已有 `dsh.bundle.patch`） | bundle 列表只在启动时读，**需重启宿主** |

改完的验收顺序（都不用重启，除非你选了第二种）：

1. `list_plugins(offset = total - 6)` 看该行——出现 `patchId: "<rowId>"` 即成功；
2. 再 `set_plugin include:<rowId> enabled=true`，应返回 `{"application":"applied","changed":false}`。

### 顺带的发布前检查：patch 文件首行必须是 `#`

`cordis.patch.yml` 若把注释写成 `//`（在 JSON/JS 里很顺手的写法），YAML 会把整行当成**标量**而不是注释，导致 bundle patch 解析失败——而插件往往因为另有一条手写 insert 仍在工作，**故障被完全掩盖**，直到别人把这包装成 bundle 才炸。

发布前用一条命令自查：`Get-Content cordis.patch.yml -Encoding utf8 | Select-Object -First 3`，确认首行是 `#`、且 `- insert:` 是顶层序列项。

## HMR 事务嵌套锁：连撞两次就停手，版本三处可不一致

热重载插件时经常撞上这个错误，原文：

```
HMR transactions cannot be nested
{ "changed": false, "application": "failed" }
```

它的含义是：**当前那次 HMR 事务还没收尾，新的重载请求进不来**。此时 `changed=false` 说明**什么都没变**，重试通常还是同样的结果。

## 处置纪律

1. **同一会话里连撞两次就停手**。第三次、第四次不会更容易成功，只会消耗时间与预算。
2. 判断这次变更**值不值得**为它去冒重载的风险：
   - 只改**版本号字符串 / 文档 / 注释** ⇒ 不值得。登记"仓库已是新版、运行中仍是旧版"，说明二者行为等价。
   - 改的是**运行期逻辑** ⇒ 必须生效，改用重启宿主（HMR 锁随宿主重启清空），而不是继续戳。
3. **不要用"禁用再启用/删除再安装"来绕过**：那会丢运行时状态，还可能把插件带进更糟的半挂状态；HMR 锁不会因此解开。
4. 交付时**如实登记三处版本**，并说清各自代表什么——它们本来就允许不同步：

   | 位置 | 含义 | 何时更新 |
   | --- | --- | --- |
   | 仓库清单（`package.json` 等） | 源码版本 | 提交即变 |
   | 运行中实例（健康接口报的版本） | **内存里真正在跑的代码** | 重载/重启才变 |
   | 线上静态产物（构建哈希 + 前端版本串） | 用户实际加载的前端 | 发布后变 |

   只有"运行中实例"落后时，功能不受影响（若本次只改版本号）；若改的是逻辑，就必须重启，否则你以为改了其实没生效。

## 查当前装的是哪版 DSH、这一版改了什么（发行取证链）

## 查"当前是哪一版"与"这一版改了什么"

用户问"最新发行版有什么新特性/修了什么 bug"时，按下面的顺序取证，别只信一个来源。

1. **本机版本**：`$env:DSH_INSTALL_DIR/package.json` 的 `version`（`@deepseek-ai/dsh`）。桌面打包版另看 `...\resources\app.asar\dsh\package.json`（`@deepseek-ai/dsh-desktop-runtime`），两者一致才算确认。
2. **渠道与最新版**：桌面端 `resources\app-update.yml` 给出 `provider` / `url` / `channel`（渠道名 `nightly` 或 `stable`；`stable` 是从旧名 `latest` 改的，无别名）。把 `url` 与 `<channel>.yml` 拼起来：
   - `https://download.deepseek.com/dsh-desk/feeds/win-x64/nightly.yml` → `version`、`releaseDate`、`sha512`。
   - 同目录下 `latest.yml` / `stable.yml` 会 404，**别把 404 当成"没有正式版"**。
   - `web_fetch` 拒收 yaml：`Error: unsupported content type "application/yaml"` → 用 `[System.Net.WebRequest]::Create($u)` 取流 + `[Text.Encoding]::UTF8.GetString($ms.ToArray())` 读原文（别用 `Invoke-RestMethod`，中文会按 Latin-1 乱码）。
3. **真正的 release notes**：仓 `github.com/deepseek-ai/deepseek-harness` 公开，`GET https://api.github.com/repos/deepseek-ai/deepseek-harness/releases?per_page=30`，tag 形如 `dsh-v<version>`，全部 `prerelease: true`；正文中英双语，分「新增功能 / 体验优化 / 问题修复 / 其他变更」四节。单版正文 7–28 KB，用 Python `urllib` 落盘再按需 read，别整段灌进上下文。
4. **npm 侧的坑**：`registry.npmjs.org/-/package/@deepseek-ai/dsh/dist-tags` 里 `latest` 可能**落后**于 `next`（rc 线发到 `next`）。只看 `latest` 会得出"最新版是旧版"的结论；要判断时间线得读 packument 的 `time` 字段排序。另外 DSH 至今没有 `x.y.z` 正式版，全是 alpha/rc，"最新发行版"= 最新预发布版。
5. **发行包自带迁移说明**：`docs/upgrade-guide/README.md` + 各节 `guide.zh.md`，讲"从某版升到下一版要改什么"。**它的分节与 GitHub Release 不是严格一一对应**（同一主题的迁移说明和公告会落在不同版本）→ 判断"哪版发布"只认 Release + yml，指南只用来查"该怎么改"。

读 asar 内文件的姿势：文件用 read 工具直接读；要**列目录**得用 electron 以 `ELECTRON_RUN_AS_NODE=1` 跑 `fs.readdirSync`（原生 glob / grep / cat 进不去 asar，会报 `系统找不到指定的路径`）。启动该进程时注意 `ProcessStartInfo.ArgumentList` 在本机不存在，见 skill `pwsh-on-windows`。

## 升级后官方插件从插件页消失：退役 / 内置 / 改名三选一

## 何时调用

用户问「上个版本还能看到的官方插件/开关，这个版本怎么没了 / 是不是被砍了 / 现在在哪开」，或你要判定某个能力是**内置**、**可装 bundle**，还是**已退役**时。前置：知道 `DSH_INSTALL_DIR`（本机在 `app.asar` 内）；后继：要改配置回本文开头的「五层 + 上线纪律」。

## 判定顺序（全只读，先别假设"被删了"）

1. **查退役名单**：`<DSH_INSTALL_DIR>\node_modules\@deepseek-ai\dsh-official-bundles\lib\index.js`
   - `RETIRED_BUNDLES`（0.2.2-rc.2 在 `:21`）注释原文：`Bundles an earlier release shipped and the installation no longer carries; app-boot removes them from profiles.` ⇒ 上一版随包发过、这一版**不再携带**，且**加载时会从 profile 组合里删掉**。这是"插件页条目凭空消失但功能还在"的第一嫌疑人。
   - `OPTIONAL_BUNDLES` / `EXPERIMENTAL_BUNDLES` / `MORE_BUNDLES` / `OFFICIAL_ON_DEMAND_CATALOG`：当前版本插件页会出现的官方条目全集。**不在这几张表里 ⇒ 它根本不是 bundle**，永远不会作为插件页条目出现（不是被下架）。
2. **查它是不是 bundle**：读包 `package.json`。有 `dsh.bundle.patch` 才是可安装 bundle；只有 `dsh.client`、或**连 `dsh` 键都没有** = 普通插件包，只能被某个 bundle 的 patch 行挂载。
3. **查是谁挂的**：`@deepseek-ai\dsh-base\cordis.patch.yml`（宿主能力）与 `@deepseek-ai\dsh-web-app\cordis.patch.yml`（Web UI）。行里有 `id:` + `name:` ⇒ 随包内置，不是可选插件。
4. **查入口搬到哪了**：`<DSH_INSTALL_DIR>\docs\upgrade-guide\README.md` 是**本安装版本**的迁移索引（按版本段列条目 + 指向 `guide.zh.md`）；功能改名、开关搬家、斜杠命令移除都记在这里，是"为什么变、迁到哪"的本机权威答案。
5. 需要确认是否真的跑起来：`plugin_manager list_plugins` 看 `enabled` / `fiberPhase`（`active` = 已挂载），比在 UI 里找更快。

## 实例：Agent Teams「智能体团队」（2026-11-12 取证，0.2.2-rc.2）

- **旧形态**：`@deepseek-ai/dsh-experimental-agent-team-profile`（插件页里一个"实验性"开关）＋ `dsh-experimental-agent-team` / `-tool-agent-team` / `-client-ui-agent-team`。
- **现状**：旧 bundle 只在 `RETIRED_BUNDLES` 里（包目录已不存在）；三个包改名为 `dsh-agent-team` / `dsh-tool-agent-team` / `dsh-client-ui-agent-team`，分别由 `dsh-base`（`cordis.patch.yml:366-372`）与 `dsh-web-app`（`:412-413`）内置挂载 ⇒ **不再有插件页条目**。
- **入口搬到会话菜单**：`docs\upgrade-guide\v0.2.1-rc.2\session-team-mode\guide.zh.md:12`「Agent Teams 随基于 base 的 profile 提供；**新 Session 默认关闭**。插件页不再提供独立的智能体团队开关。」；`v0.2.1-rc.3\team-mode-menu\guide.zh.md:12`「`/team on` 和 `/team off` 不再注册」。同一份 guide 的迁移节还给了包名替换映射（`dsh-experimental-*` → `dsh-*`）与"加载时移除旧组合选项"。
- **判据**：插件页里现在只会出现子包的中文名「任务板」(`dsh-client-ui-agent-team\locale\zh.json`) / 「团队工具」(`dsh-tool-agent-team\locale\zh.json`)；**不会再有**叫「智能体团队」的条目——不是删除，是毕业。

## 顺手：用户问「super agent 是不是 DSH 的新功能」

`deepseek-ai/dsh-superagent-prototype`（GitHub，2026-10-31 创建）是**外部 bundle**，README 原文：`Research prototype for reference only, not an official DeepSeek product.` 与 `packaged as a bundle for DeepSeek Harness`；装进**独立 profile**（`dsh superagent --from-default-profile`），不在发布包里。本机反证：全 asar 搜 `superagent` / `super agent` / `超级智能体` 在产品代码与文档里 **0 命中**（只有 got / undici 的第三方 README 提到同名 HTTP 库）。⇒ 回答口径：**能装进 DSH，但不是 DSH 自带**；媒体报道的"DeepSeek 发布超级智能体"与 repo 自述冲突，以 repo 为准。

## 坑

- 别用 `Test-Path` / `Get-ChildItem` 在 `app.asar` 里找包：对原生 FS 不可见，恒 `False`（假阴性）。列目录要用 `ELECTRON_RUN_AS_NODE=1` 跑 `<DSH_NODE_EXECUTABLE>` 的 `fs.readdirSync`，或用宿主 `read` 直接读已知路径。
- 别只读 `docs\user\`：用户文档大多是跳转页，真正解释"东西去哪了"的是 `docs\upgrade-guide\`。
- 别把"我这一版没有这个 bundle"说成"官方删了/砍了"：先按第 1 步分类，`RETIRED` 与"被下架"是两种不同的结论。

## 回答"为什么改成这样"：上游决策笔记 + upgrade-guide 版本段语义

## 硬坑：upgrade-guide 的版本段不是"生效版本"

`<DSH_INSTALL_DIR>\docs\upgrade-guide\README.md:3` 原文：`A v<T> section lists what to change when upgrading from release vT to the release after it; vT is the release being left, not the target.` ⇒ 段名 `v0.2.1-rc.2` 里的条目，**实际落地版本是 0.2.1-rc.3**。按段名回答"哪一版变的"必然错一版（本轮差点这么答）。

## 想知道"为什么改成这样"：本地 docs 没有，去上游决策笔记

本地 `docs\` 里的 team / 迁移类条目**只有"怎么做"，没有动机句**（全量扫过：中英同文，英文版也没多写）。真正的理由在上游仓库 `deepseek-ai/deepseek-harness` 的 `.agents/notes/implemented/{feature,architecture,process,simplification}/<YYYY-MM-DD>-<slug>.md`（头部 `Status: implemented`），notes 之间互相引用，并指向对应 upgrade guide。

取数（比 GitHub MCP 干净、不截断，实测 HTTP 200）：

```
web_fetch https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/.agents/notes/implemented/architecture/2026-10-20-session-team-mode.md
```

本轮验证过的三份（回答"某个功能为什么改形态"时的样板）：

- `feature/2026-08-05-agent-teams.md`——当初**为什么不做进默认 catalog**：Alternatives 原文拒绝 `Enable Teams in the default catalog`，理由 "unsolicited coordination and Team tool schemas would add latency and token cost to simple tasks"。
- `architecture/2026-10-15-agent-teams-as-subagents.md`——成员统一成 subagent 身份；独立 roster "duplicates identity, provisioning recovery, and teardown"，Team 专属工具 "shadow the standard subagent tools, forcing profiles to disable ordinary delegation"。
- `architecture/2026-10-20-session-team-mode.md`——**形态错位的直接证据**：插件级开关要求为"一次会话的协作决定"去改**共享 profile**，"It can disable another Session's capability and leaves a second control beside the Session selection"；Alternatives 否掉"保留两个开关"与"只藏插件卡不加载 Team"（后者 "would violate product isolation; moving them to their owning product groups makes the delivered support explicit"）。

## "正式 / 官方"≠ 成熟

`packages/experimental/README.md#status` 原文：`Official means the project maintains and lists the package in the Plugins page. Neither describes maturity; publication, default installation, and GUI visibility do not determine maturity either.` 升格条件是五条可验收项：named product role / documented public behavior and limitations / current consumers / release contents / test evidence，"Move the package to its product group and update affected consumers together"。⇒ 用户说"某某变成正式功能了吗"，先按这五条与"默认开没开"回答，别用"进了插件页 / 进了默认包"当成熟度。

## 取证坑

- `mcp__github__list_commits` 的 `path` 过滤**静默失效**（不报错，返回全仓最新提交）；`search_issues` 不带 `is:issue` / `is:pull-request` 会 422。
- **release notes 常常只写"怎么迁"甚至一字不提**：`dsh-v0.2.1-rc.2` / `-rc.3` 的发布说明都没有 team 段落，但变更确实发生了。别把"release notes 没写"当"没发生"，判版本要用 upgrade-guide + 安装体里的 patch 行。
- 判"某个开关现在在哪"要落到安装体：`dsh-base\cordis.patch.yml`（服务与工具行）/ `dsh-web-app\cordis.patch.yml`（UI 行）/ `plugin_manager list_plugins`（`enabled`+`fiberPhase=active`）。`docs\user\guide\` 往往**还没有**对应章节（Agent Teams 就是：服务内置、UI 齐全、用户手册无独立页）。

## 界面开关关着却仍生效：bundle 与手写 insert 是两套机制

## 界面开关关着、插件却还在跑：bundle 与手写 insert 是两套机制

**症状**：插件界面里这一项显示"未启用"，但功能照常生效（角标照画、面板照出）。

**根因**：`package.json` 里 **有依赖、但没有进 `dsh.profile.bundles`**，而真正的加载来自 profile `cordis.patch.yml` 里手写的 `- insert:`。两条路径互不相干：

| 写法 | 谁控制它 | 生效时机 |
| --- | --- | --- |
| 依赖 + `dsh.profile.bundles` 登记（包内带 `dsh.bundle.patch`） | **界面开关**（开关就是在改 `bundles`） | 启动时读 bundles ⇒ **需重启** |
| profile patch 里手写 `- insert: - id/name` | 没人控；文件在就加载 | **热生效**（改完即应用） |

所以为了"改完不用重启"而选了手写 insert 的插件，等于**绕过了界面开关** —— 用户关掉的只是 bundle 那一侧。

### 怎么选（二选一，别混用）

- **要开关有权威** → 走 bundle：依赖 + 写进 `dsh.profile.bundles`，并**删掉** profile patch 里的手写 insert。代价：改动需重启。
- **要热生效** → 只留手写 insert，并**把包从 `dependencies` 里去掉**（否则界面里仍会显示一个永远关不掉/无意义的开关）。代价：没有图形开关。
- **两者都留** → 候选项重复 ⇒ 该行变 `unaddressable`（见上节），且开关依旧无效。

> 更正上一节的一个读法：「删掉 bundle 登记让 patch 行可寻址」只在**你要热生效**时成立；若目标是让开关能控，必须反过来做。

### 改完为什么"看起来没生效"

插件行一旦加载，**改文件不会热卸**；`bundles` 又只在启动时读。所以删掉 insert 之后 `list_plugins` 里那一行**仍显示 active**——这是旧进程残留，不是改失败。验收方式：文件侧确认 patch 里该 id 已消失 + YAML 仍可解析，再**重启**一次看运行时。

### 核对清单（一行一条）

1. `package.json`：包在 `dependencies` 里吗？在 `dsh.profile.bundles` 里吗？
2. `cordis.patch.yml`：有没有同 `id` 的手写 `- insert:`？
3. 三者只能"两者成立"：**依赖 + bundles**（开关控、需重启）或 **仅 patch insert**（热生效、无开关）；三条同时成立必坏。
4. 改完 `python -c "import yaml,io;yaml.safe_load(io.open(p,encoding='utf-8'))"` 验一次 YAML，再重启验证运行时。

## 更正：插件页两种开关（bundle 级 / 行级）都是热生效

## 更正：插件页的两种开关都是热生效的（不必重启）

> 上一节说"bundle 变更需重启"，那是按"bundles 只在启动时读"的先验推断，**实测不成立**。本版本（0.2.2-rc.2）两种开关都即时应用。

插件页其实有**两种开关**，调的是两个不同的远端方法：

| 开关 | 方法 | 作用对象 | 副作用 |
| --- | --- | --- | --- |
| 包级（插件条目那一行） | `setBundleEnabled(packageName, enabled)` | `dsh.profile.bundles` 列表 | 关掉 = 从列表移除，该包提供的行立刻消失 |
| 行级（条目里的每一行） | `setPluginEnabled(entryId, enabled)` | profile `cordis.patch.yml` | 自动追加/删除 `- id: <rowId>` + `disabled: true`，且**关→开会把这段删干净**（自清洁） |

### 热生效的判据（不用重启，两次调用即可自证）

1. 记录 `list_plugins` 的 `total`；
2. 关掉开关，返回应为 `{"changed":true,"application":"applied"}`，再看 `list_plugins`：`total` **减一**、目标项消失（或 `enabled:false` + `fiberPhase:null`）；
3. 打开开关，`total` 恢复、该项回到 `fiberPhase:"active"`。

只要 `changed:true` 且 total 跟着动，就是真的热生效；**不要用"改完重启再看"来敷衍**。

### 因此选型规则要更新

- 想让开关有权威、又不想重启：**依赖 + `dsh.profile.bundles` 登记即可**（不必为了热生效去手写 `- insert:`）。
- 手写 `- insert:` 仍然可用，但它会与 bundle 登记**争同一个 `id`** ⇒ 候选重复 ⇒ 该行变 `unaddressable`（见前节），而且开关形同虚设。**同一模块只保留一种声明。**

### 未验证（需真机确认）

浏览器侧已注入的客户端代码是否在关闭开关时**即时** dispose：主机侧确认是即时的，但页面里已加载的模块可能要到刷新才彻底消失。本插件 `apply()` 返回了清理函数（移除角标与观察器），理论上会即时清理——这一条必须看真页面，不能只看 `list_plugins`。

## 补：super agent 与 DSH 的架构层关系（bundle / preset / 独立 profile）

### 三个层次（回答"它跟 DSH 是什么关系"时按这个顺序讲）

1. **形态**：它不是 DSH 功能，是一个 **bundle**。`package.json` 里 `"dsh": {"bundle": {"patch": "./cordis.patch.yml"}}`，`engines.dsh: ^0.2.1-alpha.2`，peerDependencies 全是 `@deepseek-ai/dsh-*`（session / tools / agent / permission-presets / client-ui-* …）。⇒ DSH 是运行时与扩展框架，它是上层应用。
2. **运行**：装在**独立 profile**（`dsh superagent --from-default-profile`，见 SETUP.md / `docs/006-deployment.md`），与日常 profile 隔离；往宿主里新增两样东西——两个 agent preset（主会话 `dsh-superagent-router` = `ROUTER_PRESET`；执行者 `WORKER_PRESET`，定义在 `cordis.patch.yml`）和三个插件（核心 + GitHub Source + 飞书 Source，飞书默认关）。面板是 DSH web client 插件。⇒ 全程走 DSH 的扩展点，不改本体一行。
3. **概念**：DSH 自带的多 agent 原语是 subagent / workflow / agent-team（进程内 fork/spawn、脚本编排、一次性任务）；super agent 是**产品形态**——常驻、事件驱动（监听 GitHub/飞书）、有授权模型（Policy → Mandate → Ticket）、每件活在自己的 DSH Session 里跑完再回原会话交 PR。它内部就是用 DSH Session 承载 Router/Worker 两层、用 DSH 的 subagent/skill/jobs 工具干活。⇒ 同一底座上的两种"agent 长什么样"。

### 事实源（都可复核）

- 仓库 `deepseek-ai/dsh-superagent-prototype`，包名 `dsh-superagent` v0.1.0，MIT，`author: DeepSeek Harness Team <team@dsh.dev>`，repo description `Towards a More Autonomous Agent System`。
- README 首行：`Research prototype for reference only, not an official DeepSeek product.` ⇒ **"官方团队出品" ≠ "官方产品"**，媒体标题（"DeepSeek 发布编程 agent"）是二手解读。
- `docs/007-architecture.md`：14 个主会话 `orchestrator_*` 工具；SQLite `orchestrator.sqlite`；`tests/bundle-patch.spec.ts`「The bundle's patch, read as DeepSeek Harness reads it」。
- 本机 0.2.2-rc.2 反证：480 个 docs md / 337 个 `@deepseek-ai` 包 / 30 个 profile bundle 均无它，preset 只有 standard/ptc/minimal/cordis ⇒ **发布包不含**，要玩必须单独装。
- 易混淆：第三方 `dsh-super-ptc-mode`、`dsh-superpowers-preset`（名字带 super 的 preset，无关）；`got`/`undici` README 里的 `superagent` 是 HTTP 库。全树搜 `super` 会大量命中 JS `super` 关键字与 `superseded`。

## 在打包版 ASAR 里读源码，并快速判"智能体团队协作"成熟度

## 前提：先确认是不是打包版

`DSH_INSTALL_DIR` 形如 `<安装根>\resources\app.asar\dsh\node_modules\@deepseek-ai\dsh`，且 `D:\tools\dsh` 下是 `DeepSeek Harness.exe` + `resources\app.asar` → 走本节。若是源码 checkout（`pnpm-workspace.yaml` 在根），直接用 `glob`/`grep`。

## 在 ASAR 里取证

- `read` 工具**能**直接读 ASAR 内路径，已知文件就直接读，别绕。
- `glob` / `grep` / `Get-ChildItem` / `Get-Content` 对 `app.asar\...` 是黑盒：返回空输出 + `[exit code: 1]`，或 `PathNotFound`。**这不是路径写错**，别反复试。
- 列目录 / 全文搜：写一个 `.js`，用 `ELECTRON_RUN_AS_NODE=1` 把 Electron/DSH 可执行文件当 node 起，它会穿 ASAR。最省事的封装是 Python：

```python
# run.py <script.js> [args...]
env = dict(os.environ); env["ELECTRON_RUN_AS_NODE"] = "1"
subprocess.run([EXE, script] + extra, env=env, capture_output=True)  # EXE = D:\tools\dsh\DeepSeek Harness.exe
```

子脚本里 `process.argv[2]` 是第一个参数；搜索时先 `fs.statSync(f).size` 过滤 >1MiB 再读。

- 行号只认 `src/*.ts`；`lib/*.js` 是另一份构建产物，行号对不上。

## 踩过的坑

- 照抄文档里的 PS7 写法 `$start.ArgumentList.Add($a)` → `不能对 Null 值表达式调用方法。 (InvokeMethodOnNull)`，而命令**仍 exit 0**，得到"假通过"。Windows PowerShell 5.1 的 `ProcessStartInfo` 没有 `ArgumentList`（.NET Core 才有）。修法：改用上面的 Python 封装，别在 PS 里跟引号搏斗。
- 搜索过滤器传 `"dsh-subagent/src/"` 命中 0 条：ASAR 内路径分隔符是反斜杠，先 `.replace(/\\/g,'/')` 再比。

## 判"智能体团队协作"成熟度：5 个可验证闸

1. `docs/user/` 有没有独立章节（写清限额、失败处理、什么任务不该用）
2. `subagent` 与 `workflow.agent()` 两条创建路径是否共用同一套深度/配额校验
3. 子代理失败是否回传结构化结论（而不是散文）
4. `interrupt` 是否默认开启且能打断正在跑的工具调用
5. 团队面板是否有成员实时态与空态

0.2.2-rc.2 实测基准：`TeamId` = 根 SessionId（`dsh-agent-team/src/types.ts:7-17`）、`maxDepth` 默认 1、`maxActiveSubagents` 默认 8（`dsh-subagent/src/index.ts:195-198`）、`defaultEnabled` 默认 false（`dsh-agent-team/src/index.ts:51`）、standard preset 里 `interrupt: false`（`presets/standard.patch.yml:95-98`）。结论：2 层星型可用，团队协作未闭环 — 升版后按上面 5 条重跑即可定级。

## 让「智能体团队协作」默认开启（agent-team 行配置覆盖）

## 何时用

用户说「团队模式默认关着 / 帮我默认开启 / 每个会话都要手动点」时。这是**插件行 config 覆盖**，不是新层、不新增插件行。

## 事实（0.2.2-rc.2 实测）

- 行 id 是 **`agent-team`**（不是包名），`name: '@deepseek-ai/dsh-agent-team'`，由 `@deepseek-ai/dsh-base/cordis.patch.yml:366-372` 内置插入 → desktop / headless 都带 `dsh-base`，两个 profile 都有这一行。
- `dsh-agent-team/src/index.ts:49-51` 的 `Config` **只有两个字段**：`maxTasks`（默认 256）、`defaultEnabled`（`z.boolean().default(false)`）。
- 全树只有一处消费它：`Service.init` 里注册 `agent/created`，条件为 `source === 'startup'` 且 `header.origin !== 'subagent'` 且该会话没有既有选择，然后 `session.append('team/mode', { enabled })`。
- ⇒ **只影响新建会话**：已存在会话不会被改（早退），团队状态落在会话日志的事件里、不写 header。想让某个旧会话开，只能在会话菜单里单独点。
- `settings.yaml` 没有等价开关（`dsh-settings` 的 `LEGACY_SECTION_ENTRIES` 只有 ui-developer-tools / ui-onboarding / shell）。

## 写法（可直接抄）

追加到**机器级** `~/.dsh/cordis.patch.yml`（后应用、优先级高于 profile 层，对全部 profile 生效）：

```yaml
- id: agent-team
  name: '@deepseek-ai/dsh-agent-team'
  config:
    maxTasks: 256
    defaultEnabled: true
```

- 只给桌面端时放 `~/.dsh/profiles/desktop/cordis.patch.yml`。放机器级后 profile 层**盖不回 false**（home 层后应用），所以想留「按 profile 关」的余地就放 profile 级。
- 顶层是数组，此项**与已有的 `- insert:` 项并列**，别缩进进 `insert:` 列表。

## 两个必踩的坑

1. **写成 `insert:`** → 变成第二行重复挂载（两条 `agent-team`），不是覆盖。id 定位靠「有 `id`、无 `insert`」。
2. **只写 `defaultEnabled: true`** → 漏 `maxTasks` 会被 schema 默认值顶回来。`composition-reference.md:10-11` 逐字：`A patch with an id and no insert targets the existing row with that id. ... config is replaced wholesale, never deep-merged, so restate every field the row needs.` ⇒ **config 必须写全**。

## 验证（不用起 host）

```powershell
$env:ELECTRON_RUN_AS_NODE = "1"
& $env:DSH_NODE_EXECUTABLE "$env:DSH_INSTALL_DIR\lib\bin.js" --profile headless --dump-config
```

- 判据：输出里 `- id: agent-team` **恰好 1 条**、其 config 同时有 `maxTasks` 与 `defaultEnabled: true`。多一条 = 走成了 insert。
- `--profile desktop` 会被直接拒绝，原文：`error: profile "desktop" is managed exclusively by the Electron application`。desktop 侧只能靠「新建会话看开关」验证。
- 这条同时充当**冷启动组合校验**（YAML 解析 + 行合并都在内），不会创立会话、不碰正在跑的 host。

## 生效与回滚

- 生效：新建会话即开启；已在跑的会话不受影响。config 在构造期读取，所以**只对之后创建/重建的实例**有效——没看到变化就重启一次宿主。
- 回滚：删掉这段（或从 `.bak-*` 还原）。前提是**先备份**原 patch，且别覆盖已有备份。

## 值不值

团队模式常开会把 team / 任务板的工具 schema 带进**每个**会话的工具面，而工具 schema 每轮都要重发（成本按轮线性付）。上游当初就是为此拒绝「默认开启」的。用户主动要求默认开可以做，但要把这笔成本讲清楚。

## 回答"刚更新完变了什么"：先定差集，再核四处（实测 rc.2→rc.3）

### 触发信号

用户问「刚更新的这版变了什么 / 我是不是最新 / 这次更新对我有什么影响」。
前置：本文「查当前装的是哪版 DSH、这一版改了什么（发行取证链）」一节已覆盖版本/feed/notes 的取法；本节只补它没覆盖、且本轮实际踩到的四处。全只读，不改 profile。

### 1. 先定"上一版"，只分析差集

用户"刚更新完"通常只跨一个小版本，把整个 0.2.x 的大改当成本次变化会严重夸大（rc.3 说明只有 2 条，大头在 rc.2）。

- 上一版的权威取处：`~\.dsh\dsh-runtimes\dsh-primary-runtime\runtime.json` 的 `desktopVersion`（payload 里的记录会一直留到下一次 payload 重算，所以更新后仍是旧版本号，正好当"上一版"证据）。
- **别用文件 mtime 推"何时更新"**：`app.asar` / `.exe` 的 LastWriteTime 是 NSIS 保留的**打包时间**（实测比 GitHub 发布早 26 分钟，且早于 npm 发布）。安装时刻看 `D:\tools\dsh` 目录与 `app.asar` 的 **CreationTime** —— 覆盖写会刷新 C、保留 M。
- `D:\tools\dsh\version`（44.7.0）是 **Electron 版本**，不是 DSH 版本；`~\.dsh\electron\version`（43.3.0）是运行时 Electron。两个都别当 DSH 版本答。
- DSH 版本本身：`app.asar\dsh\package.json` 的 `version`，与 `desktop-runtime.json` 的 `version` / `hostProtocolVersion` 对得上才算确认。

### 2. feed yml 里还有一项值得报：灰度

`<url>/<channel>.yml` 除 `version` / `releaseDate` / `sha512` 外还有 `stagingPercentage`（0.2.2-rc.3 = 30）。它说明"最新"≠"全量"，能解释"为什么同事实时收不到"。`latest.yml` / `stable.yml` 404 是正常现象，只认 `app-update.yml` 的 `channel` 指到的那份。

### 3. 更新失败史：先去 updater 日志取证

`%LOCALAPPDATA%\@deepseek-aidsh-desktop-updater\installer-logs\directory-failure-*.log`，原文形态：

```
Operation: MoveFileExW
Windows error: 32 (另一个程序正在使用此文件，进程无法访问。)
Source: D:\tools\dsh
Destination: D:\tools\dsh.old-{GUID}
```

含义 = 旧目录被占用（DSH 进程没退干净），不是网络/签名问题。0.2.2-rc.3 的说明第 2 条修的正是"Windows 应用内更新可能失败、无法自动重新打开"；可自控的部分只有**更新前彻底退出应用（含托盘）**。
同目录 `pending\` 存已下载待装包；`update-info.json` 只有 `fileName` / `sha512` / `isAdminRightsRequired`，**不含旧版本号**，别指望从更新器缓存反推上一版。`installer.exe` / `current.blockmap` 会被原地覆盖（改内容不改父目录 mtime），所以"缓存目录 mtime 没变"不代表没更新。

### 4. 影响面体检的 3 个必查项

1. **默认值翻转**：`fs-observation-policy` 行若 profile 里无覆盖，就跟随 0.2.2 起的新默认（禁用）⇒「写/改文件前必须先读过」**不再被运行时强制**，系统提示里那句话降级为软约束。要恢复硬约束就显式 enable 该行。
2. **插件拦截力**：兼容性先读 `engines.dsh`，再读 DSH peerDependencies；两者都没有 = 升级不做任何拦截（实测 `dsh-skin-market`、`dsh-row-time` 都没有）。精确 pin 旧版 peer（如 `dsh-llm@0.2.2-rc.1`）的插件，下个大版本必失配。
3. **会话存储**：`session.v4.jsonl.zstd` 的文件名是**日志格式版本**，不是 app 版本；旧 v3/v0 只在**打开时**按 `vN-to-vN+1` 链迁移，不开就永远不迁。

### 纪律

- 版本号、时间、灰度比例必须带证据（文件:行号或 URL）；"是不是最新"只认 feed，不认 npm 标签、不认 mtime。
- 只算差集：先证明上一版是什么，再只说这次的净变化；跨版本大改单独成一节，别混进"本次更新"。
- 未验证项单列：本机 asar 与 npm tarball 未逐字节比对；`compare/<前一版>...<本版>` 未逐 commit 读。

## 外部 SaaS 接入选型：MCP 还是原生 bundle 插件（飞书实测）

## 何时调用

- 触发信号：用户问「接某个 SaaS（飞书 / 钉钉 / Slack）该用 MCP 还是插件」「这个 MCP 值不值得挂」「飞书怎么接进来」。
- 前置：已读本文 **2.7**（MCP 只有 patch 一行这个入口）、**2.8**（工具面注入量的量法）。本节只给**方向判据 + 一个完整实测样本**，不重复量法。
- 转交边界：已经决定用 MCP 要看配置字段 → 2.7；要量具体 server 的字符数 → 2.8。

## 第一步永远是判「方向」，不是判「谁更好」

同一个 SaaS 通常两条路都有，但**数据流方向相反**，选错方向后面全白做：

| 方向 | 形态 | 什么时候是它 |
|---|---|---|
| **人 → agent**（在 SaaS 里发消息/点审批，唤起 DSH 干活） | **原生 bundle 插件**（事件驱动、常驻） | 目标句里有「在飞书里指挥 / 群里 @ 它 / 审批弹到飞书」 |
| **agent → SaaS**（模型拿工具去读写） | **MCP** 或 **CLI 封装插件** | 目标句里有「帮我读飞书文档 / 发条消息 / 查日历」 |

**关键判据：事件驱动型的能力不该做成 MCP 工具。** 让模型「每轮带一堆工具」去等一个事件，是拿线性成本换被动能力。

## 成本：三条路线差一个数量级

实测样本：飞书官方 `@larksuiteoapi/lark-mcp`（0.5.1），口径按 2.8 的紧凑 JSON `{type,function:{name:mcp__<serverName>__<tool>,description,parameters}}`：

| 配置 | 工具数 | 每轮字符 |
|---|---|---|
| 默认 preset（= `preset.default`） | 19 | **48,684** |
| `-t preset.light` | 10 | 20,880 |
| `-t` 自选 3 个 | 3 | 7,964 |
| 单个重型工具（`im.v1.message.create`） | 1 | 4,544 |
| 包内全量（`--config` 枚举开） | 1274 | 3,134,764 |

把同机已挂的 `outlook --discovery`（9 工具 ≈ 4.4k 字符）当基线：**默认 preset = 11.1×，单个重型工具 = 1.0×**。

⇒ 可复用判据：**一个重型 SaaS 工具 ≈ 一整个中小型 MCP server 的量**。所以「给 SaaS 开一整套工具」是最贵的接法；三条路线成本从低到高是 **原生插件（不进工具表） < CLI 封装插件（1~2 工具） < MCP（工具数 × 单工具成本）**。

## 关键实现事实（跨 server 复用）

1. **白名单是真过滤还是假过滤，必须实测**：`lark-mcp` 的 `-t/--tools` 在**注册前**裁剪（实测单工具时 `tools/list` 只回 1 个）；但 2.8 已记过反例——有的 server 把白名单当 catalog 过滤器，暴露面不变、能力却静默丢失。判据只有一条：`tools/list` 回来的**条数和字符数**是否真降。
2. **无凭据启动失败 = DSH 侧的静默缺席**：`lark-mcp` 不带 `APP_ID/APP_SECRET` 时 **1.5s 内 `exit 1`、stdout 0 字节**（`Error: [Lark MCP] appId, and appSecret are required`）。对照 2.1 形态①：host 照样 401、工具没了。⇒ 装完必须**点名核对** `mcp__<serverName>__<tool>`。
3. **本地化不省成本**：`-l zh` 让工具数不变、字符数几乎不变（汉字被转成 `\uXXXX`）；`-c kebab` 体积不变。别拿「换成中文」当优化。
4. **`tools/list` 原始响应 ≈ 注入量**：实测 raw 单行 48,709 vs 桥接口径 48,684，只差被丢弃的 `execution`（513）。⇒ 有现成 raw 响应时可直接拿它当上界估算，误差 <2%。
5. **未验证**：DSH 侧 `streamable-http` 的 patch 配置键名（本次没取证，别照抄示例）。

## 第三方插件的审查清单（比 MCP 更容易踩）

- **`engines.dsh` 缺席 = 能装不承诺**：抽查的一批飞书插件里多数没声明，升级时不会有任何预警。看 `engines.dsh` + 仓库 `pushed_at`，**不要看周下载量**（同质包 40+ 个，下载量被均摊）。
- **默认值是发布策略，不是安全策略**：实例 `dsh-lark-link` 默认 `groupPolicy=open`（群聊免 @ 全触发）+ `allowlist=[]`（所有人可对话）+ `permissionMode=danger-full-access`。⇒ **装完第一件事是收紧这三项**，不是先试用。
- **市场索引会过期**：索引里有条目但 npm 整包 404（撤包/未发）是常态。按索引装之前先打 registry manifest。
- **事件通道不等于零成本**：省掉的只是工具 schema；常驻进程、宿主机密、谁能触发这三笔账要单独算。

> 会话专属数字（具体包名版本、下载量、探针路径）留报告，不进本 skill。
