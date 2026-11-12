---
name: ascend-torch-npu
description: torch + torch_npu 装/验/排障：A/B 车道、版本配对、验收 True 16 253。适用于"装 torch_npu / NPU 不可用 / pip 卡死 / GLIBCXX 缺失 / 该走哪条车道"。
whenToUse: 要在昇腾机器上装 / 查 / 换 torch 与 torch_npu，判断该走 2.10.0 还是 2.12.0 车道，或 NPU 不可用、pip 卡死要定位时用；CANN 见 `ascend-cann-env`，triton 见 `ascend-triton-ascend`。
---

# 昇腾 torch + torch_npu 检测 / 安装 / 验证 / 排障

**机器（写死）**：默认 `a3` = `root@192.168.13.188`（Debian 10 / 只有 gcc 8.3 / 256 核）；备用 `a3b` = `root@192.168.13.190`。
**CANN（写死）**：9.1.0 = `/home/x00886548/env/cann/cann_9_1_0`；芯片 `Ascend910_9382`；验收期望逐字 **`True 16 253`**（16 die / soc 253 = A3）；本次实测环境 `/home/x00886548/torch_test/envs/torch_latest`（python 3.12.14，2.7G，2026-09-23 装成）。
**边界**：只碰 torch 栈。CANN → `ascend-cann-env`；conda → `ascend-conda-env`；triton-ascend → `ascend-triton-ascend`；vllm 安装 → `vllm-ascend-source-install`；起服务/运行时 → `ascend-vllm-serve`；磁盘选址 → `ascend-server-layout`；从 Windows 驱动远端 → `ascend-env` §5。

## 何时调用

**加载本 skill 当：**

- 要装 / 换 / 查 torch 与 torch_npu，或问「该装哪个版本」。
- `torch.npu.is_available()` 为 `False`、`import torch_npu` 崩、`torch.npu.device_count()` 不是 16。
- `ERROR: No matching distribution found for torch-npu==...` 或 `for torchaudio==2.12.0+cpu`。
- pip 装 torch/torch_npu 长时间零进展（卡死）；import 报 `GLIBCXX_3.4.26 not found`；或不确定该走 2.10.0 还是 2.12.0 车道。

**不要用本 skill（转交）：**
- 问题在 CANN 装 / 换 / 查或环境变量 → 用 `ascend-cann-env`；在 conda 环境或 python 版本 → 用 `ascend-conda-env`。
- 报错落在 triton / triton-ascend → 用 `ascend-triton-ascend`；vllm 与 vllm-ascend 装不上 → 用 `vllm-ascend-source-install`。
- 装好了但服务或推理跑不起来 → 用 `ascend-vllm-serve`；不知道该把文件 / 缓存写到哪个盘 → 用 `ascend-server-layout`。

**前置**：已能 ssh 进 `a3`，且 CANN 已 `source`（`ASCEND_HOME_PATH` 非空）——见本文件「前置检查」。 ／ **后继**：`ascend-triton-ascend` → `vllm-ascend-source-install`。

## 前置检查

```bash
# ① 必须先 source CANN —— 不 source 就去装/测 torch_npu 会找不到 libascend_hal.so / import 失败
export cann_path=/home/x00886548/env/cann/cann_9_1_0
source $cann_path/ascend-toolkit/set_env.sh
source $cann_path/nnal/atb/set_env.sh
echo "$ASCEND_HOME_PATH"   # 期望 /home/x00886548/env/cann/cann_9_1_0/cann-9.1.0
# ② 解释器与已装版本（不激活 conda，直接用绝对路径）
PY=/mnt/share/vllm/conda_envs/xmz_0921/bin/python; $PY -V      # 期望 Python 3.12.14
$PY -m pip list 2>/dev/null | grep -iE 'torch|numpy'           # 看 torch/torch_npu/torchvision/torchaudio/numpy
# ③ 盘：/ 与 /mnt/share 同盘已 96%（剩 139G），大文件只写 /home/vllm（6.9T，剩 1.6T）
df -h / /home/vllm
```
- 缓存必须改道：`export TMPDIR=/home/x00886548/tmp`、`export PIP_CACHE_DIR=/home/x00886548/pip-cache`，别落 `/tmp`。
- 建新环境必须显式带 NJU 镜像（`--override-channels -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c .../pkgs/r`），见 `ascend-conda-env`。

## 步骤

> **下面的示例命令用车道 B（2.12.0）演示**，因为它是本次**真机实测过**的那条；车道 A 与它的差别**仅在版本号字符串**（把 `2.12.0+cpu`→`2.10.0+cpu`、`2.12.0`→`2.10.0.post4`、`torchvision 0.27.0+cpu`→`0.25.0+cpu`、`torchaudio 2.11.0+cpu`→`2.10.0+cpu`），流程完全一致。**要跑 vllm-ascend 就照车道 A 替换版本号**（该替换组合本次未实测，见「未验证」）。

**步骤 1（必须最先做）：先定车道**——车道由**目标机器要不要跑 vllm-ascend** 决定，不是由「哪个版本新」决定。

| | 车道 A（vllm-ascend 场景，**默认**） | 车道 B（全新机器 / 不用 vllm-ascend） |
|---|---|---|
| torch | `2.10.0+cpu` | `2.12.0+cpu` |
| torch_npu | `2.10.0.post4` | `2.12.0` |
| torchvision / torchaudio | `0.25.0` / `2.10.0` | `0.27.0+cpu` / `2.11.0+cpu` |
| triton-ascend | `3.2.2` | `3.2.2` |
| 依据 | `.188` 上 `.../batch_inv_qwen35/vllm-ascend/requirements.txt` 第 16–20 行 + `pyproject.toml` 第 21–23/33 行 pin 原文（被上次构建注释掉，原文保留在注释里）：`torch==2.10.0` / `torch-npu==2.10.0.post4` / `torchvision==0.25.0` / `torchaudio==2.10.0` / `triton-ascend==3.2.2` | 官方 COMPATIBILITY 推荐组合：TorchNPU 2.12.0 + PyTorch 2.12.0 + CANN 9.1.0 + Python 3.10–3.14；**本车道已实测跑通** |

- **只要目标机器要跑 vllm-ascend 就走车道 A**。换车道要同步改 pin **并重编 vllm-ascend 的 AscendC 算子**，不是 pip 一条命令（见 `vllm-ascend-source-install`）。
- 版本事实：`2.10.0.post4` 是 2.10.0 车道上 PyPI 能装到的最新商发版；官方矩阵 26.1.1 行的 `2.10.0.post6` / `2.12.0.post2` / `2.11.0.post2` **在 PyPI 上 404**（实测 `ERROR: No matching distribution found for torch-npu==2.10.0.post6`）。官方原文：「`.postN` 用于区分同一 PyTorch 版本下安装包的后续发布，`N` 为发布序号，**不能直接换算为 TorchNPU 产品版本**」。
- 官方 URL：COMPATIBILITY `https://raw.gitcode.com/ascend/pytorch/raw/master/COMPATIBILITY.en.md`；README `https://gitcode.com/Ascend/pytorch`；商发下载页 `https://www.hiascend.com/developer/software/ai-frameworks/pytorch/download`。

**步骤 2：备好环境变量与新环境**（目的：把缓存挪出满盘的 `/`，拿到 `PY`/`PIP`）
```bash
export TMPDIR=/home/x00886548/torch_test/tmp PIP_CACHE_DIR=/home/x00886548/torch_test/pip-cache
source /home/x00886548/env/conda3/etc/profile.d/conda.sh
ENVP=/home/x00886548/torch_test/envs/torch_latest
conda create -p $ENVP python=3.12 -y --override-channels \
  -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r
PY=$ENVP/bin/python; PIP="$PY -m pip"
```
- 验证：`$PY -V` → `Python 3.12.14`；`du -sh $ENVP` ≈ 235M（`conda create` 刚建好、**还没装 torch 栈**时；装完 torch 栈后同路径 2.7G，见上文「机器（写死）」）。建环境细节见 `ascend-conda-env`。
- 复用现成环境则跳过 `conda create`，只把 `ENVP` 换成目标路径（`.188` 现成：`/mnt/share/vllm/conda_envs/xmz_0921`）。

**步骤 3：装 torch 三件套**（目的：先有 torch——torch_npu 对它是精确等值依赖）
```bash
$PIP install torch==2.12.0+cpu torchvision==0.27.0+cpu torchaudio==2.11.0+cpu \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://mirrors.aliyun.com/pypi/simple/
```
- 车道 A 换成 `torch==2.10.0+cpu torchvision==0.25.0+cpu torchaudio==2.10.0+cpu`。**未验证：** 车道 A 的 pip 序列未在隔离环境重跑（值来自 vllm-ascend pin + 既有 `xmz_0921` 实装）。
- 验证：`$PIP list | grep -i torch` 出现 `torch 2.12.0+cpu`。实测 wheel `torch-2.12.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` 192.3 MB；冷启动 93s，命中缓存 15s。
- **`--extra-index-url` 与 `+cpu` 后缀都不能省**（见坑 1）。

**步骤 4：装 torch_npu**（顺序不能反）
```bash
$PIP install torch-npu==2.12.0 --index-url https://mirrors.aliyun.com/pypi/simple/
```
- 车道 A：`torch-npu==2.10.0.post4`。验证：`pip list` 出现 `torch_npu 2.12.0`；冷启动 1:47（`torch_npu-2.12.0-cp312-cp312-manylinux_2_28_x86_64.whl` 39.5 MB / 383.8 kB/s）。
- 依赖是**精确等值**：`torch_npu 2.12.0 → Requires-Dist: torch==2.12.0`；`torch_npu 2.10.0.post4 → torch==2.10.0+cpu`。版本对不上就 import 崩。

**步骤 5：装 triton-ascend**（会连带把 numpy 拉回 1.26.4）
```bash
$PIP install "triton-ascend==3.2.2" \
  --extra-index-url=https://triton-ascend.osinfra.cn/pypi/simple \
  --index-url https://mirrors.aliyun.com/pypi/simple/
```
- 验证：`pip list | grep -i triton` → `triton 3.2.0` + `triton_ascend 3.2.2`；`numpy` 变 `1.26.4`（**正常**，见坑 4）。
- 耗时：triton-ascend 279.9 MB / 23s；社区 `triton==3.2.0` ~250 MB 走 aliyun ~450 kB/s ≈ 10 min（**整条流程最慢一步**）。细节见 `ascend-triton-ascend`。

**步骤 6：验收**（唯一硬判据）
```bash
$PY -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__, torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"
# 期望逐字：2.12.0+cpu 2.12.0 True 16 253
$PY -c "import torch, torch_npu; x=torch.tensor([1.,2.,3.]).npu(); print((x+x).cpu())"   # 期望 tensor([2., 4., 6.])
```
- 前面可能打 `[ERROR] Failed to load batch_invariant library ... GLIBCXX_3.4.26 not found`——**非致命**，不影响 `True 16 253`（见坑 3）。
- 同次实测附带项：`torch.version.cuda = None`（确认是 CPU 版 torch）、`get_device_name(0) = Ascend910_9382`。
- 完整逐字证据包：`D:\workspace\agent\skill\_recon\torch_stack_verified.md`（§9 是可直接复制的整段序列）。

## 坑与修法

**坑 1｜只给 pytorch 索引会卡在 pillow（6 分钟零进展）**——`$PIP install torch==2.12.0+cpu ... --index-url https://download.pytorch.org/whl/cpu`（不带 extra-index）时，该索引列出 `pillow-12.3.0-*.whl` 但返回 **HTTP 403**（curl 实测 `code=403 size=263`），pip 停在 256KB 不动。→ 必须加 `--extra-index-url https://mirrors.aliyun.com/pypi/simple/`，且 torch 三件套带 `+cpu` 后缀防挑到 CUDA 大包。

**坑 2｜`--index-url https://pypi.org/simple` 装 torch_npu 卡死**——`torch_npu-2.12.0-...whl` 下到 **1.3MB / 39.5MB 后零增长，卡死 4 分 41 秒**；实测 pypi.org 直连 `speed_Bps=12483`（≈12 kB/s）。→ 换 `--index-url https://mirrors.aliyun.com/pypi/simple/`（383.8 kB/s，1:47 下完）；**版本列表与 pypi.org 逐字一致，不是镜像滞后**。torch_npu **官方没有专属 pip 源**，官方命令就是 `pip3 install torch-npu==2.12.0`（默认源）。

**坑 3｜`GLIBCXX_3.4.26 not found`（`.188` 专属，最坑）**——原文 `Error detail: /lib/x86_64-linux-gnu/libstdc++.so.6: version 'GLIBCXX_3.4.26' not found (required by .../libcust_opmaster_rt2.0.so)`，严重时表现为 `RuntimeError: Engine core initialization failed`；另一处是 `[ERROR] Failed to load batch_invariant library ...`（**非致命**，不影响 `True/16/253` 与 kernel `MAX_DIFF=0.0`）。根因：`.188` 是 Debian 10 + gcc 8.3，系统 libstdc++ 只到 `GLIBCXX_3.4.25`，而 CANN 9.1.0 的 tiling 库 `libcust_opmaster_rt2.0.so` 与 batch_invariant vendor 算子都要 3.4.26。修法（用 conda 环境自带的 `libstdcxx 15.2.0`，它提供 `libstdc++.so.6.0.34` = GLIBCXX_3.4.34 做一层兜底）：
```bash
mkdir -p <WORK>/compat_lib && cp -a $CONDA_PREFIX/lib/libstdc++.so.6.0.34 <WORK>/compat_lib/
ln -sf libstdc++.so.6.0.34 <WORK>/compat_lib/libstdc++.so.6
export LD_LIBRARY_PATH=<WORK>/compat_lib:$LD_LIBRARY_PATH
```
**只前置 `compat_lib` 这个只放 libstdc++ 的目录**；绝对不要把整个 `$CONDA_PREFIX/lib` 加进 `LD_LIBRARY_PATH`（会让 git 崩，见 `ascend-conda-env` 坑 5）。

**坑 4｜numpy 被 triton-ascend 从 2.5.3 拉回 1.26.4 → 别手动动它**——`triton_ascend 3.2.2 → Requires-Dist: triton==3.2.0, numpy==1.26.4`。装完 triton-ascend 后 numpy 自动变 `1.26.4`。**顺序必须是 torch → torch_npu → triton-ascend**，别手动降 numpy。

**坑 5｜`torchaudio==2.12.0` 不存在**——原文 `ERROR: No matching distribution found for torchaudio==2.12.0+cpu`（官方停更在 2.11.0）→ 用 `torchaudio==2.11.0+cpu`。torchvision 配套是 **`0.27.0+cpu`**（METADATA 实测 `Requires-Dist: torch (==2.12.0)`，**不是** 0.25.0）。NPU 场景其实不需要 torchaudio。

**坑 6｜`pip check` 噪音可忽略**——`mindstudio-kpp` / `ms-service-profiler` / `affinity-sched` / `schedule-search` 是 CANN `set_env.sh` 经 `PYTHONPATH` 注入的包，不属于本环境；`opencv-python-headless` 要 numpy>=2 与 numpy 1.26.4 冲突是 triton-ascend 锁死导致的固有冲突。**不要为消警告动 numpy/pandas。**

**坑 7｜华为云 `ascend/repos/pypi` 不是 PEP503 index**——`https://mirrors.huaweicloud.com/ascend/repos/pypi` 是**扁平文件目录**（列 wheel 文件名），当 index 用会 `ERROR: No matching distribution found for torch-npu`；要当 index 用请用 `https://mirrors.huaweicloud.com/repository/pypi/simple/`（实测 200 且含 2.12.0）。

**坑 8｜（运维）`kill -9` 只杀 pip 子进程，wrapper 还活着**——外层 `bash /tmp/xx_install.sh` 没死会继续跑 → 同一环境出现**两个并发 pip**。杀后台安装要**连 wrapper 一起杀**（`ps -eo pid,args | grep '[x]x_install.sh'` 找 wrapper PID 一起 kill），或直接 `rm -rf` 环境重建。

## 不要做什么

- 不要跳过 `source` CANN 就去装/测 torch_npu。
- 不要先装 torch_npu 再装 torch；不要装与 torch_npu 主版本不一致的 torch。
- 不要用 `--index-url https://pypi.org/simple` 装 torch_npu（12 kB/s 卡死）；不要省 `--extra-index-url`；不要去掉 torch 三件套的 `+cpu` 后缀。
- 不要手动降/升 numpy，不要为 `pip check` 噪音动 pandas。
- 不要单独 `pip install -U triton`（会覆盖 triton-ascend，见 `ascend-triton-ascend`）。
- 不要给 vllm-ascend 场景换车道（要改 pin + 重编 AscendC 算子，不是 pip 一条命令）。
- 不要把大文件或缓存写进 `/tmp`、`/`、`/mnt/share`（同一块盘，剩 139G）。

## 验收标准

1. `$PY -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__, torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"` → **逐字 `2.12.0+cpu 2.12.0 True 16 253`**（车道 A 则前两段为 `2.10.0+cpu 2.10.0.post4`；**未验证：** 车道 A 未在隔离环境重跑）。
2. `torch.version.cuda is None`（CPU 版 torch 正确）；NPU 张量加法 `(x+x).cpu()` → `tensor([2., 4., 6.])`。
3. `pip list | grep -iE 'torch|triton|numpy'` → `numpy 1.26.4 / torch 2.12.0+cpu / torch_npu 2.12.0 / torchaudio 2.11.0+cpu / torchvision 0.27.0+cpu / triton 3.2.0 / triton_ascend 3.2.2`。
4. `pip check` 只剩坑 6 那类固有冲突与 CANN 注入包噪音，没有 torch 相关新报错；triton 侧验收见 `ascend-triton-ascend`。
