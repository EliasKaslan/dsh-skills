---
name: app-release-version-recon
description: 核查某 App 今天是否发版、更新了什么：Microsoft Store / iTunes lookup / Homebrew cask 三处版本取证，区分构建重发与服务端功能放量，全程不动本地安装。
disable-model-invocation: true
warm-triggers: chatgpt软件更新了什么 / 某App今天发版了吗 / 版本号核查 / 商店更新说明 / 不动本地安装查版本
warm-reason: 低频任务（用户偶尔问「某软件更新了什么」），不必每轮占目录成本。
---

# App 发版与更新内容取证（只读）

## 何时调用
用户问「某软件/App 今天是不是更新了 / 更新了什么」，且常附带「不要动我本地的安装」。交付 = 平台 + 版本号 + 时间 + 官方变更条目，并明确区分「构建重发」与「服务端功能放量」。
转交边界：要比模型能力/跑分 → `llm-landscape-recon`；查仓库与发行版 delta → `github-org-delta-watch`。

## 三个取证端点（已真跑通，均只读）
1) iOS/iPadOS：`https://itunes.apple.com/lookup?id=<trackId>&country=us` → `results[0].version` / `currentVersionReleaseDate` / `releaseNotes`。ChatGPT trackId = `6448311069`。
2) macOS（被 Homebrew cask 收录即可）：`https://formulae.brew.sh/api/cask/<name>.json` → `version` / `sha256`；`url` 字段里通常直接带版本号（2026-11-23 查得 `26.1117.41037`，url 尾巴是 `ChatGPT-darwin-arm64-26.1117.41037.zip`）。
3) Windows（Microsoft Store）：`https://displaycatalog.mp.microsoft.com/v7.0/products/<ProductId>?market=US&languages=en-us&fieldsTemplate=Details`，读 `Product.LastModifiedDate`（UTC 更新时间）+ `DisplaySkuAvailabilities[].Sku.Properties.Packages[].PackageFullName`。

PowerShell 取法（避免 charset 缺失导致乱码）：
    $wc=New-Object Net.WebClient; $wc.Headers.Add('User-Agent','Mozilla/5.0')
    $bytes=$wc.DownloadData($u); $json=[Text.Encoding]::UTF8.GetString($bytes)
再 `ConvertFrom-Json` 后只打印需要的字段，避免整段 JSON 进上下文。

## 判据
- **版本号 ≠ 功能开关**：服务端分批放量时，商店说明常只写 “Bug fixes and small improvements.”；装到最新版也不等于功能已开通。功能事实只认官方 release notes。
- **同构建线换 build ≠ 新功能**：同一构建线换末段 build（2026-11-19 观察到 `26.1111` 线从 `...71025` 变 `...71704`），官方 changelog 无当天条目 → 判为热修/构建重发，别包装成新功能。
- **时区**：官方日志按美西日期，商店 API 给 UTC。北京时间当天早上看到的「今天更新」，往往对应美西前一天那批条目——先换算再下结论。
- 桌面端可能没有独立日志，被记在主产品 changelog 下；用 `?type=codex-app` 这类 facet 试。

## 坑（错误原文）
- **iTunes lookup 有 CDN 缓存**：2026-11-19 首次 `country=us` 拿到旧的 `1.2026.307 / 2026-11-10`；同接口加 `&cb=<guid>` 并换 `country=gb` 才返回 `1.2026.314 / 2026-11-19T07:18:48Z`。（2026-11-23 复核：同样 `country=us` 已返回 `1.2026.315 / 2026-11-21T15:59:35Z`，缓存现象未复现，但换地区+随机参数复测仍应照做。）判「今天发没发版」必须换地区 + 随机参数复测一次。
- **Store API 的 `Version` 不是可读版本**：返回 `7323121736482816`，真实版本只在 `PackageFullName`（`OpenAI.Codex_26.1111.9664.0_x64__2p2nqsd0c76g0`）里；该产品 `ReleaseNotes` 为空，别指望它给变更内容。
- **Windows PowerShell 5.1 `ConvertFrom-Json` 解析 iTunes 大响应会炸**：`传入的数组无效，应为“,”。 (6852)`，并且会把整段原始 JSON 打印进上下文（含乱码本地化字段）。改为逐国家单次请求、先落盘再解析，或用 `[regex]` 只抠 `"version":"..."`。
- **`https://learn.chatgpt.com/docs/changelog` 是 JS 渲染**：`web_fetch` 只返回导航，`.md` 后缀 404 → 需浏览器渲染才能看到条目正文。
- **官方 release notes 直链偶发 403**：可试加 `?facet1=crm`（子代理复现，未验证：是否稳定复现）。
- **第三方站版本滞后数天**（Softpedia / TechSpot 当时仍是 11-14、11-08 的值），不能作当日证据；引用前先看 `LastModifiedDate` / `currentVersionReleaseDate`。

## 纪律
只读公开网页与商店 API：不安装、不启动、不检查更新、不读本地安装目录版本号。用户说「不要动本地」时一律按此执行；要核对本机版本先征得同意，且只做只读读取。
