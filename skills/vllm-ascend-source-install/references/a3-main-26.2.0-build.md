# main + 商发 26.2.0（CANN 9.2.0）在 A3 x86_64 上的构建链（裸机，两台实测）

2026-11-23 在 `192.168.13.190`（openEuler 22.03 SP4，64 核，glibc 2.34，gcc 10.3.1）与
`192.168.13.188`（Debian 10，256 核，glibc **2.28**，gcc **8.3.0**，`/` 仅剩 18G）上各建一套。
两台都是 A3：8 卡 16 die（`/dev/davinci0..15` + `davinci_manager`），每 die 65536MB。

## 版本对（两台实测一致）

| 组件 | 值 |
|---|---|
| CANN | 9.2.0（复用机器上已有安装树，含 `opp/.../kernel/ascend910_93`） |
| Python | 3.12.16（190）/ 3.12.15（188） |
| torch / torch_npu | 2.10.0+cpu / 2.10.0.post7 |
| triton | 3.6.0（dist `triton_ascend 3.6.0.post2`（190）/ `triton_ascend 3.6.0`（188）；`pip show triton` 为空属预期） |
| numpy / scipy / transformers | 1.26.4 / **1.13.1** / 5.19.0 |
| fla_npu | `flash_linear_attention_npu_a3` 26.10.0+feature（190）/ 26.9.1 manylinux_2_17（188） |
| vllm-ascend | main `9316dd8089b0ff7286ba83e777afe3cdffce066a`（2026-11-23） |
| vLLM | `c410543d9ffff03f5f6c4a8c0ae1d3ad082c4a15`（`.github/vllm-main-verified.commit`，两轮未变） |
| `SOC_VERSION` | **`ascend910_9391`** |

`SOC_VERSION` 取 `ascend910_9391`：官方 A3 镜像 `Config.Env` 与 `setup.py:149` 自述一致；
但**设备自报是 `Ascend910_9382`**（`get_device_name()`、`get_soc_version()=253`），
`hardware.py` 与 `CMakeLists` 把 9382/9391 归同一 A3 分支，不影响编译产物。

## 构建顺序（190 全流程跑通并出词）

```bash
ROOT=/home/x00886548/ascend-26.2.0        # 188 上是 /home/vllm/x00886548/ascend-26.2.0（/home/x00886548 是软链）
source $ROOT/env/activate.sh
cd $ROOT/run                              # 中性 cwd
export SOC_VERSION=ascend910_9391 MAX_JOBS=32 TMPDIR=$ROOT/tmp PIP_CACHE_DIR=$ROOT/cache/pip PYTHONNOUSERSITE=1
IDX="-i https://repo.huaweicloud.com/repository/pypi/simple --trusted-host repo.huaweicloud.com"
PY=$(command -v python)

# 0) 构建工具先进 venv（系统 cmake 太旧：190 无 cmake、188 是 3.13.4，都要 >=3.26）
$PY -m pip install $IDX "setuptools==80.10.2" setuptools-scm "setuptools-rust>=1.9.0" wheel pybind11 \
    "cmake>=3.26.1" ninja jinja2 "packaging>=24.2"

# 1) vLLM：empty target + 剥 torch pin。**不要**设 SETUPTOOLS_SCM_PRETEND_VERSION（见坑 1）
cd $ROOT/src/vllm && $PY tools/use_existing_torch.py --prefix
VLLM_TARGET_DEVICE=empty $PY -m pip install -v -e . --no-build-isolation $IDX
$PY -c "import vllm;print(vllm.__version__)"     # 0.1.dev1+gc410543d9.d<date>  ← 这个"难看"的版本是能跑的那个

# 2) vllm-ascend 依赖：requirements 去掉 triton-ascend 行与 arctic-inference 行后真装
cd $ROOT/src/vllm-ascend
grep -vE '^[[:space:]]*(triton-ascend|arctic-inference)' requirements.txt > /tmp/req.local.txt
wc -l /tmp/req.local.txt                  # 40 行左右；0 行说明相对路径写错
$PY -m pip install -r /tmp/req.local.txt $IDX --timeout 20 --retries 3 \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi/nightly

# 3) 回钉 numpy/scipy（裸 scipy 会解到 1.18 要求 numpy>=2，直接把 ACLNN 编译打断）
$PY -m pip install --no-deps --force-reinstall "numpy==1.26.4" "scipy==1.13.1"

# 4) triton 命名空间必须归 triton_ascend（vLLM 安装会把社区 triton 顶到 3.9.0）
$PY -m pip show triton >/dev/null 2>&1 && $PY -m pip uninstall -y triton
rm -rf $ROOT/env/py312/lib/python3.12/site-packages/triton $ROOT/env/py312/lib/python3.12/site-packages/triton-*.dist-info
$PY -m pip install --no-deps --force-reinstall $ROOT/env/wheels/triton_ascend-*.whl
$PY -c "import triton;print(triton.__version__,triton.__file__)"

# 5) fla_npu（引擎期才用到，见坑 3）
$PY -m pip install --no-deps --force-reinstall $ROOT/env/wheels/flash_linear_attention_npu_a3-*.whl
$PY -c "from vllm_ascend.ops.gdn import AscendGatedDeltaNetAttention;print('gdn OK')"

# 6) 编 vllm-ascend
cd $ROOT/src/vllm-ascend
rm -rf csrc/build csrc/build_out csrc/build_cache build
SOC_VERSION=ascend910_9391 $PY -m pip install -v -e . --no-deps --no-build-isolation
```

A3 上 `ascend910_9391` **不满足** `MATCHES "ascend310p.*|ascend950"`，所以 `vllm_ascend_kernels`（AscendC）**会真编**
（190 上 651 个 ninja 目标），产物落 `ascend910_93` 目录；这与 A5（950，跳过 kernel 编译）是主要耗时差异。

## 验收判据（190 实测值）

```
vllm-ascend  0.19.1rc2.dev3834+g9316dd808
platform     NPUPlatform device_name=npu device_type=npu
so           vllm_ascend/vllm_ascend_C.cpython-312-x86_64-linux-gnu.so (~1.1MB) import OK
torch.npu.is_available()=True  device_count=16  get_device_name=Ascend910_9382
matmul 8x8 sum 529536.0 ; acl.rt.get_device_count() -> (16, 0) ; vllm CLI --help RC=0
引擎冒烟：DeepSeek-V2-Lite 单 die + spawn → OUTPUT ' Paris.\nThe currency of France is the Euro.…'  SMOKE_RC=0
         权重 29.42 GiB，KV 13.78 GiB/475,776 tok，init 14.13s，gpu_memory_utilization=0.72
```

## 坑（每条都是实测原文）

1. **不要把 `vllm.__version__` 伪造成 `0.33.0`** —— 引擎必死在
   `RuntimeError: Cannot apply the SWA bounded replay resume patch: unexpected Scheduler._make_cached_request_data signature ('self','running_reqs','num_scheduled_tokens','spec_decode_tokens','req_to_new_blocks','iteration_details')`。
   原因在 `patch_swa_bounded_replay.py` 末尾：`if vllm_version_is("0.33.0") and _upstream_carries_replay_start():`
   —— 该 pin 上 `_upstream_carries_replay_start()` 探测为 **True**，但调度器签名已是 `iteration_details` 版、
   patch 期望 `resumed_reqs`。保持 scm 回退版本（`0.1.dev1+g<sha>`）时这条门是 False，patch 被跳过，引擎正常
   （190 实测 `patched?=False` 且出词成功）。所以：**要么让版本停在 scm 回退值，要么改用真 `v0.33.0` tag 的 vLLM**
   （`.github/vllm-release-tag.commit` = `v0.33.0`），不要"版本写 0.33.0、源码却是 c410543d"的混合态。
2. **`scipy` 必须钉 1.13.1**：裸 `scipy` 解析到 1.18.1 要求 numpy>=2，与 numpy 1.26.4 冲突，
   表现是 ACLNN 编译直接挂：`AttributeError: module 'numpy' has no attribute 'long'` +
   `A NumPy version >=2.0.0 ... SciPy (detected 1.26.4)` → `FAILED: CMakeFiles/dispatch_ffn_combine_ascend910_93_0`。
   改完要 `rm -rf csrc/build*` 重编。1.13.1 也正是 triton_ascend METADATA 的要求。
3. **`fla_npu` 的 .so 受 glibc 限制**（Debian 10 / glibc 2.28 上致命）：
   用镜像里 openeuler 构建的那份会 `version 'GLIBC_2.32' not found (required by …/libcust_opapi.so)` →
   `[Init][Geexecutor]init ge executor failed, ge errorCode=1343225857` → `RuntimeError: … aclInit, error code is 1343225857`。
   **改用 `manylinux_2_17` 的 wheel**（`objdump -T` 只需 GLIBC_2.14）即可，vllm-ascend 需要的 5 个符号都在。
4. **`triton-ascend` 命名空间会被 vLLM 安装覆盖**：`pip install -e .` 会带来社区 triton 3.9.0 →
   `triton-ascend 3.6.0 requires triton==3.6.0, but you have triton 3.9.0`，引擎期报
   `ModuleNotFoundError: No module named 'triton._C.libtriton.ascend'; 'triton._C.libtriton' is not a package`。
   修法：uninstall 社区 triton + 删掉 `site-packages/triton` 与 `triton-*.dist-info` + 回灌 triton_ascend。
5. **`arctic-inference` 会卡死 `pip install -r`**：卡在 `Installing build dependencies: started`（sdist 要 torch==2.7.0，
   `ss` 里能看到 CLOSE-WAIT）。全仓零引用，直接从 requirements 剔掉，并加 `--timeout 20 --retries 3`。
6. **单 die 可用显存小于名义值**：190 单 die 启动时只剩 **47.69 GiB / 61.27 GiB**，
   `gpu_memory_utilization=0.85` 会报 `ValueError: Free memory on device (47.69/61.27 GiB) on startup is less than desired GPU memory utilization` → 用 **0.72**。
   A3 一卡两 die，`ASCEND_RT_VISIBLE_DEVICES` 按 die 编号给。
7. **`pkill -f <串>` 会把当前 ssh 会话杀掉**（串出现在自己命令行里），表现为 `EXIT=-1` 且无输出 →
   用 PID 精确杀，或写 `[a]3_190_x` 规避自匹配。
8. `SETUPTOOLS_SCM_PRETEND_VERSION` 只在**必须**固定版本时才用；浅克隆退化出 `0.1.dev1+g<sha>`（无害，见坑 1）。

## 容器/BI 车道的旧结论（仍有效，供参考）

- 基础镜像路线最省事：`mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-a3-…`（CANN/torch/triton 已就位）。
- 只取配对 commit，不 `--depth 1` 拉全历史：`git clone --filter=blob:none --no-checkout` + `git fetch --depth 1 origin <sha>`。
- BI 算子：`bash csrc/build_batch_invariant_ops.sh ascend910_93`（A3；A2 用 `ascend910b`，950 用 `ascend950`），
  它把 OBS 的 `cann-ops-batch_invariant-<soc>-2.0.0-linux.<arch>.run` 装到 `$ASCEND_HOME_PATH/opp/vendors/batch_invariant`，
  再编 `batch_invariant_ops` wheel。自检必须同时为真：
  `torch.ops.batch_invariant_ops.npu_fused_infer_attention_score_batch_invariant.overloads()` 为 `['default','out']`，
  且 `hasattr(batch_invariant_ops, "_npu_fused_infer_attention_score_batch_invariant_get_max_workspace")`。
