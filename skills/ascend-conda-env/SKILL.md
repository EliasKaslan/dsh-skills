---
name: ascend-conda-env
description: 昇腾 conda 环境：共享 miniconda3、环境目录、NJU 镜像、免激活调用。适用于"建 conda 环境 / 换 python 版本 / 环境该放哪 / conda 官方源太慢 / python -V 不对"。
whenToUse: 需要 conda 本体（建/激活环境、装 conda 包、改 .condarc）或要确定 python 解释器绝对路径、判断环境放哪个盘时。CANN 见 ascend-cann-env，torch 见 ascend-torch-npu。
---

# 昇腾服务器 conda 环境（检测 / 新建 / 激活）

机器：默认 `ssh a3` = root@192.168.13.188（Debian 10 / glibc 2.28），备用 `ssh a3b` = root@192.168.13.190（openEuler 22.03）。**所有环境只建 `/home/x00886548/env/`**（结构见 `ascend-server-layout`）。远端驱动规则见 `ascend-env` §5；CANN 见 `ascend-cann-env`；torch 栈见 `ascend-torch-npu`。

## 何时调用

**加载本 skill 当：**
- 新建 / 激活 conda 环境、换 python 版本（3.12 → 3.13 之类）。
- `python -V` / `which conda` 不是共享 conda（期望 conda 26.7.1、base python 3.14.7）。
- 要复用 `.188` 现成的 `xmz_0921`（py3.12.14），或判断环境该放哪个盘。

**不要用本 skill（转交）：**
- CANN 装在哪、什么版本、`set_env.sh` 不生效 → 用 `ascend-cann-env`。
- CANN 已就绪但 torch / torch_npu 装不上 → 用 `ascend-torch-npu`。
- 只是不知道模型在哪、大文件该写哪个盘 → 用 `ascend-server-layout`。
- 起 vllm 服务 / 跑离线推理冒烟 / 显存释放 → 用 `ascend-vllm-serve`。

**前置**：能 `ssh a3`（免密已配）。 ／ **后继**：`ascend-torch-npu` → `ascend-triton-ascend`。

## 前置检查

```bash
# ① 哪套 conda（.188 上有两套：个人根 base 与旧 /root/miniconda3）
/home/x00886548/env/conda3/bin/conda --version            # 期望 conda 26.7.1
/home/x00886548/env/conda3/bin/conda info | grep -E 'base environment|python version|solver'
#   期望 base=/home/x00886548/env/conda3 (writable)、python 3.14.7.final.0、solver libmamba、platform linux-64
# ② 清单与落点：envs_dirs 第一项 /home/x00886548/env/conda_envs（create -n 落这）；pkgs_dirs=…/env/pkgs/conda
/home/x00886548/env/conda3/bin/conda env list
/home/x00886548/env/conda3/bin/conda config --show default_channels envs_dirs pkgs_dirs
#   期望 default_channels = https://mirrors.nju.edu.cn/anaconda/pkgs/main 与 /pkgs/r
# ③ 配置来源（"配置不生效"排查第一站）
/home/x00886548/env/conda3/bin/conda config --show-sources
ls -l /root/.condarc 2>&1                                  # 期望 No such file or directory
# ④ 磁盘：.188 / 剩 139G（96%），/mnt/share 与 / 同盘（同一 nvme0n1p2 ext4）；/home 6.9T 剩 1.6T ← 环境只放这
df -h / /mnt/share /home/vllm ; findmnt -T /mnt/share
```

## 步骤

### 步骤 1：不激活直接用（脚本 / CI 首选；不 source conda.sh、不动 PATH）
```bash
# 历史共享环境（仍在 /mnt/share/vllm/conda_envs，未迁入个人根，可继续用）
PY=/mnt/share/vllm/conda_envs/xmz_0921/bin/python
$PY -V                                  # -> Python 3.12.14
$PY -c 'import sys;print(sys.prefix)'   # -> /mnt/share/vllm/conda_envs/xmz_0921（正确）
# 个人根环境（新建的都用这种）
PY2=/home/x00886548/env/conda_envs/<name>/bin/python
$PY2 -c 'import sys;print(sys.prefix)'  # -> /home/x00886548/env/conda_envs/<name>
```
验证：`sys.prefix` 等于 env 目录本身；装包一律 `$PY -m pip install <pkg>`。`xmz_0921` = `/mnt/share/vllm/conda_envs/xmz_0921`，py3.12.14，3.7G，建于 2026-09-21 17:51:55（历史环境，不迁）。

### 步骤 2：激活（需要 conda 本体时）
```bash
source /home/x00886548/env/conda3/etc/profile.d/conda.sh && conda activate xmz_0921
python -V; echo $CONDA_PREFIX; which python
```
验证：`Python 3.12.14` / `CONDA_PREFIX=/mnt/share/vllm/conda_envs/xmz_0921` / `which python` = `.../xmz_0921/bin/python`；PATH 头部 `.../xmz_0921/bin : .../condabin : /usr/local/sbin`。

### 步骤 3：新机器一次性配置共享 conda（`setup_conda.sh`，幂等可重跑）
```bash
bash /home/x00886548/env/setup_conda.sh
```
8 步：写共享 `.condarc`（NJU 镜像 / `repodata_use_shards: false` / `envs_dirs` / `pkgs_dirs`）→ 注释 `~/.bashrc` 旧 conda init 块（`.188` 原 22–35 行）→ 写 `/etc/profile.d/conda.sh` → 追加 `# >>> xmz-shared-conda >>>` 块（`.188` 在 49–54 行，含 `conda activate base`）→ 清 `/etc/profile` 与 `~/.condarc` → `ln -sfn .../bin/conda /usr/local/bin/conda` → 自检。
验证：`grep -n xmz-shared-conda /root/.bashrc` 有输出，`ls -l /usr/local/bin/conda` 是软链。**步骤 1 是「`.condarc` 存在即跳过」**，重跑**不会**覆盖盘上已有的 `.condarc`（实测其内容与脚本 heredoc 不一致）；要改配置直接编辑 `/home/x00886548/env/conda3/.condarc`。

### 步骤 4：建新环境（必须显式带 NJU 镜像）
```bash
source /home/x00886548/env/conda3/etc/profile.d/conda.sh
MIRROR="--override-channels -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r"
conda create -n <name> python=3.12 -y $MIRROR    # 落点自动 = /home/x00886548/env/conda_envs/<name>
conda create -p /home/x00886548/env/conda_envs/<name> python=3.12 -y $MIRROR   # 显式 -p 最稳
conda activate /home/x00886548/env/conda_envs/<name>     # 按绝对路径激活，CONDA_PREFIX 正确（已实测）
```
验证：`ls -d /home/x00886548/env/conda_envs/<name>` 存在；新环境 `conda-meta/history` 的 `# cmd:` 行含 `mirrors.nju.edu.cn`（不含 = 走了官方源，重建）；`-p` 路径环境则校验 `conda activate <dir>` 后 `$CONDA_PREFIX` = 该目录。

### 步骤 5：pip 源
```bash
pip config get global.index-url     # -> https://mirrors.aliyun.com/pypi/simple/（生效的那个）
pip config debug                    # 顺序 /root/.pip/pip.conf(True) → /root/.config/pip/pip.conf(True)，后者优先
```
验证：`global.index-url` 是阿里云即可用；要改改 `/root/.config/pip/pip.conf`（XDG 优先级最高）。

## 坑与修法

**坑 1｜建环境绕过镜像 → 走官方源，慢且易超时**
`xmz_0921/conda-meta/history` 原文：`# cmd: ... conda create -n xmz_0921 python=3.12 -y --override-channels -c https://repo.anaconda.com/pkgs/main -c https://repo.anaconda.com/pkgs/r`。修法：按步骤 4 带 NJU 两源——`channels: [defaults]` 会绕过 `.condarc` 的 `default_channels`，`--override-channels` 不能省。

**坑 2｜（.188）旧 conda init 压过共享 conda**
`.188` 上有第二套完整 miniconda `/root/miniconda3`（17G，conda 26.1.1，base py3.13），其 `/root/.bashrc:22-35` init 块会把它插到 PATH 前面。用旧二进制的原文：`RequestsDependencyWarning: urllib3 (2.6.1) or chardet (7.0.1)/charset_normalizer (3.4.4) doesn't match a supported version!`
修法：`setup_conda.sh` 已把该块逐行注释（前缀 `# [setup_conda.sh 已停用] `），别手工恢复，查 `grep -n '^# \[setup_conda' /root/.bashrc`。另 `/root/.condarc` 已被移为 `/root/.condarc.bak.20260921-193553`（内容用清华 TUNA，**该源在本网段 HTTP 403**）；`conda config --show-sources` 若又列出它，再移走。**2026-11-10 又复现**：新出现 `/root/.condarc`（envs_dirs 指 `/mnt/share/vllm/conda_envs`、default_channels 用清华 TUNA），已改名 `/root/.condarc.bak.20261110-2005`——**排查"落点不对/镜像不对"先看 `show-sources`**。

**坑 3｜手工 `export PATH=<base>/bin:$PATH` → activate 后 python 仍是 base**
PATH 里留了 conda 不认识的裸路径，`conda activate` 只把 env 的 bin 插到第二位，`which python` 仍解析到 `/mnt/share/x00886548/miniconda3/bin/python`。修法：不要手工 export PATH，PATH 交给 `conda.sh` + `conda activate` 管。未验证：本机未实测复现该现象，依据是 `setup_conda.sh` 作者的注释警告。

**坑 4｜pip 生效源与 `global.trusted-host` 混搭**
`/root/.config/pip/pip.conf` = 阿里云（生效，XDG 优先）；`/root/.pip/pip.conf` = 华为云（+timeout 120）；`/etc/pip.conf` 不存在；`PIP_INDEX_URL` 未设置。原文：`pip config get global.trusted-host` → `mirrors.huaweicloud.com`，而 `install.trusted-host` → `mirrors.aliyun.com`（兜住了才没炸）。修法：统一到 `/root/.config/pip/pip.conf`，`trusted-host` 也写 `mirrors.aliyun.com`。

**坑 5｜（.190 历史记录，2026-09-23 在 .188 未复现）三条"传说坑"——只在 `.190`（不同 conda / 系统）有记录，别当通用结论、也别删；真遇到先按下面命令在目标机实测**
- `ZSH_VERSION: unbound variable`（`set -u` + conda.sh）：实测 `bash -c 'set -u; . .../miniconda3/etc/profile.d/conda.sh; echo ok'` → `ok-after-condash`，新旧两套 conda.sh 都不报；且 `.188` `command -v zsh` 无输出（没装 zsh）。脚本头留一行 `set +u` 作防御即可，别当实测坑。
- `libp11-kit.so.0: undefined symbol: ffi_type_pointer`（`LD_LIBRARY_PATH=<env>/lib` 后 git 崩）：实测 `LD_LIBRARY_PATH=/mnt/share/vllm/conda_envs/xmz_0921/lib git --version` → `git version 2.20.1` 无报错。机制上不可能：`xmz_0921/lib` 无 `libp11-kit.so.0`、无 `libffi.so.6`（只有 .7/.8），且 `ldd /usr/bin/git` 不含 p11-kit/gnutls。
- 路径环境 activate 后 `CONDA_PREFIX` 仍指 base：实测 `conda activate /home/x00886548/vllm_build_0921/conda_envs/bi_0921` 后 `CONDA_PREFIX` / `CONDA_DEFAULT_ENV` / `python` **全部正确**（conda 26.7.1 已修）。

## 不要做什么

- 不要在 `.188` 手工 `export PATH=<base>/bin:$PATH`，也不要手工 `export CONDA_PREFIX`（那是 `.190` 旧 env.sh 的做法）。
- 不要把新环境建在 `/mnt/share/vllm/conda_envs`：它与 `/` **同盘**（`.188` 剩 139G / 已 96%）。**所有新环境只建 `/home/x00886548/env/conda_envs/`**（在 6.9T 的 /home 盘上）。
- 不要跑 `conda init`：会重建指向 `/root/miniconda3` 的 init 块，压过共享 conda。
- 不要指望重跑 `setup_conda.sh` 覆盖 `.condarc`（步骤 1 存在即跳过）。
- 不要在没 source CANN 的情况下装 torch_npu 或编算子（见 `ascend-cann-env`）。

## 验收标准

1. `/home/x00886548/env/conda3/bin/conda --version` → `conda 26.7.1`；`conda info` 里 base = `/home/x00886548/env/conda3 (writable)`、python `3.14.7.final.0`、solver `libmamba`；`conda config --show-sources` 只列出 `/home/x00886548/env/conda3/.condarc`（及 `condarc.d/anaconda-auth.yml`），没有 `/root/.condarc`。
2. `$PY -V` → `Python 3.12.14` 且 `$PY -c 'import sys;print(sys.prefix)'` → `/mnt/share/vllm/conda_envs/xmz_0921`（历史环境）；个人根新环境 `sys.prefix` = `/home/x00886548/env/conda_envs/<name>`。
3. 新建环境：`ls -d /home/x00886548/env/conda_envs/<name>` 存在，且其 `conda-meta/history` 的 `# cmd:` 行含 `mirrors.nju.edu.cn`。
4. 放环境前 `df -h /home/x00886548` 余量 ≥1T；操作后 `/` 仍 >50G 可用。
