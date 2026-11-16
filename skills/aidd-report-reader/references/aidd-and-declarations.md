# AIDD历史线索与声明核查

来源：旧 aidd-report-reader（2026-11-16审查），站点 `https://aidd.huawei.blue`。本轮未登录/调用受保护API，以下为历史路径线索而非在线保证：

- `/api/v1/reports/projects/<project>/summary`：total与severity分布。
- `/api/v1/reports/tasks?project_id=...&page=...&page_size=...`：任务列表。
- `/api/v1/reports/tasks/<task>`：单任务score、分类与建议。
- `/api/v1/issues/global?project_id=...&page=...&page_size=...`：issue明细。

旧记录中的issue含issue_id/task_id/filename/severity/rule_name/original_text/suggestion/processing.location等。真实响应变化时适配解析并保留未知字段，不能按“100条足够”跳分页。

公网地址声明在一些Ascend仓库的SECURITYNOTE.md既有章节，以类型、代码地址、文件、外部地址和用途描述；文件位置与要求每仓不同。先列当前树、读本仓贡献/安全规范和扫描配置，再决定覆盖对象及格式。链接出现≠实际联网，注释/测试地址也应按规则分类。

检查报告schema而非硬套旧xlsx坐标。OOXML的sheet名需经workbook关系映射，sharedStrings/inlineStr/数字/公式缓存不同；错误列定位会造成一整类域名假漏报。结果绑定扫描和仓库commit，避免用当前行号解释旧报告。

旧“报告一定漏报”“扫描器不扫md/py/cpp”“只能改既有表”“404证明端点没了”均降为待当前范围验证的历史现象。
