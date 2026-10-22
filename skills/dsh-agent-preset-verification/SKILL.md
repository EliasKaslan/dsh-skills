---
name: dsh-agent-preset-verification
description: DSH agent preset 验收两阶段——preset 没生效但看不出哪错了、到底挂载对没对、改完先离线确认；离线过了但插件行为不对、persona 与工具在真会话里对不对、委派为什么失败；headless 不能验 preset 且会污染 home。阶段一离线逐行解析 plugins 与 config，阶段二干净 host 真会话 RPC 核对。适用于"preset 到底挂载对没对 / 改完 preset 先离线确认能不能挂 / preset 没生效但看不出哪错了 / 离线过了但插件行为不对 / 委派为什么失败 / 能不能用 headless 验收 preset / maxDepth 写 0 为什么让工具全废"。不适用：只要干净实验环境 → 用 `dsh-isolated-web-host`；不知改哪层、何时生效、怎么撤 → 用 `dsh-agent-customization`。
whenToUse: 离线（还没起会话）校验 preset 能不能挂载、plugins 里哪个包名在当前安装不存在、哪个配置键或工具名写错时用；已起会话要验 persona、工具裁剪与委派请转 live 版。模型看不到本节。
---

# 离线校验自定义 agent preset

> 本 skill 是总纲 `dsh-agent-customization` 的子 skill：只负责「离线静态校验」这一段；DSH 的分层、生效时机与上线纪律见总纲。
> **会话级验收、以及"验收入口该选哪个"（headless 不能验收 preset） → 见 `dsh-agent-preset-live-verification`**（本 skill 不复制）。

**先读这条（旧版整篇已被证伪）**：本 skill 曾建立在「`$DSH_HOME/.agent-presets/<id>/` 目录式 preset + `scanRoot` 权威健康检查」之上。**那套在 0.2.0-rc.2 上已完全失效**：`@deepseek-ai/dsh-agent-presets` 这个包**不存在**，全树唯一提到 `.agent-presets` 的地方是官方说明里的一句 *"Nothing reads that directory any more."*。现行载体是 **bundle patch 里的 `@deepseek-ai/dsh-agent-preset` 声明行**。

⇒ 所以本 skill 的**第 0 步永远是"先认机制"**；跳过它去抄别的版本的行，必失败。

## 何时调用

**加载本 skill 当：**

- 刚写了 / 改了 preset 的插件行（bundle patch 里声明行的 `config.plugins`），想在安装之前知道它能不能挂载。
- preset 看起来"没生效"，需要区分是**插件包在当前安装里不存在**、**配置键写错**、**深度策略写错**、还是**工具名写错**。
- 准备往 `plugins` 里加实验插件行，需要先知道失败会长什么样。
- 还没起会话（或不想起会话），只想要"这份 preset 静态上到底对不对"的结论。

**不要用本 skill（转交）：**
- 已经起了会话，要验运行时真相（system prompt persona 原文、真实工具裁剪、委派是否跑通、`turn/end`），或要**选验收入口** → 用 `dsh-agent-preset-live-verification`。
- 只是要一个干净的隔离实验环境（重定向 `DSH_HOME`、401 判就绪、taskkill 收尾） → 用 `dsh-isolated-web-host`。

**前置**：这台机器上能跑 `node`（本机 v24）。 ／ **后继**：静态结论为"能挂载"后，进 `dsh-agent-preset-live-verification` 做会话级验收。

## 0. 先认机制：当前这个 dsh 用哪套 preset 载体

**不要跳过。** 同一个 `$DSH_HOME` 下可能同时存在多套 dsh 安装，而**不同发布线的包名集合相差很大**（实测 `0.2.0-rc.2` 与 `0.1.0-rc.6` 至少有 5 个 preset / workflow / present 相关包互为对方独有）。三条命令，全只读：

1. 找到**正在跑的那套**安装根（从活着的 host 进程命令行里读，别猜）：

```powershell
Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -like '*dsh*bin.js*' } | Select-Object ProcessId,CommandLine
```

   → 命令行里 `...\node_modules\@deepseek-ai\dsh\lib\bin.js` 的**上一级安装根**就是后文所有命令的 `<install>`。

2. 读它声明/实际的版本——**一律读 `package.json`，绝不要按目录名猜版本**（两个 npx 安装的目录名 `b86ed90107c62dab` / `1e7f6d9597241db0` 毫无线索）：

```powershell
(Get-Content -Raw -Encoding utf8 '<install>\node_modules\@deepseek-ai\dsh\package.json' | ConvertFrom-Json).version
```

   本机实测的两套——**是两条不同的发布线（0.2.0 线 vs 0.1.0 线），不是"同一版本的 rc.2 与 rc.6"**：

   | 安装目录（无版本线索） | 实测版本 | 说明 |
   |---|---|---|
   | `%LOCALAPPDATA%\npm-cache\_npx\b86ed90107c62dab` | **`0.2.0-rc.2`** | 活着的 web host 跑在这套上 → 判"当前版本"认这个 |
   | `%LOCALAPPDATA%\npm-cache\_npx\1e7f6d9597241db0` | **`0.1.0-rc.6`** | **0.1.0 线**；包集与 0.2.0 线**相反** |

   ⇒ 写"rc.6"会让人读成 `0.2.0-rc.6`，那是个**根本不存在的版本**。两线实测差异：`dsh-agent-preset` 只在 0.2.0 线；`dsh-agent-presets`、`dsh-workflow-worker-thread` 只在 0.1.0 线；`dsh-workflow-ptc`、`dsh-tool-present` 只在 0.2.0 线。**跨线抄插件行必失败。**

3. 判它用哪套机制——**看旧机制的扫描包在不在**（注意单复数）：

```powershell
Get-ChildItem '<install>\node_modules\@deepseek-ai' -Directory | Where-Object { $_.Name -like '*preset*' } | Select-Object -ExpandProperty Name
```

   实测 `0.2.0-rc.2` 输出：`dsh-agent-preset` / `dsh-agent-preset-registry` / `dsh-client-ui-agent-preset` / `dsh-client-ui-permission-presets` / `dsh-permission-presets` —— **没有 `dsh-agent-presets`**。这就是"旧机制已死"的判据（旧机制那个包只存在于 **`0.1.0-rc.6`** 那套里）。

   想再钉一锤，看全树谁在读那个目录（用 grep 工具）：

   ```
   pattern '\.agent-presets'    path '<install>\node_modules\@deepseek-ai'
   ```

   实测命中**恰好 1 条**，且是上游说明文字 *"Nothing reads that directory any more."*（`dsh-agent-preset\skills\editing-cordis-compositions\SKILL.md:70`）。

⇒ 任一判据指向"没有 `dsh-agent-presets`"，就**不要再往 `$DSH_HOME/.agent-presets/<id>/` 写任何东西**：写进去、改内容、删掉，都**不会有任何行为变化**。

## 1. 现行载体：bundle 里的声明行

bundle 目录 = `package.json`（`"dsh": { "bundle": { "patch": "./cordis.patch.yml" } }`）+ `cordis.patch.yml`：

```yaml
- insert:
    - id: preset-<id>                     # Loader row id，惯例 preset-<preset 的 id>
      name: '@deepseek-ai/dsh-agent-preset'
      config:
        id: <id>                          # required
        plugins: [ ...插件行... ]          # required
        # 可选：name / description / order
```

- `config.id` 与 `config.plugins` 是 **required**；`plugins` 的类型只到 `z.array(z.any())`（`dsh-agent-preset/lib/index.js:13-19`）⇒ **类型层什么都放行**，包名写错它不管。
- `<id>` 的字符集由 registry 在**注册时**校验，**不要**指望 `Config()` 抓（见坑 1）。
- 改**已发布**的 preset 不是改文件，而是按 Loader row id **覆盖声明**：`- id: preset-standard` + `name` + 完整 `config`。**`config` 是整体替换、从不深合并** ⇒ 必须把 `id` / `plugins` 及原有每个字段**全部重述**，否则等于把没写的字段全删了。
- 上游权威说明就在本机：`<install>\node_modules\@deepseek-ai\dsh-agent-preset\skills\editing-cordis-compositions\SKILL.md`（格式与 legacy 迁移）；同 bundle 的 `cordis-composition-reference\SKILL.md` + `references\packages.md`（**可挂载的插件包清单**，写行前先 grep 它）。

## 2. 逐行离线校验 `plugins`（本 skill 的核心动作）

**为什么必须有这一步**：`plugins` 的类型层放行一切，所以一个包名写错、或写了**别的 dsh 版本才有的**包，`Config()` 与 `--dump-config` **都看不出来**，只在**激活 / 挂载**时才炸。离线必须把**每个插件包的解析**单独验一遍。

配套脚本（与本文件同目录，**已实测**）：`check-preset-plugins.mjs`。

```powershell
node <skill 目录>\check-preset-plugins.mjs --base "<install>" "<bundle 的 cordis.patch.yml 或 profile 的 cordis.yml>"
```

它做四件事：解 YAML（含 `!!js` 标签）、抽出**所有** preset 声明行的 `config.plugins`（含 `group: true` 的嵌套子行）、跳过 Loader 内建（`cordis:group` / `cordis:include`）、对每个真实包名用 `createRequire("<install>/package.json").resolve()` 解析。**退出码非 0 = 有行不解析。**

实测通过分支（本机 `0.2.0-rc.2`，对着正在生效的 web profile 组合，201 行）：

```
base=C:\Users\admin\AppData\Local\npm-cache\_npx\b86ed90107c62dab
rows checked=201 failed=0
```

实测失败分支（同一脚本对一份含真 / 假坏行的 patch，7 行）：

```
  declaration: loader row id=preset-review preset id=review plugins=5
  PASS   tool-subagent-list-agents (@deepseek-ai/dsh-tool-subagent-control/list-agents) -> node_modules\...\lib\types\list-agents.js
  FAIL   workflow-worker-thread (@deepseek-ai/dsh-workflow-worker-thread) -> MODULE_NOT_FOUND: Cannot find module '@deepseek-ai/dsh-workflow-worker-thread'
  FAIL   totally-made-up (@deepseek-ai/dsh-does-not-exist-9f3a) -> MODULE_NOT_FOUND: Cannot find module '@deepseek-ai/dsh-does-not-exist-9f3a'
  LOADER delegation (cordis:group)

rows checked=7 failed=2        # 退出码 1
```

- `--base` 必须是第 0 步认出的**那套安装根**。实测本机 `~/.dsh\profiles\node_modules` **根本不存在**——能解析 `@deepseek-ai/*` 的只有安装根本身，把基准指错地方会让**每一行都假失败**。
- 子路径导出（`<pkg>/<sub>`，如 `@deepseek-ai/dsh-tool-subagent-control/list-agents`）会一起验；这类行写错子路径同样在这里就报出来。
- 脚本只证"**specifier 能解析**"：**不 import、不激活、不验 `config` 的值**——配置值仍走第 3 步。

**跨发布线对照（"两条线的包集不可混用"最直观的证据）**——**同一个 bundle**（从 live 组合里抽出的 `preset-standard` 声明，19 个 plugins，共 30 行），只换 `--base` 就换结论：

```
--base <0.2.0-rc.2 那套>  →  rows checked=30 failed=0

--base <0.1.0-rc.6 那套>  →  FAIL preset-standard (@deepseek-ai/dsh-agent-preset) -> MODULE_NOT_FOUND
                             FAIL workflow-ptc (@deepseek-ai/dsh-workflow-ptc) -> MODULE_NOT_FOUND
                             FAIL present (@deepseek-ai/dsh-tool-present) -> MODULE_NOT_FOUND
                             FAIL tool-plugin-manager (@deepseek-ai/dsh-plugin-manager/tools) -> MODULE_NOT_FOUND
                             rows checked=30 failed=4
```

⇒ 这份 preset 在 0.2.0 线**全绿**、在 0.1.0 线**四处缺包**。**"这个包名到底有没有"必须先绑定安装根再问**。

- **动脚本前先读它的头部注释**：那里记了两个解析器陷阱，其中最关键的一条是 **`import.meta.resolve(spec, parent)` 的 `parent` 参数在本机 Node 上被忽略**（实测：用它会把正确的安装报成满屏 `ERR_MODULE_NOT_FOUND` 假失败），必须改用 `createRequire("<install>/package.json").resolve()`。

### 2.1 自己写脚本核对 patch 时的两个陷阱（实测示例）

上面那条只说明**脚本能处理** `!!js`；**但你为核对同一份 patch 临时手写一段解析脚本时，下面两件事必踩**。

**坑 A：`yaml.load(text)` 用 js-yaml 默认 schema 解析 bundle patch 必抛。** 实测 js-yaml `4.3.2`，对象是 `orchestrator-bundle\cordis.patch.yml`（其第 53 行就是 `disabled: !!js process.platform === 'win32'`）：

```
YAMLException: unknown tag !<tag:yaml.org,2002:js> (53:56)
```

`!!js` 是 Loader 的表达式标签，js-yaml 默认 schema 里没有它，报错只指向**第一条**这样的行。修法——注册一个 scalar 标签，把它当字符串留着（**不要求值**）：

```js
const jsTag = new yaml.Type('tag:yaml.org,2002:js', { kind: 'scalar', construct: (d) => d }); yaml.load(text, { schema: yaml.DEFAULT_SCHEMA.extend([jsTag]) });
```

可照抄同目录 `check-preset-plugins.mjs`（ESM 里它写作 `yaml.default.Type`，`construct` 额外包成 `{ __jsExpr: data }` 以防有人误求值；两种写法解出同一棵树）。**别把这个报错读成「preset 挂不上」**——它只是你的解析器缺个标签。

**坑 B（更危险）：`doc[0].config.plugins` 这个路径根本不存在，会把「根本没检查」静默读成「通过」。** 反模式：

```js
const rows = doc[0].config.plugins;              // ❌ undefined
if (!rows || rows.length === 0) report("pass");   // 任何 falsy 兜底 —— 于是一行都没查却报了"通过"
```

bundle patch 的顶层形状是 **`[{ insert: [ … ] }]`**，preset 声明行在 **`insert[0]`**：

```js
const decl = doc[0].insert[0];   // ✅ { id: 'preset-<id>', name: '@deepseek-ai/dsh-agent-preset', config: { id, plugins } }
const rows = decl.config.plugins;
```

实测同一份文件同一次运行：`doc[0].hasOwnProperty('config')` → `false`，`doc[0].config` → `undefined`，`doc[0].config.plugins` → `undefined`。

**两个数字不是一回事，别混用**（本次实测，同一文件同一次运行）：

| 数字 | 口径 |
|---|---|
| 脚本打印的 `rows checked=33` | **递归 walk** 口径：声明行自身 + 顶层 `plugins` + `group: true` 行嵌套的 `config` 里所有子行，再去掉 `cordis:group` 承载行 —— 即 `33 = 1 声明行 + 18 顶层 + 14 嵌套子行`，加上被脚本按 `LOADER` 跳过的 **3** 个 `cordis:group`（planning / compaction / delegation）正好 36 行 |
| `doc[0].insert[0].config.plugins.length` = **18** | **顶层**口径：声明行的 `config.plugins` 直接列出的行数，不含任何嵌套展开、也不含声明行自己 |

⇒ 报数字必须带上口径。拿 33 去对 `plugins.length` 会得出「脚本漏了 15 行」的假结论；反过来只认 18 会漏掉所有嵌套子行（本机这 14 行里有整个 delegation 组）。

## 3. 逐行校验 `config`（分三类，不要一律用 `Config`）

**a) 有 `Config` 导出的包**（实测 `dsh-tool-subagent` 的 exports = `Config, apply, inject, name`；另有 `dsh-persona` / `dsh-mcp-client` / `dsh-llm-retry` 等一批）：

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

- 标记串 `PRUNE_MARKER` 是 `"\n\n[... tool result middle pruned ...]\n\n"`，约束是 `headChars + 39 + tailChars ≤ thresholdChars`（`dsh-compaction-tool-result-pruner/lib/index.js:8,43-44`）。

**c) 什么都不导出的包** —— 实测三个包的 exports：

  ```
  dsh-compaction-basic               => BasicCompactionEngine, default
  dsh-compaction-tool-result-pruner  => DEFAULTS, PRUNE_MARKER, ToolResultPruner, codePointLength, default, resolveConfig
  dsh-plan-mode                      => EXIT_PLAN_MODE, PlanModeController, default, planProjectionDefinition, resolveConfig
  ```

  ⇒ **`dsh-compaction-basic` / `dsh-compaction-tool-result-pruner` / `dsh-plan-mode` 都不导出 `Config`**；compaction-basic 只能读源码核对键名与约束。

**compaction-basic 的键集与约束（按 `0.2.0-rc.2` 源码，别背旧版那份错的）**：

```
POLICY_CONFIG_KEYS（:19-29）  thresholdRatio / headroomTokens / retainRatio / retainTokens
                              / summarizationProvider / summarizationModel / maxTokens
                              / compactionRetries / maxOverflowRetries
BASIC_COMPACT_CONFIG_KEYS（:31-35）= 上面全部 + modelPolicies + auto
```

- 真校验在构造函数 / `resolveConfig` 里（**不导出**）：未知键报错在 `validateKeys`（`:209`，原文 `BasicCompactionConfig: unknown key "<k>"`）；`retainRatio >= thresholdRatio` 在 `:156`（原文 `BasicCompactionConfig: retainRatio (0.9) must be less than the resolved thresholdRatio (0.7)`）；`retainRatio` 与 `retainTokens` 互斥在 `:192`；比值须 ∈ (0,1] 在 `:223`（`assertRatio`，调用点 `:188,:190`）；`maxOverflowRetries` 非负整数在 `:195`。
- ⚠️ 旧版正文漏掉了 `headroomTokens`、且行号是别的版本的行号，**已按 `0.2.0-rc.2` 源码更正**。

## 4. 安装与看状态

- **只能走 `plugin_manager` 工具的 `action: install_bundle`**，`target` = bundle 的**绝对目录**。上游原文：*"It runs package installation and bundle selection itself; do not reproduce those steps with shell commands."*（**不要**自己拿 shell 去 pnpm/npm install 那个 bundle）。
- 该动作**会在 Host 进程里执行插件代码**，因此需要 Full access 或人工审批：*"Installing a bundle executes plugin code in the Host process, so it requires Full access or approval."* ⇒ **审批被禁用的会话里这个动作会被拒**，得有人在 UI 侧点。
- 装完看状态：`plugin_manager` 的 `list_bundles`（列出已装 bundle）与 `list_plugins`（看 `preset-<id>` 那一行的 `enabled` / `fiberPhase`）。
- **激活失败的声明行会留在 roster 上并带诊断**，在 bundle 修好并重装之前**不能组合会话**。已存在的会话及其子会话保持它们启动时的插件修订——**改过行为要去新会话里验**。

**挂载期的逐行诊断原文长什么样**（`dsh-agent-preset-registry/lib/index.js:197-222, 262-273`）：registry 对挂载子树逐行 audit，失败行拼成 `${rowId} (${pkgName}): ${detail}`，`mountPreset` 把它们 **join("\n") 后整体抛出**；还有一类是"行在等服务"（`waiting for <service>`）。包不存在时 `detail` 就是 `MODULE_NOT_FOUND` 系的信息。

## 5. `--dump-config`：只证"进树"，不证"能加载"

```powershell
node "<install>\node_modules\@deepseek-ai\dsh\lib\bin.js" --profile web --patch <patch.yml> --dump-config
```

- 它能打印**组合后的**树（含你 patch 里的声明行与 `config.plugins`），退出码 0。实测在**隔离 `DSH_HOME`** 下跑：1259 行输出、`profiles/<p>` 会被生成。
- **它会写盘，但写的是"本该是空的那份"**（旧的"别拿真实 home 跑它"已按实测更正）：`prepareProfile` 无论走哪条路径都 `writeFileSync(profile.dir/cordis.yml, PROFILE_ROOT_CONFIG)`（`dsh/lib/profile-boot-*.js:189`；`composeProfile` 另有一条 `:207`；写穿/隔离机制单一归属在 `dsh-isolated-web-host`）⇒ 在真实 home 跑它的**真实后果** = 把 `profiles/<p>/cordis.yml` 重写成**空模板**（`[]` + 三行注释）。**这不是污染**：该文件在磁盘上只为给 Loader 当 include root 锚点，真启动同样会重写它。实测本机那份曾被 Loader 的 tree write-back **烘焙成 46726 B 的整棵组合树**（源码注释原文：*can bake composed rows into this file — which would duplicate every bundle insert on the next boot*），正是这次重写把它清回 223 B。
  → 修法：跑完**核对 `profiles/<p>/cordis.yml` 是否已是空模板**（正常就该是），**别**把它当成"配置丢了"去回滚——正文本来就不该在那里；要反复验组合仍请另给 `DSH_HOME`。
- **它不 import 任何模块**。实测：拿一份 `plugins` 里塞了两条不存在包名的 patch 去 dump，**退出码 0、两行照样原样打印、输出里 error/warning 命中数 = 0**。⇒ **dump 干净 ≠ 能挂载**，坏 row 在 dump 里完全看不出来。

### 5.1 一句话判「某个 preset / 模式还在不在」（实测）

三个位置必须**分别**对账，只看其中一个必然判错：

| 看哪里 | 说明什么 | 不能说明什么 |
|---|---|---|
| `$DSH_HOME/.agent-presets/<id>/`（`preset.yml` 里带显示名） | **仅说明磁盘上还有这份 legacy 快照** | rc.2 上没有任何代码读它 ⇒ 与"还能用"无关 |
| bundle 备料目录（`package.json` 的 `dsh.bundle.patch` + `cordis.patch.yml`） | 说明"**已备好、可安装**" | 未 `install_bundle` ⇒ **零行为变化** |
| `--dump-config` 输出里的声明行 **`id: preset-<x>`** ＋ `agent-preset-registry` 的 `config.default` | **权威**：这次组合里有哪些 preset、新会话默认哪个 | 仍**不证明能挂载**（第 2 步才算） |

```powershell
$out = & node "<install>\node_modules\@deepseek-ai\dsh\lib\bin.js" --profile web --dump-config 2>&1
Write-Output "EXIT=$LASTEXITCODE"
$txt = $out | Out-String
[regex]::Matches($txt, '(?m)^\s*-?\s*id:\s*(preset-\S+)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
[regex]::Matches($txt, '<要判的 id>').Count   # 0 = 不在组合里
```

用户问「我之前那个模式还在不在」时，**"文件还在" ≠ "模式还在"**——跑完上面三行，按上表把两个结论分开说：磁盘工件在不在、组合里在不在。

## 坑与修法

- **`healthy ≠ 能挂载`（本轮最重要的两条硬事实之一）**。实测：`0.1.0-rc.6` 那套的 `scanRoot` 对同一份 preset 报 `orchestrator | healthy`，而 `0.2.0-rc.2` 里那份 preset 的插件行**有一条包名根本不存在**（`@deepseek-ai/dsh-workflow-worker-thread`）。原因：`scanRoot` / 发现层**只扫目录结构与元数据，不 import 插件**，缺包行在它眼里照样 healthy。
  → 修法：健康检查**只当"目录结构存在"的证据**，永远不能当"能挂载"的证据。判"能挂载"必须走第 2 步（逐行解析）+ 第 3 步（逐行验 config），再加会话级验收。

- **`Config()` 只是类型层，通过 ≠ 能挂载**。实测 `BasicCompactionEngine.Config({ thresholdRatio: 0.7, retainRatio: 0.9, nope: 1 })` **不抛错**，未知键 `nope` 原样留在结果对象里（`keys = thresholdRatio,retainRatio,modelPolicies,nope`）。
  → 原因：schemastery 的 `z.object` 不剥离未知键；键名与跨字段校验在 `resolveConfig` / 构造函数里。
  → 修法：能拿到 `resolveConfig` 就用它（pruner / plan-mode）；拿不到（compaction-basic）就按源码键集核对。**不要只跑 `Config()` 就宣称校验通过**。

- **`maxDepth` 语义陷阱（最容易写错的一条）**：`maxDepth` 限制的是**子代理自身的深度**，不是"父代理能否委派"。
  → 机制：`resolveChildDepth(parent, maxDepth)` 算 `delegationDepthOf(parent) + 1`，`childDepth > maxDepth` 抛 `SubagentDepthError`，消息 `subagent depth <attempted> exceeds maxDepth <max>`（`dsh-subagent/lib/types/child-agent.js`）。
  → 顶层调用者深度为 0 → 它的子代理深度为 1，所以 **`maxDepth: 0` 会让该工具的每一次调用都失败**；**`maxDepth: 1` 才是"叶子角色"**（子代理能跑，但它自己再委派会被拒）。
  → 而且实测 `Config({ provider:'spawn', toolName:'explore', maxDepth: 0 })` **不抛错**（原样返回 `maxDepth: 0`），所以离线校验抓不到，只有第一次委派才炸。
  → `maxDepth: 'provider-managed'` 也被接受，用于 codex / claude-code 这类外部 provider。

- **`toolFilter.allow` 里写的是全局工具名，且挂载期不校验**。实测 `Config({ provider:'spawn', toolName:'explore', toolFilter:{ allow:['reed'] } })` **通过**，拼错的 `reed` 原样保留。
  → 原因：`restrict()` 在**子代理创建时**才执行（`dsh-tool-subagent/lib/index.js` 里 `runtimeCtx.subagents.start` 附近），挂载期不校验。
  → 修法：写完后手工把 `allow` 列表与当前会话实际可见的工具名逐一对照，别指望启动时报错。子代理**继承父级组合**，`allow` **加不回**父级没有的工具。

- **静态 `agentOptions` 会绕过 `allowedModels` 策略**：该策略只约束"模型主动发起"的选择（`dsh-tool-subagent/lib/index.js` 的 `subagent/model-selection-policy`）。在 row 里写死 `agentOptions.provider/model` 就等于把这条策略绕过去了，别把它当模型路由的兜底。

- **部署坏 row 是致命且无声的**。实测：patch 里放一个指向不存在包的 row，host 进程**仍然存活、stdout/stderr 全空、永远不打印 token URL、端口不监听**——即**静默不服务**。
  → 后果：没有报错可看，很容易误判成"还在启动中"而一直等。
  → 修法：必须有**独立于 host 的回滚手段**——部署前备份 patch，在 host 之外轮询判活，超时自动还原备份。不要指望从 host 日志里看出问题。

- **本机端口枚举是盲的**（`netstat` / `Get-NetTCPConnection` 恒空）⇒ "端口不监听"是**恒真空断言**，既不能当失败判据也不能当清理判据；判活只认 HTTP 探针 + 启动时落盘的 pid（正文见 `dsh-isolated-web-host`）。

- **`Copy-Item -Force` 保留源 `LastWriteTime`**（本轮实测）⇒ 装完后目标 patch 的 mtime 是**候选件**的时间、**不是安装时刻**。
  → 修法：**别拿 mtime 判"什么时候装的"**——用 sha256 + 自记时刻；本轮就是靠 sha256 才发现目标文件已被换过。

- **`check-preset-plugins.mjs` 不带目标 yml 参数会打 usage 并 `exit 2`**（不是 `0`，本轮实测）。
  → 修法：离线校验命令**必须带 yml 绝对路径**；看到 `exit 2` 先怀疑**参数漏了**，别当成"校验发现 2 个问题"。

- **`rows checked=33` 与 `plugins=18` 是两个口径、不是矛盾**（本轮实测确认，**正文不在此处重述**）：算式与两行口径表在**本节 §2 末尾**（`33` = 递归 walk 行数 / `18` = `config.plugins.length` 顶层数），那里已写明"拿 33 去对 `plugins.length` 会得出脚本漏了 15 行的假结论"。⇒ 这里只记纪律：**报数字必须带口径，别拿两个数互相当证据**。

- **判"活 host"别只看 `node.exe`**（本轮实测）：机器上另有 MCP 的 node 进程与 `launch-dsh.mjs` 包装进程 ⇒ 只看 `node.exe` 会**认错 PID**（判活判错、甚至杀错）。
  → 修法：过滤命令**复用 §0 里那条**（`:38` 的 `Win32_Process` + `*dsh*bin.js*`），再与落盘 pid 复核；这里只记失败模式、不复制命令。

## 不要做什么

- 不要只跑 `Config()` 就宣称 preset 校验通过（未知键它照收）。
- 不要用 `--dump-config`（或旧的 `scanRoot` 健康检查）判断插件能不能加载——两者都不 import 模块。
- 不要往 `$DSH_HOME/.agent-presets/<id>/` 写东西来"改 preset"——`0.2.0-rc.2` 上没有任何代码读它。
- 不要在用户真实 `~/.dsh` 上试坏 row（静默不服务 + 无回滚 = 用户环境挂掉）；要试就去隔离 host。
- 不要把 `maxDepth: 0` 当成"禁止这个工具委派"——它是"禁止创建子代理"，会让工具彻底不可用。
- 不要用 shell 自己复现 `install_bundle` 的安装步骤；也不要以为审批被禁用的会话能装 bundle。
- 不要在没有备份 patch、没有 host 外探活的情况下部署实验插件行。

## 验收标准

- 第 0 步有结论：**本次用哪套机制、`<install>` 是哪条路径**（写下来，后面每条命令都依赖它）。
- `check-preset-plugins.mjs` 对目标 patch / 组合跑出 **`failed=0`、退出码 0**。
- 每个 row 都跑过对应入口：有 `Config` 的跑 `Config(cfg)`，有 `resolveConfig` 的跑 `resolveConfig(cfg)`，两者都没有的按源码键集人工核对，且全部不抛错。
- 装完后 `list_plugins` 里能看到 `preset-<id>` 行且状态正常；有诊断就逐行读它的 `rowId (pkgName): detail`。
- 部署实验 row 前：patch 已备份、host 外的判活手段已就绪、失败还原路径明确。
- 静态全绿**只说明"配置层没问题"**——persona / 工具裁剪 / 委派是否真对，仍须走 `dsh-agent-preset-live-verification`。
