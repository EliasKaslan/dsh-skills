# 在 A3 x86_64 个人目录里装「商发 26.2.0 配套」栈（两台实测）

2026-11-23，`192.168.13.190`（openEuler 22.03 SP4，64 核，glibc 2.34，gcc 10.3.1，`/home` 2.8T 空闲）
与 `192.168.13.188`（Debian 10，256 核，glibc **2.28**，gcc **8.3.0**，`/` 只剩 18G、`/home/vllm` 436G）。

商发 26.2.0 配套：**CANN 9.2.0 + torch 2.10.0+cpu + torch_npu 2.10.0.post7 + triton-ascend 3.6.0 + Python 3.12 + numpy 1.26.4 + scipy 1.13.1**。

## 0. 先看清这台机器给了什么，别急着重装

- **CANN 往往已经有**：190 在 `/mnt/share/cann/cann-9.2.0`（NFS，直接复用，含 `opp/.../kernel/ascend910_93`）；
  188 在 `/home/vllm/x00886548/mrv2_k3/cann_9_2_0`（11G，真 9.2.0，可软链复用）。
  判定顺序：`readlink -f` → `cat <cann>/version.cfg` → `ls opp/built-in/op_impl/ai_core/tbe/kernel/ascend910*` →
  `ls nnal/atb/set_env.sh`。三样齐全就是能用的安装树，不必重装。
- **前人环境可能只能部分复用**：188 的 `mrv2_k3/envs` 是 post4 / triton 3.2 / vllm 0.31，与 26.2.0 配套不符 →
  另建 py312，**不要动旧环境**。
- **系统工具链普遍太旧**：190 无 `cmake`、188 是 `cmake 3.13.4`（都 < 3.26）→ 用 pip 的 `cmake` 装进 venv。
- 磁盘：188 的 `/` 已 100% → `TMPDIR`/`PIP_CACHE_DIR`/源码/venv 全部落 `/home` 下。

## 1. Python 3.12

```bash
R=/home/x00886548/ascend-26.2.0          # 188：/home/vllm/x00886548/ascend-26.2.0
conda create -p $R/env/py312 python=3.12 -y --override-channels -c conda-forge
```
conda 卡在 `Downloading and Extracting Packages: ...working...`（`conda.anaconda.org` 超时、CPU 时间只有 2s）时，
加 `--offline` 用共享盘 pkgs 缓存即可。

## 2. torch 栈（两个必踩点）

```bash
IDX="-i https://repo.huaweicloud.com/repository/pypi/simple --trusted-host repo.huaweicloud.com"
PY=$R/env/py312/bin/python
# a) torch 必须是 CPU 轮子：华为云 pypi 的 torch 是 CUDA 版，会让后装的 torch_npu 报
#    ERROR: Cannot install torch-npu==2.10.0.post7 and torch==2.10.0 ... (torch-npu depends on torch==2.10.0+cpu)
$PY -m pip install "https://download.pytorch.org/whl/cpu/torch-2.10.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl"
# b) 再装 torch_npu 与钉住的 numpy/scipy
$PY -m pip install $IDX "torch_npu==2.10.0.post7" "numpy==1.26.4" "scipy==1.13.1"
```

- glibc 2.28（Debian 10）只能吃 `manylinux_2_17`/`manylinux_2_28` 的轮子，**`manylinux_2_34` 一律装不上**。
- `triton-ascend`：公网 pypi 只有 3.2.0 且无 cp312 → 从官方 a3 镜像取（`docker run --rm --network none ...`
  或 `docker cp`）。x86_64 上能拿到 **`triton_ascend 3.6.0.post2`**（正是 requirements 的 pin）。
  `pip install --no-deps <whl|目录>`，装完 `pip show triton` 必须为空、`import triton` 指向本环境。
- `fla_npu`：镜像里是 `flash_linear_attention_npu_a3 26.10.0+feature`。**Debian 10 上不能用它的 openeuler 版**（见坑）。

## 3. libstdc++ 兼容层（gcc 10.3 / Debian 10 必做）

```
Failed to dlopen .../fla_npu/.../libcust_opapi.so! /usr/lib64/libstdc++.so.6: version 'GLIBCXX_3.4.29' not found
→ [Init][Geexecutor]init ge executor failed, ge errorCode=1343225857
→ RuntimeError: ... aclInit, error code is 1343225857
```
系统 libstdc++ 只到 `GLIBCXX_3.4.28`。修法：把 venv 里 glibcxx 更新的一份（190 上是 6.0.34）链成
`$R/env/compat_lib/libstdc++.so.6`，并在 `activate.sh` 里**前置**到 `LD_LIBRARY_PATH`。

## 4. activate.sh（照抄，逐行都有用）

```bash
#!/bin/bash
R=/home/x00886548/ascend-26.2.0
_saved=$-
set +u                                   # CANN/nnal 脚本会引用未定义变量
source $R/env/cann-9.2.0/cann/set_env.sh
[ -f $R/env/cann-9.2.0/nnal/atb/set_env.sh ] && source $R/env/cann-9.2.0/nnal/atb/set_env.sh
case "$_saved" in *u*) set -u ;; esac
export PATH=$R/env/py312/bin:$PATH
export LD_LIBRARY_PATH=$R/env/compat_lib:${LD_LIBRARY_PATH:-}   # 需 GLIBCXX_3.4.29 时才要
export PYTHONNOUSERSITE=1
export TMPDIR=$R/tmp PIP_CACHE_DIR=$R/cache/pip
export SOC_VERSION=ascend910_9391        # 构建用；A3 设备自报 Ascend910_9382，同分支
export MAX_JOBS=32
export VLLM_WORKER_MULTIPROC_METHOD=spawn
```

## 5. 验收

```bash
source $R/env/activate.sh && cd $R/run
python - <<'PY'
import torch, torch_npu
print(torch.npu.is_available(), torch.npu.device_count(), torch_npu.npu.get_device_name())
a = torch.arange(64, dtype=torch.float32, device="npu:0").reshape(8,8)
print((a @ a).sum().item())
PY
```
190 实测：`True 16 Ascend910_9382`、matmul sum `529536.0`、`acl.rt.get_device_count() -> (16, 0)`。
A3 一卡两 die，`ASCEND_RT_VISIBLE_DEVICES` 按 **die 编号**（0..15）给。

## 6. 坑补充

- **`fla_npu` 的 openeuler 构建在 Debian 10 上要 `GLIBC_2.32`**（`version 'GLIBC_2.32' not found`，
  `objdump -T` 可查）→ 换 `manylinux_2_17` 的 wheel（只需 `GLIBC_2.14`），vllm-ascend 要的 5 个符号都在。
- **`numpy` 会被反复顶到 2.x**：`compressed_tensors`、`opencv>=5` 都会拉 numpy 2.5.5 →
  这些包一律 `--no-deps` 装，opencv 要 `<5`，最后 `--no-deps --force-reinstall numpy==1.26.4`。
- **`llguidance` 只有 sdist 且要 maturin**（`BackendUnavailable: Cannot import 'maturin'`）→ 用缓存里的
  `llguidance-1.7.6-cp39-abi3*.whl`。
- **单 die 可用显存小于名义值**（190 实测只剩 47.69/61.27 GiB）→ 引擎冒烟用 `gpu_memory_utilization=0.72`。
- 同一 venv 一次只允许一个 pip；`pkill -f <串>` 会把当前 ssh 会话自己杀掉（用 PID 或 `[a]3_` 写法）。
