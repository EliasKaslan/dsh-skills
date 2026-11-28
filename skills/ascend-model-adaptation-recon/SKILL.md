---
name: ascend-model-adaptation-recon
description: 核实指定模型及变体在昇腾推理或训练生态中的实现、跨仓分工、硬件/精度支持与未闭合缺口；适用于能否跑、适配成熟度、镜像和 Day-0 宣称取证。
whenToUse: 核实指定模型及变体在昇腾推理或训练生态中的实现、跨仓分工、硬件/精度支持与未闭合缺口；适用于能否跑、适配成熟度、镜像和 Day-0 宣称取证。
---

# 昇腾模型适配取证

固定目标模型完整名称/变体、训练或推理、模态、目标硬件与精度、期望框架/release。先读模型 config、模型卡与用户已有源码；视频/图像/语言变体、同族模型和训练/推理能力不能互相代证。

## 实现与能力

从目标 release/SHA 检查模型 registry、实现、patch/import 链、平台层、算子、recipe、测试与镜像内容。适配点可能在 vLLM 主仓、vllm-ascend、vllm-omni、MindSpeed 的不同项目或插件，不要求主仓有同名模型文件。按实际调用链说明谁提供模型、worker、编译/调度与 NPU 算子。

优先检索已有本地树。GitHub API 先解析不可变 SHA，recursive tree 必须检查 `truncated`；被截断就遍历子树或获取完整 checkout。路径搜不到只支持“该 SHA 的路径无该名称”，不能独自证明代码不支持。结合 registry、继承/patch、模型类型别名和内容检索才形成否定结论。避免 h3 之类短串假命中，必要时 `rg -P` 用 PCRE2；不把默认 rg 不支持 look-around 写成全部模式禁用。

在线状态使用一手仓库/API/官方模型卡，记录获取日期、完整 SHA 和 URL。PR 看 merged/merged_at 与合入 commit，不能以 state=closed 或 merge_commit_sha 非空认定合入。目录/搜索 API 需覆盖分页与截断；GitHub issues search 不强制 is:issue/is:pr，按需要筛选，遇 422 读响应而非套历史归因。

镜像核对精确 tag/digest、架构、实际模块与入口；算子镜像不等于包含完整推理框架。商发 tag 中的能力与 master 分开；发布时间、示例或 recipe 存在都不能单独证明该 release 在目标硬件已验收。404/401 无法独自证明模型未发布、私有资源不存在或厂商宣称为假。license=null 时查看许可文件。

## 交付

按问题给出足够的证据：实现与跨仓分工、硬件×精度×功能矩阵、可复现版本/镜像/启动入口、未闭合缺口与下一项验证。状态区分“源码存在”“文档声称”“可构建/可加载”“目标硬件真实运行”“质量/性能验收”；每条状态绑定其证据，未知标未验证。用户只问一个能力时不强制交付全生态大报告。

软件可用性和容量单独判断；容量用 `ascend-moe-ep-capacity-planning`，运行用 `ascend-vllm-serve`。历史 H3、GLM、K3 的成熟度、issue 状态与镜像 tag 只作为检索线索，不能迁成现状。

来源：`D:/workspace/share/raw/ascend-model-adaptation-recon/SKILL.md`，沉淀日 2026-11-16。修正了路径搜索即定论、404 反证、四条件充分性和固定搜索语法等过度推论。API 边界参考 [Git trees](https://docs.github.com/en/rest/git/trees)、[Pull requests](https://docs.github.com/en/rest/pulls/pulls)。逐项审查见 `D:/workspace/share/codex-review/REVIEW.md`。

## 变体权重先验格式：config 的 dtype 不算证据

## 变体权重先验格式：`config.json` 的 `dtype` 不算证据

同一模型的多份变体目录，`config.json` 可能都写 `dtype: bfloat16`、层数/专家数也一样，但**实际存储格式不同**。判据是 index 的键名与每层键数：

- 纯 BF16：`…layers.N.block_sparse_moe.experts.K.w1.weight`，每专家 3 个张量
- 打包量化：出现 `…w3.weight_packed` + `…w3.weight_scale`，每层键数约为纯权重的 2 倍

```python
import json, re, collections, sys
wm = json.load(open(sys.argv[1]))["weight_map"]   # model.safetensors.index.json
c = collections.Counter()
for k in wm:
    m = re.search(r"\.layers\.(\d+)\.", k)
    if m:
        c[int(m.group(1))] += 1
print("keys", len(wm), c.most_common(2))
print([k for k in wm if ".layers.1." in k][:2])
```

昇腾侧另有一个顺序坑：vllm-ascend 把 KDA 的 q/k/v conv1d 打包成 `ascend_conv1d_weight`，这一步只在 `process_weights_after_loading` 里发生，**晚于** vLLM 的「权重未初始化」检查，于是 plain checkpoint 直接失败：

```
ValueError: Following weights were not initialized from checkpoint:
{'...layers.{0,1,2}.self_attn.ascend_conv1d_weight'}
```

不是权重缺失，是布局不对口：要么补这 3 个打包张量，要么换预打包 checkpoint，要么改模型侧打包时机（越界，需确认）。
