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
