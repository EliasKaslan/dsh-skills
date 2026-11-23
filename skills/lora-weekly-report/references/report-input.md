# 本地PR过滤器

输入JSON为 `{"items":[...],"complete":true}`。每个item是PR详情的最小记录：repo（owner/repo）、number、merged_at（ISO8601有时区或null）、title与html_url；可保留其他字段。`complete`仅说明采集侧覆盖声明，不由过滤器证明；search的incomplete_results=true或total_count大于实际返回items时，会标覆盖不足。

在本文件所在目录（`references/`）调用：`python ../scripts/filter_merged_prs.py input.json --start 2026-11-09T00:00:00+08:00 --end 2026-11-16T00:00:00+08:00`；input.json 相对于当前 cwd，或使用绝对路径。

stdout给window、merged、未合入、窗口外、重复记录计数和coverage。重复的同repo/number若merged_at矛盾会报错，不能用后到结果静默覆盖。total_count大于实际items时，即使声称all_pages_fetched也保留PARTIAL。缺merged_at、merged非布尔、merged=true但时间空、时间无时区或数字ID无效等返回ERROR/退出码2；覆盖不足返回PARTIAL/退出码1；覆盖声明充分时返回FILTERED/退出码0，但不代表网络数据真实完整或能力验收。

原collect_lora_week.py在模块顶层读取固定PAT，搜索只首100条，窗口终点用<=；默认不用该旧网络采集器；改用当前已授权工具按上述覆盖条件采集。fetch_pr_details.py依赖该已禁用采集器（`C.API` / `C.gh` 都不存在），现同路径改为失效退出（rc=2）并打印替代做法，不再当采集器。原md2mail.py默认收件人/发件人属于历史，不能作为本轮自动发送授权，也不能当作已验证转换器。旧md2mail对外层粗体包裹链接的Markdown不能正确生成锚点；转换前用实际含链接内容验收。需要格式转换时用当前文档/邮件能力，正文不得泄露敏感PR内容。
