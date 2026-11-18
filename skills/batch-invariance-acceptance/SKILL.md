---
name: "batch-invariance-acceptance"
description: "昇腾批次不变性与训推数值一致性适配、定位、验证。适用于\"验批次不变性 / 训推logprob对不上 / prefill和decode不同 / 梯度怎么验证 / 更新后不同步\"。不适用：仅启动推理服务→ascend-vllm-serve。"
whenToUse: "处理昇腾批次不变性与训推数值一致性适配、定位、验证及知识归档时加载；模型看不到本节，触发以description为准。"
---

# 昇腾训推一致性

## 何时调用

**触发**：验模型批次不变性 / 训推logprob对不上 / prefill和decode不同 / 梯度怎么验证 / 更新后不同步。

**转交**：仅启动推理服务见 [ascend-vllm-serve](../ascend-vllm-serve/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

把“训推不同”转成可复现、可归因、可验证的数值问题。保留用户指定的模型、框架、精度、并行策略和任务边界；从已有源码、resolved config 与失败证据开始，选择当前最有区分力、成本最低的实验。可以从中途定位或已有回执复核进入，不要求每次从环境搭建重跑整条链路。

## 不可混淆的判据

- 比较对象必须是同一有效策略、相同 token 历史、位置、mask 和评分语义。先区分 raw logprob 与经温度、penalty、top-k/top-p 处理后的 logprob；不能把概率差、KL 或 token 相同称为 logpdiff=0。
- bitwise 目标比较原始 dtype 的位模式及非空有效 token；NaN/Inf、缺 rank、未命中目标分支和空 mask 不能通过。不能降精度、取整、调宽阈值、屏蔽失败 token 或复制另一侧结果制造通过。误差预算任务按事先约定的指标单独验收。
- 推理自身 BI/PD、训练自身重复性、跨框架前向、独立梯度验证、真实更新/同步、质量和性能是不同结论。只完成其中一项时，其他项注明未覆盖。
- PyTorch/torch_npu 的 NPU 开发与验证进程显式调用 `torch_npu.npu.set_deterministic_level(3)`，包括各 rank、推理 worker 和新建子进程；用当前版本真实的查询接口核对实际等级。不因上游案例或性能原因悄悄降级。非 torch_npu 后端核对其原生确定性机制，不能用另一个进程设置 torch_npu 冒充本后端保证；若任务强制要求该 API 而后端不支持，明确说明兼容性缺口。
- 证据绑定实际执行的源码、算子产物、配置、权重与状态。换了候选实现就重跑受影响的比较，历史 PASS 不自动继承。
- 遵守本轮授权的设备、工作目录和时间窗口。大模型实验前估算训推共存、offload、workspace 和同步峰值；只清理本任务资源。旧案例的设备、账号、窗口不构成新授权。

## 按证据选择入口

- 现象 → 优先区分什么 → 可选材料的完整对照表见 references/entry-routing.md。

这些是选路提示，不是根因判定或固定执行顺序。资源错误与数值差异分开记录；受污染设备上下文中的数值证据不可信。原场景失败而缩小场景通过时，先确认是否丢掉触发条件。

复用旧 DSH 验收脚本、用减层模型外推，或设计关闭 BI 的负控时，按需读 [旧验收方法的补充核查](references/dsh-acceptance-lessons.md)，避免请求漏项、空集通过、符号零和同构外推造成的假证据。

## 开发时保留的最小信息

维护一份可更新的任务契约：本轮目标与覆盖范围、实际运行环境、评分语义、有效权重版本、主要并行/状态路径、资源限制、性能/质量要求。先从现有资料恢复信息，只询问无法恢复且确实影响选择的缺项；不为参考资料中的固定审批点再增加确认流程。

给修改明确归属：现有实现复用、框架 glue、数值契约适配、真正新增的前向/反向 kernel。优先保持原生训练入口与参数容器，复用相同 forward primitive；共享 kernel 后仍核对 caller 的 dtype、布局、metadata、compile boundary 和状态。新增 backward/STE 必须写明数学契约并独立验证，不能用 forward=0 或“梯度有限非零”代替梯度正确性。

每轮只保存与待检假设有关的最小 trace；先层边界，再模块边界，最后在完全相同算子输入上复现首个差异。修复后回到原失败用例和受影响矩阵。最终结论来自交付实现实际执行的路径，不能用诊断替代路径的结果代替。

## 文档与知识沉淀

实现过程中持续写修改文档，重点说明算子：差异证据、修改前后公式及舍入点、dtype/shape/stride/ABI、前后向与保存状态、源码位置/指纹、原失败用例复测、耗时和未覆盖范围。完整原始数据留在任务目录，报告区分 PASS、FAIL、INVALID/INCONCLUSIVE、NOT RUN，不将 skip 当成通过。

适配结束或形成可复用结论后，按 [knowledge/index.md 的维护约定](knowledge/index.md) 和 [案例模板](knowledge/case-template.md) 更新 `knowledge/`。已通过的案例写清通过范围；失败尝试和待验证假设保留各自状态。不要把案例参数提升为通用开关，也不要写入凭据、大权重或全量 dump。

本 skill 提供方法，不依赖特定训练框架、推理框架、芯片代际或外部状态机。参考来源、借鉴范围与未继承的约束见 [sources.md](references/sources.md)。

## 旧脚本入口

原4份BI脚本已在同路径改为失效退出，避免被历史调用静默判PASS。读取 [脚本状态](references/legacy-tool-status.md)；实际实验按本入口的方法编写和验证当前任务工具，不能把失效退出当数值不通过或自动尝试旧副本。

## 深水区：验收报告 / bench 验收 / MRv2 抓图 / 多轮 harness

- 需求验收报告：五段骨架、被测树与 commit 口径、三条硬纪律、常见坑 → references/acceptance-report-skeleton.md。
- `vllm bench` 的「BI+整图」性能验收、指标口径与同模式对照 → references/bench-acceptance.md。
- MRv2 开 FULL_DECODE_ONLY：capture 参数改名改义、「图在跑」取证、A/B 因果、共享机纪律 → references/mrv2-full-decode-only.md。
- 10 轮数据集级 BI：输出预算、capture 桶、可续跑 harness、reused 判据 → references/dataset-rounds-bi.md。
