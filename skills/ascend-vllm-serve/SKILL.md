---
name: ascend-vllm-serve
description: 在昇腾上起 vllm 服务：三层自检、选空闲 die、serve/离线/sleep、运行时排障。适用于"起 vllm 服务 / OOM / 输出乱码 / reload_weights / 该占哪张卡 / 模型太大要 TP=2"。
whenToUse: 环境已装好、现在要真的跑模型时才用：起 OpenAI 兼容服务、跑离线推理冒烟、sleep/wake_up 与权重热更新，或服务起不来要定位；装的过程见 vllm-ascend-source-install。
---

# 昇腾 vllm / vllm-ascend 起服务、离线推理与运行时排障

装 vllm/vllm-ascend 见 `vllm-ascend-source-install`；CANN 见 `ascend-cann-env`；conda 见 `ascend-conda-env`；**从 Windows 驱动远端的硬规则见 `ascend-env` §5（本文件不重复）**。

## 何时调用

**加载本 skill 当：**

- 在 `192.168.13.188`（文档里代称 `a3`，但 ssh 用 IP，见「前置检查」）上 `vllm serve` 或 `LLM()` 跑模型；`.190`（`a3b`）同理但 ssh 易假死。
- 要 `sleep()` / `wake_up()` 释放显存，或要 `reload_weights` 热更新权重（见步骤 3.1）。
- 报 `MemoryError`、`dtype or format of parameter`、`NnopbaseExecutorDoTiling`、`No module named 'triton.experimental'`、`Engine core initialization failed`。
- 共享机上要决定占哪张 die、用多少显存、用哪个端口。

**不要用本 skill（转交）：**
- 还没装 / 要重装 / 要重编 vllm 或 vllm-ascend 的 AscendC 算子 → 用 `vllm-ascend-source-install`（本 skill 只管「跑得起来」，不管「装得上」）。
- torch / torch_npu 装不上或版本不匹配（`No matching distribution found for torch-npu`） → 用 `ascend-torch-npu`。
- triton 被 `pip install -U triton` 覆盖、要恢复 triton-ascend → 用 `ascend-triton-ascend`；CANN 环境变量不对 → 用 `ascend-cann-env`。
- 不知道模型 / 权重在哪、大文件该写哪个盘、哪张卡空闲 → 用 `ascend-server-layout`。
- 上游仓库 docs 刷新审计（需求 vs docs 缺口清单） → 用 `upstream-docs-refresh-audit`。
- e2e 用例进 CI 的落位与 estimated_times 登记 → 用 `vllm-ascend-e2e-ci-wiring`。

**前置**：`source /home/x00886548/work/batch_inv_qwen35/env_batch_inv.sh` 能跑通，三层自检 ① torch_npu 与 ② `NPUPlatform npu` 都过（②不过别做 ③）。 ／ **后继**：收尾必做「步骤 5 杀服务 + 端口 / 残留进程 / HBM 三查」；装的问题回 `vllm-ascend-source-install`。

## 前置检查

ssh 一律直连 **IP**：`ssh x00886548@192.168.13.188`。**实测客户端 `~/.ssh/config` 里没有 `a3` 别名**（`a3` 只是文档里的代称），照抄别名写法会直接连不上（未验证：其他客户端是否配了别名）。

环境激活（`.188` 唯一推荐入口，2026-09-23 实测可用，别重建）：

```bash
source /home/x00886548/work/batch_inv_qwen35/env_batch_inv.sh
```

给到 python 3.12.14（`/mnt/share/vllm/conda_envs/xmz_0921`）、vllm `84030bbe`、vllm-ascend `bf439330c`、CANN 9.1.0、`LD_LIBRARY_PATH` 已前置 `compat_lib`。**它默认 `export VLLM_BATCH_INVARIANT=1`**（见坑 5）。

三层自检，逐层来，②不过别做 ③：

```bash
python -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__, torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"
# 实测 2.10.0+cpu 2.10.0.post4 True 16 253
python -c "from vllm.platforms import current_platform as p; print(type(p).__name__, p.device_type)"   # 实测 NPUPlatform npu
python -c "import vllm, importlib.metadata as m; print(vllm.__version__, m.version('vllm-ascend'))"
# 实测 0.1.dev1+g84030bbe3.d20260921 0.19.1rc2.dev2317+gbf439330c.d20260921
```

**别读 `vllm_ascend.__version__`**（`.188` 无该属性，用 `importlib.metadata`）。

## 步骤

### 1 挑空闲 die（目的：共享机不抢别人的卡）

> 硬规则（用户 2026-11-13）：**卡上有别人的进程 ⇒ 整张卡不可用**，连"只用剩余显存跑个小东西"都不行（会毁掉别人正在跑的性能/精度数据）；判据与让路动作的唯一出处在 `ascend-server-layout`「共享机占用铁律与断点续跑」，本节只讲怎么挑、怎么起。

```bash
npu-smi info | head -20                          # 先看谁在跑；HBM-Usage 是单 die 值
python -c "
import torch, torch_npu
f=[torch.npu.mem_get_info(i)[0] for i in range(torch.npu.device_count())]
print('FREE_MB', [x//1048576 for x in f]); print('PICK', f.index(max(f)))"
```

（上面是本次实测 `pick_card.py` 的等价精简写法，同一 API。）`ASCEND_RT_VISIBLE_DEVICES` **必须在 `import torch` 之前设好**，所以先选卡再传给子进程：

```bash
export ASCEND_RT_VISIBLE_DEVICES=$(python -c "
import torch, torch_npu
f=[torch.npu.mem_get_info(i)[0] for i in range(torch.npu.device_count())]
print(f.index(max(f)))" | tail -1)
```

实测 2026-09-23：die 0 被别人的 `VLLMWorker` 占 28907MB，其余 die 仅 ~2.9GB 基线；die 9 free 62621MB（**可见**总量 62748MB = 硬件 65536MB − 驱动基线 ~2874MB，`npu-smi` 里看到的是 65536MB 硬件值，两者不矛盾）→ 选 9。

⚠️ **共享机上空闲 die 是分钟级变量，别用几分钟前的选卡快照**：2026-09-28 实测同一个 die 9，20 分钟内 free 从 `62619MB` 掉到 `20815MB`（`npu-smi` 变成 `34895/65536`）——别人的进程随时会进来。**必须在 launch 前一刻复测 `torch.npu.mem_get_info`，再定 `ASCEND_RT_VISIBLE_DEVICES`**，不要复用早先脚本或早先对话里那份选卡结果。TP≥2 时两张卡都要这样复测。

### 2 挑空闲端口

```bash
USED=$(ss -ltn | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ' ')
for p in $(seq 18000 18100); do case " $USED " in *" $p "*) ;; *) echo $p; break;; esac; done
```

验证：`ss -ltnp | grep :18000` 无输出即可用（实测取到 18000）。

### 3 离线推理冒烟（目的：不依赖 HTTP，先验引擎+算子）

```bash
python - <<'PY'
import torch, torch_npu
from vllm import LLM, SamplingParams
llm = LLM(model="/mnt/weight/Qwen2.5-0.5B", max_model_len=512, enforce_eager=True,
          gpu_memory_utilization=0.4, trust_remote_code=True)
for o in llm.generate(["你好，请用一句话介绍昇腾 NPU。", "1+1=?"],
                      SamplingParams(temperature=0.0, max_tokens=64)):
    print("OUTPUT %r" % o.outputs[0].text)
print("SMOKE_OK")
PY
```

脚本核心：`LLM(model=<本地目录>, max_model_len=512, enforce_eager=True, gpu_memory_utilization=0.4, trust_remote_code=True)` + `SamplingParams(temperature=0.0, max_tokens=64)`。验证：末行打印 `SMOKE_OK`。实测 load 10.0s、KV cache 23.25 GiB / 2,031,616 tokens、154.51 toks/s。本次脚本 `pick_card.py` / `smoke_npu.py` 在 `D:\workspace\agent\skill\_recon\serve\`（若该侦察工作区已清理，按上面两段内联片段自行重建即可）。

### 3.1 sleep / wake_up 释放显存 + 权重热更新（reload_weights）

**先决条件**（少一个必失败，对应坑 10 / 坑 14）：

```bash
export VLLM_WORKER_MULTIPROC_METHOD=spawn     # 不设 → fork 起 worker 直接 RuntimeError（坑 10）
```

```python
import torch, torch_npu
from vllm import LLM, SamplingParams
llm = LLM(model="/mnt/weight/Qwen2.5-0.5B", enable_sleep_mode=True, enforce_eager=True,
          max_model_len=1024, gpu_memory_utilization=0.6,
          additional_config={"weight_nz_mode": 0})   # 不传 → FRACTAL_NZ 报错（坑 14）
sp = SamplingParams(temperature=0.0, max_tokens=64)
```

**A→B→C 三步判据**（本次实测跑通的调用序列；测试脚本本身是会话产物、按需自建）：

```python
A = llm.generate(["你好"], sp)[0].outputs[0].text
llm.sleep(level=2)                                        # level 1 / 2 都会释放 HBM
llm.wake_up()                                             # level 2 唤醒【不】恢复权重（三重印证见下）
B = llm.generate(["你好"], sp)[0].outputs[0].text         # 期望退化：B != A
llm.collective_rpc("reload_weights", kwargs={"weights_path": "<ckpt 目录绝对路径>"})
C = llm.generate(["你好"], sp)[0].outputs[0].text         # 期望 C == A
print("VERDICT", "WEIGHT_UPDATE_PROVEN" if (B != A and C == A) else "NOT_PROVEN")
```

**只看到 C 有输出不算跑通**：level 2 唤醒后本来也还有输出，只是内容已退化；判据必须是 `B != A` **且** `C == A`。

**「level 2 唤醒不恢复权重」的三重印证**（别把它当 bug 反复排查）：① 上游 `docs/features/sleep_mode.md` 原句即如此；② 本机 `wake_up()` 只恢复 `_sleep_saved_buffers`、不重载权重；③ 实测唤醒后输出退化成重复标点串。→ 结论：**`sleep(level=2)` 之后必须 `reload_weights` 才可用**；level 1 则自带恢复。

**level 1 vs level 2 的实机判据**（看日志，别猜）：

| | level 1 | level 2 |
|---|---|---|
| offload 日志 | `CaMem sleep: offloading <n>/<m> allocations (tags=('weights',))`，**n ≠ 0** | `offloading 0/<m> allocations (tags=())` |
| 唤醒后权重 | 恢复 | **不恢复** → 不 `reload_weights` 就是错的 |

日志锚点（`grep` 用；行号取自本次源码树，随版本漂移）：`Sleep mode (level=N) freed X GiB memory, Y GiB memory is still in use.`（`vllm_ascend/worker/worker.py:275`）、`It took ... seconds to fall asleep.` 与 `It took ... seconds to wake up tags [...]`（`vllm_ascend/worker/abstract.py:346/364`）。

**API 事实**（省得翻源码；行号同上述版本）：权重传输后端名是 `npu_ipc`，**不是**上游的 `ipc`（`vllm_ascend/distributed/weight_transfer/npu_ipc_engine.py:102`）；`vllm_ascend/worker/worker.py` 里 `sleep` / `wake_up` / `update_weights` / `reload_weights` 分工不同——`update_weights` 是 start→update(分块)→finish 状态机，只配 `load_format="dummy"` 的四阶段 weight_transfer；`reload_weights` 与 `dummy` **互斥**（坑 11）。

**HTTP 侧**：`POST /sleep?level=2` —— level **只从 query string 读，JSON body 被忽略**（实测对照，坑 15）。

### 3.2 sleep level 决定你能断言什么（别在 level 2 上断言精度）

| level | 实测语义 | 可以断言 | 不可以断言 |
|---|---|---|---|
| `sleep(level=1)` | 权重 offload 到 host，唤醒后**逐位恢复** | **精度**：同一 prompt 的 `token_logprobs` 漂移实测 `0.000000e+00` | — |
| `sleep(level=2)` | 权重被**丢弃** | 只断言**机制**：显存释放量、服务仍存活、端点返回 200 | 输出文本与精度（唤醒后必然退化，见步骤 3.1） |

所以：**要验精度就用 level=1；用 level=2 却断言输出一致，是在断言一个不成立的前提。**

**HTTP 端点**（这三个都要求进程环境变量 `VLLM_SERVER_DEV_MODE=1`，否则不注册）：

```bash
export VLLM_SERVER_DEV_MODE=1
curl -s -o /dev/null -w '%{http_code}\n' -X POST 'localhost:18000/sleep?level=1'   # 200，空体
curl -s -o /dev/null -w '%{http_code}\n' -X POST 'localhost:18000/wake_up'        # 200，空体
curl -s 'localhost:18000/is_sleeping'                                             # {"is_sleeping": true|false}
```

- `/sleep` 与 `/wake_up` 都返回**空体 200** → **不要调 `.json()`**（会抛 JSON 解析错误）；`level` 只从 query string 读（见步骤 3.1 的 HTTP 侧）。
- `GET /is_sleeping` 存在，返回 `{"is_sleeping": bool}` —— 判"睡没睡"用它，别去解析空体响应。

实测另一条量级事实：K3 减层（2~4 层 / 16 专家 / top-4）+ `--load-format dummy` 在 **TP1 + eager** 下能起来（就绪约 26s），可用于快速验端点与机制、不必下真权重。

### 4 起 OpenAI 兼容服务

```bash
vllm serve --help | head -40     # 参数名以本机为准：usage: vllm serve [model_tag] [options]
setsid nohup vllm serve /mnt/weight/Qwen2.5-0.5B --port 18000 --max-model-len 512 \
  --enforce-eager --gpu-memory-utilization 0.4 --trust-remote-code \
  > /home/x00886548/serve_test/serve.log 2>&1 < /dev/null &
```

就绪判据（轮询日志，别只 sleep）：`grep -m1 'Application startup complete' serve.log`。curl **全部写进远端 .sh 跑**（PowerShell 内联会吃引号）：

```bash
curl -s localhost:18000/v1/models
curl -s localhost:18000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"/mnt/weight/Qwen2.5-0.5B","messages":[{"role":"user","content":"hello"}],"max_tokens":48,"temperature":0}'
```

实测：ready **24s**、两端点均 200 且返回中文、engine init 2.73s、KV 23.47 GiB、HBM 2874 → 28889 MB。

### 4.1 权重超过单 die HBM → `--tensor-parallel-size 2`

判据：单 die 硬件 65536MB、驱动基线后**可见约 61.28GiB**；模型 BF16 权重（看 `ls -l *.safetensors` 求和）大于它就必须 TP≥2。实物参考：`Qwen3.5-35B-A3B` = 71.9GB = 66.96GiB（14 shard）→ TP=1 不可行，TP=2 每 die 承担 ≈33.48GiB 权重。

最小改动就是在步骤 4 的 flag 串上加 `--tensor-parallel-size 2`（`ASCEND_RT_VISIBLE_DEVICES` 必须**在起 vllm 前**设好、且要两张都空闲，见步骤 1）：

```bash
export ASCEND_RT_VISIBLE_DEVICES=<dieA>,<dieB>
vllm serve <模型绝对路径> --served-model-name <name> --port <port> \
  --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.85 \
  --dtype bfloat16 --enforce-eager --limit-mm-per-prompt '{"image": 2, "video": 0}' \
  --max-num-seqs 16 --max-num-batched-tokens 4096 --trust-remote-code
```

- `--limit-mm-per-prompt` 传多模态 key 被 v0.30.0 正常接受；`--trust-remote-code` 对没有 `auto_map` 的模型是 no-op 但无害。
- 就绪判据与步骤 4 相同（`grep -m1 'Application startup complete'`）；实测参考值：**就绪 114 秒**、`Loading safetensors checkpoint shards: 14/14`、每 die `32.93GiB weights + 3.68GiB activation`、`KV cache 14.96 GiB = 1,126,027 tokens`、`seed=0`、吞吐 ≈ **21 tok/s**（此时 `VLLM_BATCH_INVARIANT=1` 生效，见坑 5）。
- 收尾（步骤 5）期望值：杀服务后两张 die 的 HBM 应从约 `52876/65536` 回落到 `2869/65536` 基线附近。

### 5 收尾杀服务（必须做）

```bash
PID=$(ss -ltnp | grep :18000 | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1); kill -TERM $PID
ss -ltnp | grep :18000 || echo "PORT RELEASED"
# 只 kill 自己端口上的 PID；绝不用 pkill -f vllm——本机 NPU0 上就有别人的 VLLMWorker
```

## 坑与修法

1. **权重是 git-lfs 指针 → `MemoryError`**（实测复现，文件正好 134 字节）。原文：`File ".../vllm/transformers_utils/utils.py", line 114, in parse_safetensors_file_metadata` → `metadata = json.loads(f.read(length_of_metadata).decode("utf-8"))` → `MemoryError`（上层是 `maybe_untie_word_embeddings`）。判别：`ls -la *.safetensors` 看 134 字节 + `head -c 200 model.safetensors | grep -c git-lfs` → 1。修法：下真权重，别 `git clone`；`/mnt/weight/Qwen2.5-0.5B/model.safetensors` 是真权重（988097824 字节）。
2. **`import vllm` 报 `No module named 'triton.experimental'`**（实测：直接 `import triton.experimental` 复现；`import vllm` 后再 import 即 OK，`vllm_ascend/__init__.py` 打了 stub）。**装完 vllm-ascend 即消失，别单独升级 triton**（会覆盖 triton-ascend）。
3. **`.188` 缺 `GLIBCXX_3.4.26`（运行时坑，症状像算子 API 用错）**。实测原文：`[ERROR] Failed to load custom_transformer library ... via dlopen.` + `Error detail: /lib/x86_64-linux-gnu/libstdc++.so.6: version 'GLIBCXX_3.4.26' not found (required by .../op_tiling/lib/linux/x86_64/libcust_opmaster_rt2.0.so)`，随后 `RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {'EngineCore': 1}`。旧记录的 `dtype or format of parameter` / `NnopbaseExecutorDoTiling` 是同一根因的另一表现（**未验证：本次未复现该措辞**）。修法：`export LD_LIBRARY_PATH=/home/x00886548/work/batch_inv_qwen35/compat_lib:$LD_LIBRARY_PATH`（env 脚本已做）；只前置 `compat_lib`，**别加整个 `$CONDA_PREFIX/lib`**（`git` 会崩）。
4. **`VLLM_USE_V1` 已废弃**。实测：设了不致命，起服务打 `WARNING ... [envs.py:2290] Unknown vLLM environment variable detected: VLLM_USE_V1`，服务照样 200；`vllm.envs` 已无该属性（`AttributeError: module 'vllm.envs' has no attribute 'VLLM_USE_V1'`）。V1 是唯一引擎 → **不要设**；同理别设 `VLLM_VERSION`（未验证：本次只实测了 `VLLM_USE_V1`）。
5. **env 脚本默认 `VLLM_BATCH_INVARIANT=1`，慢 5.5 倍**。实测同模型同卡：BI=1 → load 20.8s / **27.87 toks/s**；`unset VLLM_BATCH_INVARIANT` → load 10.0s / **154.51 toks/s**（日志另有 `Disabling cascade attention when VLLM_BATCH_INVARIANT is enabled.`）。不要求批次不变性就先 unset。
6. **共享机抢卡/显存**：`gpu_memory_utilization=0.4` 在小模型上仍一次吃 23 GiB KV（单 die 共 61.28 GiB）；一个进程只占一张卡，先按步骤 1 挑 free 最大的 die，别拉满利用率。
7. **无害噪声**（别当故障）：`/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory`（每条 ssh 都打）、`NPUCachingAllocator ... require processing for 32 padding size`、`[Gloo] Rank 0 is connected to 0 peer ranks`、`VLLM_USE_V1 not set, auto-detected`。
8. **思考型模型的 CoT 会写进 `content`，别误判成"没输出答案"**（2026-09-28 在 `.188` 实测）：`max_tokens=48` / `256` 时 `choices[0].message.content` 全是 `Thinking Process:` 之类的推理过程、`finish_reason=length`，**看起来像失败，其实是正常行为**。要给最终答案就把 `max_tokens` 放到 **≥1000**（实测 1200 才吐出最终答案；一次请求约 55s）。所以**冒烟判据只能写成「HTTP 200 且 `content` 非空」**，不要断言 content 里就是答案本身、也不要因为 `finish_reason=length` 判服务异常。
9. **换模型前先验架构支持，比 grep 源码可靠**（上机前的决定性判据）：
   ```bash
   python -c "from vllm.model_executor.models.registry import ModelRegistry as R; print('Qwen3_5MoeForConditionalGeneration' in R.get_supported_archs())"
   ```
   ⚠️ **别把"vllm-ascend 侧没有该模型同名文件"误判成"不支持"**：实测主仓有实现（`vllm/model_executor/models/qwen3_5.py`），而 ascend 侧无专属文件、只有继承式 patch（`vllm_ascend/patch/worker/patch_qwen3_5.py`），照样能跑。要判全树适配程度见 `ascend-model-adaptation-recon`。

10. **`RuntimeError: Cannot re-initialize NPU in forked subprocess. To use NPU with multiprocessing, you must use the 'spawn' start method`**
    → 原因：NPU 上下文不能跨 fork 继承。
    → 修法：起 `LLM()` / `vllm serve` **之前** `export VLLM_WORKER_MULTIPROC_METHOD=spawn`。
11. **`NotImplementedError: Model reloading with `dummy` format`**
    → 原因：`load_format="dummy"` 与 `reload_weights` **互斥**；dummy 只能配 weight_transfer 的四阶段 `update_weights`（start → update 分块 → finish）。
    → 修法：要热更新就用真权重 + `reload_weights`；要用 dummy 就必须走 `update_weights`，二选一。
12. **`TypeError: GPUModelRunner.reload_weights() got an unexpected keyword argument 'model_path'`**
    → 修法：参数名是 **`weights_path`**：`llm.collective_rpc("reload_weights", kwargs={"weights_path": "<ckpt 目录>"})`。
13. **只 `wake_up(tags=["weights"])` 就 `generate()` → 挂住**：日志停在 `Processed prompts: 0%` 数分钟不动、不报错。
    → 原因：KV cache 没被唤醒，生成走不下去。
    → 修法：生成前唤醒 `kv_cache`，或直接全量 `llm.wake_up()`（本次用全量）。
14. **`ValueError: FRACTAL_NZ mode is enabled...`**（原文片段，完整尾句本次未留档）
    → 修法：构造 `LLM()` 时传 `additional_config={"weight_nz_mode": 0}`。
15. **HTTP 调 `/sleep` 时 body 里的 level 不生效**：level **只从 query string 读**，JSON body 里的 level 被忽略 → 写成 `POST /sleep?level=2`。
16. **`pkill -f '<模式>'` 会杀掉自己的 ssh 包装进程**：现象是命令无输出、只得到 `[exit code: 1]`（模式串匹配到了自己那条命令行）。
    → 修法：把模式写成不自匹配的形式，例如 `pkill -f "[t]est_x"`（字符类让模式本身不再包含字面量 `test_x`）。
17. **强杀（`kill -9`）进程后该 die 残留 HBM**：现象是服务已不在，`npu-smi info` 里该 die 的 HBM 却明显高于基线。
    → 修法：强杀后必须复查 `npu-smi info`（步骤 5 的收尾三查之一），确认进程真退出、HBM 回落到基线；别以为"进程没了显存就没了"。
18. **图模式下 `reload_weights` / `update_weights` 可能丢值**：上游尚未闭合（vllm issue #15648、RFC #16558，原话 "pointer stability does not imply value preservation"）。
    → 本次用 `enforce_eager=True`（无图模式）规避。**未验证：去掉 `enforce_eager` 后 `reload_weights` 是否真丢值，本次未测。**

19. **整体赋值 `PYTHONPATH` → `import torch_npu` 报 `ModuleNotFoundError: No module named 'acl'`**（实测复现）。
    → 原因：为了挂一个额外包写成 `export PYTHONPATH=/some/dir`，把 CANN 原本在 `PYTHONPATH` 里的搜索路径**覆盖**掉了（`acl` 就在那里）。
    → 修法：**追加式**写法 `export PYTHONPATH=/some/dir:${PYTHONPATH:-}`（`:-` 兜住空值）。归因：这不是 CANN 装坏，别去重装（CANN 路径真相见 `ascend-cann-env`）。

## 不要做什么

- 不要 `pip install`/卸载任何包；不要 `pip install -U triton`；不要重建 vllm。
- 不要设 `VLLM_USE_V1` / `VLLM_VERSION`。
- 不要 `pkill -f vllm`；不要动 `/home/x00886548/env/cann/`、`/usr/local/Ascend`、`/etc/Ascend`、`xmz_0921` 里的包。
- 不要在共享机上占用**未确认空闲**的 die、也不要起自己放不下的模型；**「别占多张卡」不是绝对禁令**——TP≥2 要同时占两张，但前提是 launch 前一刻确认两张都空闲（见步骤 1 与 4.1）；`gpu_memory_utilization` 别无脑拉满（TP=2 实测可用 0.85，留基线余量给别人）。
- 不要把大文件/日志写 `/`、`/mnt/share`、`/tmp`、`/root`（同盘仅剩 139G）；写 `/home/x00886548/serve_test/`。
- 内联 ssh 里别用 `<` `"` `$()`；脚本里别用 heredoc（会永久挂起）。
- 别在 `load_format="dummy"` 下用 `reload_weights`（互斥，坑 11）；也别只 `wake_up(tags=["weights"])` 就 `generate()`（会挂住，坑 13）。
- 强杀进程后不复查 `npu-smi` 不算收尾（坑 17）；`pkill -f` 的模式别能匹配到自己那条命令行（坑 16）。

## 验收标准

1. 三层自检 = `True 16 253` / `NPUPlatform npu` / 两个版本串非空。
2. 离线冒烟打印 `SMOKE_OK`，出文本，toks/s > 0。
3. `/v1/models` 含 `"id"`；`/v1/chat/completions` 返回 200 且 `choices[0].message.content` **非空**（思考型模型这里可能是 CoT，见坑 8，不是失败）。
4. 收尾三查：`ss -ltnp | grep <port>` 为空、`ps -ef | grep 'vllm serve'` 无残留、目标 die HBM 回落到基线（单卡实测 28889 → 2857 MB；TP=2 实测 52876 → 2869 MB）。

5. sleep / 权重热更新（步骤 3.1）：`sleep(level=1|2)` 后该 die 的 used HBM 应降到 ~1GiB 量级（权重确实被释放的证据），`wake_up()` 后回到与 sleep 前同量级；A→B→C 打印 `VERDICT WEIGHT_UPDATE_PROVEN`（`B != A` **且** `C == A`），只看到 C 有文本不算过。

**未验证**：`.190`（`a3b`）上的起服务、冒烟与多卡本次未跑（ssh 易假死）→ `.190` 的多卡仍未验证。`.188` 上 `--tensor-parallel-size 2` **已实测通过**（TP=2 起服务 + 真推理成功，见步骤 4.1）。
