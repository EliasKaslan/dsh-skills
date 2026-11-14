---
name: dsh-plugin-market
description: DSH 插件市场：无官方源、format:1 校验、engines.dsh 兼容门禁、升级后市场静默失效与修复
whenToUse: 问「插件市场里有什么能装/兼容当前 DSH 版本吗/Discover 空白/怎么加索引源/这个插件能不能用」时加载
---

# DSH 插件市场与索引源：无官方源、format:1 校验、engines.dsh 兼容判定

# DSH 插件市场与索引源（0.2.2-rc.2 实测）

## 何时调用

- 触发：问「插件市场里有哪些插件 / 有没有兼容当前版本的插件 / Discover 页为什么是空的 / 怎么加索引源 / 某个第三方插件能不能装」。
- 交接：写插件、验收插件行是否生效 → `dsh-agent-customization`；查 DSH 自身文档与包清单 → `dsh-doc`（`references/packages.md`）。
- 前置：确认运行时版本（profile bundle 的 `version` 字段即当前 DSH 版本）。

## 硬事实：官方市场不自带任何索引源

- 市场 = `@deepseek-ai/dsh-experimental-plugin-market-bundle`（experimental、optional、无平台限制）。装上才得到 Host 服务 `plugin-market` + Web「Plugins → Discover」tab + `plugin_market` agent 工具；不装时 profile 里 `- id: plugin-market` 的 config 是悬空的，没人消费。
- 官方**没有**默认索引：源码 `src/index.ts` 里 `indexes: z.array(url).default([]).volatile()`；README 原文 "No index source is configured by default"。Discover 空 ≠ 坏了，是没配源。
- 配源位置：profile 的 `cordis.patch.yml` → `- id: plugin-market` / `config.indexes: [https URL, ...]`；Discover/Settings 写的是同一处（`settings.update`）。
- 索引 URL 必须是**规范形式**（无空格、无 fragment、无凭据、http(s)），否则只显示错误、永不 fetch（错误原文 `Index URL is not in canonical form`）。

## 索引格式 format:1（以验证器源码为准，别信二手描述）

包 `@deepseek-ai/dsh-plugin-market-index`，校验函数 `parseMarketIndex`（src/index.ts，约 330 行）。

必填：`format` 必须是**数字** `1`（`$.format must be 1`）；`title`（对象形式必须含 `en`，`$.title must contain en`）；`plugins[]` 的 `name`、非空 `versions[]`；每版 `version`（精确 SemVer）、`publishTimestamp`（**整数 Unix 秒**，`must be an integer number of Unix seconds in [0, 10^11)`）、`source`（`{"type":"npm"}` 或 `{"type":"git","url","commit":40位小写hex}`）。

**`engines` 是可选**（`optional(object,'engines') ?? {}`）：省略 = 无约束。二手资料常说「每版必须声明 engines.dsh、否则整份索引被拒」，与源码不符。

`metadata.category/labels/sortKeys` 必须先在同一 `metadata` 里声明再用，否则整份索引被拒（`references undeclared id "x"`）。

## 兼容判定口径（与安装同一套）

`@deepseek-ai/dsh-app-boot` 的 `plugin-compatibility.ts`：`semver.satisfies(runtimeVersion, range, { includePrerelease: true })`；runtime 取 app-boot 自身 `package.json` 版本。有 `engines.dsh` 就独占判定，没有才回退到 `@deepseek-ai/dsh*` peerDependencies。不满足 → 安装被拒，只能对精确 `name@version` 记豁免。

**预发布陷阱**：`engines.dsh: "^0.2.2"` **匹配不到** `0.2.2-rc.2`；写死 `"0.2.2-rc.1"` 也不匹配 rc.2。要覆盖 rc.2 必须写成 `^0.2.2-rc.1` 或 `>=0.2.2-rc.1 <0.3.0-0`。

## 只读判定一个插件能不能用（不装市场也能做）

1. 下索引：`Invoke-WebRequest` 后用 `[IO.File]::WriteAllBytes` 保有原始字节，再交给 Python 以 utf-8 解析（PowerShell 直接 `ConvertFrom-Json` 吃大文件容易爆）。
2. 逐版判 engines：`require('C:/Program Files/nodejs/node_modules/npm/node_modules/semver')`（npm 自带；profile 里通常没有 semver 包，`require('semver')` 会 `Cannot find module 'semver'`）。
3. 版本对得上 npm：`https://registry.npmjs.org/<name>`（scope 用 `@` 保留、`/` 编码）。**latest 标签常落后**：`@deepseek-ai/dsh` 的 `latest` 是 rc.1，rc.2 只在 `next`；market bundle 自己 `latest=0.2.1-alpha.4`，装 rc.2 必须写全版本。
4. 质量交叉核对：GitHub API 的 `stargazers_count`/`pushed_at`/`archived` 对索引里的 `sortKeys.stars`（实测索引值比真实偏低约一成，量级可信；索引没给 star 的别猜）。
5. 分档：A = engines 明确覆盖 + npm 可查 + 仓库活跃；B = 只有 star/活跃、manifest 无 engines（「能装不承诺」）。

`dsh.so` 这类大市场索引约 10 MB、上万条，四分之一左右声明了 compatible；README 实测 2 万条约 130 MiB heap，全量下载 + 内存全文索引，小内存机器慎挂。

## 可信度纪律

- 索引自称「Install-Verified & Security-Audited」是索引方声明，不是官方审计；索引本身无签名，`name/version/engines` 都是索引方的说法，安装时会用源 manifest 复检。
- `official: true` 只代表由 DeepSeek 发行，不代表「稳定」。

## 坑

- asar 内的 glob/grep/ls 全部失败（`os error 3`），只能对已知绝对路径用 read 工具。
- 索引条目里 `repository` 是对象 `{url,directory}`，`category/keywords/stars` 在 `metadata` 下，不在插件顶层——按顶层读会全是 None。
- `publishTimestamp` 写成毫秒会被整份拒绝（上界 `1e11`）。
- 一次装错版本（如把 rc.1 精确 pin 的插件装到 rc.2）不会自动纠正，要先卸再装或记精确豁免。

## 安装市场 bundle：必须重启，且会动三处文件

## 安装市场 bundle：必须重启，并且会改三处文件（0.2.2-rc.2 实测）

装法固定写全版本，不能用 latest（`latest` 是 0.2.1-alpha.4）：

```
plugin_manager install_bundle target=@deepseek-ai/dsh-experimental-plugin-market-bundle@0.2.2-rc.2
```

返回 `application: "restart-required"`、`restartReason: "package-moved"`、`nextStep` 要求重启 DSH。**HMR 不覆盖**：新包解析到了另一个目录，必须重启 host；重启前 Plugins 页没有 Discover，`plugin_market` 工具也不会出现在工具列表里。

一次安装会动三处：

1. profile 的 `package.json`：`dependencies` 加包，`dsh.profile.bundles` 数组追加 bundle 名；
2. profile 的 `pnpm-workspace.yaml`：`minimumReleaseAgeExclude` 自动追加本包及其依赖的 13 条 `0.2.2-rc.2` 条目（pnpm 11 的 supply-chain 策略，不是报错，别手动删）；
3. `node_modules`：pnpm 落 51 个包，日志在 `profiles/<name>/.plugin-manager/logs/operation-*/pnpm.log`。

bundle 自带的 `cordis.patch.yml` 只 insert 两行：`plugin-market`（`disabled: !!js "!ctx.get('profileContext')"`）和 `ui-plugin-market`。profile 里已有的 `- id: plugin-market` + `config.indexes` 是对这两行的 **override**，不要再写 `name`/`moduleName`，否则同一模块声明两次会 `unaddressable`。

peer 判断：bundle 只要求 `@deepseek-ai/cordis ~4.1.0`，运行时 `app.asar/dsh/node_modules/@deepseek-ai/cordis/package.json` 的 version 是 `4.1.0`，满足。pnpm 那句 `[WARN] Issues with peer dependencies found. Run "pnpm peers check" to list them.` 是 profile 里其它第三方插件的既有警告，别归因给市场包。

回滚：`plugin_manager set_bundle enabled=false`（config 保留）或 `remove_bundle`（同时删依赖）。两者同样 `restart-required`，回滚后也要重启才算数。

## 自建索引：托管位置、git 源不能自引用、发布前自检

"把插件注册到 DSH 市场"没有提交入口——市场只按**配置的索引 URL** 渲染，聚合索引由各自的运营方决定收录。
所以唯一可执行的"注册"是：**自己发布一个 format:1 索引**，把自己的插件登记进去，再把该 URL 加进 `plugin-market.config.indexes`。

## 索引文件放哪：不要放构建产物目录

构建脚本通常会 `rm -rf` 输出目录再重建（静态站常见做法），手放进去的文件会在下次构建时**被删掉**。
放**仓库根的独立目录**（如 `market/index.json`），用 raw HTTPS 提供：

- `raw.githubusercontent.com/<owner>/<repo>/main/market/index.json` —— 可匿名抓取，实测 200
- GitCode 的 raw 端点对抓取器常返回 **403（反爬）**，不要用它当索引源

## 循环依赖：git 源必须指向"已存在的提交"

`source.git.commit` 要求 40 位小写 hex，而索引文件本身要**随后**才提交 ——
索引不可能引用包含自己的那个提交。做法固定为两步：

1. 先发布代码提交（它就是"已发布版本"）；
2. 再把索引写成**指向第 1 步的 commit**，单独提交一次。

代价是历史里多一个提交；这是格式要求带来的，不是纪律问题。

## 发布前自检清单（对着校验器，不是对着文档）

- `format` 必须是**数字** `1`（字符串会被拒）
- `title` 是对象时**必须含 `en`**
- 每版 `version` 是精确 SemVer；`publishTimestamp` 是**整数 Unix 秒**（毫秒会让整份被拒，上界 1e11）
- `source` 三选一：`{type:'npm'}` 或 `{type:'git', url, commit:40位hex}`
- `engines` 可选；一旦写了，就用**与 DSH 相同的判据**本地复验：
  `semver.satisfies(runtimeVersion, range, { includePrerelease: true })`
  （npm 自带 semver：`require('<nodejs>/node_modules/npm/node_modules/semver')`，profile 里通常没有 semver 包）
- **预发布陷阱**：`^0.2.2` 匹配不到 `0.2.2-rc.2`；要覆盖 rc 必须写 `>=0.2.2-rc.1 <0.3.0-0` 这类显式范围

## 可见性与边界

索引没有签名，`name/version/engines` 都是索引方的说法，安装时 DSH 会用源 manifest 复检——
所以插件自己的 `package.json` 里也要有同样的 `engines.dsh`，两处必须一致。
自建索引只在**配了该 URL 的机器**上可见；想让别人也能装，对方要么加同一 URL，要么由大索引运营方收录（无提交渠道）。

## 审计声称免密的第三方插件（免费额度从哪来、账记在谁头上）

## 何时调用

用户问「这个插件免费是真的吗 / 天上掉馅饼吗 / 免费用前沿模型 API 是什么套路 / 这个包能装吗」。目标不是复述 README，而是回答三件事：额度从哪个钱包出、账最终记在谁头上、装上去拿到了什么远程执行权。

## 六步探针（按性价比排序）

1. **先读项目自己的逆向文档**：`docs/*-wire.md`、`TECHNICAL*.md`、`SYNC.md`。声称「免密、无需 Key」的项目往往自己就把闸门规则写得很细（UA 形状、必带请求头、会话 id 铸造形状、必须逐字声明的官方工具集、官方系统提示）。有这类文件，基本已可判定「冒用官方客户端 + 拆分配额桶」，不必再猜。
2. **验匿名令牌**：定位 `public`/`anonymous` 凭据常量与 `CLIENT_UA` 常量所在的版本文件；源码注释里出现 `impersonates` 一类字样就是自认。
3. **列全出网面**：grep 全仓 `https?://`，去重成域名表，逐条标注「上游 / 作者自建 / CDN / IP 查询」，并确认有没有把 prompt、用量、会话回传给作者（除专门车道外）。
4. **验「加密封条」是不是安全剧场**：若盐/pepper 常量与解封函数在同一文件、分片与密文又都随包发布，则封条可离线解开，文件头声称的「无法重建」为假。这是高频虚标点。
5. **验升级与推送信任根**：updater 里 pin 的公钥有几把（一把 = 作者单点可向全部实例推代码）；公告 feed 有无独立签名；能否弹全屏内容、能否用 `<img src>` 加载任意 http(s)（追踪像素）。
6. **验安装期**：`package.json` 有无 `preinstall/install/postinstall/prepare`；`files` 白名单与实际随包二进制是否一致（拆片 `.part` + 运行时解压 `spawn` 要单独点出来）。

## 判定口径

- **谁付钱要分开说**：上游厂商推广位 / 作者自建池 / 用你自己的账号 / 自带 Key。四条合成一句「免费」就是误导。
- **代价通常记在用户头上**：上游 ToS 常明文禁止非官方客户端接入（「其他客户端一律 403，即使有有效 Key」）；被封的是用户的出口 IP 与配额桶。
- **「不限量」几乎总是假的**：必有 429 窗口、地区 403，以及 free 版被砍的上下文/输出上限（去比对同名付费模型的 limit）。
- **作者变现**：联盟返利码、每日弹窗广告、star 门槛、可远程推送的更新通道——这些才是「免费」的对价，必须在报告里点明。

## 坑

- **子代理对同一 host 说法不一致时，以源码里的常量为准**，不要以 README 表格为准——README 常滞后于代码，默认端点与文档写法不一致很常见。
- **裸名 npm 包 ≠ 官方包**：同名包可能是已 deprecated 的第三方 fork；要比「裸名包下载量 vs 官方 scoped 包下载量」，下载量更高的那个反而可能是冒名的。判「fork 冒用包名」与「投毒」要分开结论，但按投毒级风险对待。
- 结论必须区分**已验证**与**未验证**：没读过源码就不能写「没有后门」，只能写「未发现」。
- 别把「工程质量高」（测试套件、manifest 哈希、失败开放）当成「可信」——两者是不同维度。

## 边界

只审计，不安装、不跑 `npm install` / `npm test`、不执行插件本体。不代替用户做合规判断，只把「上游条款禁止 + 风险落在用户」这一事实摆出来。

## 语言键必须小写、本地化字段只在 plugin 级、用宿主自带校验器离线验索引

## 语言键必须全小写（一条就能让整份索引失效）

`localizedText()` 用 `LANGUAGE_ID = /^[a-z]{2,8}(?:-[a-z0-9]{1,8})*$/u` 校验键名（`src/index.ts`，`fail(... 'must be keyed by a lowercase language id')`）。**`zh-CN` 不合法**，`zh-cn` 才合法——地区子标签也必须小写。

失败是**整份索引被拒**，不是「这一条不显示」：`title`、plugin 级 `title`/`description` 任一处写 `zh-CN`，整份索引解析抛 `MarketIndexError`，插件在市场里根本不出现（Discover 只显示索引错误）。写索引时把语言键当 npm 包名的 scope 那类硬约束对待。

## 本地化字段只在 plugin 级，version 级写了会被静默丢弃

- **plugin 级**（`plugins[].`）：`title`、`description`、`icon`（相对索引 URL 解析）、`author`（纯字符串）、`homepage`、`repository`、`metadata`、`versions`。
- **version 级**（`versions[].`）：只有 `version`、`publishTimestamp`、`source`、`engines`。

`marketVersion()` 只挑这四个字段，多写的 `description` **不报错、直接丢掉**。想让它显示就把 `description` 放到 plugin 级（对象形式，需要同时给 `en` + `zh-cn`）。

## 离线用宿主自带的校验器验索引（不是对着文档数格式）

`app.asar` 里的 `@deepseek-ai/dsh-plugin-market-index` 就是宿主真正用的那份校验器，解出来直接 import，比手写格式检查可靠（且能拿到第一条违规的精确 JSON 路径）。

asar 头部的偏移是个坑，实测这套值可用：

```python
f.seek(0); head = f.read(16)
hdr_json_len = int.from_bytes(head[8:12], 'little')   # JSON 长度
base = 8 + int.from_bytes(head[4:8], 'little')         # 文件数据起点
f.seek(0); blob = f.read(base)
header = json.loads(blob[16:16 + hdr_json_len].decode('utf-8'))   # JSON 从 16 开始
# 每个文件: 绝对偏移 = base + int(entry["offset"]), 长度 = int(entry["size"])
```

（`16 + hdr_json_len` 当数据起点会**早 3 字节**，解出来的 `package.json` 前面多一个 `};\n`、`ERR_INVALID_PACKAGE_CONFIG`——这个错位很难看出来，所以照抄上面 `base` 那行。）

把 `@deepseek-ai/dsh-plugin-market-index`、`@deepseek-ai/dsh-package-manifest`、`node_modules/semver` 三棵子树按 `node_modules/<name>/` 还原到临时目录即可 `import`：

```js
import { parseMarketIndex } from '@deepseek-ai/dsh-plugin-market-index';
// 第二个参数必须是**绝对 URL**，不是 {source}：签名是 (value, indexUrl: string)
try {
  const out = parseMarketIndex(raw, 'https://raw.githubusercontent.com/<owner>/<repo>/main/market/index.json');
  console.log('PASS', out.plugins[0].versions.map((v) => v.version));
} catch (e) { console.log('FAIL', e?.name, '|', e?.message); }
```

写反了会得到一句误导性错误：`$ index URL {"source":"..."} must be an absolute URL`。

**索引源与 package.json 的 `engines.dsh` 下界必须一致**：市场按索引里的范围放行，装完 profile 却按包自己的 `engines.dsh` 复检——索引放宽成 `>=0.2.2-rc.1` 就等于把插件推给未验证的宿主，装完在 profile 那步才失败。市场侧可以带上界（`>=0.2.2-rc.2 <0.3.0-0`），包侧通常只写下界，取两者交集后**下界相同**即可。

## 确认当前运行时版本：profile 常常没有 version 字段（0.2.2-rc.2 实测）

## 确认当前运行时版本：profile 常常没有 `version` 字段

本文开头写的「profile bundle 的 `version` 字段即当前 DSH 版本」在本机不成立（0.2.2-rc.2 实测）：
`~/.dsh/profiles/<name>/package.json` 只有 `dependencies` 与 `dsh.profile.bundles`，**没有** `version`，按该说法去读会拿到空值。

真正的版本在运行时清单里，用 read 工具直接读这个**已知绝对路径**（asar 内 glob/grep/ls 仍全部失败，read 已知路径可用）：

`D:\tools\dsh\resources\app.asar\dsh\package.json`

- `name` 是 `@deepseek-ai/dsh-desktop-runtime`，`version` 就是当前 DSH 版本（实测 `0.2.2-rc.2`）；
- 同文件 `dependencies` 里所有 `@deepseek-ai/dsh*` 应为同号，可交叉核对；
- 拿这个版本号去判 `engines.dsh`，记得 `includePrerelease: true`（`^0.2.2` 匹配不到 `0.2.2-rc.2`）。

本机 profile 里正在用的索引源（`cordis.patch.yml` → `- id: plugin-market` → `config.indexes`）：
`https://cdn.dsh.so/market/index.json`、`https://dsh-plugin-lab.github.io/market/index.json`，
另有一条自建索引（git 源指向已发布提交）。未验证：这两份公共索引当前的收录量与新鲜度本轮没有亲自统计。

## 运行时升级后市场静默失效：profile 旧 pin 被兼容性门禁禁用（0.2.2-rc.2 → rc.3 实测）

## 症状：市场"失效"但没有任何报错

- Plugins → Discover 打不开或空白；`plugin_market` agent 工具从工具列表里**静默消失**。
- 活体插件树里 `include:plugin-market` 是 `enabled:false, fiberPhase:null`，而**同 bundle 的 `ui-plugin-market` 仍 active**（客户端 UI 在、宿主服务没起来）。
- 索引源本身正常，不用去查网络。

## 判据链（三条，逐条可查）

1. `plugin_manager` → `action=list_plugins`，分页翻全量（limit=50，offset=0/50/…）筛 `enabled!==true || fiberPhase!=="active"`。
   **`enabled:false + fiberPhase:null` 是两种原因同形**：patch 层 `disabled: true`（平台/配置）与兼容性 preflight 禁用。前者能在 `cordis.patch.yml` 里查到 `disabled:`，后者**查不到**、只在 boot stderr 留痕（本机不落盘，故无法直接取原文）。
2. 定位该行的实际清单：`profiles\<name>\node_modules\<moduleName>\package.json` 存在则**以它为准**（profile 会 shadow 掉 app 内置的版本）；不在才读 `app.asar\dsh\node_modules\...`。
3. 判据一句话：**无 `engines.dsh` 且存在 `@deepseek-ai/dsh*` peer 不满足运行时版本** = preflight 命中。
   源码 `app-boot/lib/index.js` 的 `unmetRequirements`：有 `engines` 时 engines 独占判定、peerDeps 被忽略；否则每个 `@deepseek-ai/dsh*` peer 都要 `semver.satisfies(rt, range, {includePrerelease:true})`。
   所以**只有官方插件会被这条门禁打到**，第三方插件通常没有 dsh peer，不受影响。rc.3 实测全树 225 行里 26 行禁用，其中 25 行是 patch 层明文/平台条件，只有 plugin-market 一行是 preflight 命中。

## rc.3 的根因变化：市场 bundle 变成 app 内置

- rc.3 的 `app.asar\dsh\package.json` 里已有 `@deepseek-ai/dsh-experimental-plugin-market-bundle: 0.2.2-rc.3`、`dsh-plugin-market`、`dsh-client-ui-plugin-market`、`dsh-plugin-market-index`。**rc.2 时代不是内置的**，所以才要 pnpm 装进 profile。
- 升级后 profile 里那条 rc.2 依赖还在 → `node_modules` 里有 rc.2 的 `dsh-plugin-market`（peers 精确 `0.2.2-rc.2`）→ **shadow 掉内置的 rc.3** → 门禁禁用整行。

## 修复：只删 profile 依赖、保留 bundles 条目

`plugin_manager` 的两条路**都走不通**（rc.3 实测）：
- `install_bundle target=...@0.2.2-rc.3` → `{"code":"already-installed"}`（app 已内置，故判"已装"）
- `remove_bundle` → `{"code":"not-removable"}`（installation 态 bundle 不可移除）

正确做法：
1. 编辑 `profiles\<name>\package.json`：删掉 `dependencies` 里的 `@deepseek-ai/dsh-experimental-plugin-market-bundle`，**保留** `dsh.profile.bundles` 里的同名条目（删了 bundles 条目市场就整个消失）。
2. 在 profile 目录跑 `pnpm install` 剪掉孤儿包（实测 `Packages: -53`），可用 `--reporter=append-only`。
3. 重启 host（`restart-required`）。

**为什么能work**：`dsh.profile.bundles` 里的 app 内置 bundle（`dsh-base`、`dsh-web-app`、`dsh-experimental-cot-translation-bundle`）本来就不在 profile 依赖里，照样从 asar 解析加载——这是同 profile 内可直接比对的先例，改前先用 `Test-Path node_modules\@deepseek-ai\<name>` 验一遍这些先例目录确实不存在。

设置覆盖仍然有效：asar 里 bundle 自带的 patch 只 insert `id: plugin-market` + `id: ui-plugin-market`，profile 的 `- id: plugin-market`（只有 `config.indexes`，别写 name/moduleName）按下标合并。

## 验证

- 重启后 `list_plugins` 里 `include:plugin-market` 应为 `enabled:true / fiberPhase:active`；`plugin_market` 工具重新出现在工具列表（bundle 自带注释原文：该工具只在服务挂载时注册）。
- 索引侧不用动：3 条源全 200，11141 个插件全部通过 `parseMarketIndex`。

## 坑

- 别用 `list_bundles` 的 `version`/`installed` 判 profile 实际版本：那是 installation(asar) 清单，profile pin 在 rc.2 时它也照样显示 `0.2.2-rc.3 / installed:true`。
- 别在 `cordis.patch.yml` 里给这行加 `disabled: false`：preflight 在合成之后跑，会再禁一次。
- `pnpm-workspace.yaml` 的 `minimumReleaseAgeExclude` 会留下旧版条目，无害、不必删。
- 本机 pnpm 在 PATH 上是 `pnpm.CMD`（实测 11.23.0）；`pnpm.ps1` 被执行策略拦，直接调 `.ps1` 得到 `PSSecurityException: 因为在此系统上禁止运行脚本`。
- asar 是单文件：内部 `glob`/`grep` 全部 `os error 3`，只能对已知绝对路径用 read；`D:\tools\dsh\resources\app.asar\dsh\package.json` 可直接 read，用来交叉确认内置包与运行时版本。
