# 在 A5/aarch64 个人目录里装「商发 26.2.0 配套」栈（实测）

2026-11-20 于一台 A5（openEuler 24.03 LTS-SP3，aarch64，384 核，8×Ascend950DT 96GB，
driver `26.2.0.b020`，`/usr/local/Ascend` 下**只有 driver/firmware、没有 toolkit**）。
在当前目标机选择并核对自己的可写项目目录和安装包目录。下列命令中的 `ASCEND_PROJECT_ROOT` 和 `CANN_PACKAGE_DIR` 分别取这两个目录。

## 0. 先确认目标是什么

商发 26.2.0 配套（依据官方 950 底座镜像名
`swr.cn-south-1.myhuaweicloud.com/ascendhub/mindspeed-ops:26.2.0-cann9.2.0-torch_npu2.10.0.post7-950-openeuler24.03-py3.12`）：

| 组件 | 版本 |
|---|---|
| CANN | 9.2.0（toolkit + `Ascend-cann-950-ops` + `nnal`） |
| Python | 3.12 |
| torch | 2.10.0+cpu |
| torch_npu | 2.10.0.post7 |
| triton | 3.6.0（由 triton_ascend 提供） |
| numpy | 1.26.4 |

**不要**用 vllm-ascend main 的 README（写 `CANN == 9.2.1`）去覆盖用户指定的「26.2.0 配套」；
两者不一致时按用户指定装，并把偏离写进交付。

## 1. CANN 9.2.0（离线，run 包在共享盘）

```bash
R="${ASCEND_PROJECT_ROOT:?set the verified project root}"
P="${CANN_PACKAGE_DIR:?set the verified package directory}"
cp -a /etc/Ascend/ascend_cann_install.info /root/backup_cann_install.info 2>/dev/null   # 安装器会改写它

bash $P/Ascend-cann-toolkit_9.2.0_linux-aarch64.run  --install --quiet --install-path=$R/env/cann-9.2.0
bash $P/Ascend-cann-950-ops_9.2.0_linux-aarch64.run  --install --quiet --install-path=$R/env/cann-9.2.0
bash $P/Ascend-cann-nnal_9.2.0_linux-aarch64.run      --install --quiet --install-path=$R/env/cann-9.2.0
```

- 装完结构：`$R/env/cann-9.2.0/{cann-9.2.0, ascend-toolkit/latest -> …/cann-9.2.0, nnal/atb}`，
  `source $R/env/cann-9.2.0/cann/set_env.sh` 会把 `ASCEND_HOME_PATH` 指到 `…/cann-9.2.0`（vllm-ascend 的 `setup.py`
  就是靠这个环境变量找 CANN，不必造 `/usr/local/Ascend/ascend-toolkit/latest`）。
- **NFS 上的无害噪声**：`lsattr: Operation not supported While reading flags on …/cann_uninstall.sh`、
  `rm: cannot remove '…/share/info/opbase/script': Directory not empty`；子包仍报 `install success`，照常可用。
- 950 算子的真实落点：`opp/built-in/op_impl/ai_core/tbe/kernel/ascend950/`（本机 7.2G / 10747 个 .o）；
  `opp/built-in/data/op/Ascend950PR_*/unified_bank` 只有元数据。**`opp/vendors/` 是空的**——
  不要用「vendors 里有没有东西」判断 950-ops 装没装。
- `lib64` 是软链到 `aarch64-linux/lib64`；检查动态库要 `find -L`，否则全误报 MISSING。
  9.2.0 只提供静态 `libtiling_api.a`（无 `.so`），`target_link_libraries(... tiling_api)` 静态链即可。

## 2. 独立 Python 3.12

```bash
/root/miniconda3/bin/conda create -p $R/env/py312 python=3.12 -y --override-channels -c conda-forge
$R/env/py312/bin/python -V          # 3.12.16
```

用 `-p` 建在共享盘上而不是 `python -m venv`，是为了不依赖 `/root/miniconda3` 将来被清理。

## 3. torch 栈（唯一慢的一步，先把带宽问题解决）

```bash
IDX="-i https://repo.huaweicloud.com/repository/pypi/simple --trusted-host repo.huaweicloud.com"
PY=$R/env/py312/bin/python
# 大包直接 curl 本地轮子再装，比 pip 走慢镜像稳（本机 146MB / 20s）
curl -L -C - -o /tmp/wheels/torch.whl <torch-2.10.0-cp312-cp312-manylinux_2_28_aarch64.whl 的直链>
$PY -m pip install $IDX /tmp/wheels/torch.whl "torch_npu==2.10.0.post7" "numpy==1.26.4"
```

- `torch-npu` 在 pypi 上按 dist 名 `torch_npu` 取；本机实测 `2.10.0.post7` 有 cp312 aarch64 轮子。
- `triton-ascend` **公网没有 cp312 的 3.6.x**（pypi 只有 3.2.0 且 cp39/310/311）→ 用共享盘预编译 wheel，
  A5 历史实测使用了适配 b020 的预编译 cp312/aarch64 wheel，请从当前获准的制品目录定位。
  （331576350 B，sha256 `f49ed70ce966da1d0170179d231044297edf7eb1c26fa5fd8b63772a18aa696b`；也曾有 b030 制品，**按当前 driver 代次选**）。
  `pip install --force-reinstall --no-deps <whl>`，装完 `python -c "import triton;print(triton.__version__,triton.__file__)"`
  必须指向本环境 site-packages 且 `dist 'triton'` 为 `PackageNotFoundError`。

## 4. activate.sh（多 agent 复用的入口）

```bash
#!/bin/bash
# 商发 26.2.0 配套：CANN 9.2.0 + torch 2.10.0 + torch_npu 2.10.0.post7 + triton-ascend 3.6.0
R="${ASCEND_PROJECT_ROOT:?set the verified project root}"
_saved_opts=$-           # 调用方可能开了 set -u
set +u                   # nnal/atb/set_env.sh 会引用未定义的 ZSH_VERSION
source $R/env/cann-9.2.0/cann/set_env.sh
[ -f $R/env/cann-9.2.0/nnal/atb/set_env.sh ] && source $R/env/cann-9.2.0/nnal/atb/set_env.sh
case "$_saved_opts" in *u*) set -u ;; esac
export PATH=$R/env/py312/bin:$PATH
export PYTHONNOUSERSITE=1
export TMPDIR=$R/tmp PIP_CACHE_DIR=$R/cache/pip
```

## 5. 验收（每条都必须是真输出）

```bash
source $R/env/activate.sh && cd $R/run        # 中性目录
python - <<'PY'
import torch, torch_npu
print(torch.npu.is_available(), torch.npu.device_count(), torch_npu.npu.get_device_name())
a = torch.arange(64, dtype=torch.float32, device="npu:0").reshape(8,8)
print((a @ a).sum().item())
PY
```

本机实测：`True 8 Ascend950DT_9582`，matmul sum `529536.0`；
`torch_npu.npu.get_device_properties(0)` → total_memory 93952MB / cube 32 / vector 64；
`import acl` OK（`acl.rt.get_device_count()` → 8）。**`import aclnn` 不存在**：aclnn 在 9.2.0 是对外 C 库
`libopapi*.so`（在 `aarch64-linux/lib64`），没有 Python 模块。

## 6. 复用注意

- 不要把 `numpy` 升到 2.x：`triton_ascend` METADATA 钉 `==1.26.4`，`scipy 1.13.1` 要求 `<2.3`。
  装 vLLM 等上层后会把它顶高，装完必须回钉并重验 `import triton` + 真机张量。
- 多个 agent 共用同一 venv 时，**同一时刻只允许一个 pip**；先 `ps -eo args | grep 'pip install'` 确认。
