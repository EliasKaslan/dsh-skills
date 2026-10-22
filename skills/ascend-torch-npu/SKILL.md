---
name: ascend-torch-npu
description: 昇腾 NPU 上 torch + torch_npu 的检测 / 安装 / 验证 / 排障（默认 a3=192.168.13.188，备用 a3b=.190）——先定车道：A（跑 vllm-ascend，默认）torch 2.10.0+cpu + torch_npu 2.10.0.post4；B（全新机器）torch 2.12.0+cpu + torch_npu 2.12.0；含 pip 序列、验收 True 16 253、torch_npu→torch 等值依赖、pip 卡死与 GLIBCXX_3.4.26 缺失。适用于"装 torch_npu / 该装哪个 torch 版本 / NPU 不可用或 device_count 不对 / torch 卡死零进展 / 报 GLIBCXX_3.4.26 not found / 不确定走 A 还是 B 车道"。不适用：triton 报错 → 用 `ascend-triton-ascend`；vllm 装不上 → 用 `vllm-ascend-source-install`。
whenToUse: 要在昇腾机器上装 / 查 / 换 torch 与 torch_npu，判断该走 2.10.0 还是 2.12.0 车道，或 NPU 不可用、pip 卡死要定位时用；CANN 见 `ascend-cann-env`，triton 见 `ascend-triton-ascend`。模型看不到本节。
---

# 昇腾 torch + torch_npu 检测 / 安装 / 验证 / 排障

**机器（写死）**：默认 `a3` = `root@192.168.13.188`（Debian 10 / 只有 gcc 8.3.0 / 256 核 / 1448 GiB）；备用 `a3b` = `root@192.168.13.190`（**2026-10-22 整机不可达**）；A5 `root@177.8.21.1`（**需连 A5 VPN 后可达**，见 `univpn-vpn`）。三台准入状态见 `ascend-env` §1。
**CANN（写死）**：9.1.0 = `/mnt/share/x00886548/cann/cann_9_1_0`；芯片 `Ascend910_9382`；验收期望逐字 **`True 16 253`**（16 die / soc 253 = A3）。**现成 py3.12 环境（2026-10-22 复核）**：`/home/vllm/x00886548/zero_v0230/envs/vllm312`（3.12.15）等 6 个 + `/mnt/share/vllm/conda_envs/xmz_0921`（3.12.14）——**旧文引用的 `/home/vllm/x00886548/torch_test/envs/torch_latest` 已被删掉，别再用**（完整清单见 `ascend-conda-env`）。
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

**前置**：已能免密 ssh 进 `root@192.168.13.188`，且 CANN 已 `source`（`ASCEND_HOME_PATH` 非空）——见本文件「前置检查」。 ／ **后继**：`ascend-triton-ascend` → `vllm-ascend-source-install`。

## 前置检查

```bash
# ① 必须先 source CANN —— 不 source 就去装/测 torch_npu 会找不到 libascend_hal.so / import 失败
export cann_path=/mnt/share/x00886548/cann/cann_9_1_0
source $cann_path/ascend-toolkit/set_env.sh
source $cann_path/nnal/atb/set_env.sh
echo "$ASCEND_HOME_PATH"   # 期望 /mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0
# ② 解释器与已装版本（不激活 conda，直接用绝对路径）
PY=/mnt/share/vllm/conda_envs/xmz_0921/bin/python; $PY -V      # 期望 Python 3.12.14
$PY -m pip list 2>/dev/null | grep -iE 'torch|numpy'           # 看 torch/torch_npu/torchvision/torchaudio/numpy
# ③ 盘：/ 与 /mnt/share 同盘（系统盘，长期紧张）——大文件只写 /home/vllm；具体余量自己 df -h 取
df -h / /home/vllm
```
- 缓存必须改道：`export TMPDIR=/home/vllm/<user>/tmp`、`export PIP_CACHE_DIR=/home/vllm/<user>/pip-cache`，别落 `/tmp`。
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

**版本纪律（2026-10-08 用户定，优先于本节其它说法）**：

- **版本只以 `vllm-ascend` 仓的 `requirements.txt` 为参考**——`.188` 现成 checkout（`/mnt/share/x00886548/workspace/batch_inv_qwen35/vllm-ascend/requirements.txt`）里 torch / torch-npu / torchvision / torchaudio / triton-ascend 这几行**已被注释掉**，**pin 原文就保留在注释里**（形如 `# torch==2.10.0  # pin removed -> reuse the torch stack installed in this env`），直接读注释即得版本，不用另找依据。
- **`vllm` 仓的 `requirements.txt` 不用参考**（它的 pin 与本流程无关，读了只会把自己绕进去）。
- **依赖冲突不用管**：`pip check` 的 numpy / fastapi / starlette / opencv 之类互斥、CANN `set_env.sh` 经 `PYTHONPATH` 注入的包噪音，**一律不当失败**。判据只有步骤 5 的 `True 16 253`。
- 因此**不要把时间花在"对齐版本"上**：装得上、`import` 得动、NPU 可用即通过；真遇到版本冲突导致 import 崩，先按坑 2 换源重试，别去逐个升降包。

**步骤 2：备好环境变量与新环境**（目的：把缓存挪出满盘的 `/`，拿到 `PY`/`PIP`）
```bash
ROOT=/home/vllm/x00886548/envbuild
export TMPDIR=$ROOT/tmp PIP_CACHE_DIR=$ROOT/pip-cache        # 缓存别落 /tmp
source /mnt/share/x00886548/miniconda3/etc/profile.d/conda.sh
ENVP=$ROOT/envs/vllm312                    # ★ 与步骤 4、与 `ascend-env` §3.1 的 P2 落点是**同一个** env
export CONDA_PKGS_DIRS=$ROOT/conda_pkgs    # conda 包缓存也别落系统盘（详见 `ascend-conda-env` 步骤 4）
MIRROR="--override-channels -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r"
conda create -p "$ENVP" python=3.12 -y $MIRROR
PY=$ENVP/bin/python; PIP="$PY -m pip"
```
- 验证：`$PY -V` → `Python 3.12.14`；`du -sh $ENVP` ≈ 235M（`conda create` 刚建好、**还没装 torch 栈**时；装完 torch 栈后同路径 2.7G，见上文「机器（写死）」）。建环境细节见 `ascend-conda-env`。
- 复用现成环境则跳过 `conda create`，只把 `ENVP` 换成目标路径（`.188` 现成：`/mnt/share/vllm/conda_envs/xmz_0921`）。

**步骤 3：把整个 torch 栈**预下载**到本地 wheelhouse**（＝ `ascend-env` §3.1 的 **lane P3**，可完全并行）

目的：把"下载"整段从串行路径上摘掉。**用一个 py3.12 解释器**即可（`.188` 现成的 `xmz_0921` 就是），**不需要目标 env 存在** → 因此它与 conda 建环境（P2）也没有依赖关系。

```bash
ROOT=/home/vllm/x00886548/envbuild
WH=$ROOT/wheelhouse; mkdir -p "$WH/log"
DL=/mnt/share/vllm/conda_envs/xmz_0921/bin/python    # 只要与目标 env 同为 py3.12 即可，不是目标 env
# 约束文件由 `ascend-env` §3.1 落点块**统一创建**（唯一写者；换车道改那里一行，如 2.10.0+cpu）。
# 这里只读校验：两组各自 echo > 同一文件的话，极端时序下可能被 pip 读到截断的空文件 → 约束静默失效。
[ -s "$WH/constraints.txt" ] || { echo "缺少 $WH/constraints.txt：先按 ascend-env §3.1 落点块创建（echo 'torch==2.12.0+cpu' > \$WH/constraints.txt）" >&2; exit 1; }
# torch 三件套 + torch_npu 合为一条命令：一次依赖解析，torch 本体只有一个下载者
( $DL -m pip download -d "$WH" -c "$WH/constraints.txt" \
    torch==2.12.0+cpu torchvision==0.27.0+cpu torchaudio==2.11.0+cpu torch-npu==2.12.0 \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/ > "$WH/log/torch_stack.log" 2>&1 ) &
wait
ls "$WH" | grep -E '^(torch|torch_npu|torchvision|torchaudio)-'
```

- **为什么合成一条命令（2026-10-08 修，原写法有坑）**：`torch_npu 2.12.0` 的依赖里有 `torch==2.12.0`（精确等值，见步骤 4）。若把 torch_npu 单独发一组**且不带 `--no-deps`**，pip 会按 `--index-url` 去解析这个 `torch==2.12.0`——**从 PyPI 镜像下来的是 CUDA 版 `torch-2.12.0`（GB 级），不是 `+cpu` 版**，既违背坑 1 的 `+cpu` 纪律又白费带宽；**改带 `--no-deps` 又会漏掉 torch_npu 的其余依赖**。**合成一条命令 + `-c` 约束**同时解决两者。
- **约束为什么有效（2026-10-08 在 `.188` 实测，不是推断）**：
  - `packaging` 判定：`==2.12.0+cpu` 匹配 `2.12.0` → **False**；匹配 `2.12.0+cpu` → **True**；而 torch_npu 要求的 `==2.12.0` 匹配 `2.12.0+cpu` → **True**。→ 约束**既能排除**无 local label 的 CUDA 版，**又不与** torch_npu 的等值依赖冲突（这正是"合成一条命令"能成立的前提）。
  - 索引侧：`pip index versions torch --index-url https://download.pytorch.org/whl/cpu` 列的**全是 `+cpu` 形态**（`2.14.1+cpu … 2.12.0+cpu … 2.2.0+cpu`）；`--index-url https://mirrors.aliyun.com/pypi/simple/` 列的**全是无 local label 形态**（`2.14.1 … 2.12.0 …`）。两个源不可能混淆。
- torch_npu **不在 whl/cpu 源上**，只在 aliyun 镜像上（坑 2），所以 `--extra-index-url` 指 aliyun 不能省。
- **triton-ascend 那一组不在本文里下**——它归 `ascend-triton-ascend` 步骤 ⓪ 管，往**同一个** `$WH` 下并复用同一份 `constraints.txt`。**别两边都下同一个包**：两个 `pip` 并发写同一个 wheelhouse 里的同名 wheel，轻则白费一次带宽，重则互相覆盖。这条 lane 因此是 **1+1 两组**（本文一组 + triton 一组）。
- 车道 A 只换版本号（见步骤 1 的表），`constraints.txt` 同步改成 `torch==2.10.0+cpu`。**未验证**：车道 A 的 pip 序列（2.10.0+cpu / 2.10.0.post4 / 0.25.0 / 2.10.0）未在隔离环境重跑过（值来自 vllm-ascend 注释里的 pin + 既有 `xmz_0921` 实装）。
- **判完成看 wheelhouse 里的 whl 名，不看进程**。
- **这条命令不要加 `--no-deps`**：这里的目标是让 wheelhouse 自带整棵依赖树，步骤 4 才能真离线装。实测（`--no-index` + 缺包）会直接 `No matching distribution found`，说明离线装不会偷偷回源。
- `--extra-index-url` 与 `+cpu` 后缀都不能省（坑 1）；torch_npu 换 pypi.org 会 12 kB/s 卡死（坑 2）。
- 实测 wheel 体积：`torch-2.12.0+cpu-cp312-cp312-manylinux_2_28_x86_64.whl` 192.3 MB；`torch_npu-2.12.0-...whl` 39.5 MB。**若 wheelhouse 里出现 `torch-2.12.0-cp312-...whl`（不带 `+cpu`、体积 GB 级）就是约束没生效**，删掉它并检查 `-c "$WH/constraints.txt"` 是否真加上。
- **未验证**：本条"拉全依赖树 + 之后离线装"的往返只在 `six` 这种纯 py wheel 上实测过（`pip download -d` → `pip install --no-index --find-links` 通过）；torch 全家未试。若步骤 4 报缺包，**去掉 `--no-index --find-links` 改在线装同样三条命令即可**，版本别改。
- **未验证**：本组与 `ascend-triton-ascend` 步骤 ⓪ 的 triton 组**并发写同一个 `$WH` 与同一个 pip 缓存**。实测只验过单组下载；若日志出现缓存争用告警，给其中一组单独设 `PIP_CACHE_DIR`，或把 triton 组挪到 `wait` 之后串行下。
- **未验证**：目标 env 不是 py3.12 时需加 `--python-version/--abi/--platform/--only-binary=:all:` 才能跨版本下（这些开关实测被 pip 接受，但只用纯 py wheel 验过）。

**步骤 4：离线安装 torch 栈**（＝ 串行段 **S2**，三步顺序**不可换、不可并行**）

```bash
ENVP=/home/vllm/x00886548/envbuild/envs/vllm312
PY=$ENVP/bin/python; PIP="$PY -m pip"; WH=/home/vllm/x00886548/envbuild/wheelhouse
$PIP install --no-index --find-links "$WH" torch==2.12.0+cpu torchvision==0.27.0+cpu torchaudio==2.11.0+cpu
$PIP install --no-index --find-links "$WH" torch-npu==2.12.0
$PIP install --no-index --find-links "$WH" "triton-ascend==3.2.2"
```

- **为什么必须串行**：`torch_npu` 对 torch 是**精确等值依赖**（`torch_npu 2.12.0 → Requires-Dist: torch==2.12.0`；`torch_npu 2.10.0.post4 → torch==2.10.0+cpu`，对不上 import 就崩）；`triton-ascend` 会**覆盖** triton 并锁 `numpy==1.26.4`。预下载只省下载时间，**不改变安装顺序**。车道 A 换成对应版本号。
- 验证：`$PIP list | grep -i torch` → `torch 2.12.0+cpu`、`torch_npu 2.12.0`；`$PIP list | grep -i triton` → `triton 3.2.0` + `triton_ascend 3.2.2`，`numpy` 变 `1.26.4`（**正常**，坑 4）。
- 实测耗时（在线装、冷启动）：torch 三件套 93s（命中缓存 15s）、torch_npu 1:47、triton-ascend 279.9 MB/23s + 社区 `triton==3.2.0` 约 250 MB 走 aliyun ~450 kB/s ≈ **10 min（整条流程最慢的一步）**。离线装省掉的正是这一段。细节见 `ascend-triton-ascend`。

**步骤 5：验收**（唯一硬判据）
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
WORK=/home/vllm/x00886548/envbuild          # ← 换成你自己的目录（别写 <WORK> 这类尖括号，bash 会当重定向）
mkdir -p $WORK/compat_lib && cp -a $CONDA_PREFIX/lib/libstdc++.so.6.0.34 $WORK/compat_lib/
ln -sf libstdc++.so.6.0.34 $WORK/compat_lib/libstdc++.so.6
export LD_LIBRARY_PATH=$WORK/compat_lib:$LD_LIBRARY_PATH
```
**只前置 `compat_lib` 这个只放 libstdc++ 的目录**；绝对不要把整个 `$CONDA_PREFIX/lib` 加进 `LD_LIBRARY_PATH`（会让 git 崩，见 `ascend-conda-env` 坑 5）。

**坑 4｜numpy 被 triton-ascend 从 2.5.3 拉回 1.26.4 → 别手动动它**——`triton_ascend 3.2.2 → Requires-Dist: triton==3.2.0, numpy==1.26.4`。装完 triton-ascend 后 numpy 自动变 `1.26.4`。**顺序必须是 torch → torch_npu → triton-ascend**，别手动降 numpy。
> **2026-10-08 起**：numpy 与 vllm 侧要求的冲突**不用管**（用户定的纪律，见「版本纪律」）。只有后面装 vllm 时它真把 numpy 静默升到 2.x、导致 triton-ascend 报错，才回退一次；那时用 `pip install --no-deps numpy==1.26.4`（细则见 `vllm-ascend-source-install` 坑 4）。**为这个冲突停工、逐个试版本是不允许的。**

**坑 5｜`torchaudio==2.12.0` 不存在**——原文 `ERROR: No matching distribution found for torchaudio==2.12.0+cpu`（官方停更在 2.11.0）→ 用 `torchaudio==2.11.0+cpu`。torchvision 配套是 **`0.27.0+cpu`**（METADATA 实测 `Requires-Dist: torch (==2.12.0)`，**不是** 0.25.0）。NPU 场景其实不需要 torchaudio。

**坑 6｜`pip check` 噪音可忽略**——`mindstudio-kpp` / `ms-service-profiler` / `affinity-sched` / `schedule-search` 是 CANN `set_env.sh` 经 `PYTHONPATH` 注入的包，不属于本环境；`opencv-python-headless` 要 numpy>=2 与 numpy 1.26.4 冲突是 triton-ascend 锁死导致的固有冲突。**不要为消警告动 numpy/pandas。**

**坑 7｜华为云 `ascend/repos/pypi` 不是 PEP503 index**——`https://mirrors.huaweicloud.com/ascend/repos/pypi` 是**扁平文件目录**（列 wheel 文件名），当 index 用会 `ERROR: No matching distribution found for torch-npu`；要当 index 用请用 `https://mirrors.huaweicloud.com/repository/pypi/simple/`（实测 200 且含 2.12.0）。

**坑 8｜（运维）`kill -9` 只杀 pip 子进程，wrapper 还活着**——外层 `bash /tmp/xx_install.sh` 没死会继续跑 → 同一环境出现**两个并发 pip**。杀后台安装要**连 wrapper 一起杀**（`ps -eo pid,args | grep '[x]x_install.sh'` 找 wrapper PID 一起 kill），或直接 `rm -rf` 环境重建。

**坑 9｜`import torch_npu` 缺一个未声明的依赖 `pyyaml`，但报的是"backend extension"**（2026-10-08 实测）：表面报错逐字为 `RuntimeError: Failed to load the backend extension: torch_npu. You can disable extension auto-loading with TORCH_DEVICE_BACKEND_AUTOLOAD=0.`，**真因**是 `ModuleNotFoundError: No module named 'yaml'`（来自 `torch_npu/npu/_memory_viz.py`）⇒ `pip install pyyaml` 即可，**不要去重装 torch_npu**。

**坑 10｜`ImportError: libhccl.so` = CANN 的 `set_env.sh` 没 source，不是装坏了**：`libhccl.so` 由 CANN 提供，先 `set +u` 再 `source <p>/cann/set_env.sh`（与 `nnal/atb/set_env.sh`）后重试；对照「前置检查」的 `ASCEND_HOME_PATH` 非空。**不要为此重装 torch / torch_npu。**
**别 source `nnal/asdsip/set_env.sh`**：它会把自身 lib 目录插到 `LD_LIBRARY_PATH` 最前，导致 `libtbe_adapter.so: undefined symbol: _ZN3Mki15PlatformManager8InstanceEv`，并挤掉 `compat_lib` ⇒ 只需 toolkit + `nnal/atb` 两段；详见 `ascend-cann-env`。

> **同一句 `Failed to load the backend extension: torch_npu` 有两个完全不同的原因**（D1 缺 `pyyaml` / D2 没 source CANN）⇒ 排障**分开走**，不要只认一种：先看有没有 `No module named 'yaml'` 的 traceback（**所以别丢 stderr**，见 `ascend-env` §5），没有再去核 `ASCEND_HOME_PATH` 与 `libhccl.so` 的 `ldd` 结果。

## 不要做什么

- 不要跳过 `source` CANN 就去装/测 torch_npu。
- **不要因为 `Failed to load the backend extension: torch_npu` 就重装 torch_npu**：先分两条路查（坑 9 缺 `pyyaml` / 坑 10 没 source CANN）。**别丢 stderr**——`No module named 'yaml'` 那行 traceback 是唯一能一眼定位真因的东西（见 `ascend-env` §5）。
- **不要先装 torch_npu 再装 torch**；不要装与 torch_npu 主版本不一致的 torch。
- **不要为了"对齐版本"或消依赖冲突而停工**：不读 vllm 仓的 requirements、不逐个升降包、不为 `pip check` 报错反复重装（见「版本纪律」）。
- 不要在步骤 3（下载 lane）里做安装动作，也不要在步骤 4（串行安装）里再夹下载；下载 lane **不碰目标 env**。
- 不要用 `--index-url https://pypi.org/simple` 装 torch_npu（12 kB/s 卡死）；不要省 `--extra-index-url`；不要去掉 torch 三件套的 `+cpu` 后缀。
- 不要手动降/升 numpy，不要为 `pip check` 噪音动 pandas。
- 不要单独 `pip install -U triton`（会覆盖 triton-ascend，见 `ascend-triton-ascend`）。
- 不要给 vllm-ascend 场景换车道（要改 pin + 重编 AscendC 算子，不是 pip 一条命令）。
- 不要把大文件或缓存写进 `/tmp`、`/`、`/mnt/share`（同一块系统盘，长期紧张，余量现场 `df -h` 看）；wheelhouse 一律落 `/home/vllm`。

## 验收标准

1. `$PY -c "import torch, torch_npu; print(torch.__version__, torch_npu.__version__, torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"` → **逐字 `2.12.0+cpu 2.12.0 True 16 253`**（车道 A 则前两段为 `2.10.0+cpu 2.10.0.post4`；**未验证：** 车道 A 未在隔离环境重跑）。
2. `torch.version.cuda is None`（CPU 版 torch 正确）；NPU 张量加法 `(x+x).cpu()` → `tensor([2., 4., 6.])`。
3. `pip list | grep -iE 'torch|triton|numpy'` → `numpy 1.26.4 / torch 2.12.0+cpu / torch_npu 2.12.0 / torchaudio 2.11.0+cpu / torchvision 0.27.0+cpu / triton 3.2.0 / triton_ascend 3.2.2`。
4. `pip check` 只剩坑 6 那类固有冲突与 CANN 注入包噪音，没有 torch 相关新报错；triton 侧验收见 `ascend-triton-ascend`。
   > **2026-10-08 起这条不算验收项**：冲突不用管（见「版本纪律」）。真正的硬判据只有第 1 条。
5. **并行编排对齐**：`ascend-env` §3.1 的 lane P3 = 本文步骤 3，串行段 S2 = 本文步骤 4；lane 完成判据是 wheelhouse 里 whl 名齐全，**不看进程**。
