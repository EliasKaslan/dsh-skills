---
name: dsh-agent-customization
description: DSH 改造 agent 行为的入口总纲——改了 AGENTS.md 为何不生效、插件行坏了怎么回滚、settings.yaml 改了为何没反应、这次改动属于哪一层；含五层生效时机、热重载≠冷启动、坏 row 三形态、MCP 挂载与会话日志找回旧版本。适用于"改 DSH 的行为该改哪一层 / 改了 AGENTS.md 为何不生效 / 插件行坏了怎么回滚 / settings.yaml 改了为何不生效 / MCP 怎么挂进来 / 实验包怎么挂 profile / 中文 UI 不是中文提示词 / 会话日志里能不能找回旧版本 / 会话日志怎么解压 / 本轮运行失败 / finish_reason 报错怎么判 / 上游还是 DSH 的 bug"。不适用：只离线验负载挂载 → 用 `dsh-agent-preset-verification`；只要干净实验环境 → 用 `dsh-isolated-web-host`。
whenToUse: 要改 DSH 自身行为（行为宪法 / 流程 skill / agent 组合 / 默认 preset / 插件行与 patch），或要判定改动何时生效、怎样回滚、上线前还差哪一步时，先加载本总纲。模型看不到本节。
---

# DSH「改造 agent 行为」总纲

本 skill 是**入口**：先在这里定"改哪一层、怎么生效、怎么撤、上线还差什么"，具体动作交给对应子 skill。
**单一归属**——每一步的详细命令、错误原文只写在子 skill 里，本总纲只写入口与纪律，不复制正文。

## 何时调用

- 触发信号：用户说"改 DSH 的行为 / 让它以后都这样 / 新写一个 skill / 换个 agent 组合 / 加一个插件行"，或你正要动 `~/.dsh` 下的任何一层配置。
- 触发信号：用户说"把某个 MCP server 挂给 DSH / MCP 工具用不了 / 这个 MCP 挂上去要占多少上下文"，或你正要往 patch 里写一行 MCP 插件（先读 **2.7 / 2.8 / 2.9**）。
- 触发信号：host 起了但页面打不开、改了配置不知何时生效、改完想回滚。
- 触发信号：要挂一个实验包 / 官方 bundle 进 profile，或要判断"手工 row / 空 patch 前提的脚本今天还管不管用" → 读 **2.11**；要看那个包的策略文本为什么是英文、README 指的文件为什么找不到 → 见「不要做什么」末两条。
- 触发信号：文件被**覆盖 / 没备份**，要问"会话日志里能不能找回旧版本""文件被覆盖了怎么恢复""`session.v4.jsonl.zstd` 怎么解压" → 读 **2.12**。
- 触发信号：用户说"本轮运行失败""这次 turn 挂了""某个报错在历史上出过几次""把这个错误码全库扫一遍" → 读 **2.12** 的**全库扫描配方**与 **2.17**（`Provider finish_reason: <X>` 的溯源链与"是不是 DSH 的 bug"判据）。
- 触发信号：要改"新会话的默认 preset"，或**正在运行的 host** 上改完 preset registry 那一行后**工具面只剩 MCP 工具**、再改回去也不恢复 → 读 **2.13**（正确字段是 volatile 的 `selectedDefault`；热改这一行的 `config` 会让**已存在会话**当场崩塌且**不自愈**，只有重启进程能恢复）；报错 `Config field "default" is not volatile` 或 `... is overridden by a home patch or command-line overlay` 也是 **2.13**。
- 触发信号：你正要跑 `dsh_base\tools\sync-to-dsh-home.ps1` / `tools\check-drift.ps1`，或要问"`config\` 里这份快照还是不是真快照""`-Apply` 会不会把 live 覆盖回去""重建 home 是不是跑一次 `-Apply`" → 读 **2.14**（池是**分发源**不是回滚库；`-Apply` 会静默回退 `AGENTS.md`，动手前先做方向裁定）。
- 触发信号：你要**清理 / 整理 `~/.dsh/skills` 根**（移 `.bak` 之类残留、给 skill 目录瘦身），或看到 `credentials` / `.key` / `.pem` / `.token` 这类文件不知能不能移 → 读 **2.15**（被 skill 正文引用的凭据**就地保留**；移走 = 假指针 + 可能推翻用户决策）。
- 转交边界：只验 preset 静态可挂载 → `dsh-agent-preset-verification`；已起会话验 persona / 工具 / 委派 → `dsh-agent-preset-live-verification`；只搭干净环境 → `dsh-isolated-web-host`；把跑通的流程写成新 skill 的协议 → `sedimenting-skills`；skill 集合的定期体检（重复 / 失效指针 / 预算）→ `dsh-skill-self-audit`；MCP 工具的实际用法（接管 Outlook.com 邮箱、设备码登录） → `outlook-mailbox-control`。
- 前置：知道 `DSH_HOME`（默认 `~/.dsh`）与当前 host 的端口；**改自己正跑在里面的那个 host 前，先读完第 2 节**。 ／ **后继**：按第 3 节阶梯顺序走，最后回到第 2.6 节确认回滚路径。

## 1. 五个可改层 + 生效时机（实测）

| 改什么 | 位置 | 何时生效 |
|---|---|---|
| 行为宪法 | `~/.dsh/AGENTS.md` | 会话**首个请求**时加载；**文件被改动后 harness 会检测到并热刷新注入**（实测：改完当轮即收到 `Updated instructions from: ~/.dsh/AGENTS.md — This file changed after it was loaded.` 并用新正文替换旧正文）→ **无需重启**；但刷新时机由 harness 的变更检测决定，别假设"改完对所有正在跑的会话都立刻生效" |
| 流程 skill | `~/.dsh/skills/<name>/SKILL.md` | **写入即可被发现**，无需重启（实测两次）；first-party `write`/`edit` 会让 skill provider 失效并重发目录 |
| 层 3 · agent 组合（**载体已变，2026-10-08 证伪后更正**） | **profile 组合里的 `@deepseek-ai/dsh-agent-preset` 声明行**（loader row id 惯例 `preset-<id>`，`config.plugins` 是插件行列表）。`~/.dsh/.agent-presets/<id>/` 目录式 preset **已被弃用、全树无代码读取** | 声明行随 profile 组合**热重载**；但**只有空会话能切换 preset**，已建会话不换 |
| 层 4 · 默认 preset / 模型路由（**载体已变，同左**） | **profile patch 层**：`<profile>/cordis.patch.yml` 里的 `- id: agent-preset-registry`（**部署**默认 `config.default` / **用户**默认 `config.selectedDefault`）与 `- id: agent-default-model`。`~/.dsh/settings.yaml` **已不是活体配置**，只是**一次性 legacy 导入源**（见下方补充） | patch 热重载；两个字段的**取值**都只影响**新建会话**——但**改正在运行的 host 的这一行**会让**已存在会话**的工具面静默崩塌，见 **2.13** |
| 插件行 / patch | `<profile>/cordis.patch.yml` | **热重载**——但热重载的成败判据与冷启动完全不同，见第 2.1 节 |

**但有一个例外，它会让人把"惰性"误判成"装失败"（本轮实测，两条独立证据）**：**经 `link:` 挂进来的 bundle patch 文件，其内容改动不热重载**——生效时机是**冷启动**。证据：① 隔离 lab（`artifacts\orchestration-review\06-persona-candidate-verification.md`）：热改 bundle patch 内容后，**新建**会话仍拿到**旧** persona（**9,197 字符**）；**冷启动**后老会话被重挂载成 **7,177 字符**、工具面仍 **31**、turn 正常结束。② **Lead 现场第二例（本轮）**：把瘦身 persona 装成生效件后，Lead **正在跑的会话** system prompt **仍是旧版 `Hard rules`**。⇒ 三条纪律：① 生效时机 = **冷启动**、不是热刷新；② 装完**不重启不是失败，是惰性**；③ **别把它当"改完立刻能观测"的层**——对照上表第一行：`AGENTS.md` 是**热刷新**的，**两者不同层、结论别互相套用**。

**这一节的反直觉结论**：上面这些层**大多是热生效的**，所以"改完立刻观察到了变化"**证明不了这个改动是安全的**。真正需要**重启**才能验证的是插件行 / patch 的**冷启动正确性**（第 2.1 节）——"现在没坏"不等于"下次还能起来"。

补充：**给 DSH 挂 MCP server 就是"插件行 / patch"层**（没有独立 MCP 配置文件，唯一入口是 patch 里一行 `@deepseek-ai/dsh-mcp-client`）——落点、能力边界与**三种**失败形态见 **2.7**，接入前必须先量的"工具面注入量"见 **2.8**，`env` 传值保真的量法见 **2.9**。

补充（**旧断言已被证伪**）：本节曾写"`.agent-presets` 的 roster 每次读取都重扫，改 preset 后连 host 都不用重启"。**`0.2.0-rc.2` 起不成立**——那套目录**没有任何代码读**，写进去 / 改内容 / 删掉都**不会产生任何行为变化**。"改了没生效"要先确认**本次运行的那套 dsh 用哪套机制**（安装根可能不止一套，**且版本号要读 `package.json`、不能按目录名猜**——本机两套是 `0.2.0-rc.2` 与 `0.1.0-rc.6` 两条发布线），再怀疑声明行写错。

> **载体形状、逐行离线校验、`install_bundle` 安装**的正文**单一归属在 `dsh-agent-preset-verification`**，本总纲只留这一行指针、不复制。

**`settings.yaml` 是一次性 legacy 导入源（在第 1 节里它不是一层），三条要点**（源码 `@deepseek-ai/dsh-settings` 的 `importLegacyDocument()`）：

1. 任何 profile 的 DSH 进程 boot 完成后，只要 `$DSH_HOME/settings.yaml` 存在 → **先 `rename` 成 `settings.yaml.imported`**（**原文件消失**；且**改名先于写入**，所以部分失败也不会重试）。
2. 再逐**顶层键**调 `update(ns, values)`，**`ns` 必须是 profile entry id**（源码注释原文 `@param ns Profile entry id.`）。
3. 键名**不是** entry id（`agent-presets` 不是；`agent-default-model` **是**）→ 抛 `No configurable plugin entry "<ns>"`，但**只有 `logger.warn`、进程照常起来、没有任何报错**，该 section 只剩在 `.imported` 里，**哪一层都不生效**。

⇒ 三条纪律：① 别把 `settings.yaml` 当可维护的活体配置（它会被 boot 吞掉）；② 想通过它改配置，**顶层键必须是 entry id**；③ 判"改完生效没有"**不能看进程起没起来**，要看**目标层**（patch / 组合）里那行在不在——**失败是静默的**。

## 2. 上线纪律（本总纲最重要的一节）

### 2.1 热重载 ≠ 冷启动，失败模式完全不同（实测）

同一个**坏 row**（指向不存在的包）在两种路径下表现截然不同。**"坏 row"其实有三种形态，别当成一种**（下表三行依次是形态 ① / ③ / ②，其中 ①② 是冷启动的两个分支、③ 是解析期）：

| 路径 | 现象 | 致命性 |
|---|---|---|
| **冷启动 · 形态①**（row 校验合法，但 MCP server 起不来） | 进程**不挂**：host **照常起来并服务**（不带 token 的 HTTP GET **401**），只有那个 MCP server 子进程起不来 → **工具静默缺席** | **最危险**：唯一可见迹象是子进程 stderr 一行（实测 `command` 指向不存在的可执行文件时，GBK 解码原文：`'npx-definitely-not-a-real-binary-3f9a' 不是内部或外部命令，也不是可运行的程序或批处理文件。`）；host 侧**没有任何报错** |
| **冷启动 · 形态③**（YAML 语法错误） | 进程直接 **`EXITED code=1`**，stderr 原文 `Error: dsh: failed to parse patches …\cordis.patch.yml: YAMLException: can not read an implicit mapping pair; a colon is missed (16:20)`（`dsh-app-boot/lib/index.js:1197`，解析在 `:1149`；同一位置的读文件失败见 `:1147`） | **不致命**：硬退出 + 报错可见（依据：YAML 在插件树之前解析，promise 没人 await → 未捕获 → 退出码 1）——**这一形态不静默** |
| **冷启动 · 形态②**（host 正常起来了、新工具却没注册上） | host 打得开（**401** 照常通过），工具面里就是没有它 → 仍**静默** | **危险**：`401` **不算**接入成功。**本次未取证**（无实跑日志）——仍必须防，判据见 2.7 |
| **热重载**（同一个坏 row） | host **继续服务**（保留旧树），但坏 patch **留在盘上** | **非致命**，但**下一次重启才会静默挂掉**——当场看不出问题，这是最危险的形态 |
| **热重载 · 改的是正在运行 host 的 `agent-preset-registry` 行 `config`**（取值合法也一样） | host 照常服务，但**所有已存在会话**的工具面**当场静默崩塌**（只剩 MCP 工具），**热重载不自愈**、再改回去也不恢复；**只有重启进程才恢复**（重启后旧会话自愈） | **当场致命且静默**——与上一行恰好相反（上一行是"现在没事、以后才坏"）。详见 **2.13** |
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

### 2.5 已知地雷：实验 Agent Teams 插件**顶掉**原生委派工具名（旧断言已证伪）

**已被证伪的旧断言（2026-10-08 修正）**：本节原写"`dsh-experimental-agent-team` + `-tool-agent-team` 一旦挂载，**所有普通子代理委派都会失败**（`TEAM_NOT_MEMBER`），且**没有任何配置级绕法**"。**这两句都不成立**，反证如下（均为本次实测）：

- **真实机制是"工具名被顶掉"，不是"委派全废"**。`-tool-agent-team` 在**每个 Team 成员的 `agent.ctx` 作用域**里重新注册 4 个名字：`send_message` / `list_agents` / `interrupt_agent`——原生 `@deepseek-ai/dsh-tool-subagent-control` 恰好用这 3 个——外加 Team 专有的 `wait_agent`。同作用域**后注册者胜出** ⇒ 拿到的是 Team 版 schema（`send_message` 的 `target,message`），原生版被**遮蔽**而非卸载。
  - 取证：把**未打补丁**的 team 插件与原生 `dsh-tool-subagent-control` + `.../list-agents` 依次装进同一个录制作用域，3 个原生名全部归 team；把 team 插件换成**改名后**的版本，3 个原生名全部归原生、且 `team_*` 4 个名并存（差分对照，两种情形各跑一次）。
- **有配置级绕法**：原生行还在不在，取决于**组合层**。`-agent-team-profile` bundle 把 `tool-subagent-control` / `tool-subagent-list-agents` / `tool-subagent` / `tool-subagent-fork` 四条置 `disabled: true`；而 **web profile 的 agent preset 层在它之后把同样这几条重新插入**（`--dump-config` 里同一 `id` 先出现 `disabled: true`、后面再出现一次不带 `disabled`）。所以 web/standard preset 组合下**两族并存、原生委派可用**，只是名字被抢。
  - **注意**：profile 用户层（`$DSH_HOME/cordis.patch.yml`）写 `- id: <同名>` **不会**"覆盖"bundle 的 `disabled: true`，实测会**追加出重复行**；要让原生行回来，得看该组合里有没有一层在 team bundle **之后**重插它们。
- **真正的伤害**（才是要防的）：① 同一个 `send_message` 按调用者身份挂两套 schema（成员见 `target`，非成员见 `agent_id`）→ 请求前缀分裂；② 把 `send_message` 指向普通子代理时报 `Error: active teammate "<id>" not found`（实测原文，Team 版的 code 是 `TEAM_MEMBER_NOT_FOUND`），而模型以为自己调的是原生工具；③ `dsh-subagent` 的可续委派标记探测被绕过（未验证：来自早前静态阅读，本次未复测）。
- **判据（实测）**：给隔离 host **只挂** `-agent-team-profile` bundle 时，该会话工具面里**原生三条全部缺席**（29 个工具，只剩 `team_*`）；把原生行重插后**同一组合**变成 32 个工具、两族并存。⇒ **"挂上就全废"不成立，取决于挂在哪一层、有没有人把原生行插回来。**

→ **纪律（取代旧的"先别挂"）**：① 只要普通委派、不要 Team 时，别让原生行被 `disabled` 掉；② 要两族并存时，把 Team 那 4 个工具改名（`team_send_message` / `team_list_agents` / `team_interrupt_agent` / `team_wait_agent`），做法见 2.10；③ 无论哪条，验收必须**去会话工具面点名核对**（看 `send_message` 的 `parameters` 里是 `agent_id` 还是 `target`），**401 / "启动成功"都不算数**。

### 2.6 生效 / 回滚矩阵（每层都要能一句话说清"怎么撤"）

| 层 | 怎么撤 | 撤完何时生效 |
|---|---|---|
| `AGENTS.md` | 改回原段落 / 删掉新增段 | 下一次变更检测热刷新（同第 1 节） |
| skill | 删 `<name>/SKILL.md` 或改回原文 | 下一轮目录重发即生效，无需重启 |
| 层 3 · preset 声明行 | 删 / 还原 profile 组合里那条 `@deepseek-ai/dsh-agent-preset` 声明行（若是覆盖声明，还原成原 `config`——**`config` 是整体替换，必须整套重述**） | patch 热重载；但**已建会话不能换 preset**，要新会话才看到 |
| 层 4 · profile patch | 删 / 还原那两个 patch 行（`agent-preset-registry` 的 `config.default` / `config.selectedDefault`、`agent-default-model`）。**注意**：`selectedDefault` 是**用户默认**，它落在 profile patch 文件里 ⇒ 改它等于改文件（**备份在前**，见 2.13） | patch 热重载；但改的是**正在运行的 host** 时，已存在会话的工具面**当场崩塌且不自愈**（2.13），**重启**才恢复；字段**取值**本身只影响**新建会话** |
| `settings.yaml`（**已不是一层**） | **撤不了也不需要撤**：boot 第一步就把它 `rename` 成 `settings.yaml.imported`，原文件已消失；要恢复只能手工从 `.imported` 抄回去再重启 | 见第 1 节"`settings.yaml` 是一次性 legacy 导入源"；**改完生效与否是静默的**，别靠进程起没起来判 |
| 插件行 / patch | 用备份还原（`[]` 或原数组） | 热重载立即恢复服务树；**还原后仍要重启一次验证冷启动**，因为热重载成功不代表干净 |
| 插件包**本体**（直接改 `node_modules` 里已装的包） | 跑补丁脚本的 `--restore`（或从备份目录拷回），并校验 sha256 与上游包**逐字节相同** | 下一次**冷启动**加载该包时；`npx` / `npm install` 重装会**静默覆盖**补丁（2.10） |

### 2.7 MCP 接入层（本层的一个特例，实测）

要给 DSH 挂一个 **MCP server** 时，它**不是新的一层**——它就是第 1 节里的**"插件行 / patch"层**，落点仍然只有 `cordis.patch.yml`。

**先删掉错误的心智模型**（实测）：

- **没有**独立的 MCP 配置文件、**没有** `mcpServers` 键、**没有** `~/.dsh/mcp/*.json` 这类声明文件（该目录可以是空的）。**唯一的声明入口 = patch 里的一行 cordis 插件**，插件固定是 `@deepseek-ai/dsh-mcp-client`。
- patch 文件的形状是**单一顶层 `- insert:` 列表**，每个 server 一行、**4 空格缩进**，与既有插件行同级追加即可。
- **那条"必须重启"的注释已被实测证伪（它不能被无条件当结论）**：文件顶部注释逐字写着：**Requires restarting `npx @deepseek-ai/dsh web` to take effect.** —— 但**向一个语法合法的 patch 追加一条新 MCP row，会被热重载直接拉起、无需重启**。反证（四个值都来自真实 host，不是推断）：① host 进程 `node …dsh\lib\bin.js web --port 3080`（PID 20920）启动于 **2026-10-09 15:06:02**（改动前已跑约 4 天）；② patch 在 **2026-10-13 15:10:45** 被追加该 row；③ 该 MCP 子进程（命令行 `node …\dsh-qqmail\lib\mcp-server.js --allow-write`）的启动时间**同为 2026-10-13 15:10:45**；④ **已存在的会话**函数清单**当场**新增 12 个 `mcp__qqmail__*` 工具，真调用返回真实邮箱数据。⇒ **"追加新 row 需要重启"不成立**；注释与"改完必须冷启动"的旧结论**只适用于"冷启动正确性"这件事**（见 2.1：热重载成功不代表下次能起来）。
- **边界（别过度泛化）**：本轮验证的只是「**向一个语法合法的 patch 追加一条新 MCP row**」。**未验证**：修改一个**已存在** MCP row 的 `config` 是否也热生效——那件事**没有取证，别写成结论**（它的失败模式与 2.13 的 `agent-preset-registry` 那类"热改已存在的行会让已存在会话崩塌"是风险不同的两件事）。
- 行定位靠 `id:`（自取唯一名）；工具对模型暴露为 **`mcp__<serverName>__<tool>`**。
- 能力边界（决定"这条路走不通"要在第 3 节之前就判）：**只支持 `stdio` 与 `streamable-http`，没有 `sse`**；**只桥 tools，不桥 resources / prompts**。

**上线纪律按 2.1 / 2.2 / 2.3 全套走**，另补 MCP 专属四条：

1. **在隔离 host（重定向 `DSH_HOME`）冷启动验证"同一组合"**——实测成功那组的形态是：`stdout` 只有一行 `dsh web: http://127.0.0.1:<port>/?token=…`、`stderr` **0 字节**。判据是"**打印了 URL 那一行**"，不是"进程还活着"。
2. **失败形态有三种，都要单独判**：① **合法 row、但 server 起不来**（host 照常服务、无 token GET 照样 **401**，工具**静默缺席**——见 2.1 形态①，唯一痕迹是子进程 stderr 一行；"无 token 401"**不算**接入成功）；② **host 正常起来了、新工具却没注册上**（**同样静默**，`401` 会照样通过；**本次未取证**，但仍必须防）；③ **YAML 语法错误**（**不是静默**：进程直接 `EXITED code=1` + 解析报错，见 2.1 形态③）。⇒ 无论走哪一条，都必须再去会话的工具面里**点名核对那个新工具是否存在**（`mcp__<serverName>__<tool>`）。
3. **追加 MCP row 的验收三段（本轮实测跑通的顺序，别跳、别只用其中一段）**：
   1. **静态组合**：`node <dsh bin.js> --profile web --dump-config` **退出码 0**，且输出里 `name: '@deepseek-ai/dsh-mcp-client'` 的计数**恰好 +1**（改前改后各数一次）。⚠ 它**只组合、不 mount**——`--dump-config` 通过**证不了**工具会挂上（同 2.10 第 1 条）。
   2. **隔离 host 冷启动 + 真建会话**：另给一个 `DSH_HOME` 冷启动（`dsh-isolated-web-host`），在**该 host 的真会话**里，从 **`request/header`（服务端权威、模型自述不算）**点名核对工具名与总数（取法见 `dsh-agent-preset-live-verification` §2：`data.header.tools[].name`）。
   3. **真实会话里真调用一次只读工具**：拿到真实数据才算通（"工具名出现了"不等于"能调通"）。
   - 三段的分工：① 管"配置层写对了"，② 管"挂载了 + 会话拿得到"，③ 管"调用真能通"。只做 ① 是**假通过**。
4. **证明"只追加、没重写"（共享 YAML 的安全前提）**：改动前先记下**原文件字节数 N** 与原文件 `sha256`；改动后算新文件**前 N 个字节**的 `sha256`，**必须仍等于改前那个值** ⇒ 证明这次改动是纯追加、没有重写任何既有字节。本轮实测相等。任意一处被重排/重写，这个等式立刻不成立。
   - ⚠ **数这类值别用 PS 5.1 的 `>` 重定向**：它写出来的是 **UTF-16LE**（首字节 `ff fe`），后续按 utf-8 解会报 `UnicodeDecodeError: 0xff in position 0` ⇒ **数行数 / 判 BOM 一律二进制读**（`[System.IO.File]::ReadAllBytes` / Python `open(p,'rb')`；细则与其它编码坑见 `pwsh-on-windows`）。

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


### 2.10 改"已装插件包**本体**"：断言式补丁脚本 + 三层验证（实测）

当插件行层做不到、必须改插件**代码**本身时，改动落在 `node_modules/<pkg>/lib/index.js`。**不要手工改那个文件**——重装会静默覆盖，且没人能重现你改过什么。

**1) 把补丁写成"可重跑的断言式脚本"**，不是一次性 hack：一张 `[old, new]` 替换表，每条**断言锚点在该文件里恰好出现一次**（匹配 0 次或 ≥2 次都**整体中止、一个字节都不写**），配 `--check`（只验锚点不落盘）、`--root <包目录>`、带时间戳备份、`--restore`。上游一升级、锚点漂移，脚本会**响**，而不是产出半个补丁。

- **纯文本替换标识符时，`old` 取"不含前导空白"的唯一子串**：JS 缩进不影响语义，所以 `new` 的缩进写错只是难看；但 `old` 多一个 tab 就匹配不上。需要保留缩进时用正则捕获（`^(\t*)key: \{` … `$1`），**且替换必须用字符串 replacer**——`source.replace(re, () => rep)` 是**函数** replacer，`$1` / `$&` **不会展开**，会**原样写进源码**（本次实测踩到：靠"文本变了"看不出来，只有额外断言"没有 `$1` 泄漏"才抓得住）。
- 每次改完立刻过**语法闸门**：补丁后的文件另存 `.mjs` 跑 `node --check`（只解析语法、不解析模块依赖），挡住"锚点对但拼坏了"。
- 若补丁让插件**新增一个 `inject` 依赖的 service**（例如给工具加 `fs`），要意识到：该 service 在某个组合里缺席时，**整个插件行会静默不服务**（同 2.1 形态①）。
- 补丁只改**包**不改**数据契约**：凡是写进会话日志的东西，都要按下面第 2 条过一遍回滚。

**2) 回滚安全性是**设计时**决定的，不是事后补的**：
- **不要**给 `.strict()`（`additionalProperties: false`）的**持久化 / 快照** schema 加字段：会话日志虽是 append-only 事实源，但快照类 schema 是 strict 的 ⇒ 老代码遇到新字段**直接拒绝**，于是"打完补丁写出的日志，回滚后读不了"。
- **要**用**加法型事件**：新事件类型挂在**白名单式**分发函数后面（本次 `isTeamEvent()` 只认 4 个类型、未知类型走 `return state`），未打补丁的老代码**直接忽略**新事件 ⇒ 打完补丁写出的日志回滚后仍可解析。判据一句话：**新事件在旧代码里是"被忽略"而不是"被拒绝"**。
- `stateVersion` 能不升就不升（一升，旧代码就会面对"更新的检查点"）。

**3) DSH 没有"按 agent 归因的改动清单"，别把验收设计在它上面**（实测）：
- `dsh-workspace-changes` 按**顶层会话、按轮**统计，且**显式跳过子代理会话**（`lib/index.js:985-986`）⇒ 某个队友的改动落在哪些文件**无法归因**。
- `pwsh` / `bash` 走子进程，**不产生**任何 workspace 变更事件（写文件、跑格式化器、代码生成器一律不算）。
- `FsInfo.version` 是 `dev:ino:size:mtimeNs:ctimeNs` 这类**不透明 stat 令牌**，**不是内容哈希**，不能当"文件没变"的证据；它也不能用来判"是不是同一个内容"。
⇒ 想验"队友有没有越界写"，靠事件流做不到；**能验的是"它声称产出的文件是否存在、内容哈希是多少"**——所以把验收设计成**点名 + 宿主算哈希**（见 `orchestrating-subagents` §8）。

**4) 自己打的补丁必须过三层验证**（缺一层别上生产环境）：
1. **静态组合**：`dsh --profile <p> --dump-config` 跑通、退出码 0、补丁包按名解析到。**注意它只组合不 mount**，"能 dump"≠"能挂载"（判 mount 的场地见 `dsh-isolated-web-host`）。
2. **确定性单元**：把补丁后的包 `import` 进一个 stub `ctx`（假 `agents.list()` 返回一个 stub Agent + 它的 `ctx.tools.register`、假 `ctx.fs`），**直接调用 `defineTool` 注册出来的工具**，断言：注册名集合、错误 `code`、返回值的形状、以及**输出 schema 是否声明了返回的每个字段**（`def.output.schema.properties`；多一个未声明字段在真机上会被 strict 拒）。这一层不花 LLM 钱、可反复跑，是性价比最高的一层。
3. **真会话**：隔离 host 里真跑一轮，读会话日志的 `request/header`（工具清单）与 `system/message`（注入的策略正文）**点名核对**；再拿**未打补丁的包做对照**跑同一套断言（差分对照才是"我的改动确实生效"的证据，自证不算）。

### 2.11 把一个实验包挂进 profile 的形状（官方自己就是这么挂的）

替换式挂载只有两步，**顺序不能反**：先按 `id` 关掉要取代的旧行，再 `insert` 新行。

```yaml
- id: tool-subagent          # ① 关掉要取代的旧行（行级、按 id 匹配）
  disabled: true

- insert:                    # ② 再追加新行；每行三件套 id / name / config
    - id: agent-team
      name: '@deepseek-ai/dsh-experimental-agent-team'
      config:
        maxMembers: 8
        maxTasks: 256
```

- **官方自己就是这么挂 Agent Teams 的**：`dsh-experimental-agent-team-profile\cordis.patch.yml`（33 行）= **4 个 `disabled: true`**（`tool-subagent-control` / `tool-subagent-list-agents` / `tool-subagent` / `tool-subagent-fork`，:4-14）+ **一个顶层 `- insert:`**（:16）下 **3 行**：`agent-team`（:17-24，config 键 `maxMembers` / `maxTasks` / `maxPendingMessagesPerMember` / `maxMessageBytes` / `disposalTimeoutMs`）、`tool-agent-team`（:26-30，config 键 `freshProvider: spawn` / `forkProvider: fork`）、`ui-agent-team`（:32，无 config）。
- `disabled` 是**行级 + 按 `id` 匹配**；在 profile **用户层**写同名 `- id:` **不会**覆盖 bundle 的 `disabled: true`——实测会追加出重复行（机制与后果见 2.5）。判"到底谁生效"看 `--dump-config` 里同一 `id` 是否出现两次（先 `disabled: true`、后不带）；**能 dump ≠ 能挂载**，逐行离线校验的正文单一归属在 `dsh-agent-preset-verification`。
- **挂实验包先查官方 bundle，别自己 vendoring + 手写 row**：官方已把 `@deepseek-ai/dsh-experimental-agent-team-profile` 做成 bundle（带 `cordis.patch.yml` + `dsh.bundle.patch`）并列入 `dsh-app-boot\lib\index.js:552-557` 的 `OPTIONAL_BUNDLES`（该数组的注释原文 `offered switched off by the plugin manager`，:548）⇒ 直接走官方路径。反例（实测）：手工方案那批 `*.tgz` 与 `staged\` 备料全是**过时的 0.1.5-rc.2**，比运行时装着的 0.2.0-rc.2 落后一整代。
- **失效模式（实测）：手工 row 方案会随 patch 长出真实 row 而整体失效。** 那套 apply / watchdog 脚本以「`cordis.patch.yml` 必须恰为裸 `[]`」为硬门槛；本机 patch 现为 **1311 B / 4 条真实 row**（`llm-pi-ai` / `agent-default-model` / `ui-settings-general` / `permission`）⇒ `apply-team-live.ps1` / `team-live-watchdog.ps1` 在 guard 处 `exit 3`；更坏的是 `deploy-team.ps1` **先污染后拒绝**（第 1 步真会创建 `profiles\node_modules\@deepseek-ai` 并拷入过时的 0.1.5 包，第 3 步才 throw `profile patch is not a bare [] and has no team rows; refusing to clobber.`）。⇒ 判据：**凡以"某个文件必须是空 / 必须是某个形状"为前提的自动化，动手前先验证那个前提还成立**，并默认它**在拒绝之前可能已经改过磁盘**。

### 2.12 从会话日志回收被覆盖的旧版本（DSH 自身的记录面，实测）

文件被**覆盖 / 没备份**时，**旧版本仍能从会话日志里逐字节重建**——日志记着每一次 `read` 的**逐行快照**。

**1) 日志在哪、什么形状**

- 路径：`$DSH_HOME\sessions\<workspace-slug>\<agentId>\session.v4.jsonl.zstd`（实测形态 `--D-workspace-agent-dsh_base--\<uuid>\session.v4.jsonl.zstd`；**一个会话一个目录，子代理也各有一份**）。
- 它是**多帧 zstd 拼接**（每帧 magic `28 B5 2F FD`）⇒ **`zstdDecompressSync` 单次只解第一帧**，只拿到开头那一小段；必须按 magic **切帧循环**解压再拼。本仓现成工具 `tools\session\read-session-log.mjs` 已这么做（实测一次解出 **126 帧 / 235 条记录 / 1283123 字节**），但它**只按 pattern 打印行**，要取证得自己解析 JSONL。
- 日志是 JSONL，逐行一条：`tool/call`（`data.callId` / `data.name` / `data.arguments` 是 **JSON 字符串**，还得再 `JSON.parse` 一次）与 `tool/result`（用 `data.message.toolCallId` 配对）。

**2) `read` 的结果就是一份可逐字节重建的快照**

关键字段是 **`tool/result` 里的 `data.meta`**（不是 `message.meta`，实测那里是 `null`）：

- `meta.path` / `meta.totalLines` / `meta.lang` / **`meta.offset`** / **`meta.lines` = `[{number, text}]`**。
- 重建写法：**`meta.lines.map(l => l.text).join('\n') + '\n'` 逐字节等于当时的文件**（本轮实测 sha256 对上）。
- **注意 `meta.lines` 可能是"窗口"而不是全文**：带 `offset` 的读只回一段（实测 `lines` 40 项而 `totalLines` 是 234）⇒ 直接 `join` 会**静默**产出 40 行的假文件（4690 B 冒充 234 行）。**重建前必须断言 `offset === 1 && lines.length === totalLines`**。
- `content[0].text` 里那份带 `N: ` 行号前缀的正文是**给人看的**，要重建得先剥前缀；**优先用 `meta.lines`**。

**3) 用途 + 自证（本轮实测：`orchestrating-subagents`）**

- 用途：取"**该写手在首次写入之前的那次 `read`**"，就是被覆盖前的旧版本。
- **自证必须双向，只对一个方向不算证明**：
  - **正向** = 对**写手自己在磁盘上实测的** `bytes` / `sha256`（日志原文：`bytes=22962 sha256=3f6a9dd800b622fb BOM=False CR=0 LF=234`）。
  - **反向** = 把日志里它的每一次 `edit`（`old_string` / `new_string`；`replace_all` 决定全替换还是只中首个）**依次回放**到重建文本上，看能否精确复现它**改后**的状态。
- 本轮两个方向都命中：重建 **12860 B**（153 行）+ **5 次 `edit` 全部命中、0 失败** ⇒ 回放终态 **22962 B / sha256 `3f6a9dd800b622fb…c89916`**，与写手自测、以及**我在 PowerShell 里独立算的**磁盘哈希**三者逐字节一致**。顺带一条判据纪律：真值是实测的 **12860 B**，而不是任何"估算的尺寸带"——拿自己估的区间当验收判据会把**正确的交付误判为失败**（见 `orchestrating-subagents` §9.7）。
- 边界：最后一帧可能在追加中被截断 ⇒ 单帧解压失败要**容忍并跳过**，别把整次取证判失败；日志只记**被读写过的内容**——从没被 `read` 过的文件不在里面。

> 会话 id / 隔离 home 路径等属**会话专属证据**，留报告，不进本 skill。

### 2.12.1 全会话扫某个错误串的复现配方（zstd 流式精确匹配）

**要回答"这个报错在本机历史上出过几次、命中哪些会话"** 时用它。会话文件散布在 `C:\Users\admin\.dsh\sessions\<工作区转义名>\<agentId>\` 下，名字有 `session.jsonl.zstd` / `session.v3.jsonl.zstd` / `session.v4.jsonl.zstd` 三种以上 ⇒ **按扩展名 `.zstd` 全树扫**最稳，别按文件名猜。

**必须用精确 JSON 模式匹配**：`content_filter` 这类子串会在**排查会话自己的正文里**反复出现（本轮实测：子串命中 49 行，其中 **39 行**是排查会话里的普通文本巧合）⇒ 裸子串计数会把"我自己的排查过程"当成事件数。

```powershell
$code = @'
import os, zstandard
d = zstandard.ZstdDecompressor()
for dp, _, fn in os.walk(r"C:\Users\admin\.dsh\sessions"):
    for f in fn:
        if f.endswith(".zstd"):
            p = os.path.join(dp, f)
            lines = d.stream_reader(open(p, "rb")).read().split(b"\n")
            for i, l in enumerate(lines, 1):
                if b'"Provider finish_reason: content_filter"' in l:
                    print(p, i, len(lines))
'@
$code | python -X utf8 -
```

- **匹配用 bytes 字面量**（`b'"…"'`）而不是子串技巧：抓的是日志里那个**带引号的 JSON 字段值**，这正是"精确模式"的落地方式。
- **必须流式**（`stream_reader`）：会话日志是**多帧拼接** zstd，单帧 API 只回第一帧且不报错（假否定，逐字配方与证据 → `pwsh-on-windows` 陷阱表"多帧拼接 zstd"行）；`stream_reader` 顺带满足**不落盘**。
- **事件计数判据：行数 ÷ 2 = 事件数**——真实事件在一条 `assistant/attempt` 里**成对出现**（`finish` chunk 行 + 紧随的 `turn/end` 行）⇒ 别把命中行数直接当次数报。本轮实跑：**677 个文件 / 264,383,956 B → 10 行 / 5 事件 / 4 会话**。
- **依赖**：python 的 `zstandard` 模块（无它直接 ImportError）。**本机 zstd 会话合计约 260 MB 量级**（时刻值）⇒ 耗时在解压、不在匹配。
- **坑**：别用 `d.decompress(b)`（单帧，多帧文件只有第一帧）；别按文件名（`session.v4.jsonl.zstd`）找，要按扩展名扫；别忘"÷2"。
- 本节的**下游**：拿到命中的会话后再判"这错误是不是 DSH 的 bug"→ 见 **2.17**（错误串的实装链路行号**单一归属在 2.17**，本节只写扫描配方、不复制链路）。

### 2.13 改"正在运行 host"的 registry 行：已存在会话的工具面**当场静默崩塌**（实测，全库最隐蔽的一种）

**这是与 2.1 相反方向的坑**：2.1 的坏 row 是"**当场无感、重启才死**"；本节是"**当场就坏、重启才活**"。

**现象（实测）**：在**正在运行**的 host 上改 preset registry 那一行的 `config` 取值 ⇒ **下一个提问时所有已存在会话的工具面只剩 MCP 工具**（实测：12 个 MCP + 1 个泄漏的 `subagent` = **13** 个；正常应为 **31 / 43** 量级）。**这几个数字是本次实测示例，不是常量。** 四个关键性质：

- **不自愈**：继续提问不恢复；**把那条 patch 改回原样也不恢复**（热重载已经毁掉了挂载点）。
- **只有重启进程才恢复**；重启后**旧会话自愈**——会话本身没坏，坏的是**进程内的挂载**。
- **触发与取值无关**：`standard` → `orchestrator` / `ptc` / `minimal` **都复现**。⇒ 危险的不是"改错了值"，而是"**动了这一行的 `config`**"。
- **新会话一切正常**（这正是它难被发现的原因）。

**机制一句话**：host 面（patch / 组合层）的 `tool-*` 行**全都是 `disabled`**，会话的工具**只能来自 preset realm**；而 realm **只在 `composeAgent().setup` 里 `mount` 一次**——`composeAgent(presetId)` 返回的 `setup` 内容是 `installSelection(agent)` + `await presets.mount(agentCtx, resolvedId)`（`dsh-api-session-controller/lib/types/agent.js:388-401`），**已发布的会话不会再跑 setup**。registry 插件因 `config` 变化被 Loader 重建 ⇒ 旧注册的 disposer 跑 `unregister()` → `generation.retired = true` → `collect()` → `generation.scope.dispose()` → `mountPreset` 注册的 effect 清理函数 `tree.root.stop()`（`dsh-agent-preset-registry/lib/index.js:511-523` / `:569-573` / `:263-267`）⇒ **realm 被 stop 且不重挂**。新会话走新 setup，所以新会话没事。

⇒ **正确心智模型**：这一行的 `config` **不是"改完只影响新会话"**——那句话只在**冷启动**语境下成立（第 1 节表格）；在**正在运行的 host** 上热改它，代价是**当前所有会话**。

**要"让某个 preset 成为新会话默认"，字段是 volatile 的 `config.selectedDefault`，不是非 volatile 的 `default`：**

- 取值逻辑：`defaultId = selectedDefault ?? default`（`dsh-agent-preset-registry/lib/index.js:494`；schema `:473`——`default` 是普通字段，`selectedDefault: z.string().volatile()`）。
- 写入方式（**GUI「设为默认」走的就是同一个口**）：`settings.update("agent-preset-registry",{ selectedDefault: <id> })`（`dsh-client-ui-agent-preset/lib/client.js:1072` 逐字如此）。
- 实测：写入后 `isDefault` 翻转、**不带 preset 建会话即得该 preset**、**冷启动仍生效**。而走 `settings` 通道写 `default` 会被**拒**，逐字错误原文：`Config field "default" is not volatile`（`dsh-settings/lib/index.js:507` / `:520`）。
- ⇒ **`selectedDefault` = 用户默认；`default` = 部署默认。** 要改用户默认就别去动 `default`。

**`volatile` 的语义（别猜）**：**不是"只在本进程有效"**。schema 注释原文是 "Select fields whose nearest volatile ancestor makes them editable **without remounting**"（`dsh-settings/lib/types/schema.js:39`，`lib/index.js:118` 同文）——即**免重挂载、就地改值**。**这正是它安全的原因**：写 `selectedDefault` 走"就地改值"，**不会触发 registry 插件重建**，所以**不会**引发上面那场崩塌。
**反例口径**：**不要拿 `applies: "live"` 当安全依据**——它在类型声明里就是**写死的字面量** `applies: 'live'`（`dsh-api-settings-controller/lib/typert.host.js:489`）⇒ 对**所有** namespace 恒为 `live`，对"会不会重挂载"**零信息量**。

**两条会被"拒"的写入路径**（都要在动手前先试，别等写坏了才发现）：

1. **home patch / 命令行 overlay 里已配置同一行** ⇒ 拒，逐字原文（`<id>` 位实测为 `agent-preset-registry`）：`Configuration for "agent-preset-registry" is overridden by a home patch or command-line overlay`（`dsh-config-editor/lib/index.js:122`）。
2. **非 volatile 字段** ⇒ `Config field "<path>" is not volatile`（同上）。

**写 settings 会整份重写重排 profile patch**：路径是 `writeFileAtomic(path, String(document))` → `reconcileProfilePatches(...)`，整体包在 `hmr.runExclusive(run)` 里（`dsh-config-editor/lib/index.js:123` / `:125` / `:134`；reconcile 失败会回写 `before`，`:127-129`）。因为**整份文档被重新序列化**，实测副作用是**既有行"值没变、样式变"**（引号风格、缩进被改写）⇒ **动手前先备份**。

**操作建议（三条，按顺序）**：

1. **动手前**确认目标行的 `config` 里**非 volatile 字段取值不变**（本轮真实环境就是"现状 `default: standard`，只新增 `selectedDefault`"——**只做加法，不改既有非 volatile 值**）。
2. **备份** profile patch（写 settings 会整份重排，见上）。
3. **改完必须重启一次**才算彻底安全——**冷启动成功 ≠ 热重载成功**（2.1），而本节反过来说：**热重载本身就能把活着的会话弄坏**。

> 本节所有行号取自本机 `node_modules/@deepseek-ai/*`（`0.2.0-rc.2` 线）；升级后行号会漂，**判据与错误原文**才是可迁移的部分。

### 2.14 `config\` 快照池是「分发源」不是「回滚库」：一次 `-Apply` = 一次无声的教义回退（实测）

> 编号说明：本节原拟编入 **2.13**，但 2.13 已被上节（registry 行崩塌）占用 ⇒ **顺延为 2.14**。

**它到底是哪一侧的源。** `D:\workspace\agent\dsh_base\config\manifest.json` 是「repo 侧 → live 侧」的映射表：`path` = **仓库侧写入源**，`source` = **live 溯源记录**；而决定"写到哪"的 `Get-DshLivePath`（`tools\sync-to-dsh-home.ps1:84-97`）**只按 `path` 前缀推导、完全不看 `source`**。方向由开关定（`:9-11`）：`-Capture` = live → 快照；`-Apply` = 快照 → live；**不带开关就是 dry-run，只打印不动手**（`:6-7` / `:357`）。两个真读它的消费者：写手 `tools\sync-to-dsh-home.ps1`（`config/skills/* → <live>\skills\*` 的映射在 `:92-95`；池只认 `dsh-*` 目录，`:130`）与比对器 `tools\check-drift.ps1`（`:110` 注释逐字 `snapshot -> live`；`:159-161` 证明 `config/AGENTS.global.md` 与 `<live>\AGENTS.md` 是同一份东西的两侧）⇒ **它是分发源（安装源），不是回滚库。**

**开关的逐字语义与 `-Capture` 的覆盖面（本轮实测 `tools\sync-to-dsh-home.ps1`）。** `:9-10` 逐字 `-Capture   live -> snapshot   (copy live files over the snapshot, then rewrite` + `config\manifest.json so it describes the result)`；`:11` 逐字 `-Apply     snapshot -> live   (back up every target file first, then copy)`；`:6-7` 无开关 = **dry-run**（`:357` 逐字 `DRY RUN -- no switch given, nothing was read from or written to the snapshot/live home.`，`:359` 打印 `-Capture would copy N file(s) live -> snapshot:`）。⇒ 语义有两点必须说全，别只记成"重新 capture"：**① 方向 = 把 live 盖到快照上**；**② 覆盖面 = 逐文件 copy（只写快照侧）+ 整份重写 `config\manifest.json`**。实现即"只写快照侧"：`:232-249` 的 Capture 分支只写 `$c.To`，`:242` 用 `Copy-Item -LiteralPath … -Destination … -Force` ⇒ **字节保真、无重编码**（不会给 skill 文件加 BOM）。

**实锤危害（同一机制、不同时刻；下面每个数字都是时刻值，别背成常量）。** `-Capture` **之前**有两次独立读数：Lead 复核得 `matched=8 drift=8`（**8 条全部 `live-newer`** = 1 个 `AGENTS.md` + 6 条 live `dsh-*` SKILL.md + 1 个脚本 `dsh-skill-authoring\check-skill-frontmatter.ps1`），**exit=2**；我上一轮复跑读到的条数比它少 1（差在那条期间刚被人改过的脚本）——**同一个池、两次读数就能差一条**。当时 dry-run 逐字打印 `-Apply would copy N file(s) snapshot -> live (with backup)`（N = 漂移条数）⇒ **那一刻的任何一次 `-Apply` 都是一次无声回退**。**重新 `-Capture` 之后**实测 `matched=16 drift=0 snapshot-only=0 live-only=0` + 脚本自己的原文 `No drift: the snapshot matches the live DSH home.`，**exit=0**（`:247` 脚本自己就写着 `Run check-drift.ps1 to confirm the result shows no drift.`）⇒ 池此刻已是真快照、`-Apply` 与 live 相等。**但风险只是被判据化，没有被消除**：`AGENTS.md` 是热刷新的、live 随时在动 ⇒ 只要 live 再前进一次，同一条 `-Apply` 就又是一次回退（**本节这次改稿本身就让池落后 1 条**）。

**为什么这叫"教义回退"而不只是"版本回退"（这段历史可当场复核，不必信本节的旧数字）。** 改造前两侧 `AGENTS.md` 的**章节编号完全一致（都 §0–§12）**，语义却相反——快照侧 §2 = 「触发即委派」、§3 = 「可以自己做」；live 侧 §2 = 「生产权在子代理」、§3 = 「审计通道」。**两份改造前原件都还在磁盘上**（只读），可直接逐字复核：`artifacts\backups\orchestration-opt-20261009\001__Users__admin__.dsh__AGENTS.md` 与同目录 `014__workspace__agent__dsh_base__config__AGENTS.global.md`（我本轮已按这两份复核过它们的 `## 0`–`## 12` 标题）。⇒ 那些**按编号引"宪法 §2 / §3"** 的 skill，回退之后会指向**相反语义**，而且**没有任何报错**。**现值**（2026-10-09 改造前实测）：两侧**逐字节相等 = 12,955 B / sha256 `C9AE86A3…`**——改造后本值必然失效，属时刻值；同样是时刻值，会随每次改造再变。

**两个必须一起说的限定（别夸大）**：

1. **这不是自动路径，是"装了子弹没扣扳机"。** `config\_backup` 目录**不存在**（`Test-Path` = False；备份根由 `-Apply` 才创建，`:263`）⇒ 历史上**从未 `-Apply` 过**。全机唯一与 DSH 相关的计划任务是 `DSH-Skill-SelfAudit`，在其 skill **全部文件**里 grep `-Apply|-Capture|sync-to-dsh-home|check-drift` = **0 命中**（本轮实测）⇒ 回退只会由人手动敲。
2. **池自己不会告诉你它旧了。** manifest 的 `bytes` / `sha256` 字段是**死数据、无人校验**——`check-drift.ps1:134-139` 是**现算** `Get-FileHash` 后比对，**从不读 `$e.sha256`**。⇒ **字段过期不产生任何 drift**（本轮就是这样被抓到的：两条失效字段一直躺着，`check-drift` 一声不吭，只有自己现算才看得见）。失效样例（`-Capture` **之前**实测；`-Capture` 会重写 manifest ⇒ 现值已刷新，样例只作形态参考）：`agent.cordis.yml` 记 21867 B / `d1e9f32a` 而磁盘 22980 B / `e8873211`；`preset.yml` 记 360 B / `dad344d4` 而磁盘 553 B / `9b6691f3`。⇒ 判据：**别把"manifest 没报错"当成"快照是新的"**；要判同步只能跑 `check-drift` 或自己现算。

**纪律：方向裁定没做完，任何人不得跑 `-Apply`。** 裁定 = 二选一：① **重新 `-Capture`**（让池重新成为真快照，推荐）或 ② **删池**；`-Capture` 也是写操作（它改的是池、并重写 manifest），同样在裁定之后做。**两个开关一起给 = 直接失败**（`:57-59` 逐字 `FATAL: pick one direction. -Capture and -Apply are mutually exclusive.`，`exit 1`）。

**本轮实测读数（2026-10-09，范例；每个数字都是时刻值）。** `-Capture` **之前**：`check-drift.ps1` 得 `matched=13 drift=3 snapshot-only=0 live-only=0` + **`EXIT=2`**；`sync-to-dsh-home.ps1` **dry-run** 逐字打印 `-Capture would copy 3 file(s) live -> snapshot:`（**恰好 3 个目标，没有附带拉入**）；**先备份再**跑 `-Capture`，**复跑** `check-drift.ps1` 得 `matched=16 drift=0` + 原文 `No drift: the snapshot matches the live DSH home.` + **`EXIT=0`**。**退出码定义：`0` = 无漂移 ／ `2` = 有漂移 ／ `1` = 用法或环境错误。** ⇒ **标准四步法（顺序不能换）**：① `check-drift.ps1` 判方向 → ② `sync-to-dsh-home.ps1` dry-run 先量（确认 copy 集合**恰好等于**漂移条数）→ ③ **先备份再** `-Capture` → ④ 复跑 `check-drift.ps1` 验收 `drift=0 + EXIT=0`。

**执行 + 验收配方（四条命令，顺序不能换）**

```powershell
$R='D:\workspace\agent\dsh_base'
# ① 先定方向：看 live-newer / snapshot-newer（exit=0 无漂移 / exit=2 有漂移）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\check-drift.ps1"
# ② dry-run（不带开关，不动任何文件）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\sync-to-dsh-home.ps1"
# ③ 裁定后真跑（写操作；实现见 sync-to-dsh-home.ps1:232-249）
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\sync-to-dsh-home.ps1" -Capture
# ④ 验收：必须以 drift=0 + exit=0 收尾
powershell -NoProfile -ExecutionPolicy Bypass -File "$R\tools\check-drift.ps1"
```

- **验收判据 = 第 ④ 步 `drift=0` 且 `exit=0`**（收尾行 `No drift: the snapshot matches the live DSH home.`）。**别拿"capture 输出说 copy 了 N 个文件"当验收**——它只说明第 ③ 步动过 N 个文件，不说明结果对。
- **前提：动手前先确认所有写手都已停**（`AGENTS.md` 是热刷新的、live 随时在动）⇒ **`drift=0` 是时刻、不是属性**：live 再改一次就得**重跑 `-Capture`**，否则池立刻又落后。**纪律：改完 live 必须 capture**——只改了 live 侧却把漂移留着，等下一次谁跑 `-Apply`，就会**把 live 静默回退成旧快照**（刚改的内容没有任何报错地消失）。
- **坑：dry-run 会把两个方向都列出来，且对"两侧都存在但不同"的文件，两份清单是同一批**（`:196-229` 两个 plan 共用同一条"hash 不等"判据，`:359` / `:363` 分别打印）⇒ **光看清单分不出谁新、也就选不出开关**，方向只能由第 ① 步判。
- **坑：判"manifest 被重写"必须看 `generated_at`，不能看字节数。** `-Capture` **哪怕只 copy 1 个文件也会整份重算 manifest**（`sync-to-dsh-home.ps1:246` 打印 `manifest.json rewritten: 17 entries`），但 manifest 的**字节数可能完全不变**（Lead 实测：重算前后都是 **7,260 B**——只有 `sha256` / `bytes` 字段在换值）⇒ 拿"文件大小没变"当"没重写"会得出**假结论**，让人误以为 capture **静默失败**。同理，manifest 里那条过期的 59027 B 旧记录，在重算前后**都产生不了 drift**（`check-drift.ps1:134-139` 从不读 `$e.sha256`）。**更硬的一条实测**：四轮 `-Capture` 下来 manifest **恒为 7,260 B**，而 `generated_at` **四次各不同**；根因 = `Write-DshManifest` 各字段长度守恒（只有 `bytes` 跨位数时才偶然变）⇒ **字节数对"是否被重写"零信息量**。**并且不要手工改 manifest**：它只是 `-Capture` 的产物——`:244` 每次整份重写（`Write-DshManifest`）、`:246` 打印 `manifest.json rewritten: N entries`；而判漂移**从不读**它的 `sha256` 字段（`check-drift.ps1:134-135` 逐字 `$sh = Get-DshHash $snapPath` / `$lh = Get-DshHash $livePath`，现算后比对）⇒ **手改任何字段都不会影响判漂移的结果**，只会制造一份更不可信的记录。
- **非 `dsh-*` skill 不产生 drift 是设计内过滤、不是漏报**（本轮实测）：`sync-to-dsh-home.ps1:130` 与 `check-drift.ps1:176` 是**逐字同一句** `if ($d.Name -notlike 'dsh-*') { continue }`，后者上游 `:155` 的注释还写明 `deliberately`。⇒ `pwsh-on-windows` / `sedimenting-skills` 本轮被改过，但**既不入池、也不报 `[LIVE-ONLY]`**——这是设计，别当漏报去"修"。**推论（重要）**：改这类 skill（例如 `orchestrating-subagents`、`sedimenting-skills`）时，`check-drift` **不会报警**、快照里也**没有备份** ⇒ 对它们而言 `artifacts\backups\<name>.<日期>.bak` 是**唯一**回滚源；另一个会话正在改的技能也全在这类池外 ⇒ **它们的改动在 `check-drift` 里完全不可见**。
- **`check-drift` 的 `matched` 是动态值，不能进验收判据**（旧文把它定义成"可比文件数"是**错的**，以本轮实测为准更正）：`matched` = **hash 逐条相等的文件数**（`check-drift.ps1:136-137` 只在 `$sh -eq $lh` 时 +1，汇总打印 `:193-194`）⇒ `matched + drift` 才等于可比文件数（本轮 capture 前 `13 + 3 = 16`、capture 后 `16 + 0 = 16`）；只有 `drift=0` 时它才恰好等于"条目数 − `[SKIP]` 数"（17 − 1 = 16）。⇒ **验收只认 `drift=0` 与 `EXIT=0`**；把 `matched=16` 当常数写进判据，条目数一变就会误判。
- **判"池真同步"只能靠三件套**：`file_count` 与实际条数一致（`check-drift.ps1:104-105`；本轮实测 17/17）+ `generated_at` 是本次（本轮实测 `2026-10-09T14:52:01+08:00`）+ **现算 hash** 逐条相符。两个脚本都**不打印、也不写任何 `STALE` 标记**（`check-drift.ps1` 只有 `[SKIP]` `:117` / `[BROKEN]` `:122` / `[SNAP-ONLY]` `:128` / `[DRIFT]` `:147` / `[LIVE-ONLY]` `:186` 五种标签；manifest 里 `(?i)stale` 匹配 0）⇒ **根本不存在"检查有没有 STALE 行"这一步**，别照着一个不存在的前提下结论。
- `config\_backup\` 子树不进 manifest（`:144` / `:163`）。

**池的覆盖边界（池的定义权威 = 现存产物 `D:\workspace\agent\dsh_base\config\manifest.json`：本轮 recapture 后 **17 条 / `file_count=17` / `generated_at=2026-10-09T14:52:01+08:00**；宪法 §9 只讲**备份与回滚纪律**、**已不再定义池**，别再去宪法里找这句话）**：池**覆盖不到真正生效的编排 preset**。池里 preset 那半边指向**已死的** `~/.dsh\.agent-presets`（运行时全部 `.js` 里 `.agent-presets` 出现 0 次，见 `02-mechanics.md` 的 Q3 / Q7）；**真正生效**的是 **`artifacts\presets\orchestrator-bundle\cordis.patch.yml`**（经 `profiles\web\package.json:5` 的 `link:` 挂载 + `profiles\web\cordis.patch.yml:69-73` 的 `selectedDefault: orchestrator` 选中）——**bundle patch 与 profile patch 都不在池内** ⇒ **`-Apply` 无法恢复现网真正生效的编排 preset**，只能恢复一个没人读的目录式旧件。⇒ 「重建 home = 跑一次 `-Apply`」是**错的**。**同一条边界还有第二半**：同步与漂移检测**只认 live `skills\dsh-*`**（`sync-to-dsh-home.ps1:130` 逐字 `shared cross-project library, not ours`）⇒ `orchestrating-subagents` / `pwsh-on-windows` / `sedimenting-skills` 这类**非 `dsh-*` 的 skill 根本不在池内**——改它们**不产生任何 drift**（`check-drift` 永远显示"无漂移"，给的是**假安心**），同时它们也**没有自动回滚源**（改前必须自己留副本）。

**与第 1 节表格的呼应**：`AGENTS.md` 是**热刷新**的（第 1 节表格：改完当轮即收到 `Updated instructions from: ~/.dsh/AGENTS.md …`）⇒ **回退宪法的影响面不只新会话**，而是每个正在跑的会话**下一轮**就开始按旧教义行事。

> 本节行号取自 `tools\sync-to-dsh-home.ps1` / `tools\check-drift.ps1`（本机当前版本）；脚本一改行号就漂，**可迁移的是判据**（方向由字段定、drift 方向定生死、manifest 哈希字段不可信、池覆盖不到生效 preset）。

### 2.15 skill 根卫生：清理 `~/.dsh/skills` 时，**被正文引用的凭据文件就地保留**（实测反例）

> 编号说明：接 2.14 顺延为 **2.15**。

`~/.dsh/skills` 是**多会话共享**目录（一次清理立刻对所有会话生效），而 skill 正文是用**相对路径**点名自己目录里的文件的 ⇒ **移走被引用者 = 制造假指针**：会话照着正文去找一个不存在的文件，**而且没有任何报错**。更重的一层：它可能**推翻用户的既有决策**。

**实测反例（本轮）**：`ascend-env\credentials.txt`（2,011 B）全库被 **6 处**引用——

| 引用方 | 行 | 性质 |
|---|---|---|
| `ascend-env` | `:38` / `:244` | 凭据本体所在 skill（"新值只写在 `credentials.txt`"） |
| `vllm-ascend-source-install` | `:11` | 密码 fallback 指过去 |
| `github-pr-flow` | `:32` / `:154` | **2026-10-08 用户决策的单一出处**（凭据允许放 skill 目录内、就地保留） |
| `dsh-skill-self-audit` | `:132` | **点名要求校验该文件真实存在，找不到按 FAIL 报** |

⇒ 移走一个 2 KB 文件 = **1 个 FAIL + 3 条假指针 + 推翻一条用户决策**。

**对照**：两枚 15,395 B 的编辑器残留（`.bak`）全库 **0 命中**引用 ⇒ 才属可移；本轮取证时它们**已被并行清理者移走**（该目录只剩 `SKILL.md` 21,580 B）——这也正说明**清单与行号都会漂，判据只能是"动手前 grep 一次"**。

**纪律（清理前逐条执行）**

1. **只移明确的编辑器残留**：`.bak` / `.orig` / `.tmp` 这类；即便如此也要**先看引用命中**再移，不要凭扩展名好看就动。
2. **任何 `*credentials*` / `*.key` / `*.pem` / `*.token` 一律先 grep 全库引用**；**被任何 skill 正文引用的就地保留**——被引用者移走等于制造假指针，还可能推翻用户的既有决策。
3. **移动一律是"移入 `artifacts\backups\skill-hygiene-<日期>\`、保留原相对路径、记 sha256"**，**不删除**（"移走"必须可逆）。

**取证（只读，可抄）**

```powershell
# 1) 全库谁被点名（列引用方 + 行号；数次数别用 Select-String -AllMatches，它恒为 0）
Get-ChildItem 'C:\Users\admin\.dsh\skills' -Recurse -File -Filter *.md |
  Select-String -Pattern 'credentials\.txt' -Encoding utf8 |
  ForEach-Object { "{0}:{1}" -f $_.Path, $_.LineNumber }
# 2) 残留候选（显式计数，不要从目录外观下结论）
Get-ChildItem 'C:\Users\admin\.dsh\skills' -Recurse -File |
  Where-Object { $_.Name -match 'credentials|\.bak$|\.orig$|\.tmp$' } |
  ForEach-Object { "{0}  {1} B  sha={2}" -f $_.FullName, $_.Length, (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower().Substring(0,8) }
```

> 凭据的**登记与存在性校验规则**单一归属在 `dsh-skill-self-audit`，凭据**存放策略**的单一出处是 `github-pr-flow` §0；本节只写"清理时怎么不制造假指针"。

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

### 2.17 「本轮运行失败」+ `Provider finish_reason: <X>`：透传 / 可重试 / 致命三分，以及"是不是 DSH 的 bug"判据

> 承接 **2.12.1**（扫出错误串之后怎么判读）。本节只写**判据与实装链路**，不写扫描配方。

**先拆掉最容易被误读的一层：那句报错文字不是 DSH 的判定。** 用户可见的

```
本轮运行失败
Provider finish_reason: content_filter
```

是 **UI 的 i18n 标题 + 上游字段透传**——`"message.turnError": "本轮运行失败"`（英文 `"This turn failed"`）在 `node_modules\@deepseek-ai\dsh-client-ui-chat\lib\client.js:5526`（英文 `:5715`）。**"本轮运行失败"是界面文案，"Provider finish_reason: …" 是上游给的** ⇒ 报告这类问题时不要把两句一起当成"DSH 崩了"的证据。

**实装位置的取证方法**（**别写死路径**，本机会漂移）：从活着的 host 进程命令行取 `<install>`（配方见 `dsh-agent-preset-verification` §0）；`~\.dsh\launcher\runtime` 在本机**已不存在**，旧文拿它当「唯一权威」已失效。**`D:\workspace\agent\dsh_base` 不是 DSH 源码树**（只有 `artifacts/` 与备份）⇒ 在那里找不到实现，**别在错的地方读源码**。

**链路四跳**（每一跳都给 `文件:行号` + 可搜的名字）：

1. `node_modules\@earendil-works\pi-ai\dist\api\openai-completions.js:1190-1212` 的 `mapStopReason()`——**错误字符串在这里生成**：`:1202-1203` `case "content_filter"` → `{ stopReason:"error", errorMessage:"Provider finish_reason: content_filter" }`；`:1204-1205` `network_error` 同形；`:1206-1210` `default` → `Provider finish_reason: ${reason}`（**别忘 default 分支：任何没被枚举的上游 reason 都从这儿出**）；`:1197-1198` `length` → **非错误**（UI 显示的是"已达到输出 token 上限"）。⇒ 报错里那个 `<X>` 就是**上游 worker 的 `finish_reason` 原样**。
2. `node_modules\@deepseek-ai\dsh-llm-pi-ai\lib\index.js:1380-1391` `classifyPiAiError()`——**没有 `content_filter` 分支** ⇒ 落到 `:1390` `return "PI_AI_ERROR"`。⚠️ `:1389` 会把含 `network|connection|socket|fetch|ECONN*` 的文本判成 `TRANSPORT`（**这决定下一步它可不可重试**）。
3. `node_modules\@deepseek-ai\dsh-llm\lib\types\retry-policy.js:16-22` 默认重试码 = `EMPTY_RESPONSE / RATE_LIMIT / SERVER / TIMEOUT / TRANSPORT`。**`PI_AI_ERROR` 不在内**。
4. `node_modules\@deepseek-ai\dsh-llm-retry\lib\index.js:160` ⇒ 不在集合内 ⇒ **不进退避、直接放行**（把错误抛给上层）。只有把策略显式配成 `mode: "always"` 才会**无条件重试**。

**判据（可迁移，换任何错误串都照做）**：**报错字符串里带着上游的 `finish_reason` ⇒ 先怀疑上游、而不是 DSH**。三步判定动作：① 在 **runtime** 的 dist 里 grep 这个字符串（找到"是谁生成它"的那一跳）；② 读 `classifyPiAiError()` 有没有**为该类错误开专门分支**（没开 = 归 `PI_AI_ERROR` / 跟 `network|connection|socket|fetch|ECONN*` 沾边的会被误判成 `TRANSPORT`）；③ 查该 code **在不在 `retry-policy.js` 的重试集合里**。**三条一起看才能判"透传 / 可重试 / 致命"**——只看报错文字得不出任何一条。

**已知真实形态（本机实测，属证据不属结论；别再当成"上下文超长"）**：多次事件里模型**已经产出数百到数千个输出 token** 后上游才给 `content_filter`（**输出侧过滤**）；也出现过**第 1 轮第 1 步、usage 全 0、模型只吐一句拒绝语**（**输入侧 / 网关兜底**）。⇒ **与"上下文超长"无关**（命中的 prompt 都小于该模型 `contextWindow`），也**与"会话有多长"无关**。**附带结论**：`content_filter` 归为**不可重试的致命错误** ⇒ 已生成的输出被**整个丢弃**、**无降级、不换模型**——这是**健壮性设计取舍**，不是"报错了"的 bug。

**不要做什么**：① 不要在 `D:\workspace\agent\dsh_base` 里找这段实现（它只有 artifacts）；② 不要把 `length`（`mapStopReason` 的 `:1197-1198`）判成错误并写进排查清单（UI 文案完全不同）；③ 不要只 grep 第二跳就下结论——**没有专门分支**是判"不可重试"的**必要条件之一**，还得看第 3、4 跳。

**验收标准**：能一句话说出这个错误串是**谁生成的**（文件:行号）+ **归到哪个 code** + **在不在重试集合里** + **会不会丢弃已生成输出**。四条都答得出才算判完。

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
- 不要把"热重载后页面还能打开"当成部署成功——换的是冷启动的账。（**唯一的精度例外**：**向语法合法的 patch 追加一条新 MCP row** 实测会被热重载拉起、无需重启，见 2.7；但那**不豁免**"冷启动正确性"这一步，也**没有**验证"热改一条**已存在**的 row 的 `config`"。）
- 不要在没有 **host 之外**的看门狗时，改自己正跑在里面的那个 host。
- 不要提交一个**没被真实故障触发过**的回滚/看门狗脚本，也不要让重启命令漏掉 `DSH_HOME` / `--port` / `--no-open`。
- 不要**以为**"挂了 `dsh-experimental-agent-team` + `-tool-agent-team`，所有普通委派就全废（`TEAM_NOT_MEMBER`）、且没有配置级绕法"——**那是已被证伪的旧断言**（2.5）。真实后果是它**顶掉 `send_message` / `list_agents` / `interrupt_agent` 三个原生名**（把 `send_message` 指向普通子代理时报 `active teammate "<id>" not found` 就是这么来的），而两族能否并存取决于**有没有一层在 team bundle 之后把原生行插回来**。⇒ 别按"先别挂"办，按 2.5 的三条纪律办，并且**去会话工具面点名核对 schema**（`agent_id` vs `target`）。
- 不要手工改 `node_modules` 里已装插件包的源码：写成**断言式补丁脚本**（`--check` / 时间戳备份 / `--restore`，锚点必须唯一）；**不要**给 `.strict()` 的持久化 schema 加字段（回滚后老代码读不了日志）；**不要**把"队友有没有越界写"设计在 workspace 变更事件上（DSH 没有按 agent 的归因，2.10）。
- 不要把 `failOnStartupError` / `toolCallTimeoutMs` 改离默认值——`failOnStartupError: true` 只把"形态①的静默缺席"升级成"整个 host 起不来"，对形态③（YAML 解析错误）**买不到任何保护**（2.7 表）。
- 不要**去找**"MCP 的配置文件"或写 `mcpServers` 键——DSH 没有那一层，唯一入口是 patch 里的一行 `@deepseek-ai/dsh-mcp-client`（2.7）；也不要指望 `sse`，它只支持 `stdio` / `streamable-http`，且**不桥** resources / prompts。
- 不要在**没量过**工具面注入量之前就把 MCP server 挂上去——工具 schema 每轮重发，成本按轮线性付（2.8）；也不要先假定"`--discovery` 类开关 + 工具白名单能叠加"，**必须三组对照实测**（单开 / 单开 / 同开），否则可能白付"能力消失"的代价。
- 不要把"隔离 host 打得开（401）"当成 MCP 接入成功——**形态①/②都**是 host 正常但工具没来，**必须点名核对工具**（2.1 / 2.7）。
- 触发信号：用户说"把某个实验包 / 官方 bundle 挂进 profile / 手工 row 还管不管用"，或你正要写 `- id: … disabled: true` + `- insert:` 这种替换式 patch（先读 **2.11**）。
- 不要以为**中文 UI 就等于中文系统提示词**：四个团队包的中文只在 `locale\zh.json`（每包 2 行）与 `README.zh.md`（实测 108 / 72 / 47 / 50 行）里，`lib\*.js` 的 **CJK 行数为 0**（三个包实测 0；只有 UI 包的 `client-ui-agent-team\lib\client.js` 24 行是界面词条）⇒ 注入给模型的 `team:policy` 仍是**纯英文**（`tool-agent-team\lib\index.js:21` 起）。要改策略文本就改 `lib\*.js`，改 locale 不会动系统提示词。
- 不要把 README 里交叉引用的文档当可用来源：`agent-team` / `tool-agent-team` 的 README 指向 `../../../docs/subsystems/agent-team.md`、`../../../docs/config-catalog.md`、`../../../docs/tool-catalog.md`、`../../../.agents/notes/implemented/...`，在 npx 安装根的 `node_modules` 下**逐条 `os.path.exists` 全为 False**（全树只有无关的 `undici\docs`）⇒ **只能依据 `README*`（含 `README.zh.md` / `README.i18n.yaml`）与 `lib/`**，别照 README 的路径去找文档。
- 不要在本总纲里找具体命令——按第 3 节进对应子 skill；本总纲不复制它们的正文。

## 验收标准

1. 能一句话说出本次改动**属于哪一层**、**何时生效**、**怎么撤**（第 1、2.6 节）。
2. 若动了插件行 / patch：已在**隔离环境冷启动**验证**同一组合**（同 profile 文件 + 同 `node_modules`），并观察到启动 URL + 401。**挂了 MCP server 时再加一条**：新工具名**点名**核对过（`mcp__<serverName>__<tool>` 真的出现）——host 打得开**不算**过（2.7 的形态①/②就是"host 正常、工具没了/静默缺席"）；**追加 row 时另按 2.7 的三段验收逐段留证**（`--dump-config` 计数 +1 → 隔离会话 `request/header` 点名 → 真调用一次只读工具），并用 2.7 的"前 N 字节 sha256 相等"证明**只追加没重写**；并对该 server 量过一次**工具面注入量**、与已挂 server 做过基线对比（2.8）；有非 ASCII `env:` 时另按 2.9 用探针 server 验一次保真（判据 = codepoints + utf8 hex 逐项相等）。
3. 若动的是自己正跑着的 host：看门狗**已用人为杀 host 实测过**回滚与重启分支，且重启命令显式带 `DSH_HOME` / `--port` / `--no-open`，marker 文件已落盘。
4. 按第 3 节阶梯留下证据：离线校验结论 → 隔离 host 就绪（401）→ 在线 `agentPreset`/persona/工具/`turn/end` → 上线后的冷启动证据。
5. 子 skill 与总纲的交叉引用双向齐全（总纲 → 子 skill；子 skill description 的"不适用 → 用 `dsh-agent-customization`"）。
6. 遇到"本轮运行失败 / `Provider finish_reason: <X>`"这类报错时，能按 **2.17** 说出**谁生成它（文件:行号）／归到哪个 code／在不在重试集合里／会不会丢弃已生成输出**——四条答不全就说明还没判完。
