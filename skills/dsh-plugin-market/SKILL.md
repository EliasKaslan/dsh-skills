---
name: dsh-plugin-market
description: DSH 插件市场/索引源：无官方源、format:1 校验、engines.dsh 兼容判定与第三方源陷阱
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
