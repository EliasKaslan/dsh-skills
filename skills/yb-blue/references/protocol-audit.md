# 原 yb.py 的静态审查

审计不执行网络请求，不读取真实 config/PAT，不复制脚本作为可用新实现。保留协议方法但修正以下边界：

| 原行为/问题 | 使用或修复要求 |
|---|---|
| request 把 Authorization 附给所有 URL，get_file 可用服务器返回的 download_url | 凭据只发明确同源 API；跨源下载单独无认证客户端，校验 scheme/host |
| assert_no_secret 只在 message body 路径；附件与 publish 未调用，且有 YB_ALLOW_SECRET 绕过 | 各外发字节都检查并按用户披露范围复核，不启用绕过 |
| recursive tree 未处理 truncated | 完整遍历/分页或报不完整，不能据部分树断言无消息 |
| poll 写 seen，读取最新limit可能让老消息饥饿 | 预览不改游标，明确消费点；以稳定顺序处理并记录失败重试 |
| envelope 至少片数与整体hash部分检查，重复seq/上限不足 | 严格唯一连续seq、消息id一致、总bytes+hash必填、分片与总体资源上限 |
| split_bytes 未校验limit，0可能不前进 | 入口拒绝非正或不足一个最大UTF-8字符的limit，检查每轮进展和每片UTF-8边界；优先换行不等于接受无限长片 |
| 锁文件按600秒年龄抢占 | 原子锁并检查所有者存活；不要把长上传误认死锁；state原子替换仍需锁 |
| doctor 只警告公共仓库 | 远端可见性必须符合本次数据发布授权；私库也不代替内容审核 |

Git Contents 的409/422重试和Git Data的非force ref更新只是一部分并发控制；成功需回读目标路径内容/commit SHA，与本次任务id对应。API受理不证明对端读取、执行或完成。正文/附件分开完整性校验，下载文件名不可越过用户指定输出目录。恢复旧状态和重发前先查同一id，避免重复执行。
