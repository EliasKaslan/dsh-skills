---
name: ascend-moe-ep-capacity-planning
description: 在昇腾 MoE 部署前核算每 rank 权重、KV/线性注意力状态与运行峰值，筛选合法 TP/DP/PCP/EP 组合；适用于需要几张卡、并行配置和显存余量，不替代真机可运行验收。
whenToUse: 在昇腾 MoE 部署前核算每 rank 权重、KV/线性注意力状态与运行峰值，筛选合法 TP/DP/PCP/EP 组合；适用于需要几张卡、并行配置和显存余量，不替代真机可运行验收。
---

# 昇腾 MoE 容量规划

固定模型 revision、层数/截断、运行精度与量化 loader、并行组、总/每 DP 请求量和缓存布局。读取 config 时识别 text_config/vision_config 及字段别名，记录实际 resolved config；不要把旧 K3/GLM 的字段、权重大小和卡数当默认。

## 建模

将权重按实际 loader 和并行层分为 routed expert（EP 域）、TP 分片、每 rank 复制、PP stage/其他域。q_a/kv_a、norm、router、shared experts 的分片方式从本版本实现取证；不能把全部非专家都除 TP。量化按 packed bytes、scale、zero、padding、重排与反量化工作区计，不统一套逻辑参数×2，也不从 U8 numel 推出全部逻辑参数。

EP 几何由目标后端 group 定义；许多版本 EP=DP×PCP×TP，PP 等维度不属于同一 EP group。核实而非宣称 EP 永远等于全部卡数。TP/DP/PCP、头数/维度约束与拓扑一起验证。枚举合法组合并比较余量，不预设最大 TP 总最优。

专家不均分必须检查 dispatch/gather 和 kernel，不因 Python 可初始化就称支持。某些历史 Ascend 路径会崩或错算；默认只将整除组列为候选，证实目标后端支持后才放行不均分。EPLB 冗余专家既影响整除也增加驻留权重，不能只加个数字绕过校验。按每 rank 完整专家数算最坏 rank：`ceil(E/EP)×每专家bytes`，不能对所有专家参数总数除 EP 后取整冒充专家分配。

## 预算与结论

现场读取 `free_bytes, total_bytes = torch.npu.mem_get_info(logical_id)`，单位用 bytes/GiB，确认调用设备已准入。free 和 total 不颠倒；驱动可见 total 与 npu-smi 物理 HBM 不强行相减凑基线。以当前引擎的预算算法、实际 utilization/KV 固定预算和外部分配为准，不能固定 56.378 GiB 或 0.92。

逐 rank 分开列权重、KV/递归状态、激活、通信、框架、图池、加载/reload 峰值与安全余量。通信若已含在 non-torch 里就不再叠加。MLA cache 取实际 head_size/dtype/scale/分片策略；KDA/DeltaNet 稳态递归状态常按每序列计，但多步推测、chunk、prefix snapshot 和临时 workspace 另核，不能因此断言 KV 永远非瓶颈。

使用 [scripts/plan_capacity.py](scripts/plan_capacity.py) 与 [输入说明](references/planner.md) 复算已确定的分项。工具要求显式输入及证据标记，不从模型名猜公式；结果是容量候选或下界，不是服务 PASS。未知开销可计算下界，状态必须是 INCONCLUSIVE，不能置 0 后宣称 FITS。

给出权重下界排除、含开销的最小候选、推荐余量及翻转条件。全局物理总量不够可作必要条件反证；全局足够不保证每 rank 足够。所有组合均非法或不完整时可报告“未找到”，不能硬给最小卡数。上机读取真实 profile/加载峰值后回填并复验实际目标；减层结论不外推全模。

底本：原 ascend-moe-ep-capacity-planning 及 ep_mem_model.py，2026-11-16 已复现专家分配低估、旧表隐含 override 和总量不一致；旧估算器已停用。详见 `D:/workspace/share/codex-review/REVIEW.md`。
