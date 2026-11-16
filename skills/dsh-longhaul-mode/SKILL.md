---
name: "dsh-longhaul-mode"
description: "检查用户明确采用的 DSH Longhaul 工程契约、红基线、yardstick 与独立审计，或诊断既有 .longhaul run；只用于 Longhaul，不自动接管普通 DSH 任务。"
disable-model-invocation: true
warm-triggers: "Longhaul 长线模式 / longhaul_ 工具 / .longhaul 账本"
warm-reason: "低频专用模式；以当前DSH运行时证据为准。"
---

# 检查 DSH Longhaul

先核实当前 profile/bundle、实际公开工具和已有 .longhaul/run.json；原笔记称 bundle 未装配，但2026-11-16本机 local-bundles/longhaul 目录已存在，不能继续用旧结论。路径存在也不证明运行时工具可用。原“7个工具”是 DSH 的名字，当前 DSH 无这些工具时不得假装调用，也不自动 create_goal 或修改系统工作方式。

当当前schema实际公开时，工具族为longhaul_init/status/record/feature/verify/audit/close；每个参数与返回码按当前版本读取。通常init建立SPEC与feature清单，status读取现状，record记过程证据，feature推进单项，verify运行并密封验收，audit取独立裁决，close做全run关闭核验。恢复已有run先status，不用init/reset清掉历史；reset会归档旧账本，属于需要明确范围的变更。

1. 固定目标、范围、允许修改文件、验收命令和完成证据。已有契约先读状态与哈希链，分清 contract-stale、yardstick-modified、no-red-baseline、REVISE 的实际原因。
2. 对要修复的缺陷，在旧实现上运行同一份测试，确认失败来自目标行为；导入失败、环境不齐、任意 crash 不能算有效红基线。保留基线 commit、测试摘要、原始退出码和关键断言。
3. 实现后运行契约中的命令，记录 HEAD、工作树 diff/指纹、命令、退出码与产物。改变验收或测试标尺时显式修订契约并重做必要验证，不把机械“冻测试”变成永不修正错误测试。
4. 若使用独立审计者，依当前宿主允许的委派方式配置只读输入与独立验收；它不应有本 run 的 longhaul 状态修改工具。检查范围、差异和证据，不以执行者自评代替审计结果。
5. 关闭前核对所有 feature 和当前验收结果；契约要求重跑时执行，不能沿用已失效的历史绿灯。哈希链只能证明一定程度的记录一致性，不证明测试正确、身份或授权。

.longhaul 排除在代码树指纹外有避免记账导致自失效的用途，但不能借此把验收脚本或影响产品的文件藏进排除目录。reset/归档、tamper-probe 和 --help 均先查实现；历史 selftest 帮助入口可能运行整套用例，不在真实 run 上试。失败时保留原账本，先解释需要修订的具体条件，再按现有授权推进。
