# main + 商发 26.2.0（CANN 9.2.0）在 A5 950DT aarch64 上的构建链

**实测**：2026-11-20，一台 A5（openEuler 24.03 LTS-SP3，aarch64，8×Ascend950DT 96GB，driver `26.2.0.b020`）。
在实际目标核对环境根 `ASCEND_PROJECT_ROOT` 与 FLA wheel 路径 `FLA_NPU_WHEEL`。环境搭建见 [ascend-cann-env](../../ascend-cann-env/SKILL.md)。

## 版本对（实测生效，非推测）

| 组件 | 值 |
|---|---|
| CANN | 9.2.0（toolkit + `Ascend-cann-950-ops` + `nnal`） |
| Python | 3.12.16（conda-forge） |
| torch / torch_npu | 2.10.0+cpu / 2.10.0.post7 |
| triton | 3.6.0，由 dist `triton_ascend 3.6.0+dev20261029222414` 提供 |
| numpy / scipy / transformers | 1.26.4 / 1.13.1 / 5.19.0 |
| vllm-ascend | main `1e0f0da1f740400a1d6796bcc23a13b53ca0b464`（2026-11-20 12:06 +08:00） |
| vLLM | `c410543d9ffff03f5f6c4a8c0ae1d3ad082c4a15`（取自 `.github/vllm-main-verified.commit`） |
| fla_npu | `flash_linear_attention_npu_a5 26.9.1+dev36e67d2`（`py3-none-manylinux_2_34_aarch64` wheel） |
| `SOC_VERSION` | `ascend950dt_9582` |

官方 `quay.io/ascend/vllm-ascend:nightly-main-a5`（2026-11-17）里是 **CANN 9.2.1**，README 也写 `CANN == 9.2.1`；
本机 driver 是 26.2.0.b020，按「商发 26.2.0 配套」用 **CANN 9.2.0** 构建通过并跑通引擎，属对官方认证组合的偏离，需单列。

## 构建顺序（逐条实测通过）

```bash
ROOT="${ASCEND_PROJECT_ROOT:?set the verified project root}"
source $ROOT/env/activate.sh          # CANN + nnal/atb + py312
cd $ROOT/run                          # 中性 cwd，别在 vllm/ 里启动 python
export SOC_VERSION=ascend950dt_9582 MAX_JOBS=32 TMPDIR=$ROOT/tmp PIP_CACHE_DIR=$ROOT/cache/pip PYTHONNOUSERSITE=1
IDX="-i https://repo.huaweicloud.com/repository/pypi/simple --trusted-host repo.huaweicloud.com"
PY=$(command -v python)

# 0) 构建工具（会动 setuptools，必须在装 vLLM 前）
$PY -m pip install $IDX "setuptools==80.10.2" setuptools-scm "setuptools-rust>=1.9.0" wheel pybind11 \
    "cmake>=3.26.1" ninja jinja2 "packaging>=24.2"

# 1) vLLM：剥掉 torch pin，按 empty target 装（不编 CUDA、不拉 torch==2.14.0）
cd $ROOT/src/vllm && $PY tools/use_existing_torch.py --prefix
VLLM_TARGET_DEVICE=empty $PY -m pip install -v -e . --no-build-isolation $IDX
$PY -c "import vllm;print(vllm.__version__)"     # 0.34.0rc1.dev388+gc410543d9.d20261120.empty

# 2) triton 命名空间必须归 triton_ascend（本机 empty 装法实测**没有**拉 pypi triton，只做核对）
$PY -m pip show triton >/dev/null 2>&1 && { $PY -m pip uninstall -y triton; \
   $PY -m pip install --force-reinstall --no-deps \
   $ROOT/env/wheels/triton_ascend-3.6.0+dev20261029222414-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_34_aarch64.whl; }
$PY -c "import triton;print(triton.__version__, triton.__file__)"   # 必须是本环境 site-packages，且 pip show triton 为空

# 3) vllm-ascend 运行时依赖（requirements 去掉 triton-ascend 那一行后必须真装）
cd $ROOT/src/vllm-ascend
grep -vE '^[[:space:]]*triton-ascend' requirements.txt > /tmp/req.local.txt
wc -l /tmp/req.local.txt                       # 38 行；0 行说明你的相对路径错了
$PY -m pip install -r /tmp/req.local.txt $IDX \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi \
    --extra-index-url https://mirrors.huaweicloud.com/ascend/repos/pypi/nightly

# 4) 回钉 numpy / transformers（上一步与 vLLM 会把它们顶高）
$PY -m pip install "numpy==1.26.4" "transformers==5.19.0" $IDX

# 5) fla_npu（aarch64 A5 专用 wheel，requirements 不声明）
$PY -m pip install --no-deps --force-reinstall \
   "${FLA_NPU_WHEEL:?set the verified A5 wheel path}"
$PY -c "from vllm_ascend.ops.gdn import AscendGatedDeltaNetAttention;print('gdn OK')"

# 6) 编 vllm-ascend
cd $ROOT/src/vllm-ascend
rm -rf csrc/build csrc/build_out csrc/build_cache build
SOC_VERSION=ascend950dt_9582 $PY -m pip install -v -e . --no-deps --no-build-isolation
```

`SOC_VERSION` 必须以 `ascend950` 开头：`CMakeLists.txt:61` 的 `MATCHES "ascend310p.*|ascend950"` 因此**跳过
`vllm_ascend_kernels`（AscendC）编译**，但 `csrc/build_aclnn.sh` 的 `^ascend950` 分支仍会用 CANN 的
`tools/ccec_compiler/bin/bisheng` 编 7 个 ACLNN 自定义算子（sparse_flash_attention、add_rms_norm_bias、
moe_gating_top_k_hash …）+ third_party protobuf/abseil，本机 32 并发约 12 分钟。

## 验收判据（贴实测值）

```
vllm          0.34.0rc1.dev388+gc410543d9.d20261120.empty
vllm-ascend   0.19.1rc2.dev3750+g1e0f0da1f
current_platform  NPUPlatform  device_name=npu
vllm_ascend/vllm_ascend_C.cpython-312-aarch64-linux-gnu.so   实际存在并 import 成功
torch.npu.is_available()=True  device_count=8  get_device_name=Ascend950DT_9582
npu matmul(64×64 fp32) 结果正确；vllm CLI `--help` RC=0；`vllm.entrypoints.openai.api_server` import OK
```

引擎级冒烟实测（2026-11-20，`DeepSeek-V2-Lite`，**单卡 TP=1**，`enforce_eager=True`，`gpu_memory_utilization=0.6`）：

```
PROMPT: The capital of France is
OUTPUT: ' Paris.\nThe currency of France is the Euro.\nThe languages spoken in'
E2E_RC=0   TOTAL 191.3s（其中 import vllm ~96s，权重 41GB 走 NFS 加载占大头）
```

三条必须同时满足，否则引擎起不来（都会在 `LLM(...)` 阶段炸，`import vllm_ascend` 不报错）：

1. `export VLLM_WORKER_MULTIPROC_METHOD=spawn` —— 否则
   `RuntimeError: Cannot re-initialize NPU in forked subprocess. To use NPU with multiprocessing, you must use the 'spawn' start method`
2. 用了 `spawn` 就必须给脚本加 `if __name__ == "__main__":` 保护，否则
   `RuntimeError: An attempt has been made to start a new process before the current process has finished its bootstrapping phase.`
3. **多卡（TP≥2）在本机未打通**：`hcclCommInitRootInfoConfig(...) error code is 4 (internal error)` +
   `ERR02200 DIST call hccl api failed`（发生在 `vocab_parallel_embedding` 的 all_reduce）。
   本机其他租户的 8 卡作业正常，说明是 HCCL/通信配置（网卡选择、rootinfo、ranktable）问题而非构建问题；
   单卡 TP=1 可完全绕开。要跑多卡先按本机既有容器/作业的 HCCL 环境变量对齐，别改 vllm-ascend 源码去回避。

## 坑（错误原文 → 修法）

- `python tools/use_existing_torch.py`（**不带** `--prefix`）会把 requirements 里**任何含 torch 的行**都删掉，
  包括带 `--hash=` 的续行；只用 `--prefix` 只剥 `torch=/torchvision=/torchaudio=/torchcodec=` 开头的 pin。
  该脚本本版已从仓库根移到 `tools/`。
- `pip install -r` 指向一个**空文件**时 pip 返回 0 且什么都不装，症状是后面 `import` 缺 xgrammar/quart/numba 等。
  先 `wc -l` 确认行数。
- vLLM 的依赖会把 `numpy` 顶到 2.3.5，而 `triton_ascend` 的 METADATA 要求 `numpy==1.26.4`、`scipy 1.13.1` 要求 `<2.3` →
  必须回钉。`opencv-python-headless 5.1.0.95` 声明 `numpy>=2`，但在 1.26.4 下 `import cv2` 实测正常（属声明性冲突）。
- `pip` 报 `vllm-ascend ... requires triton-ascend===3.6.0.post2, but you have triton-ascend 3.6.0+dev…` —— 预期，
  因为 cp312 的 3.6.x 在任何公网索引都没有，只能用共享盘 wheel，用 `--no-deps --force-reinstall` 装。
- CANN 9.2.0 只有静态 `libtiling_api.a`（`aarch64-linux/lib64/`），没有 `.so`；`CMakeLists` 里
  `target_link_libraries(... tiling_api ...)` 静态链上即可，不必去补 `.so`。
- `$ASCEND_HOME_PATH/lib64` 是**软链**到 `aarch64-linux/lib64`；用 `find` 检查动态库时不加 `-L` 会全部误报 MISSING。
- 引擎启动时若提示 `NPU Triton causal_conv1d_update is unavailable ... falling back to the PyTorch implementation`，
  这是 fla/triton 侧已知降级（不影响 eager 出词），不是构建失败。
- `VLLM_USE_V1` 在本版是未知环境变量（`Unknown vLLM environment variable detected: VLLM_USE_V1`），V1 已是默认，别设。
