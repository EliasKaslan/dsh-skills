---
name: ascend-env
description: 昇腾环境入口：按当前问题选择服务器访问、工作区、运行栈、源码构建、服务或数值一致性验证。
whenToUse: 不知昇腾环境从哪开始，或需要选择对应子skill时使用；已定位问题可直接进入子skill。
---

# 昇腾环境入口

从已有证据和当前问题进入，不要求每次从零安装。机器清单和版本只作带日期线索，使用前现场核实；用户指定的模型、硬件、框架和范围优先。

| 需求 | 入口 |
|---|---|
| 进入服务器/隧道/SSH | [ascend-server-access](../ascend-server-access/SKILL.md) |
| 磁盘/缓存/空卡与真权重 | [ascend-server-layout](../ascend-server-layout/SKILL.md) |
| CANN/Python/torch/Triton运行栈 | [ascend-cann-env](../ascend-cann-env/SKILL.md) |
| 源码版本配对与构建 | [vllm-ascend-source-install](../vllm-ascend-source-install/SKILL.md) |
| 真实推理与sleep/reload | [ascend-vllm-serve](../ascend-vllm-serve/SKILL.md) |
| 模型实现/平台与支持取证 | [ascend-model-adaptation-recon](../ascend-model-adaptation-recon/SKILL.md) |
| MoE并行与显存预算 | [ascend-moe-ep-capacity-planning](../ascend-moe-ep-capacity-planning/SKILL.md) |
| BI/PD/跨框架数值和真实更新 | [batch-invariance-acceptance](../batch-invariance-acceptance/SKILL.md) |

驱动/设备、实际source的CANN、目标Python与torch、真实算子、模型运行分别验收。缺依赖、资源不可用、数值差异和未执行不能互相代替。复杂远程命令的传输方式与有限重试见服务器访问入口。
