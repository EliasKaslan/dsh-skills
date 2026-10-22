# KDA 系模型的隐藏硬依赖 `fla_npu`（从 `ascend-vllm-serve` 正文原样拆出）

> 从 `ascend-vllm-serve/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## KDA 系模型（Kimi-K3 / GLM5next）的隐藏硬依赖 `fla_npu`

### ⚠️ 先判「会不会真走进 KDA / GDN 导入链」，再判 `fla_npu` 是否必需

**别把本节读成「所有 GLM 5.x 都要 `fla_npu`」——那是误读。** 上手第一步是查该模型的 HF / ModelScope `config.json`，用 `model_type` / `architectures` **反查它会 import 到哪条链**，再决定要不要 `fla_npu`：

| `config.json` 的 `model_type` / `architectures` | 实际走哪条路 | `fla_npu` |
|---|---|---|
| `glm_moe_dsa` / `GlmMoeDsaForCausalLM`（**GLM-5.2** 实测：HF `zai-org/GLM-5.2`） | `vllm_ascend/models/deepseek_mtp.py:AscendGlmMoeDsaForCausalLM`，**不经过 `glm5next`** | **不需要** |
| Kimi-K3（`KimiK3ForConditionalGeneration`） | `vllm_ascend/ops/kimi_kda.py` | 需要 |
| `glm5next`（= **GLM-5.3-Flash**，**不是** GLM-5.2） | `models/glm5next/…` → `.kda` → `ops/causal_conv1d` | 需要 |

- `fla_npu` 只被这 4 处**无条件**模块级 import：`vllm_ascend/models/glm5next/ops/causal_conv1d.py:6`（导入链 `glm5next/model.py:81 -> .kda -> ops.causal_conv1d`）、`vllm_ascend/ops/kda.py:11`、`vllm_ascend/ops/kimi_kda.py:15`、`vllm_ascend/ops/gdn.py:23,60`。**没走进这条链的模型不需要 `fla_npu`**。
- `glm5_next` ≠ GLM-5.2 的判据：同仓 `vllm_ascend/patch/__init__.py:269` 逐字写着 "The GLM-5.3-Flash architecture is maintained in vllm-ascend (`vllm_ascend/models/glm5next/`)"。
- **下面整节的 glibc 闸门只对「真的走进 KDA / GDN 链」的模型成立**（Kimi-K3 系、GLM-5.3-Flash 系）；`glm_moe_dsa`（GLM-5.2）这一类**不需要** `fla_npu`，与 glibc 闸门无关。

**本节记录的是「判据与闸门」，并且已在容器路线端到端验证通过**（起服务 + `/v1/models` 200 + `/v1/chat/completions` 200，见「出路 ③ 落地」一节的逐字实测）。**但宿主机那条路线确实走不通**：`.188` / `.190`（glibc 2.28 / 2.31）上不可能装上 `fla_npu` —— **这一点没有被推翻**，被推翻的只是"只有换机器或自己编两条路"。

### 症状与报错锚点（在**检视模型架构**阶段就炸，不是运行时才炸）

`vllm serve <KDA 模型目录> --load-format dummy …` 逐字原文（**这串就是下次能被搜到的锚点**）：

```text
(APIServer pid=21595) ERROR 10-09 20:20:52 [registry.py:1114] Error in inspecting model architecture 'KimiK3ForConditionalGeneration'
(APIServer pid=21595) ERROR 10-09 20:20:52 [registry.py:1114] subprocess.CalledProcessError: Command '['…/python', '-m', 'vllm.model_executor.models.registry']' returned non-zero exit status 1.
(APIServer pid=21595) ERROR 10-09 20:20:52 [registry.py:1114] RuntimeError: Error raised in subprocess:
(APIServer pid=21595) ERROR 10-09 20:20:52 [registry.py:1114] ModuleNotFoundError: No module named 'fla_npu'
pydantic_core._pydantic_core.ValidationError: 1 validation error for ModelConfig
  Value error, Model architectures ['KimiK3ForConditionalGeneration'] failed to be inspected.
```

### 谁引入的（vllm-ascend commit `12e7e1cb` 实测行号；全是**模块级** import ⇒ 缺包直接 ImportError）

- `vllm_ascend/ops/kimi_kda.py:15` → `from fla_npu.ops.ascendc import causal_conv1d_fn, causal_conv1d_update`
- `vllm_ascend/ops/kda.py:11` → `from fla_npu.ops.ascendc import chunk_kda_fwd, recurrent_kda`
- `vllm_ascend/ops/gdn.py:23` / `:60` → `chunk_gated_delta_rule_fwd` 等
- `vllm_ascend/models/glm5next/ops/causal_conv1d.py:6` → `causal_conv1d_fn, causal_conv1d_update`

**版本事实（反例，很重要）**：vllm-ascend `9df651d0b`（2026-09-28）的 `kimi_kda.py`（28535 B）对 `fla_npu` **零命中** ⇒ 这个硬依赖是 **2026-09-28 → 2026-10-09 之间**引入的，旧版不需要它。
**但别把「退回旧 commit」当通用退路**：`9df651d0b` 不含 PR #16959 —— 只有在你不需要新代码时才成立。

### 官方来源（从 vllm-ascend 自己的 CI 逐字抄出）

`.github/workflows/_selected_tests.yaml:266-311`：

```yaml
env:
  NPU_TYPE: ${{ matrix.group.npu_type }}
  GIT_PROXY: https://gh-proxy.test.osinfra.cn/
run: |
  FLA_VERSION=26.9.1+deva4a7958
  FLA_RELEASE_TAG=v26.9.1-beta2
  case "$NPU_TYPE:$(uname -m)" in ... esac
  FLA_DOWNLOAD_URL="https://github.com/flashserve/flash-linear-attention-npu/releases/download/${FLA_RELEASE_TAG}/${FLA_WHL}"
  if [ -n "${GIT_PROXY:-}" ]; then FLA_DOWNLOAD_URL="${GIT_PROXY}${FLA_DOWNLOAD_URL}"; fi
  curl --fail --location --show-error --silent --retry 3 --retry-delay 5 --retry-all-errors "$FLA_DOWNLOAD_URL" -o "/tmp/$FLA_WHL"
  echo "$FLA_SHA256  /tmp/$FLA_WHL" | sha256sum --check
  uv pip install --no-deps "/tmp/$FLA_WHL"
  python3 -c "import fla_npu.ops.ascendc"
```

- 仓库 `github.com/flashserve/flash-linear-attention-npu`，release `v26.9.1-beta2`（**prerelease**，2026-09-23）。
- 文件名模板：`flash_linear_attention_npu_<platform>-26.9.1+deva4a7958-py3-none-manylinux_2_34_<arch>.whl`
- **URL 里 `+` 必须写成 `%2B`**（否则 curl 拿到的不是那个文件）；装法带 `--no-deps`；**验收 = `python3 -c "import fla_npu.ops.ascendc"` 不报错**。

### 档位 → SOC 映射，以及怎么在自己的机器上定档

| 档位 | SOC |
|---|---|
| a2 | `ascend910b` |
| a3 | **`ascend910_93`** |
| a5 | `ascend950` |

```bash
python -c "import torch, torch_npu; print(torch.npu.get_device_name(0)); print(torch_npu.npu.get_soc_version())"
uname -m
```

实测（`.188`）：`get_device_name(0)` = **`Ascend910_9382`**、`get_soc_version()` = **253**、`uname -m` = **`x86_64`** ⇒ 取 **a3 + x86_64**。
（「`Ascend910_9382` 与 `ascend910_93` 同族」的机理见 `vllm-ascend-source-install` §4 的 `-soc_version` 条，**本文件不重复**。）

**可达性实测**（`curl -s -o /dev/null -w %{http_code}`）：`https://gh-proxy.test.osinfra.cn/` = 200、`https://ghfast.top/` = 200、直连 `github.com` 也 = 200（但平时直连常 60s 超时，代理更稳）。

### ★ 先量 glibc，再决定要不要下这个 wheel ★

**该 wheel 的平台标签是 `manylinux_2_34`，且官方只发布这一种**：`/tags` 里 26 个 tag，只有 `v26.9.1-beta2` 是带资产的 release，6 个 wheel **全是 `manylinux_2_34`**。

**两步量法（不必真装就能判；先做这个，再决定下载）**：

```bash
getconf GNU_LIBC_VERSION
# 解开 wheel 看里面 .so 需要多新的 glibc
unzip -o <wheel> -d /tmp/flachk >/dev/null
for so in $(find /tmp/flachk -name '*.so'); do
  echo "$so : $(strings -a "$so" | grep -o 'GLIBC_2\.[0-9]*' | sort -V | tail -1)"
done
```

实测 wheel 内 `.so` 的 `maxGLIBC`：

```text
fla_npu/custom_aclnn_extension_lib.cpython-312-x86_64-linux-gnu.so ...... GLIBC_2.32
.../op_api/lib/libcust_opapi.so ........................................ GLIBC_2.32
.../op_api/lib/libopapi.so ............................................. GLIBC_2.32
.../op_proto/es/lib/linux/x86_64/libes_transformer_cust.so ............. GLIBC_2.32
.../op_impl/ai_core/tbe/op_tiling/liboptiling.so ....................... GLIBC_2.34
.../op_impl/ai_core/tbe/op_tiling/lib/linux/x86_64/libcust_opmaster_rt2.0.so  GLIBC_2.34
.../op_proto/lib/linux/x86_64/libcust_opsproto_rt2.0.so ................ GLIBC_2.34
```

**机器实测**：`.188` = Debian 10 / glibc **2.28**；`.190` = Debian 11 / glibc **2.31** ⇒ **两台都不够**。

**pip 会直接拒绝**（逐字）：

```text
ERROR: flash_linear_attention_npu_a3-…-manylinux_2_34_x86_64.whl is not a supported wheel on this platform.
```

**即使绕过 pip（`--target` 或 `unzip -o`）也加载不了**，动态加载器逐字报：

```text
OSError: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found
  (required by .../fla_npu/opp/vendors/fla_npu_transformer/op_api/lib/libcust_opapi.so)
RuntimeError: Unable to load embedded FLA NPU custom op_api library: .../libcust_opapi.so.
  Dynamic loader error: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found
```

### glibc < 2.32 时的处置（三条出路）

- 结论（**已被 2026-10-22 实测部分推翻，务必按此修正理解**）：**"glibc < 2.32 的宿主跑不了 KDA 系模型"只对官方那个 `manylinux_2_34` wheel 成立，对"本机从源码构建的 wheel"不成立。** 判据是 wheel 里 `.so` 的 `maxGLIBC`，不是宿主的 glibc 数字。
- 三条出路：
  1. **换 glibc ≥ 2.34 的机器**。
  2. **★ 在本机从源码构建 `fla_npu`（2026-10-22 已实测走通，首选，不需要 docker）**：
     - 产物 `flash_linear_attention_npu_a3-26.9.1+unknown-py3-none-manylinux_2_17_x86_64.whl`（40,693,290 B，平台标签是 **`manylinux_2_17`**）。
     - 关键实测：解开后**所有 `.so` 的 `maxGLIBC` 都是 `GLIBC_2.14`**（官方 wheel 是 2.32/2.34）⇒ **`2.32/2.34` 这个门槛来自官方构建工具链，不是源码本身**。
     - 在 `.188`（glibc **2.28**）上：`pip install --no-deps --no-index <该 wheel>` 成功；`import fla_npu.ops.ascendc` 通过，`causal_conv1d_fn / causal_conv1d_update / chunk_kda_fwd / recurrent_kda` **四个符号齐全**。
     - ⇒ **先试 ②，再考虑 ③**；② 省掉容器与 glibc 绕行的全部复杂度与副作用。
  3. 改用本机已有的新 glibc 容器镜像（也走通过）→ 见下一小节。**仍适用于"手上只有官方 wheel"的情形。**
  > 上一版这里写过"②未验证：本次未做"，那句于 2026-10-22 被实测推翻，已改。
- **不要升级系统 glibc**（`.188` / `.190` 都是多租户共享机，升 glibc 会连带影响所有租户的运行时）。

### 出路 ③ 落地：用本机已有的新 glibc 容器镜像（已端到端验证）

**根本判据（比背镜像名更重要）**：**glibc 向后兼容** ⇒ 用一个**更高 glibc 的容器**，可以**同时**加载宿主机那套 **glibc-2.28 编的** `torch_npu` / `vllm_ascend_C`，**和**需要 ≥2.32/2.34 的 `fla_npu` —— **一次解开两个卡点**。
等价说法：**这条依赖卡的从来不是"某台机器"，而是"glibc ≥2.34 的运行环境"；容器是最省事的提供方式。**

**镜像不用拉**（`docker pull` 在本机**不通**：`registry-1.docker.io ... connection reset by peer`）—— **镜像已经在本机**：

```bash
docker images | grep -E 'vllm-ascend|mindspeed-ops|cann'
```

实测本机有 `vllm-ascend:main-latest-20261009`（= `quay.nju.edu.cn/ascend/vllm-ascend:nightly-main-a3`，**同一 image id `5d99a6a9e66e`**）、`quay.nju.edu.cn/ascend/vllm-ascend:v0.28.0.rc1-a3`、`…cann:9.1.0-a3-openeuler24.03-py3.12`、`mindspeed-ops:master-a3-openeuler24.03-py3.12-x86_64` 等。
**2026-10-22 复核（`docker images` 当前前几名，别人会随时拉新的，只作"库里大概有什么"的参考）**：`vllm-ascend:nightly-main-a3-openeuler-1017` 22.8G、`quay.nju.edu.cn/ascend/vllm-ascend:nightly-main-a3-openeuler` 22.8G、`quay.nju.edu.cn/ascend/vllm-ascend:nightly-main-a3` 22.3G、`quay.io/ascend/sglang:main-cann9.1.0-a3-amd64` 18G、`quay.nju.edu.cn/ascend/vllm-ascend:v0.28.0.rc1-a3` 25.9G、`mindspeed-ops:master-a3-openeuler24.03-py3.12-x86_64` 15G。⇒ **镜像 tag 会随他人活动变**，选型一律现场 `docker images` 列表，别照抄本节某一行。

**选镜像的判据 = 进去量 glibc 与 `fla_npu`**（实测 `vllm-ascend:main-latest-20261009`：**Ubuntu 22.04.5 / glibc 2.35**、torch 2.10.0+cpu、torch_npu 2.10.0.post4、vllm 0.30.0）：

```bash
getconf GNU_LIBC_VERSION
python -c "import fla_npu.ops.ascendc; print('FLA_OK')"     # 实测打印 FLA_OK ⇒ 镜像里已装好 fla_npu
```

**坑 ①：docker 里没有 `ascend` runtime**（只有 `runc` / `io.containerd.runc.v2`）⇒ 要**手工直通**：挂 `/usr/local/Ascend/driver`、`/usr/local/dcmi`、`/usr/local/bin/npu-smi`，`--privileged --net=host --ipc=host`；设备节点 `/dev/davinci0..3`（可用则加）、`/dev/davinci_manager`、`/dev/devmm_svm`、`/dev/hisi_hdc` 都在。
**坑 ②：`PYTORCH_NPU_ALLOC_CONF=expandable_segments:True` 会搞坏 vllm-ascend 的 CaMemAllocator**（`AssertionError`）⇒ 这条路上**不要设**它（与我们过去"设了更省显存"的直觉相反）。

**端到端实测（逐字，可直接当验收基线）**——容器 `k3c-s2` + 真实减层包 `/k3w/kimi_k3_reduced_4l`（`num_hidden_layers=4, num_experts=896, hidden_size=7168, bf16`）：

```text
args = --dtype bfloat16 --max-model-len 512 --enforce-eager --load-format dummy
       --tensor-parallel-size 4 --enable-expert-parallel --gpu-memory-utilization 0.8
       --max-num-seqs 4 --trust-remote-code --served-model-name k3
       --additional-config {"weight_nz_mode": 0}
日志 = [model.py:692] Resolved architecture: KimiK3ForConditionalGeneration
       [kimi_k3.py:116] Overriding vision_config.text_hidden_size from 2304 to 4096 to match text_config.hidden_size
       [model.py:715] Defaulting to tokenizer_mode='kimi_k3' for KimiK3ForConditionalGeneration
       Application startup complete.
       "GET /v1/models HTTP/1.1" 200 OK
       "POST /v1/chat/completions HTTP/1.1" 200 OK
响应 = {"choices":[{"message":{"content":"  like,NULL like,NULL like,NULL like,NULL"},"finish_reason":"length"}],
        "usage":{"prompt_tokens":89,"completion_tokens":8}, "system_fingerprint":"vllm-0.30.0-tp4-ep-9df7a6aa"}
```

- ★ **判据型细节**：`system_fingerprint` 形如 `vllm-<版本>-tp<TP>-ep<EP>-<hash>` ⇒ **可用它一眼确认 TP/EP 真生效了**（本例 `tp4-ep`）。
- ★ `content` 是重复串**不是失败**（减层 + `dummy` 权重，同步骤 3「小模型输出退化不是环境问题」）：**判据只看两端点 200 且 `content` 非空**。
- ★ **判容器要走精确过滤器**：`docker ps --filter name=k3c` 是**子串匹配**，会同时命中 `k3c-s2` ⇒ 用 `docker ps --filter 'name=^k3c-s2$'`。
- ★ **`docker ps` 在本多租户机会列出 ~44 个别人的容器** ⇒ **不要裸跑 `docker ps -a` 刷屏**，一律带 `--filter`。

### K3 在 A3 上能不能跑：先认版本配对，别把它当环境问题

**判据一句话**：Kimi-K3 的 MLA decode 在 mainline 上走的是 **A5（Ascend950）的非连续 KV cache 契约**，A3（本文默认的 `.188`，soc 253）没有对应实现 ⇒ 用"今天的主线"装出来的环境**服务能起、首个请求必 500**。

- 先确认环境没问题（这些都该是绿的）：`Resolved architecture: KimiK3ForConditionalGeneration` / `Setting kv cache block size to 128 for ASCEND_MLA backend(s)` / `MLA decode backend …: FIA` / `Available KV cache memory: … GiB` / `Application startup complete`。
- 首个 `/v1/chat/completions` 的报错原文（逐字）：
  ```text
  npu_fused_infer_attention_score_v2_symint … call aclnnFusedInferAttentionScoreV4 failed, error code is 561002
  Invalid_Argument(EZ0037): Parameter keyRope of FusedInferAttentionScore is invalid.
    Reason: In PA and not MXFP8 Fullquant scenarios, keyRope does not support non-contiguous tensors.
  ```
  给 decode 的 `key_rope` 补 `.contiguous()` 只会让报错**前移一位**（变成 `Parameter key … key tensor must be contiguous`），因为两个入参都不连续 —— 这条路走不通，别在上面耗时间。
- 根因用探针一次问出来（比读代码快）：K3 的 KV cache **每块把 latent 与 rope 交错存在同一块 buffer**：
  ```text
  k_nope (9168,1,128,512) stride=(73728,65536,512,1)  contig=False
  k_pe   (9168,1,128, 64) stride=(73728, 8192, 64,1)  contig=False     # 73728 = 65536 + 8192
  ```
  `mla_v1.get_kv_cache_shape()` 返回 `(num_blocks, block_size, num_kv_heads, kv_lora_rank + qk_rope_head_dim)` ⇒ **融合 cache 是设计如此**，不是现场 bug。对它 `.contiguous()` = 复制整块 cache（本例 1.2 GB/层/步），不可行。
- 上游定性：vllm-ascend **#16464 [RFC] A5 non-contiguous KV cache and Flash MLA/KDA integration for DSpark**（open，2026-09-13）逐字写了 `Scope: A5/Ascend950`、`it does not introduce a new A2/A3 implementation`，待办正是 import Flash MLA + stride-aware `ScatterPaKvCache` 以支持 **non-contiguous page axis**。
- **A3 本身能跑 K3 —— 是主线回归**：同机、同减层模型、同参数，用 10-09 那套配对 `vllm 0.30.1.dev0+gced6857af` + `vllm-ascend 12e7e1c` 实测 **`HTTP=200` 且 content 非空**（dummy 权重，文本无意义）。
- ⇒ **要在 A3 上跑 K3，就别用"今天的主线"**（vllm-ascend 钉到 `12e7e1c` 一带 + 它的 verified commit）；要保今天的主线，就去 A5 跑。配对怎么选见 `vllm-ascend-source-install`。

