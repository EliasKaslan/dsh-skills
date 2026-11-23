---
name: ascend-env
description: 昇腾环境入口：按当前问题选择服务器访问、工作区、运行栈、源码构建、服务或数值一致性验证。
whenToUse: 不知昇腾环境从哪开始，或需要选择对应子skill时使用；已定位问题可直接进入子skill。
---

# 昇腾环境入口

从已有证据和当前问题进入，不要求每次从零安装。选机和登录按 [服务器访问](../ascend-server-access/SKILL.md) 读取当前资源文件。版本按现场核实，用户本轮指定的模型、硬件、框架和范围优先。

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

## 默认环境（用户没指定环境时）

用户只说「在 188 / 190 / A5 上跑某个任务」，**没有**指定 CANN、torch、Python 或镜像版本时：

- **直接复用本机现成的「昇腾商发 26.2.0 配套」栈，不要自建、不要换镜像、不要重装 CANN。**
- 三台机器的激活路径、四条硬规矩（中性目录启动 / `spawn` + `__main__` / 不伪造 `vllm.__version__` / 不动 numpy-scipy）在用户 `AGENTS.md` §12；栈内容与每台的已知边界见 [ascend-cann-env](../ascend-cann-env/SKILL.md)。
- 只有这两种情况才转 `ascend-cann-env` 重建或改造：用户明确给了别的版本/镜像；或现成栈被破坏（`activate.sh` 缺失、`import vllm_ascend` 失败、NPU 不可用）。
- 重建前先取证该机是否已有可复用 CANN（很多机器上只是没装 toolkit，或前人已装好），不要一上手就装十几 G。
