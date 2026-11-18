## 10 轮数据集级 BI：输出预算、batch/capture 桶与可续跑多轮 harness

## 10 轮数据集级 BI：先修输出预算，再谈分数

**适用**：需求要求"连续跑 N 轮 math500 证明批次不变性"，或验收分数偏低想调上去。

### 1) 先看截断率，再谈模型能力

`finish_reason=length` 占比高时，accuracy 主要反映**输出预算**而不是模型水平：长推理/thinking 类模型在 `max_tokens=512`
下常有一半以上样本被截断，分数会被压到接近腰斩。做法：先统计每轮 `truncated`，再把 `max_tokens` 提到 2k 量级、
`max_model_len` 相应放大，直到截断降到个位数百分比，然后才用这个配置出分。
报告里两个数都留：低预算版本用来说明"为什么要加预算"，高预算版本作为验收口径——两个都是真的，不能只留好看的那个。

### 2) 轮次成本靠 batch 压下来

把 `max_num_seqs` 提到 32，并把 `cudagraph_capture_sizes` 同步扩到 `[1,8,16,32]`（**capture 桶必须覆盖实际 batch size**，
否则该 batch 落回非图路径），单轮 500 题的耗时可以从十几分钟量级压到几分钟量级，10 轮才能在一小时内跑完。
基准命令里的 `--max-num-seqs` 与精度脚本里的 `max_num_seqs` 要分开设置，别互相套用。

### 3) 多轮 harness 必带四件（否则跑完说不清）

- 每轮独立落盘 `math500_<mode>_rNN.jsonl` + `summary_<mode>_rNN.json`；
- summary 记录 `accuracy / mean_tokens / truncated / text_sha256 / identical_to_round1 / reused / sec`；
- 已存在的轮次直接跳过并置 `reused=true`（断点续跑，中断最多损失一轮）；
- 判定：所有轮 `accuracy` 集合只有一个值 **且** 所有轮 `text_sha256` 相同。

### 4) 别把 `reused` 当确定性

确定性工作负载下每轮耗时高度一致，看起来像"没真跑"。**必须核 `reused=false` 与各轮 jsonl 的 mtime 间隔**
（例如每轮间隔与单轮耗时同量级），再下"10 轮可复现"的结论；只凭 summary 里的耗时相同就断言，容易把复用当成复现。

### 5) 与"逐位一致"判据分开

10 轮**同模式**完全相同，只证明同模式可复现（dataset 级批次不变性）；**跨模式**（整图 vs eager）文本可能大面积不同，
但分数可以无显著差异。两条判据不能互相替代，报告里要分开写（见本 skill《用 vllm bench 做 BI+整图性能验收 + 同模式对照》一节）。
