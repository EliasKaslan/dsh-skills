# 数据集级 harness 的静默坑

## 1. 开机前必做的 schema 核对

字段名与脚本假设不符时，推理会完整跑完才在评分阶段崩（实测：500 题 × max_tokens 2048 / TP=2，2h10m 后才抛 `KeyError: 'answer'`，本轮结果未落盘）。

```bash
data=/data/LLM/datasets/math/test.jsonl
wc -l "$data"
python3 - "$data" <<'PY'
import collections, json, sys
path = sys.argv[1]
c = collections.Counter()
for line in open(path, encoding='utf-8'):
    if line.strip():
        c.update([tuple(sorted(json.loads(line).keys()))])
for keys, n in c.most_common():
    print(n, keys)
PY
```

只看 `head -1` 可能漏掉混合 schema（有的行有 `answer`、有的没有）。

## 2. 三道护栏

```python
PROBLEM_KEYS = ("problem", "question", "prompt", "query", "text")
ANSWER_KEYS = ("answer", "expected_answer", "ground_truth", "final_answer", "target", "gt")

def pick(d, cands, kind, i):
    for k in cands:
        if k in d:
            return k
    raise SystemExit("ERROR: 第 %d 行缺 %s 字段；实际 keys=%s" % (i, kind, sorted(d)))

pkey = pick(items[0], PROBLEM_KEYS, "problem", 0)
akey = pick(items[0], ANSWER_KEYS, "answer", 0)
for i, it in enumerate(items):
    if pkey not in it or akey not in it:
        raise SystemExit("ERROR: 第 %d 行字段不全：%s" % (i, sorted(it)))
print("SCHEMA problem=%s answer=%s n=%d" % (pkey, akey, len(items)), flush=True)
```

没有 answer 但有 `solution` 时：取最后一个 `\boxed{...}` 兜底，并在汇总里标“答案来源=boxed 兜底”，不让它和标准答案口径混在一起。

原始生成先落盘，评分/汇总作第二遍：

```python
raw = os.path.join(out_dir, "raw_%s_r%02d.jsonl" % (tag, r))
if os.path.exists(raw):
    texts = [json.loads(l)["text"] for l in open(raw, encoding="utf-8") if l.strip()]
else:
    outs = llm.generate(prompts, sp, use_tqdm=False)
    texts = [o.outputs[0].text for o in outs]
    with open(raw, "w", encoding="utf-8") as f:
        for i, t in enumerate(texts):
            f.write(json.dumps({"id": i, "text": t}, ensure_ascii=False) + "\n")
```

## 3. 日志与进程清洗

- `mkdir -p $workspace/logs` 必须在第一个 `tee` 之前。`logs/` 只由被注释掉的 `prepare_environment` 创建时，`tee` 报 “No such file or directory” 但管道继续执行：控制台有全部输出、磁盘上一无所有，整轮日志静默丢失。
- 顶部加 `set -o pipefail`，让 `PIPESTATUS[0]` 之外的失败（tee 打不开文件等）也能暴露。
- 清洗用 `pkill -9 -f VLLM::Worker` 或 `pgrep -f X | xargs -r kill -9`；GNU xargs 在 pgrep 无匹配时仍会执行裸 `kill -9`，打出 kill 的 usage 并返回非零。

## 4. 崩溃后的收尾日志怎么读

- `[ERROR] <时间> (PID:..., Device:-1, RankID:-1) ERR99999 UNKNOWN applicaiton exception`：CANN 对“未捕获 Python 异常”的补记，`Device/RankID = -1` 即非设备级故障；它与主异常是同一事件，不要当第二个故障去查 NPU。
- `[shutdown] Executor: waiting for worker exit count=N` / `Parent process exited, terminating worker queues` / `workers still running after grace period; sending SIGTERM count=N`：主进程异常后 TP worker 的正常收尾，不是 HCCL 挂死。
- `torch.accelerator.empty_host_cache() only available in Pytorch >=2.9`：vLLM 新版 shutdown 调了高版本 torch API，本机 torch 偏低 → 跳过；本身无害，但说明 torch / vllm / vllm-ascend 未完全配套，值得 `pip show torch vllm vllm-ascend` 对一遍。

## 5. 冒烟与全量的取舍

500 题 × max_tokens 2048、TP=2、max_num_seqs=32 的 graph 轮次约 2h10m（含 init）；10 轮 graph + 1 轮 eager ≈ 24 小时。先 `--rounds 2 --max-tokens 256 --max-num-seqs 4` 跑通 schema / 落盘 / summary，再全量。断点续跑会复用同名 `out/*.jsonl`，冒烟后务必换 `--out` 目录或清空，否则会把冒烟结果当正式结果。
