---
name: aidd-report-reader
description: "读取AIDD等文档质量扫描报告，校验分页、项目范围与问题聚合，并将报告命中对账到仓库交付件；适用于扫描分数、fatal/critical清单和公网地址声明覆盖核查。"
whenToUse: "需要读取AIDD等文档扫描报告、核对分页统计、严重问题和公网地址声明与仓库交付件。"
disable-model-invocation: true
---

# 文档质量报告读取与对账

确认目标站点、项目、报告/任务版本和扫描commit。连接工具优先，浏览器使用当前可用的受支持接口；已有会话不要求重新登录，未登录按正常OAuth/可见UI流程进入，登录失败停止盲试。

旧AIDD经验中的Vue内部状态注入、脚本勾协议或读取localStorage token不能作为当前DSH默认登录方案。协议与授权按用户选择处理，不能为抓报告强行绕过交互；不得输出或持久化会话凭据。

## 数据覆盖

优先界面导出或当前工具支持的已授权只读数据通道；API线索见 [references/aidd-and-declarations.md](references/aidd-and-declarations.md)，以当前页面实际请求/文档重新核实。SPA路由200不代表登录；401/403/404/502都不能单独证明接口永久下线。

逐页获取，检查total/total_pages、去重ID、项目过滤、返回schema、报表时间及中途变化。summary、task明细与issue列表统计互核；严重程度缺字段/未知类别单列，不能默默归normal。task详情可能不含issues，不用空字段推“零问题”。

保留 issue/task ID、文件、原文、建议、rule、severity、位置与引用版本。按severity/rule/category/文件聚合，列fatal/critical及疑似误报；扫描器建议需对照真实上下文，不能按分数自动修改文档或批量替换术语。

## 仓库交付件对账

先确认当前规则、扫描范围和目标仓已有声明位置。报告可能漏命中，但“全仓所有URL都必须声明”和“只扫某几类后缀”都不能从一次历史案例推广。按确立范围重新检索，区分报告漏报、扫描范围外和声明缺口。

把每条命中的文件/位置/地址/用途与声明逐项关联；位置可能是chunk相对offset，需还原到目标commit。报告xlsx按关系表定位sheet和单元格类型，不固定Q/R/L列或假定sheetN；复杂表格交给当前DSH可用表格解析能力（先检查实际工具schema）。

修改时沿用仓库规范，URL可达不等于引用正确，失效URL也不宜为过门禁盲删。没有既有文件时按任务要求创建，不能因旧“最小改动口径”禁止补必要文件。只读审计请求不自动授权提交/发布。

## 2026-11 现场复核：树层级、接口与「未处理」判读

站点 `https://aidd.huawei.blue`。登录由浏览器密码库填充后点「立即登录」，无验证码；令牌约 1 小时有效（JWT iat/exp 差 3600），401 是过期不是接口下线，重登即可。取数据用页面上下文 `fetch` + `Authorization: Bearer <localStorage.authToken>`，只发 GET。

## 层级与接口

- 层级是 `领域(昇腾=16) → 全部产品 → 产品 → 版本 → 项目`。MindSpeed-Ops 是「产品 MindSpeed / 版本 26.2.0 或 master / 项目」，在"全部产品"下找不到同名产品。
- 树：`/api/v1/file-management/projects?group_id=16&include_all_projects=true`，看 `node_type` 区分 group/product/version/project。
- 问题：`/api/v1/issues/global?project_ids=<proj_id>&validity=valid|all&view=current|history`；聚合用同参数的 `/counts-by-project`、`/counts-by-file`。
- 任务组：`/api/v1/detection-tasks/groups?sort_by=created_at&sort_order=desc`；文件表：`/api/v1/file-management/projects/all-files?project_id=`。

## 判读坑（实测）

- `project_id=`（单数）在 issues/global 会被忽略，返回"我可见的全量问题"，容易把别的项目问题算到本项目头上；必须用 `project_ids=`。
- 必须显式 `cache:'no-store'`：否则浏览器缓存返回 `items:[]` 或 `{}`，`total` 却正常，误读成零问题。
- `page_size=200` 可能返回空 items（total 仍正确），改 100 分页。
- **「未处理」= `feedback_status` 为 `pending` 或为空值（`null`），不是只有 `pending`。** 只按 `=== 'pending'` 过滤会漏掉「从未处理过」的条目：本项目 64 条 pending 全部回填后，平台仍显示 2 条未处理，它们就是 `feedback_status=null` 的老条目。收尾自检必须同时统计两者为 0：

```js
const left = all.filter(x => !x.feedback_status || x.feedback_status === 'pending');
```

- 先看 `validity=all`：`pending` 可能全是 `validity≠valid` 的失效条目，UI 的「有效问题」只算 valid，两边数字不一致属正常。
- `403 {"detail":{"code":"PERMISSION_DENIED","permission":"project:read","reason":"default_deny"}}` 常见于产品/版本节点，不代表子项目不可读；权限按项目成员判定，逐项目试。

## 问题处理闭环与反馈回填（2026-11 实测）

## 问题处理闭环与反馈回填（2026-11 实测）

把某个项目的「未处理」清零 = 取 `feedback_status=pending` → 逐条对仓内实现核对 → 需要改的提 PR、不需要的在平台回填。

**反馈接口**（页面上下文 fetch，Bearer 用 `localStorage.authToken`）：

```js
await fetch('/api/v1/issue-management/issues/' + issue_id + '/feedback', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + t, 'Content-Type': 'application/json' },
  body: JSON.stringify({ status: 'rejected_false_positive', comment: '...' })
});
// 200 → {"status":"rejected_false_positive","rating":null,"comment":"..."}
```

- `status` 实测可用：`accepted_modified`（采纳并已修改）、`rejected_false_positive`（误报/无需改）。写入是更新当前状态，重复提交只覆盖。
- 收尾自检：重取 `validity=all&view=current` 逐页统计 `feedback_status`，确认 `pending` 归零；逐条回读备注也能核对是否落库。
- 批量提交串行 + 每条间隔约 100ms，64 条一次全部 200，没有被限流。

**判定纪律**（同一批里三种坑都会出现）：

1. 拼写字典误判合法标识符：CANN `gert::`（GE Runtime 命名空间）、内核张量名 `Ad`，改成 `ge::`/`id` 反而错。
2. 扫描器建议方向与实现相反：文档表格写「未知型号默认走 ATB」，实现是返回 MAX_VERSION 走 `addmm_`——要按实现改文档，不能照抄建议。
3. 原文/行号已随后续提交失效：先 `git log -p -- <file>` 与全仓 `git grep` 判是否已修，再决定修还是回填。

每条结论都要落到代码行、提交号或全仓一致性上；扫描发生在若干天前时行号一律不可信，按文本 grep 定位。
