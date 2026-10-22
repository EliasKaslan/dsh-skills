---
name: ascend-conda-env
description: 昇腾服务器 conda 环境的检测 / 新建 / 激活与换 python 版本（默认 a3=192.168.13.188，备用 a3b=.190）——共享 miniconda3 在 /mnt/share/x00886548/miniconda3（conda 26.7.1，base py3.14.7），新建环境默认落 /mnt/share/vllm/conda_envs、必须显式带 NJU 镜像，不激活可直接用绝对路径 python。适用于"建 conda 环境 / 复用已有环境拷到新根 / 激活环境 / 换 python 版本 / python -V 不是共享 conda / 环境该放哪个盘 / conda create 走官方源很慢"。不适用：CANN 装哪、版本、set_env.sh 不生效 → 用 `ascend-cann-env`；torch 或 torch_npu 装不上 → 用 `ascend-torch-npu`。
whenToUse: 需要 conda 本体（建/激活环境、装 conda 包、改 .condarc）或要确定 python 解释器绝对路径、判断环境放哪个盘时。CANN 见 ascend-cann-env，torch 见 ascend-torch-npu。模型看不到本节。
---

# 昇腾服务器 conda 环境（检测 / 新建 / 激活）

机器：默认 `root@192.168.13.188`（Debian 10 / glibc 2.28），备用 `root@192.168.13.190`（Debian 11，**2026-10-22 整机不可达**），A5 `root@177.8.21.1`（**需连 A5 VPN 后可达**，见 `univpn-vpn`）；文档代称 `a3` / `a3b` / `a5`，**本机 ssh config 没有这几个别名，命令一律直连 IP**（见 `ascend-env` §1）。远端驱动规则见 `ascend-env` §5；CANN 见 `ascend-cann-env`；torch 栈见 `ascend-torch-npu`。

**`.188` 现成环境清单（2026-10-22 实测 7 个，全部 py3.12，别急着重装）**：

```bash
for d in /home/vllm/*/*/envs/* /home/vllm/*/envs/* /mnt/share/vllm/conda_envs/*; do [ -d "$d" ] && { printf '%s  ' "$d"; "$d/bin/python" -V 2>/dev/null; }; done
```
实测输出：`/home/vllm/x00886548/batch_inv_glm52/envs/vllm312`、`.../cann91_v0230/envs/vllm_v0230`、`.../sv0230/envs/gcc10`（工具链 env）、`.../sv0230/envs/vllm312`、`.../vllm_0230/envs/vllm0230`、`.../xmz_1009_k3/envs/xmz_1009_k3`、`.../zero_v0230/envs/vllm312` —— **前六个都是 3.12.15**；另有共享的 `/mnt/share/vllm/conda_envs/xmz_0921`（**3.12.14**）。⇒ **命名不等于位置**：`vllm312` 这个名字在 4 个不同项目目录下各有一份，激活/装包前先 `echo $CONDA_PREFIX` 确认是哪一份。

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

**前置**：能免密 `ssh` 进 `root@192.168.13.188`。 ／ **后继**：`ascend-torch-npu` → `ascend-triton-ascend`。

## 前置检查

```bash
# ① 哪套 conda（.188 上有两套：共享 与旧 /root/miniconda3）
/mnt/share/x00886548/miniconda3/bin/conda --version        # 期望 conda 26.7.1
/mnt/share/x00886548/miniconda3/bin/conda info | grep -E 'base environment|python version|solver'
#   期望 base=/mnt/share/x00886548/miniconda3 (writable)、python 3.14.7.final.0、solver libmamba、platform linux-64
# ② 清单与落点：envs_dirs 第一项 /mnt/share/vllm/conda_envs（create -n 落这）；pkgs_dirs=/mnt/share/vllm/conda_pkgs
/mnt/share/x00886548/miniconda3/bin/conda env list
/mnt/share/x00886548/miniconda3/bin/conda config --show default_channels envs_dirs pkgs_dirs
#   期望 default_channels = https://mirrors.nju.edu.cn/anaconda/pkgs/main 与 /pkgs/r
# ③ 配置来源（"配置不生效"排查第一站）
/mnt/share/x00886548/miniconda3/bin/conda config --show-sources
ls -l /root/.condarc 2>&1                                  # .188 期望 No such file or directory
# ④ 磁盘：/ 与 /mnt/share 同盘（同一 nvme0n1p2 ext4，系统盘、长期紧张）；/home/vllm 是独立大容量盘 ← 大环境放这（余量现场 df -h 取）
df -h / /mnt/share /home/vllm ; findmnt -T /mnt/share
```

## 步骤

### 步骤 1：不激活直接用（脚本 / CI 首选；不 source conda.sh、不动 PATH）
```bash
PY=/mnt/share/vllm/conda_envs/xmz_0921/bin/python
$PY -V                                  # -> Python 3.12.14
$PY -m pip -V                           # -> pip 26.2.1 from .../lib/python3.12/site-packages/pip (python 3.12)
$PY -c 'import sys;print(sys.prefix)'   # -> /mnt/share/vllm/conda_envs/xmz_0921（正确）
```
验证：`sys.prefix` 等于 env 目录本身；装包一律 `$PY -m pip install <pkg>`。`xmz_0921` = `/mnt/share/vllm/conda_envs/xmz_0921`，py3.12.14，3.7G，建于 2026-09-21 17:51:55。

### 步骤 2：激活（需要 conda 本体时）
```bash
source /mnt/share/x00886548/miniconda3/etc/profile.d/conda.sh && conda activate xmz_0921
python -V; echo $CONDA_PREFIX; which python
```
验证：`Python 3.12.14` / `CONDA_PREFIX=/mnt/share/vllm/conda_envs/xmz_0921` / `which python` = `.../xmz_0921/bin/python`；PATH 头部 `.../xmz_0921/bin : .../condabin : /usr/local/sbin`。

### 步骤 3：新机器一次性配置共享 conda（`setup_conda.sh`，幂等可重跑）
```bash
bash /mnt/share/x00886548/workspace/setup_conda.sh
```
8 步：写共享 `.condarc`（NJU 镜像 / `repodata_use_shards: false` / `envs_dirs` / `pkgs_dirs`）→ 注释 `~/.bashrc` 旧 conda init 块（`.188` 原 22–35 行）→ 写 `/etc/profile.d/conda.sh` → 追加 `# >>> xmz-shared-conda >>>` 块（`.188` 在 49–54 行，含 `conda activate base`）→ 清 `/etc/profile` 与 `~/.condarc` → `ln -sfn .../bin/conda /usr/local/bin/conda` → 自检。
验证：`grep -n xmz-shared-conda /root/.bashrc` 有输出，`ls -l /usr/local/bin/conda` 是软链。**步骤 1 是「`.condarc` 存在即跳过」**，重跑**不会**覆盖盘上已有的 `.condarc`（实测其内容与脚本 heredoc 不一致）；要改配置直接编辑 `/mnt/share/x00886548/miniconda3/.condarc`。

### 步骤 4：建新环境（必须显式带 NJU 镜像）
```bash
source /mnt/share/x00886548/miniconda3/etc/profile.d/conda.sh
MIRROR="--override-channels -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r"
conda create -n vllm312 python=3.12 pip -y $MIRROR    # 默认落点 /mnt/share/vllm/conda_envs/vllm312（系统盘，不推荐）
conda create -p /home/vllm/x00886548/envbuild/envs/vllm312 python=3.12 pip -y $MIRROR   # 大环境走 /home/vllm，26.7.1 支持 -p
conda activate /home/vllm/x00886548/envbuild/envs/vllm312     # 按绝对路径激活，CONDA_PREFIX 正确（已实测 bi_0921）
```
验证：`ls -d /mnt/share/vllm/conda_envs/vllm312` 存在；新环境 `conda-meta/history` 的 `# cmd:` 行含 `mirrors.nju.edu.cn`（不含 = 走了官方源，重建）；`-p` 路径环境则校验 `conda activate <该目录>` 后 `$CONDA_PREFIX` = 该目录；**并且 `$ENVP/bin/pip -V` 必须能打印出指向 `<ENVP>` 的 pip**（只验 `python -V` 会漏掉下面那条坑）。

- **`pip` 必须显式写进包列表（2026-10-10 实测）**：`conda create -p <ENVP> python=3.12` **不一定把 `pip` 放进 env**，而"`<ENVP>/bin/pip -V` 能打印"又常被当成环境验收判据 ⇒ 不写 `pip` 会得到"环境建好了、验收却过不了"（更糟的是拿别的解释器的 pip 装到错的 site-packages 里）。**写法：`conda create -p <ENVP> python=3.12 pip -y $MIRROR`**；验收 = `$ENVP/bin/pip -V` 第一行指向 `<ENVP>/lib/python3.12/site-packages/pip`。

> 上面这几个路径是**可直接粘贴的实例**。`<name>` / `<user>` / `<ENVP>` 这类尖括号写法在 bash 里是**重定向符**，照抄进 shell 会报语法错或截断文件——要替换就替换成真实值，别把尖括号一起粘进去。

**这一步要放进并行 lane（＝ `ascend-env` §3.1 的 P2）**：`conda create` 对 CANN、对网络下载、对两仓 clone **零依赖**，应当和它们**同时发**，而不是等 CANN 装完再建。把这一步写成独立 lane 脚本 `lane_p2_conda.sh`（本地写好 → base64 通道推到远端，见 `ascend-env` §5），内容：

```bash
set +u
source /mnt/share/x00886548/miniconda3/etc/profile.d/conda.sh
MIRROR="--override-channels -c https://mirrors.nju.edu.cn/anaconda/pkgs/main -c https://mirrors.nju.edu.cn/anaconda/pkgs/r"
L=/home/vllm/x00886548/envbuild
ENVP=$L/envs/vllm312                                 # ← 换成你自己的环境目录（别写 <...> 占位符，bash 会当重定向报语法错）
export CONDA_PKGS_DIRS=$L/conda_pkgs                 # ★ 必加：把包缓存也改道，否则会写系统盘的 pkgs_dirs
conda create -p "$ENVP" python=3.12 pip -y $MIRROR
$ENVP/bin/python -V
$ENVP/bin/pip -V                                     # pip 没进 env 时这里会失败，见步骤 4 上面那条坑
```

下发与判完成（**看产物，不看进程**）：

```bash
L=/home/vllm/x00886548/envbuild
setsid nohup bash $L/lane_p2_conda.sh > $L/lane_p2_conda.log 2>&1 < /dev/null &
# 判完成：解释器能跑就算绿
$L/envs/vllm312/bin/python -V
```

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载 `ascend-conda-env`、`ascend-server-layout`；加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\<name>\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。

- **只建环境，不装包**：这条 lane 的边界是「建出解释器」，`pip install` 一律留给串行段（torch 栈属 **S2**、vllm/vllm-ascend 属 **S3**，见 `ascend-env` §3.2）。子代理跑这条 lane 时也不得碰 pip。
- **`export CONDA_PKGS_DIRS` 不能省（2026-10-08 修）**：共享 `.condarc` 里 `pkgs_dirs` 是 `/mnt/share/vllm/conda_pkgs`（在系统盘上），而 **`conda create -p` 只改环境落点、不改包缓存落点**——不显式改道，这条 lane 就会往系统盘写几百 MB 到 GB 的解包缓存，「写盘白名单只给自己那一格」在物理上不成立。改道后这条 lane 的两个落点都在 `/home/vllm` 下。
  - 仍有一处**不在白名单内**但可忽略：conda 会把新 prefix 登记进 `~/.conda/environments.txt`（几十字节、落 `/root` 即系统盘）。这是 conda 的固定行为，不值得为它扩权（**机制推断，未实测**）。除它之外，`conda create -p` 不写 `.condarc`（只读）、也不走 `envs_dirs`/`CONDA_ENVS_PATH`。
- **环境落点也必须在 `/home/vllm`**（`-p` 显式指定）：`conda create -n` 的默认落点是 `/mnt/share/vllm/conda_envs`（系统盘），大环境会把 `/` 推满。
- **多 lane 并行时，不能拿 `$ROOT/log/lane_pids` 的行数判"有没有重复实例"（2026-10-10 实测）**：它是**各 lane 共享的 append 文件**（`ascend-env` §3.3 记的就是它），行数只等于"被记录过几次"，与"现在有几个实例在跑"无关。**判重复要对每条 lane 自己的日志做特征计数**——脚本里给本 lane 打一个唯一开始标记，然后 `grep -c 'P2 START' $L/lane_p2_conda.log` **必须 == 1**；`>1` 就是真起了两个实例（本轮实测出现过两个同名长任务实例互抢同一个日志文件、新实例截断旧日志，据此误判过"旧实例已死"，见 `ascend-env` §5 末）。

### 步骤 4b：复用已有环境——整目录拷到新根（比重装 torch 栈快一个量级）

场景：要一个**独立根**（不与已交付环境互相踩），但已有环境里的 torch 栈与难装的包（`fla_npu` / `xgrammar` / `llguidance` / `fastokens`）不想重来。实测 3.8 GB 的环境 `cp -a` **4 秒**。

```bash
OLD=/home/vllm/x00886548/<旧根>/envs/<name>
NEW=/home/vllm/x00886548/<新根>/envs/<name>
mkdir -p "$(dirname "$NEW")" && cp -a "$OLD" "$NEW"
"$NEW/bin/python" -c "import attr, pip; print('COPY_OK')"        # ① 先证拷贝本身没坏
for f in "$NEW"/bin/*; do                                         # ② 只改带 shebang 的文本脚本
  [ -f "$f" ] || continue
  head -c 2 "$f" 2>/dev/null | grep -q '#!' || continue
  head -c 300 "$f" 2>/dev/null | grep -q "$OLD" && sed -i "s|$OLD|$NEW|g" "$f"
done
"$NEW/bin/python" -c "import attr, pip; print('REWRITE_OK')"      # ③ 改完再验一次
```

- 判据：①②③ 三次都打 OK，且 `grep -rl "$OLD" "$NEW/bin" | wc -l` 归零（或只剩二进制）。
- **只改 `bin/`，绝不对 site-packages 做 `grep -rl | xargs sed -i`**（2026-10-22 实测，代价是白拷一次）：`.pyc` / `.so` 里也含旧根字符串，二进制被改写后任何 import 都炸 `ValueError: bad marshal data (unknown type code)`——本轮由 `import attr` 先爆，**看着像环境本身坏了，其实是自己的 sed 干的**。
- 旧根字符串留在 `.pyc` 的 `co_filename` 与 `dist-info/RECORD` 里**无害**（只影响 traceback 路径），别为"干净"去清。
- 真正必须处理的只有两处：`bin/` 的 shebang（本机 3.12 环境实测 **133 个文件里 97 个以 `#!` 开头**），以及**继承来的 editable 安装**——`__editable__*.pth` / `*_finder.py` 指向**旧源码树**，必须先 `pip uninstall -y vllm vllm-ascend` 再在新根重装（见 `vllm-ascend-source-install`）。

### 步骤 5：pip 源
```bash
pip config get global.index-url     # -> https://mirrors.aliyun.com/pypi/simple/（生效的那个）
pip config debug                    # 顺序 /root/.pip/pip.conf(True) → /root/.config/pip/pip.conf(True)，后者优先
```
验证：`global.index-url` 是阿里云即可用；要改改 `/root/.config/pip/pip.conf`（XDG 优先级最高）。

**⚠️ 阿里云在本网段只给 HTTP/1.1 限速 → 装大包看起来"零进展"（2026-10-08 实测）**：pip/urllib3 只走 HTTP/1.1，而阿里云对该协议限到 **185 KB/s**；同一 URL 用 `curl`（HTTP/2）实测 **14.2 MB/s**，同一 `curl` 强制 `--http1.1` 复现 **181 KB/s**，而 `mirrors.huaweicloud.com` 走 HTTP/1.1 也有 **7.9 MB/s**。→ 结论是**协议 + 源**，不是网络慢、也不是包大。装 100MB 量级的包（torch 栈、triton-ascend、vllm 依赖）时临时换源：

```bash
export PIP_INDEX_URL=https://mirrors.huaweicloud.com/repository/pypi/simple
export PIP_EXTRA_INDEX_URL=https://triton-ascend.osinfra.cn/pypi/simple   # 仅装 triton-ascend 时需要
export PIP_TRUSTED_HOST=mirrors.huaweicloud.com
```

实测效果：triton-ascend 安装从 20+ 分钟（一直下不完）变成 **60 秒**。

- **只 export 到当前 shell，不要改 `/root/.config/pip/pip.conf`**：那是全机共享配置，别的会话/别的任务会跟着变（本机就是多租户共用）。
- 判"到底是源的问题还是网的问题"用**同 URL 三连对照**：`curl` 默认 / `curl --http1.1` / 换源 `curl`。三者差一个数量级才能定性。
- 换源也会换掉 `--extra-index-url` 的语义：`PIP_EXTRA_INDEX_URL` 是**追加**，原来 pip.conf 里的阿里云仍会被查；要完全绕开就用 `PIP_INDEX_URL` + `--index-url` 显式指定。

## 坑与修法

**坑 1｜建环境绕过镜像 → 走官方源，慢且易超时**
`xmz_0921/conda-meta/history` 原文：`# cmd: ... conda create -n xmz_0921 python=3.12 -y --override-channels -c https://repo.anaconda.com/pkgs/main -c https://repo.anaconda.com/pkgs/r`。修法：按步骤 4 带 NJU 两源——`channels: [defaults]` 会绕过 `.condarc` 的 `default_channels`，`--override-channels` 不能省。

**坑 2｜（.188）旧 conda init 压过共享 conda**
`.188` 上有第二套完整 miniconda `/root/miniconda3`（17G，conda 26.1.1，base py3.13），其 `/root/.bashrc:22-35` init 块会把它插到 PATH 前面。用旧二进制的原文：`RequestsDependencyWarning: urllib3 (2.6.1) or chardet (7.0.1)/charset_normalizer (3.4.4) doesn't match a supported version!`
修法：`setup_conda.sh` 已把该块逐行注释（前缀 `# [setup_conda.sh 已停用] `），别手工恢复，查 `grep -n '^# \[setup_conda' /root/.bashrc`。另 `/root/.condarc` 已被移为 `/root/.condarc.bak.20260921-193553`（内容用清华 TUNA，**该源在本网段 HTTP 403**）；`conda config --show-sources` 若又列出它，再移走。

**坑 3｜手工 `export PATH=<base>/bin:$PATH` → activate 后 python 仍是 base**
PATH 里留了 conda 不认识的裸路径，`conda activate` 只把 env 的 bin 插到第二位，`which python` 仍解析到 `/mnt/share/x00886548/miniconda3/bin/python`。修法：不要手工 export PATH，PATH 交给 `conda.sh` + `conda activate` 管。未验证：本机未实测复现该现象，依据是 `setup_conda.sh` 作者的注释警告。

**坑 4｜pip 生效源与 `global.trusted-host` 混搭**
`/root/.config/pip/pip.conf` = 阿里云（生效，XDG 优先）；`/root/.pip/pip.conf` = 华为云（+timeout 120）；`/etc/pip.conf` 不存在；`PIP_INDEX_URL` 未设置。原文：`pip config get global.trusted-host` → `mirrors.huaweicloud.com`，而 `install.trusted-host` → `mirrors.aliyun.com`（兜住了才没炸）。修法：统一到 `/root/.config/pip/pip.conf`，`trusted-host` 也写 `mirrors.aliyun.com`。

**坑 5｜（.190 历史记录，2026-09-23 在 .188 未复现）三条"传说坑"——只在 `.190`（不同 conda / 系统）有记录，别当通用结论、也别删；真遇到先按下面命令在目标机实测**
- `ZSH_VERSION: unbound variable`（`set -u` + conda.sh）：实测 `bash -c 'set -u; . .../miniconda3/etc/profile.d/conda.sh; echo ok'` → `ok-after-condash`，新旧两套 conda.sh 都不报；且 `.188` `command -v zsh` 无输出（没装 zsh）。脚本头留一行 `set +u` 作防御即可，别当实测坑。
- `libp11-kit.so.0: undefined symbol: ffi_type_pointer`（`LD_LIBRARY_PATH=<env>/lib` 后 git 崩）：实测 `LD_LIBRARY_PATH=/mnt/share/vllm/conda_envs/xmz_0921/lib git --version` → `git version 2.20.1` 无报错。机制上不可能：`xmz_0921/lib` 无 `libp11-kit.so.0`、无 `libffi.so.6`（只有 .7/.8），且 `ldd /usr/bin/git` 不含 p11-kit/gnutls。
- 路径环境 activate 后 `CONDA_PREFIX` 仍指 base：实测 `conda activate /home/vllm/x00886548/vllm_build_0921/conda_envs/bi_0921` 后 `CONDA_PREFIX` / `CONDA_DEFAULT_ENV` / `python` **全部正确**（conda 26.7.1 已修）。

**坑 6｜搬环境后 `import` 炸 `ValueError: bad marshal data (unknown type code)`**
症状是**随机某个包**先爆（本轮是 `import attr`，pip 自己也是 python 包，紧随其后全崩），很容易误判成"环境装坏了"。真因见步骤 4b 的第二条：对 site-packages 做 `grep -rl | xargs sed -i` 把 `.pyc` / `.so` 改坏了。修法：删 `__pycache__`/`*.pyc` 只能救回纯 python 的字节码损坏，**救不了被改写的 `.so`** ⇒ 唯一稳妥解是重拷一份，然后**只改 `bin/`**。

## 不要做什么

- 不要在 `.188` 手工 `export PATH=<base>/bin:$PATH`，也不要手工 `export CONDA_PREFIX`（那是 `.190` 旧 env.sh 的做法）。
- 不要把大环境建在 `/mnt/share/vllm/conda_envs`：它与 `/` **同盘**（系统盘，长期紧张），大环境用 `/home/vllm`（独立大容量盘）；建之前 `df -h` 现场看余量。
- 不要跑 `conda init`：会重建指向 `/root/miniconda3` 的 init 块，压过共享 conda。
- 不要指望重跑 `setup_conda.sh` 覆盖 `.condarc`（步骤 1 存在即跳过）。
- 不要在没 source CANN 的情况下装 torch_npu 或编算子（见 `ascend-cann-env`）。

## 验收标准

1. `/mnt/share/x00886548/miniconda3/bin/conda --version` → `conda 26.7.1`；`conda info` 里 base = `/mnt/share/x00886548/miniconda3 (writable)`、python `3.14.7.final.0`、solver `libmamba`；`conda config --show-sources` 只列出 `/mnt/share/x00886548/miniconda3/.condarc`，没有 `/root/.condarc`。
2. `$PY -V` → `Python 3.12.14` 且 `$PY -c 'import sys;print(sys.prefix)'` → `/mnt/share/vllm/conda_envs/xmz_0921`；激活后 `echo $CONDA_PREFIX` 同值，`which python` 指向该 env 的 `bin/python`。
3. 新建环境：`ls -d /mnt/share/vllm/conda_envs/<name>` 存在，且其 `conda-meta/history` 的 `# cmd:` 行含 `mirrors.nju.edu.cn`。
4. 放环境前 `df -h /home/vllm` **现场判余量够不够**（本文件不记阈值）；操作后 `/` 仍有可见余量（系统盘多租户共用、长期紧张，别写满）。
