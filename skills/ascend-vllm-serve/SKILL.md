---
name: ascend-vllm-serve
description: 在昇腾 A3（.188/.190）上把装好的 vllm + vllm-ascend 跑起来——三层自检、按 HBM 挑空闲 die、起 OpenAI 兼容服务、离线推理冒烟、sleep/wake_up 显存释放与重载、运行时排障。适用于"在昇腾上起 vllm 服务 / 跑离线推理冒烟 / sleep mode 释放显存 / sleep level 1 还是 2 / wake_up 后输出乱码 / reload_weights 热更新权重 / 报 MemoryError 或 dtype / import torch_npu 报 No module named 'acl' / 别设 VLLM_TARGET_DEVICE / 报 aclInit 107001 / Kimi-K3 在 A3 上 500 EZ0037 / 模型太大单卡放不下要 TP=2"。不适用：装/重装/编译 vllm-ascend → 用 `vllm-ascend-source-install`；栈装不上（torch_npu、pip） → 用 `ascend-torch-npu`。
whenToUse: 环境已装好、现在要真的跑模型时才用：起 OpenAI 兼容服务、跑离线推理冒烟、sleep/wake_up 与权重热更新，或服务起不来要定位；装的过程见 vllm-ascend-source-install。模型看不到本节。
---

# 昇腾 vllm / vllm-ascend 起服务、离线推理与运行时排障

装 vllm/vllm-ascend 见 `vllm-ascend-source-install`；CANN 见 `ascend-cann-env`；conda 见 `ascend-conda-env`；**从 Windows 驱动远端的硬规则见 `ascend-env` §5（本文件不重复）**。

## 何时调用

**加载本 skill 当：**

- 在 `192.168.13.188`（文档里代称 `a3`，但 ssh 用 IP，见「前置检查」）上 `vllm serve` 或 `LLM()` 跑模型；`.190`（`a3b`，**2026-10-22 整机不可达**）与 A5 `177.8.21.1`（**需连 A5 VPN 后可达**，见 `univpn-vpn`）同理，接入状态见 `ascend-env` §1。
- 要 `sleep()` / `wake_up()` 释放显存，或要 `reload_weights` 热更新权重（见步骤 3.1）。
- 报 `MemoryError`、`dtype or format of parameter`、`NnopbaseExecutorDoTiling`、`No module named 'triton.experimental'`、`Engine core initialization failed`、`AttributeError: module 'vllm.v1.engine.utils' has no attribute 'get_physical_gpu_ids_for_local_dp_rank'`。
- **KDA / 线性注意力系模型（Kimi-K3、GLM5next）起不来**：报 `ModuleNotFoundError: No module named 'fla_npu'`、`Error in inspecting model architecture`、`Model architectures ['KimiK3ForConditionalGeneration'] failed to be inspected.` → 见下文「KDA 系模型（Kimi-K3 / GLM5next）的隐藏硬依赖 `fla_npu`」一节（含 glibc 闸门）。**注意：不是所有 GLM 5.x 都需要 `fla_npu`——先查 `config.json` 的 `model_type`，`glm_moe_dsa`（GLM-5.2）不需要**。
- 共享机上要决定占哪张 die、用多少显存、用哪个端口。
- **起服务前的容量规划**（这个 MoE 模型要几张卡、EP/TP/DP 怎么配、64GB 卡真实预算 56.378 GiB 够不够） → 用 `ascend-moe-ep-capacity-planning`（本 skill 从"已经决定要起"开始）。

**不要用本 skill（转交）：**
- 还没装 / 要重装 / 要重编 vllm 或 vllm-ascend 的 AscendC 算子 → 用 `vllm-ascend-source-install`（本 skill 只管「跑得起来」，不管「装得上」）。
- torch / torch_npu 装不上或版本不匹配（`No matching distribution found for torch-npu`） → 用 `ascend-torch-npu`。
- triton 被 `pip install -U triton` 覆盖、要恢复 triton-ascend → 用 `ascend-triton-ascend`；CANN 环境变量不对 → 用 `ascend-cann-env`。
- 不知道模型 / 权重在哪、大文件该写哪个盘、哪张卡空闲 → 用 `ascend-server-layout`。
- 上游仓库 docs 刷新审计（需求 vs docs 缺口清单） → 用 `upstream-docs-refresh-audit`。
- e2e 用例进 CI 的落位与 estimated_times 登记 → 用 `vllm-ascend-e2e-ci-wiring`。

**前置**：`source /mnt/share/x00886548/workspace/batch_inv_qwen35/env_batch_inv.sh` 能跑通，三层自检 ① torch_npu 与 ② `NPUPlatform npu` 都过（②不过别做 ③）。 ／ **后继**：收尾必做「步骤 5 杀服务 + 端口 / 残留进程 / HBM 三查」；装的问题回 `vllm-ascend-source-install`。

## 前置检查

ssh 一律直连 **IP**：`ssh root@192.168.13.188`。**实测客户端 `~/.ssh/config` 里没有 `a3` / `a3b` / `a5` 别名**（它们只是文档里的代称；2026-10-22 复核仍只有 `.188` / `.190` 两段 Host），照抄别名写法会直接连不上。三台当前状态见 `ascend-env` §1：**`.188` 可达；`.190` 整机不可达（ping 100% 丢包）；A5 `177.8.21.1` 需先连 A5 VPN 才可达（见 `univpn-vpn`）**——"连不上"先判是哪一种，别一律当环境坏。

环境激活（`.188` 唯一推荐入口，2026-09-23 实测可用，别重建）：

```bash
source /mnt/share/x00886548/workspace/batch_inv_qwen35/env_batch_inv.sh
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

> **平台层（`current_platform` 不是 `NPUPlatform npu`）失败的第一诊断点**：先 `echo $VLLM_TARGET_DEVICE` —— 只要它是 `cpu`，所有平台插件都被绕过、必然退化成 `UnspecifiedPlatform`（机理、源码行号与配方见 `vllm-ascend-source-install` §5.3）。

## 步骤

### 1 挑空闲 die（目的：共享机不抢别人的卡）

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

⚠️ **多卡列表必须升序，且绝不能设成空字符串（2026-10-22 在 `.188` A3 实测）**：

| 取值 | 结果 |
|---|---|
| `1,3,9,11`（升序、不连续）/ `9,11,13,15` / `9`（单卡） | ✅ 正常，`device_count` 对得上 |
| `11,9,3,1`（**降序**） | ❌ `aclInit` 失败 |
| `""`（**空字符串**） | ❌ 同上 |
| 真正 unset（`env -u`） | ✅ 16 卡全可见 |

```text
RuntimeError: Initialize:../torch_npu/csrc/core/npu/sys_ctrl/npu_sys_ctrl.cpp:165 NPU function error: aclInit, error code is 107001
Invalid_Argument(EE1003): Obtaining the logical device ID based on the user device ID failed because value 0 for parameter userDevId is invalid. Expected value: [0, 0).
```

- **按"最空闲优先"挑卡天然产出降序列表**（`sorted(..., reverse=True)`）⇒ 选完必须再 `sorted()` 一次才赋给 `ASCEND_RT_VISIBLE_DEVICES`。
- **"设为空串" ≠ "unset"**：脚本里 `export ASCEND_RT_VISIBLE_DEVICES=$PICK` 在 `PICK` 为空时会变成空串，正好复现这个错；赋之前先判空并 abort。

### 2 挑空闲端口

```bash
USED=$(ss -ltn | awk '{print $4}' | sed 's/.*://' | sort -u | tr '\n' ' ')
for p in $(seq 18000 18100); do case " $USED " in *" $p "*) ;; *) echo $p; break;; esac; done
```

验证：`ss -ltnp | grep :18000` 无输出即可用（实测取到 18000）。

- **`.188` 有常驻服务占着固定端口，别撞**（2026-10-22 `ss -ltnp` 实测）：`8686`/`8687`/`9800` = `vector`（日志采集）、`9500`/`9100` = `node_exporter`、`9200` = `npu_exporter`、`8118` = `privoxy`、`111` = `rpcbind`、`53` = `dnsmasq`（绑 `192.168.122.1`，libvirt）、`6010–6015` = 别人 ssh 的 X11 转发。⇒ 起服务只用 `18000–18100` 这一段（或 8000 这类惯例端口先 `ss` 探一下），**不要用 9100/9200/9500** ——会与监控打架，而且报错长得像"端口被 vllm 自己占了"。
- 端口一旦被并发抢占，`vllm serve` 的报错是 `OSError: [Errno 98] Address already in use`（不指向"别人的服务"）⇒ 见到它先 `ss -ltnp | grep :<port>` 看去向，再换端口。

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

- **同配置另一次冒烟实测值（2026-10-08，模型 `/mnt/weight/Qwen2.5-0.5B`、`max_model_len=512`、`enforce_eager=True`、`gpu_memory_utilization=0.4`）**：权重 **0.9320 GB**、加载耗时 **0.29 s**；`Available KV cache memory: 23.25 GiB`、`GPU KV cache size: 2,031,872 tokens`、`Maximum concurrency for 512 tokens per request: 3968.50x`；`init engine (profile, create kv cache, warmup model) took 9.66 s`；启动时 `Free memory on device (61.16/61.28 GiB)`。⇒ 上面那次记的 KV 是 `2,031,616`、这次是 `2,031,872`，**两次不是同一次运行**；别把某个具体 token 数当"必须逐字一致"的判据。
- **小模型 + 固定 temperature 的输出重复退化不是环境问题**（2026-10-08 实测）：`temperature=0.0` 下两条 prompt 的第二条会输出 `+1+1+1+…` 直到 `max_tokens`——这是**模型能力问题，不是环境问题**。判环境成功**只看是否打印出 `SMOKE_OK`**，不要拿输出内容好不好去判。

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
CKPT = "/mnt/weight/Qwen3.5-35B-A3B"                      # ← 换成你的 ckpt 目录（别把 <...> 尖括号粘进 python，会当比较运算符）
llm.collective_rpc("reload_weights", kwargs={"weights_path": CKPT})
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
  > /home/vllm/x00886548/serve_test/serve.log 2>&1 < /dev/null &
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
DIE_A=4; DIE_B=5                             # ← 换成步骤 1 挑出的两张空闲 die（**变量形式**，别把 <dieA> 粘进 shell）
MODEL=/mnt/weight/Qwen3.5-35B-A3B            # ← 换成模型绝对路径
export ASCEND_RT_VISIBLE_DEVICES=$DIE_A,$DIE_B
vllm serve "$MODEL" --served-model-name qwen3-35b-a3b --port 8000 \
  --tensor-parallel-size 2 --max-model-len 32768 --gpu-memory-utilization 0.85 \
  --dtype bfloat16 --enforce-eager --limit-mm-per-prompt '{"image": 2, "video": 0}' \
  --max-num-seqs 16 --max-num-batched-tokens 4096 --trust-remote-code
```
> 上面三个变量与 `--port` 都要换成真实值——`<dieA>`、`<模型绝对路径>` 这类尖括号在 bash 里是**重定向符**，照抄会读不存在的文件或截断文件。

- `--limit-mm-per-prompt` 传多模态 key 被 v0.30.0 正常接受；`--trust-remote-code` 对没有 `auto_map` 的模型是 no-op 但无害。
- 就绪判据与步骤 4 相同（`grep -m1 'Application startup complete'`）；实测参考值：**就绪 114 秒**、`Loading safetensors checkpoint shards: 14/14`、每 die `32.93GiB weights + 3.68GiB activation`、`KV cache 14.96 GiB = 1,126,027 tokens`、`seed=0`、吞吐 ≈ **21 tok/s**（此时 `VLLM_BATCH_INVARIANT=1` 生效，见坑 5）。
- 收尾（步骤 5）期望值：杀服务后两张 die 的 HBM 应从约 `52876/65536` 回落到 `2869/65536` 基线附近。

### 5 收尾杀服务（必须做）

```bash
PID=$(ss -ltnp | grep :18000 | sed 's/.*pid=\([0-9]*\).*/\1/' | head -1); kill -TERM $PID
ss -ltnp | grep :18000 || echo "PORT RELEASED"
# 只 kill 自己端口上的 PID；绝不用 pkill -f vllm——本机 NPU0 上就有别人的 VLLMWorker
```

## KDA 系模型（Kimi-K3 / GLM5next）的隐藏硬依赖 `fla_npu` → `references/kda-fla-npu.md`

**只有模型确实会走进 KDA / GDN 导入链时才需要读。** 该文件（原正文 209 行，逐字保留）依次解答：会不会真走进 KDA 链 → 症状与报错锚点（**炸在"检视模型架构"阶段，不是运行时**）→ 谁引入的（`12e7e1cb` 实测行号，全是**模块级** import）→ 官方 CI 逐字来源 → 档位→SOC 映射与定档方法 → **先量 glibc 再决定下不下这个 wheel** → glibc < 2.32 的三条出路（出路 ③ 已端到端验证）→ K3 在 A3 上的版本配对。

判据一句话：**`import` 阶段就 `ImportError: No module named 'fla_npu'`** ⇒ 按该文件查；能正常 import 就不要提前装它，版本对不上反而会把 vllm 依赖树带崩。
## 坑与修法

1. **权重是 git-lfs 指针 → `MemoryError`**（实测复现，文件正好 134 字节）。原文：`File ".../vllm/transformers_utils/utils.py", line 114, in parse_safetensors_file_metadata` → `metadata = json.loads(f.read(length_of_metadata).decode("utf-8"))` → `MemoryError`（上层是 `maybe_untie_word_embeddings`）。判别：`ls -la *.safetensors` 看 134 字节 + `head -c 200 model.safetensors | grep -c git-lfs` → 1。修法：下真权重，别 `git clone`；`/mnt/weight/Qwen2.5-0.5B/model.safetensors` 是真权重（988097824 字节）。
2. **`import vllm` 报 `No module named 'triton.experimental'`**（实测：直接 `import triton.experimental` 复现；`import vllm` 后再 import 即 OK，`vllm_ascend/__init__.py` 打了 stub）。**装完 vllm-ascend 即消失，别单独升级 triton**（会覆盖 triton-ascend）。
3. **`.188` 缺 `GLIBCXX_3.4.26`（运行时坑，症状像算子 API 用错）**。实测原文：`[ERROR] Failed to load custom_transformer library ... via dlopen.` + `Error detail: /lib/x86_64-linux-gnu/libstdc++.so.6: version 'GLIBCXX_3.4.26' not found (required by .../op_tiling/lib/linux/x86_64/libcust_opmaster_rt2.0.so)`，随后 `RuntimeError: Engine core initialization failed. See root cause above. Failed core proc(s): {'EngineCore': 1}`。旧记录的 `dtype or format of parameter` / `NnopbaseExecutorDoTiling` 是同一根因的另一表现（**未验证：本次未复现该措辞**）。修法：`export LD_LIBRARY_PATH=/mnt/share/x00886548/workspace/batch_inv_qwen35/compat_lib:$LD_LIBRARY_PATH`（env 脚本已做）；只前置 `compat_lib`，**别加整个 `$CONDA_PREFIX/lib`**（`git` 会崩）。
4. **`VLLM_USE_V1` 已废弃**。实测：设了不致命，起服务打 `WARNING ... [envs.py:2290] Unknown vLLM environment variable detected: VLLM_USE_V1`，服务照样 200；`vllm.envs` 已无该属性（`AttributeError: module 'vllm.envs' has no attribute 'VLLM_USE_V1'`）。V1 是唯一引擎 → **不要设**。
   > **`VLLM_VERSION`：2026-10-08 二次修正（上一轮的"该设时必须设"也已不成立）**。原写"同理别设 `VLLM_VERSION`"是错的；但上一轮改成"**必须设**"在 vllm `v0.23.0` 上同样不成立——该版本 `setup.py` **不再读 `VLLM_VERSION`**（`grep -n VLLM_VERSION setup.py` 逐字只剩 `VLLM_VERSION_OVERRIDE` 两行），且**不导任何变量时** `vllm_version_is("0.23.0")` 本来就为 `True`：它是**版本线**判定，不是等值判定。逐字三向实测见 `vllm-ascend-source-install` §5.1（**单一归属，本文件只留指针**）。
   > 仍然成立的噪声事实：起服务路径能看到 `WARNING [envs.py:2088] Unknown vLLM environment variable detected: VLLM_VERSION`（**无害，别为消它去改代码**）；离线 `LLM()` 冒烟路径该 warning 实测 **0 次**。
   > 下面那条 `AttributeError: module 'vllm.v1.engine.utils' has no attribute 'get_physical_gpu_ids_for_local_dp_rank'` 的观测**只对"仍读取该变量"的 vllm 版本成立**：它记的修法 `export VLLM_VERSION=<tag>` 在 `v0.23.0` 上不可能生效，请改用 `VLLM_VERSION_OVERRIDE` 或核对配对版本（§5.1）。
   > 完整机理、~20 处受影响分支、以及一行预检命令见 `vllm-ascend-source-install` §5 与 §6 坑 10。
5. **env 脚本默认 `VLLM_BATCH_INVARIANT=1`，慢 5.5 倍**。实测同模型同卡：BI=1 → load 20.8s / **27.87 toks/s**；`unset VLLM_BATCH_INVARIANT` → load 10.0s / **154.51 toks/s**（日志另有 `Disabling cascade attention when VLLM_BATCH_INVARIANT is enabled.`）。不要求批次不变性就先 unset。
   > **要证「BI 下结果真的批次不变」**（而不只是"BI 装上了"）→ 跑算子级验收配方：`vllm-ascend-source-install` §5.5（`torch.equal` 逐位比、参考必须是**同一个逻辑行**、空张量判 FAIL、负控；**正文归它，本文件只留指针**）。
6. **共享机抢卡/显存**：`gpu_memory_utilization=0.4` 在小模型上仍一次吃 23 GiB KV（单 die 共 61.28 GiB）；一个进程只占一张卡，先按步骤 1 挑 free 最大的 die，别拉满利用率。
7. **无害噪声**（别当故障）：`/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory`（每条 ssh 都打）、`[W NPUCachingAllocator.cpp:202] Warning: The current CANN and HDK(driver) versions require processing for 32 padding size, with memory allocation. (function operator())`、`WARNING [parallel_state.py:2092] torch._C._host_emptyCache() only available in Pytorch >=2.5`、`WARNING [utils.py:1404]` 与 `WARNING [platform.py:1067] GPU-specific parameter is not supported on Ascend`、`[Gloo] Rank 0 is connected to 0 peer ranks. Expected number of connected peer ranks is : 0`（**单卡时正常**）、`VLLM_USE_V1 not set, auto-detected`。
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

20. **运行期 `export VLLM_TARGET_DEVICE` → 平台层**静默**降级，三层自检的第 ③ 层就此假失败**（2026-10-10 实测）。
    → 原因：只要该变量 == `cpu`，`vllm/vllm/platforms/__init__.py` 会在**咨询任何平台插件之前**就 `return` cpu 插件 ⇒ 平台层退化成 `UnspecifiedPlatform`（机理、源码行号与配方见 `vllm-ascend-source-install` §5.3，**单一归属**）。构建期的 `VLLM_TARGET_DEVICE=empty` 是**另一回事**（让 `ext_modules=[]`），与运行期**无关**，别顺手把它带进运行 shell。
    → 修法：**运行期 `unset VLLM_TARGET_DEVICE`**——一键激活 / env 脚本里都**不要** export 它。干净态自检实测：`TARGET_DEVICE_ENV None` + 平台层 `NPUPlatform npu`。

## 不要做什么

- 不要 `pip install`/卸载任何包；不要 `pip install -U triton`；不要重建 vllm。
- 不要设 `VLLM_USE_V1`（已废弃）。**`VLLM_VERSION` 要按版本区分、不要无条件设也不要无条件不设**：vllm `v0.23.0` 上它**已不被读取**（真开关 `VLLM_VERSION_OVERRIDE`），且不导它时 `vllm_version_is("0.23.0")` 本来就 `True`——见本文件坑 4 的二次修正与 `vllm-ascend-source-install` §5.1。
- 不要 `pkill -f vllm`；不要动 `/mnt/share/x00886548/cann/`、`/usr/local/Ascend`、`/etc/Ascend`、`xmz_0921` 里的包。
- 不要 `export VLLM_TARGET_DEVICE`（运行期只要它是 `cpu` 就把平台层静默降级成 `UnspecifiedPlatform`，见坑 20）；构建期的 `VLLM_TARGET_DEVICE=empty` 与运行期无关，别带进来。
- 不要在共享机上占用**未确认空闲**的 die、也不要起自己放不下的模型；**「别占多张卡」不是绝对禁令**——TP≥2 要同时占两张，但前提是 launch 前一刻确认两张都空闲（见步骤 1 与 4.1）；`gpu_memory_utilization` 别无脑拉满（TP=2 实测可用 0.85，留基线余量给别人）。
- 不要把大文件/日志写 `/`、`/mnt/share`、`/tmp`、`/root`（同一块系统盘，长期紧张，余量现场 `df -h` 看）；写 `/home/vllm/x00886548/serve_test/`。
- 内联 ssh 里别用 `<` `"` `$()`；脚本里别用 heredoc（会永久挂起）。
- 别在 `load_format="dummy"` 下用 `reload_weights`（互斥，坑 11）；也别只 `wake_up(tags=["weights"])` 就 `generate()`（会挂住，坑 13）。
- 强杀进程后不复查 `npu-smi` 不算收尾（坑 17）；`pkill -f` 的模式别能匹配到自己那条命令行（坑 16）。

## 验收标准

1. 三层自检 = `True 16 253` / `NPUPlatform npu` / 两个版本串非空。
2. 离线冒烟打印 `SMOKE_OK`，出文本，toks/s > 0。
3. `/v1/models` 含 `"id"`；`/v1/chat/completions` 返回 200 且 `choices[0].message.content` **非空**（思考型模型这里可能是 CoT，见坑 8，不是失败）。
4. 收尾三查：`ss -ltnp | grep <port>` 为空、`ps -ef | grep 'vllm serve'` 无残留、目标 die HBM 回落到基线（单卡实测 28889 → 2857 MB；TP=2 实测 52876 → 2869 MB）。

5. sleep / 权重热更新（步骤 3.1）：`sleep(level=1|2)` 后该 die 的 used HBM 应降到 ~1GiB 量级（权重确实被释放的证据），`wake_up()` 后回到与 sleep 前同量级；A→B→C 打印 `VERDICT WEIGHT_UPDATE_PROVEN`（`B != A` **且** `C == A`），只看到 C 有文本不算过。

**未验证**：`.190`（`a3b`）上的起服务、冒烟与多卡始终没跑成——2026-09-23 是 ssh 全程不通，**2026-10-22 复核直接整机不可达（ping 100% 丢包）**；A5（`177.8.21.1`）**需先连 A5 VPN 才可达**，起服务相关全部 `未采`。⇒ 这两台的任何"跑起来了"都不要写。`.188` 上 `--tensor-parallel-size 2` **已实测通过**（TP=2 起服务 + 真推理成功，见步骤 4.1）。
