---
name: "win-scheduled-task-forensics"
description: "在 Windows 只读追查定时弹窗、后台进程和开机启动来源，关联计划任务、Run 项、启动目录、服务与 WMI，并在明确授权后验证单项禁用或恢复。"
whenToUse: "在 Windows 只读追查定时弹窗、后台进程和开机启动来源，关联计划任务、Run 项、启动目录、服务与 WMI，并在明确授权后验证单项禁用或恢复。 模型触发仍以description为准。"
disable-model-invocation: true
warm-triggers: "谁装了每日定时程序 / 停掉某个计划任务 / 排除持久化项"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# Windows 启动来源取证

先收集事件时间（含时区）、窗口/进程名、PID/创建时间、命令行与可执行文件路径。进程可能很短命，建立时间窗并保存证据；缺权限要报告未覆盖，不推断不存在。

1. 枚举计划任务的完整 TaskPath+TaskName、enabled、state、action、trigger、last run/result。包含 Microsoft 路径再按线索排序，任务路径本身不能证明安全或无关。
2. 查看当前账户与机器的 Run/RunOnce（注意注册表视图）、用户/公共 Startup、服务启动类型/可执行文件；需要时按权限检查 WMI event filter、consumer 和 binding。覆盖这几类不能证明机器没有任何其他持久化来源。
3. 把动作指向的脚本、配置、日志和触发时间与观察相互印证。某配置字段或 PID 相同不是单独定案证据；任务结果码按该程序契约解读，不能把 exit 3 一律解释为失败或无害。
4. 需要改动时先保存确切任务 XML、独立 enabled 状态及必要 ACL/动作信息；XML 声明与实际编码要一致，BOM 本身不意味着 XML 无效。按授权禁用指定项，再验证 enabled、定义和观察结果；禁止按模糊名称批量停用。
5. 停止相关进程前再次匹配 PID、创建时间和可执行文件，防 PID 复用；不使用 quitall 关闭同类所有实例。恢复时按原路径/定义/状态复核，不假定 XML 导入会保留全部运行状态。

计划任务 DACL 和完整性级别决定谁可修改，不是所有任务都要求管理员；Access denied 是受限证据。报告说明来源归因强度、实际改动、恢复路径和未覆盖区域。用户要求 DSH 提醒/定期检查时路由当前DSH已公开且授权的自动化接口，不以此 skill 自动新建 Windows 任务。
