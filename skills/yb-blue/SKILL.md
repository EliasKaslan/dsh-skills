---
name: "yb-blue"
description: "审查或操作用户明确指定的 GitHub 文件式 YB 跨区任务桥，验证任务信封、分片完整性、游标与结果归因；用于已有 yb-blue 协议，不自动向任何远端发送任务或文件。"
whenToUse: "审查或操作用户明确指定的 GitHub 文件式 YB 跨区任务桥，验证任务信封、分片完整性、游标与结果归因；用于已有 yb-blue 协议，不自动向任何远端发送任务或文件。 模型触发仍以description为准。"
disable-model-invocation: true
warm-triggers: "黄蓝协同 / 给黄区派活 / yb.py poll"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# YB 文件任务桥

先确认仓库、分支、桥协议版本、方向、对端和本次授权（读取/发任务/回执/上传）。旧 yb.py 在 import 时读取本地配置，doctor 会访问账号，poll 会消耗本地 seen 状态；不要为“看看能否跑”直接 import 或执行 --help。GitHub 认证走 [github-pr-flow](../github-pr-flow/SKILL.md)，秘密不放命令行/URL。

发送前写可判定的任务：目标、必要背景、可复制命令、每步预期/退出码、可写边界、禁止事项、需要回报的产物路径/字节数/哈希和失败证据。命令输出可能有秘密，先按上下文脱敏；不要求对端无条件逐字回传全部环境。将 task/message/correlation id 贯穿回执；“已收任务”与“已验收完成”分开。

读取时区分未消费预览和会写 seen 的 poll。先完整获取树/分页，遇 truncated 不报告没有新消息。校验 envelope 的协议、方向、任务id、总片数、每片唯一seq、总字节上限及 SHA256；缺片/重复片冲突不能拼成成功消息。详见 [原实现的审查与协议要求](references/protocol-audit.md)。

上传附件/发布与正文发送有同样的外部披露风险；逐个扫描实际字节并复核目标仓库可见性，正则未命中不等于“无秘密”。未经本次明确指示不新建任务、发 done、上传或 publish，skill 触发本身不授予发送权。

本次已把 `scripts/yb.py` 同路径换成 exit78 退役入口，避免跨源认证和未检查附件外发。协议审查与任务合同仍可用；实际发送只走已审查的当前公开接口，不运行旧脚本或备份。
