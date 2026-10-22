---
name: ascend-env
description: 昇腾 NPU 服务器环境搭建入口总纲（a3=192.168.13.188 默认 / a3b=.190 备用）——**先并行再串行**的 4 lane 编排（CANN 包下载 ∥ conda 建环境 ∥ torch 栈 whl 预下载 ∥ 两仓 clone，barrier 后串行安装），含子代理写盘边界、机器怎么进、三层验收、从 Windows 驱动远端（scp 优先通道，内联引号会静默零命中）的硬规则；具体步骤一律在子 skill。适用于"在昇腾机器上装环境 / 怎么并行搭环境省时间 / 下载和编译能不能同时跑 / 什么能并行什么必须串行 / 要不要派子代理去下载 / 不知道该先做哪一步 / 从零搭一套能跑 vllm 的环境 / 机器进不去或 ssh 假死"。不适用：目录与磁盘、模型在哪 → 用 `ascend-server-layout`；装 CANN → 用 `ascend-cann-env`；conda 与 python → 用 `ascend-conda-env`；跑推理 → 用 `ascend-vllm-serve`。
whenToUse: 昇腾环境从零搭建的编排入口——「哪些步骤能并行 / 先并行后串行的 lane 怎么划 / 子代理边界 / 该按什么顺序调哪个子 skill」看这里；具体步骤在子 skill。模型看不到本节。
---

# 昇腾 NPU 环境总纲

**这是入口 skill，不是操作手册。** 本文件只负责三件事：**机器怎么进**、**该按什么顺序调用哪个子 skill**、**全局验收与共用硬规则**。具体步骤一律在子 skill 里，别在本文件里找细节。

## 何时调用

**加载本 skill 当：**
- 要在 `a3`（`.188`）/ `a3b`（`.190`）/ `a5`（`177.8.21.1`）上从零搭昇腾环境，或不知道先做哪一步、该用哪个子 skill。**注意：三台的当前可用性差别很大——`.188` 可用、`.190` 整机不可达、A5 **要先连上 A5 VPN 才可达**（见 `univpn-vpn`），动手前先看 §1 的状态列**（2026-10-22 复核）。
- 要按顺序调度：服务器目录 → CANN → conda → torch_npu → triton-ascend → vllm 安装 → 起服务。
- 需要全局三层验收（`npu-smi` / `torch.npu.is_available()` / `NPUPlatform`），或要 `ssh` 从 Windows 驱动远端（避免 PowerShell 引号、heredoc 导致的静默失败）。

**不要用本 skill（转交）：**
- 目录地图、磁盘红线、模型在哪、哪张卡空闲 → 用 `ascend-server-layout`。
- 装 / 换 / 查 CANN → 用 `ascend-cann-env`；conda 与 python 版本 → 用 `ascend-conda-env`。
- torch / torch_npu / triton-ascend / vllm-ascend 安装 → 用 `ascend-torch-npu`、`ascend-triton-ascend`、`vllm-ascend-source-install`；起服务跑推理 → 用 `ascend-vllm-serve`。
- 卡在本机 PowerShell 命令本身的坑（编码 / 计数 / BOM / PS7 语法） → 用 `pwsh-on-windows`。

**前置**：无（本 skill 是入口，先把 §1 的机器访问与 §5 的远端硬规则读掉）。 ／ **后继**：`ascend-server-layout` → `ascend-cann-env` → `ascend-conda-env`。

## 1. 机器与访问

> ★ **状态列是时刻值，每次都现场复核**：机器会下线、会重装、负载会变。**照抄状态行去做事**是本 skill 最容易被坑的地方。

| 机器 | ssh 别名 | 主机名 / 系统 | 角色与当前状态（2026-10-22 复核） |
|---|---|---|---|
| `root@192.168.13.188` | **`a3`** | `node-zj-110-132` / Debian 10，256 核 / 1448 GiB | **默认，可用**（免密 + 密码都实测通过）。8 NPU × 2 die = 16 die，全部 `Health OK`。**多租户共用、load 常年很高**（2026-10-22 实测 ≈281；2026-10-08 ≈277）——旧文写的「load ~20，稳定」**已作废**，它是重载机：别把 `MAX_JOBS` 打满，也别指望编译快 |
| `root@192.168.13.190` | `a3b` | `zj-131` / Debian 11，64 核（历史记录） | ⛔ **2026-10-22 整机不可达**：本机与 `.188` **双向** `ping` 100% 丢包、TCP 22 超时，3 次重试全败（用户裁决：按"当前整机不可达"登记）。历史：2026-09-23 曾连续 9 次不通；2026-10-08 恢复过（当时坏的是免密，用密码重装公钥即恢复）。**规格未复核，沿用旧记录但不得当现状引用** |
| `root@177.8.21.1` | `a5` | `ip-177-8-21-1.rev.wkve.net.br` / aarch64，384 核 / 2262 GiB | ✅ **可用，但必须先连 A5 VPN**。2026-10-22 更正：旧文「凭据已登记、当前不可达」是**在没连 A5 的情况下测出来的**，判错了。真值是——**连上 UniVPN 的 `A5` 配置（账号 `vpn_xmz`）后 `177.8.21.1:22` 可达**；不连 A5 则从公网确实全丢（当时的 ICMP/TCP 全闭由此而来），**且连蓝区网关也不通**（只推 `192.168.0.0/16`）。实测规格：NPU `Ascend950DT`、`npu-smi 26.2.0.b020`、`/` 3.5 T 用 88%、**无 nvidia-smi**。连/切 VPN 的方法见 **`univpn-vpn`**。⚠️ 与 `.188` **互斥**：连 A5 时 `.188` 不通，反之亦然 |

```bash
ssh -n -o BatchMode=yes root@192.168.13.188 "hostname; npu-smi info | head -12"   # 免密已配好（2026-10-22 复核仍有效），直接用
```

- **本机没有 `a3` / `a3b` / `a5` ssh 别名**：2026-10-08 实测 `ssh a3` → `Could not resolve hostname a3`；2026-10-22 复核 `~/.ssh/config` **仍只有两段** `Host 192.168.13.188` / `Host 192.168.13.190`（没有 `a5`，也没有 `177.8.21.1`）。**`a3`/`a3b`/`a5` 只是文档代称，命令里一律写 IP**；子 skill 正文里若出现 `ssh a3`，按「.188 默认 / .190 备用 / 177.8.21.1 = A5」换算成 IP（同见 `ascend-vllm-serve` 的前置检查）。
- 密码 fallback：本 skill 目录的 `credentials.txt`（**2026-10-22 已补 A5 行并复核 `.188` 密码仍有效**；正常情况下用不到，换机器 / 公钥被清时才用）。**「机器可达」≠「免密有效」，两件事分开测**：先 `ssh -o BatchMode=yes`，失败且报 `Permission denied (publickey,password)` 就用密码登进去重装公钥（见 `credentials.txt` 里的复核记录）。`.188` 实测 `PermitRootLogin yes` + `PasswordAuthentication yes`，密码通道可用。
- **`.190` 的 ssh 假死**：`ssh_dispatch_run_fatal: Connection to 192.168.13.190 port 22: Connection timed out`（卡在 `expecting SSH2_MSG_KEX_ECDH_REPLY`）是 load ~90 导致 sshd 排不上 CPU，**多数情况重试即可**（2026-09-22 实测同一分钟内先连败 6 次、随后连胜 4 次）。排查顺序：`ping` → TCP 22 → 读 sshd banner → 再 ssh。**但 2026-09-23 连续 9 次全败、2026-10-22 又是双向不通，别把「重试就行」当成必然。** **2026-10-08 复核：`.190` 一次即通且返回 `zj-131`——当时坏的是免密而非可达性，用密码登进去把公钥追加回 `authorized_keys` 就恢复了；下次 `.190` 连不上，先分清是「连不上 TCP」（2026-10-22 就是这种，ping 也丢包）还是「连上了但公钥被拒」（2026-10-08 那种）。**
- **`.188` 另有一条与本机无关的组网**：机器上跑着 `tailscaled`（节点名 `npu-server` / `100.106.254.81`，tailnet 里另有一个 `skhalid-local` 100.85.1.19）。**本机没有 tailscale 客户端**（2026-10-22 实测 `Get-Command tailscale` 为空），所以 `100.x` 那条路走不通——`npu-smi`/`ss -ltnp` 里看到 `100.106.254.81:*` 的监听属正常，**别拿它当备用登录地址**。
- **`.188` 每条 ssh 都会在 stderr 打一行** `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory`。这**不是偶发噪声，是真实断链**：2026-10-22 复核 `/usr/local/Ascend/ascend-toolkit` 是一个**空目录**（既没有 `set_env.sh`，也没有 `latest` 软链；2026-09-23 复查时 `readlink -f .../latest` 还返回空、旧软链曾指向不存在的 `/usr/local/Ascend/cann-9.1.0/cann`）。
  - 影响范围**仅限「默认路径」**：`.188` 真正在用的 CANN 9.1.0 在 `/mnt/share/x00886548/cann/cann_9_1_0`（`env_batch_inv.sh` 就是 source 它，2026-10-22 复核仍能起 `True/16`），只要显式 source 就不受影响；`/usr/local/Ascend/cann-9.0.0/set_env.sh` 是另一套确实可用的旧安装。
  - **别依赖 `/usr/local/Ascend/ascend-toolkit`**（空壳目录）。修法与判据见 `ascend-cann-env`。

### 1.1 接一台没见过的机器（新机 / 长期没上的机器，照这个检查单跑）

**三层分开测，结论分开写**——把这三件事混成一句「连不上」是本轮最大的时间浪费点：

```powershell
# ① 可达性（ICMP）——只说明网络层；ping 不通也可能是被墙，不代表机器死了
Test-Connection -ComputerName 177.8.21.1 -Count 2 -Quiet
# ② 端口（TCP）——用短超时 TcpClient，**别用 Test-NetConnection**：它对不通的地址会挂几分钟
$c=New-Object Net.Sockets.TcpClient; $t=$c.BeginConnect('177.8.21.1',22,$null,$null); $t.AsyncWaitHandle.WaitOne(4000,$false)
# ③ 认证（ssh）——只有这一层失败才轮到查 key / 密码 / PasswordAuthentication
ssh -v -o ConnectTimeout=10 root@177.8.21.1 hostname
```

- **探测顺序**：`ping` → 常用端口（22/2222/2022/10022/8022，必要时再 20000+/30000+/40000+/50000+ 各取一小段）→ `traceroute`。本轮 A5 就是这条路走完：ICMP 全丢、1–2000 与五个高位段全闭、`traceroute` 出公网到 `177.54.235.35` 后静默 ⇒ 结论只能写成「路径不通 / 机器未就绪」。
- **不要扫全端口段**：公网地址整段扫既慢又像在踩点；先问用户端口 / 跳板 / VPN，问不到就按「不可达」登记，**别用扫出来的东西推断机器规格**。
- **「连不上」≠「不存在」**：可以写进交付物的只有「何时、从哪、用什么命令、观察到什么」；`主机名 / OS / 卡数 / 磁盘 / CANN` 一律标 `未采`，**禁止从 A3/A5 这类代号反推型号**。
- 真接上以后，**只读采集**一遍再动任何写操作：`hostname; nproc; free -g; npu-smi info; df -h; cat /etc/Ascend/ascend_cann_install.info`——采集脚本用法见 §5（`scp` + `md5sum` 闸门，别内联）。

## 2. 子 skill 索引（按搭建顺序；前一层不通不要做后一层）

| 顺序 | skill | 负责什么 |
|---|---|---|
| 1 | `ascend-server-layout` | 机器目录地图、模型在哪、磁盘红线、写文件该去哪、现成可复用环境 |
| 2 | `ascend-cann-env` | CANN 检测 / 安装 / 激活 / 多版本 / 卸载（toolkit+ops+nnal、驱动&Toolkit 合一包） |
| 3 | `ascend-conda-env` | conda 检测 / 新建 / 激活 / 共享环境规范 |
| 4 | `ascend-torch-npu` | torch + torch_npu 商发版本安装与 NPU 可用性验证 |
| 5 | `ascend-triton-ascend` | triton-ascend 安装与验证（与社区 triton 的共存关系） |
| 6 | `vllm-ascend-source-install` | vllm + vllm-ascend 源码**配对安装**（含 AscendC 算子编译） |
| 7 | `ascend-vllm-serve` | **起服务 / 离线推理 / 冒烟**、运行时坑、权重准备 |

> 6 与 7 是「vllm / vllm-ascend」这一块的两半：6 管装得上，7 管跑得起来。
>
> **注意：下面这张表是「职责索引」，不是执行顺序。** §3 的 4 条并行 lane 是**横切**这张表的：CANN 的下载、conda 的建环境、torch 栈的下载、两仓的 clone 都属于并行段，只有安装才按这张表的层级串行走。

## 3. 执行编排：先并行、再串行（**本套件的默认执行方式**）

**核心原则：把「下载 / 克隆 / 建环境」这类 IO 密集、彼此不写同一路径的动作全部提前并行做掉；只把有真实前后依赖的安装动作留在串行段。** 从零搭一套的墙钟 ≈ `max(各并行 lane) + 串行段`，而不是各步骤之和。**别一条一条顺着 §3.4 跑。**

### 3.1 依赖图与 4 条并行 lane

> **证据边界（别把下面当结论用）**：2026-10-08 在 `.188` 实测的是**各条命令用到的原语**——三个 `curl` 并发 HEAD 都返回 200、curl 7.64 不支持 `--parallel`/`-Z`、raw.githubusercontent 上的 verified commit 可直读、`pip download` + `pip install --no-index --find-links` 往返、`.188` 现成 wheelhouse 解释器可用。**整条链的端到端往返没有跑过**：离线装只验过 `six` 这类纯 py wheel，torch 全家未试；同一 `$WH` 上的并发写、跨 python 版本下载开关、车道 A 的 pip 序列，均在各子 skill 里逐条标了「未验证」。**照做前先按各子 skill 的未验证项决定要不要加冗余。**

```
P0 现场取数（免密 / df -h / npu-smi）                ← 必做，不占并行额度
 │
 ├─ P1 CANN 三个 .run 并发下载 ───────┐
 ├─ P2 conda 建环境 ─────────────────┤
 ├─ P3 torch 栈 whl 预下载 ──────────┤  4 条 lane 同时发
 └─ P4 vllm / vllm-ascend 两仓 clone ┘
                                     │ barrier：4 条全绿
                                     ▼
 S1 CANN 安装：toolkit → source → nnal → ops → import acl
 S2 torch → torch_npu → triton-ascend（从本地 wheelhouse 离线装）
 S3 vllm → vllm-ascend（源码装 + 编 AscendC 算子）
 S4 三层验收（§4）→ `ascend-vllm-serve`
```

| lane | 干什么 | 落点（写白名单） | 为什么能并行 | 细节在哪 |
|---|---|---|---|---|
| **P1** | CANN toolkit / nnal / A3-ops 三个 `.run` 并发下载（≈4.2G，整条流程最大的墙钟项） | `<PKGS>` | 纯网络 IO，三个文件互不相干 | `ascend-cann-env` 坑 11 |
| **P2** | `conda create -p <ENVP> python=3.12` | `<ENVP>` **+ `$ROOT/conda_pkgs`**（`conda create` 必然写包缓存，见下） | 对 CANN / 网络 / 两仓零依赖 | `ascend-conda-env` 步骤 4 |
| **P3** | torch+torchvision+torchaudio+torch_npu（**一条命令**）/ triton-ascend 的 whl **预下载到本地 wheelhouse**（**1+1 两组，同一个 `<WH>`**） | `<WH>` | `pip download` 只是下载，**不需要目标 env 存在**——用任意**同 python 版本**的解释器即可（`.188` 现成的 `xmz_0921` 就是 py3.12.14） | `ascend-torch-npu` 步骤 3（torch 栈 + torch_npu）+ `ascend-triton-ascend` 步骤 ⓪（triton-ascend） |
| **P4** | `vllm` 与 `vllm-ascend` 两仓 clone + 切 tag/commit | `<SRC>` | 两仓互不写同一目录；配对 commit 用 **raw.githubusercontent 免 clone 拿**（实测 200），所以是真并行 | `vllm-ascend-source-install` §1 |

**落点建议（全在 `/home/vllm` 大盘；`/` 上只放小脚本，见 §6）**：

```bash
ROOT=/home/vllm/x00886548/envbuild        # ← 换成你自己的目录（**别写 `<...>` 占位符，bash 会当重定向报语法错**）
PKGS=$ROOT/pkgs          # P1
ENVP=$ROOT/envs/vllm312  # P2
CPKGS=$ROOT/conda_pkgs   # P2 的包缓存：必须显式改道，否则 conda 会写共享 pkgs_dirs（系统盘）
WH=$ROOT/wheelhouse      # P3
SRC=$ROOT/src            # P4
mkdir -p "$WH"
echo 'torch==2.12.0+cpu' > "$WH/constraints.txt"   # ★ P3 的唯一写者（车道 A 写 2.10.0+cpu）
```

- **`constraints.txt` 只在这里写、两个下载组都只读**：它把 torch 的候选集钉成带 local label 的 `+cpu` 版本（PEP 440 语义已实测：`==2.12.0+cpu` 不匹配 PyPI 上的 `2.12.0`、匹配 `2.12.0+cpu`；而 torch_npu 要求的 `==2.12.0` 匹配 `2.12.0+cpu`）。若两组各自 `echo >` 写同一个文件，极端时序下 `pip` 可能读到被截断的空文件 → **约束静默失效**（详见 `ascend-torch-npu` 步骤 3）。

- **P3 的下载解释器必须与目标 env 同 python 版本**，否则 wheel tag 不匹配、离线装不上（目标 py3.12 就用 `xmz_0921`）。要跨版本下载得加 `--python-version/--abi/--platform/--only-binary=:all:`（**未验证**：只用 `six` 这类纯 py wheel 验过这些开关被接受，没验过 torch 全家）。
- **P2 必须连包缓存一起改道**：共享 `.condarc` 里 `pkgs_dirs` 指向 `/mnt/share/vllm/conda_pkgs`（在系统盘上）。`conda create -p` **只改环境落点、不改包缓存落点**，所以 lane 脚本里要显式 `export CONDA_PKGS_DIRS=$CPKGS`——否则「白名单只给自己那一格」在物理上不成立（详见 `ascend-conda-env` 步骤 4）。
- **并行只到 lane 这一层**：共享机（2026-10-08 实测 256 核 / load ~277）上再往 lane 里 fan-out 只会互相拖慢。

### 3.2 barrier 与串行段（为什么这几步不能并行）

- **barrier 只有一条**：4 条 lane 全部落地后才进串行段。**判完没完看产物，不看进程**（`ps` 里有 pid ≠ 下载成功）。
- **S1 必须串行**：nnal / ops 要求**同路径 toolkit 已装且已 `source`**（不 source 就装 nnal 直接 exit 4）→ toolkit → nnal → ops 顺序不可换。
- **S2 必须串行**：`torch_npu` 对 torch 是**精确等值依赖**；`triton-ascend` 会**覆盖** triton 并锁 numpy → 三者顺序不可换。预下载只省"下载慢"，**不改变安装顺序**。
- **S3 必须串行**：vllm-ascend 要求 vllm 已在环境里，且 `--no-build-isolation` 下要过 vllm-ascend 的 build 依赖校验。
- **串行段里不要再夹下载**：S2 的安装**推荐** `--no-index --find-links <WH>`，把网络整段从串行路径上摘掉。实测 `--no-index` 下 wheelhouse 里没有的包必然 `No matching distribution found` → 能证明它真断网、不会偷偷回源；**但整条 torch 栈的"下载→离线装"往返只在 `six` 这类纯 py wheel 上验过**（见 `ascend-torch-npu` 步骤 3 的未验证项），所以轮询到缺包时按那里写的在线回退走，别硬扛。

### 3.3 用子代理跑这 4 条 lane（**建议，但边界写死**）

4 条 lane 各派一个子代理，**主 Agent 保留 barrier 与整个串行段的控制权**。委派 prompt 里必须写进去的边界：

- **只做本 lane 的下载 / clone / 建目录**。**禁止**：`pip install`、`conda activate`、`source set_env.sh`、改 `/etc`、改 `PATH`、`rm -rf` 任何非本 lane 目录、杀进程、装系统包。
- **写盘白名单只给自己那一格**（§3.1 表「落点」列）。要写白名单外的路径 → **停下回报，不要自己扩权**。
- 回报只要「产物路径 + 体积 + 校验值 + 日志末 10 行」，**不要回贴整段日志**（省主 Agent 上下文）。
- **没有子代理工具就自己后台化**（脚本名照 §3.1 的 lane 命名，**别写 `<lane>.sh` 这种占位符**——bash 会把 `<` `>` 当重定向，`bash` 转头去读一个叫 `lane` 的文件并 truncate 掉 `.sh`/`.log`）：
  ```bash
  setsid nohup bash $ROOT/lane_p1_cann.sh > $ROOT/lane_p1.log 2>&1 < /dev/null &
  echo $! >> $ROOT/lane_pids        # 记下 pid 到文件，清理只认这份记录（见 `orchestrating-subagents` §7）
  ```
- 长任务下发方式见 §5（**base64 通道**，别用管道直推脚本正文）。

> **子代理供给**：下发前在 prompt 里点名让它 `skill` 加载本任务所需的 skill——按该 lane 取：CANN 下载 → `ascend-cann-env`；conda 建环境 → `ascend-conda-env`；torch 栈 whl 预下载 → `ascend-torch-npu`；clone 无 skill；四条 lane 一律再加 `ascend-server-layout` 作写盘白名单；加载不到（工具受限的子代理）就把 `C:\Users\admin\.dsh\skills\<name>\SKILL.md` 路径给它 `read`。机制与判据见 `orchestrating-subagents` §3.1。
> 并发成员 ≥2 或子任务 ≥3 时，按 `orchestrating-subagents` §9.1 在本轮 cwd 落 `.dsh-run\<日期>-ledger.md` 台账，收尾清空。

**lane 完成判据（看产物）**：

```bash
ls -l $PKGS/*.run                                     # P1：三个 .run 体积对上，两个 md5 对已记录值
$ENVP/bin/python -V                                   # P2：env 能跑
ls $WH | grep -E '^(torch|torch_npu|torchvision|torchaudio|triton|triton_ascend)-'   # P3：目标 whl 名齐全
git -C $SRC/vllm-ascend log --oneline -1; git -C $SRC/vllm log --oneline -1          # P4：HEAD 是目标 commit
```

### 3.4 串行顺序（与并行段衔接；前一层不通不要做后一层）

1. **P0：进机器、看目录与磁盘** → `ascend-server-layout`（先知道模型在哪、能往哪写）
2. **CANN** → `ascend-cann-env`（**下载属 P1，安装属 S1**）
3. **conda 环境** → `ascend-conda-env`（**属 P2**）
4. **torch 栈**（torch → torch_npu → triton-ascend，顺序不能换）→ `ascend-torch-npu`、`ascend-triton-ascend`（**下载属 P3，安装属 S2**）
5. **vllm + vllm-ascend** → `vllm-ascend-source-install`（**clone 属 P4，安装属 S3**）
6. **起服务 / 冒烟** → `ascend-vllm-serve`（**属 S4**）

**已有环境优先复用，别重建**：`.188` 上 `source /mnt/share/x00886548/workspace/batch_inv_qwen35/env_batch_inv.sh` 就能拿到一套已验证的 vllm + vllm-ascend（清单见 `ascend-server-layout`）。

**版本不要纠结**（用户 2026-10-08 定的纪律，细则见子 skill）：torch 栈版本**只参考 vllm-ascend 的 `requirements.txt`**（pin 被注释掉时，注释里保留着原文，直接读注释）；**vllm 的 requirements 不用参考**；装出来有依赖冲突**不用管**（`pip check` 噪音、numpy / fastapi 之类），只要 §4 三层验收过就算成。

## 4. 全局三层验收（逐层来，别一上来就跑模型）

```bash
npu-smi info | head -12                                    # ① 卡在、驱动在
python3 -c "import torch, torch_npu; print(torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"   # ② 期望 True 16 253
python3 -c "from vllm.platforms import current_platform as p; print(type(p).__name__, p.device_type)"                          # ③ 期望 NPUPlatform npu
```

- ② 的 `253` = A3（soc version），`16` = 16 die。
- 每层的完整判据、期望值、常见报错见对应子 skill。**②不过就别做 ③**。
- **三层验收要在最后一步安装之前先跑一次并落盘（before 基线），否则"通过"无法与"本来就对"区分**；配套的 `env -i` 承载 shell 对照法见 `orchestrating-subagents` §9.10。
- **完成标记不是证据**（2026-10-08 实测两起）：lane 脚本会打印 `LANE_Px_DONE` / `S4_DONE` 之类标记，**失败也照样打印**。判完成只看**产物**——文件是否存在/大小/条数、日志里有没有 `rc=` 行、验收命令是不是真被执行过。实测两次踩中：P4 的 clone **失败**却仍打印了 DONE；S3 被打断后**标记照打**。
- **shell 退出码也不可靠时要看产物**：该机器**每次 ssh 都会因 `/root/.bashrc` 里那行失效的 `set_env.sh` 而以 exit 1 结束**（§1），所以 `exit=1` 既可能是真失败、也可能只是这行噪声。判据回到产物本身，不要只看退出码。
  - **`.188` 上 `ssh` 的退出码一律不可作为成功判据**（2026-10-09 实测）：`ssh -n root@192.168.13.188 "echo hi"` 命令本身成功、输出 `hi`，紧接着 `echo $?` 却是 **`1`**——真因就是 `/root/.bashrc: line 36` 那行失效 `set_env.sh`；**非零退出码与命令本身是否成功无关**。判成功只能靠**产物**（落盘文件 / 目录 / 明确写出的标记行）。确实要机判时，让**远端命令自己把结果写进文件**（把 `$?` 或结果 echo 进 `$ROOT/log/...`），再从本机读那个文件——**不要从 ssh 的退出码判**。
  - **同族注意：不要用跨机时间戳排序事件**（2026-10-09 实测）：**远端时钟比本机慢约 6 分钟**，本机的 17:33 与远端的 17:27 可能是同一瞬间；跨机对时间只认**产物内容 + 你本机读它的时刻**。

## 5. 从 Windows 驱动远端（所有子 skill 共用；违反会**静默失败**）

- **内联 ssh 命令里禁用 `<`、`"`、`$()`**：PowerShell 会解析错误或吃掉内层引号（实测 `grep -E "a|b"` 的引号被剥掉，远端把 `|b` 当成了管道）。**2026-10-08 补机制（本轮复发 6 次，两次据此误判"进程已经死了"）**：本机是 Windows PowerShell 5.1，它会把**单引号内的双引号重新转义成 `\"`** 再交给原生程序，远端 bash 收到的是**字面引号** ⇒ `grep`/`pgrep`/`awk` 的模式**静默零匹配**（看着像"什么都没找到"，其实压根没匹配上），语法错误还会被 `2>$null` 一起吞掉。逐字症状：`bash: -c: line 0: syntax error near unexpected token '('`。**修法**：内联 ssh 只做**无引号的简单命令**（`cat <path>`、`bash /tmp/x.sh`）；凡需要模式匹配或含变量者，一律**落脚本文件再推**（**首选 `scp`**，见下）。**2026-10-10 追加两条逐字实测**：`pgrep -af "pip|bisheng"` → 远端报 **`bash: bisheng: command not found`**；`python -c "...sys.argv[1]..."` → 远端报 **`bash: -c: line 0: syntax error near unexpected token 'sys.argv[1]'`**。**危险点在于"零命中"看起来就像"没找到"**——它与"确实不存在"在当次输出里**无法区分**（再被 `2>$null` 一吞更看不出）⇒ 别拿它下"没有这个进程 / 没有这条记录"的结论。同理，为避引号而省略引号会让模式**静默降级**：`grep -n installed successfully <log>` 报 **`grep: successfully: No such file or directory`**，实际只按 `installed` 匹配 ⇒ **多词模式必须写进 `.sh`**。
- 复杂命令一律**本地写 .sh/.py → 用 base64 管道送过去**（2026-10-08 实测改，**取代原来的 `tail -c +4` 直推写法**）：

  ```powershell
  $f = ".\x.sh"
  # 必须读**原始字节**：Get-Content -Raw 在 PS 5.1 会按 GBK 解码，含中文的 .sh/.py 会被静默改坏
  $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($f))
  ssh root@192.168.13.188 "printf '%s' '$b64' | base64 -d > /tmp/x.sh"
  ssh -n root@192.168.13.188 "md5sum /tmp/x.sh"    # 与本机 (Get-FileHash -Algorithm MD5 $f).Hash 逐字比对
  ssh -n root@192.168.13.188 "bash /tmp/x.sh"
  ```

  - **判据只有一条：`md5sum` 与本地 md5 相同才算推送成功**。md5 不一致时**不要**接着跑——远端那份已经坏了。这条能同时兜住 GBK 改坏、CRLF、截断三种坏法。

- ★ **通道优先级（2026-10-10 实测改）：首选 `scp`，base64 是退路。** `scp` 是**干净通道**——它不经 PowerShell 的引号重写、逐字节搬运：本轮把一段含 **2 个单引号 + 30 个双引号、1391 B** 的 `.sh` 用 `scp` 推送后，远端 `md5sum` 与本地**逐字相符**（byte-exact），**完全绕开下面那条"内联 ssh 引号被重写"的坑** ⇒ 能 `scp` 就别内联。

  ```powershell
  scp ".\x.sh" root@192.168.13.188:/tmp/x.sh
  ssh -n root@192.168.13.188 "md5sum /tmp/x.sh"   # 必须等于本机 (Get-FileHash -Algorithm MD5 .\x.sh).Hash
  ```

  **判据与 base64 通道同一条：`md5sum` 逐字相符才继续**。`scp` 的唯一注意点仍是**本地文件自己带 BOM 会被一起搬过去**（见本节 BOM 那条）。
  - **`scp` 会偶发 `Connection closed`（2026-10-22 实测 1 次）**：症状是 `scp.exe: Connection closed`、`Get-FileHash` 与远端 `md5sum` 都对不上（远端根本没这个文件，或只写了半截）。**先原样重试一次**（本轮第 2 次即成功、md5 相符），不要立刻去怀疑路径/权限/防火墙；**判"推送成功"只认远端 `md5sum`**，`scp` 自己没报错也不代表到位。
  - 采规格这类**多段只读脚本**（本轮 5 个）用同一条通道跑通，写法：本地 `[IO.File]::WriteAllText($p,$body,[Text.UTF8Encoding]::new($false))` 落盘 → `scp` → 比 md5 → `ssh -n ... "bash /tmp/x.sh 2>/dev/null"`（远端把 stderr 关掉，专门用来甩掉 `.188` 那条 bashrc 噪声，别用本机 `2>$null`）。
  - **`Get-Content -Raw` 会让"base64 通道"也坏**（2026-10-08 实测）：`Get-Content -Raw` → **GBK 解码** → `UTF8.GetBytes` 重编码，纯 ASCII 脚本侥幸无损，**含中文的脚本会被改坏**——实测 `scripts/strip_torch_pins.py`（中文 docstring）推过去后 `python` 报 `SyntaxError: invalid non-printable character U+E15E`（`閲屽舰濡` 这类 GBK 乱码），且**字节数从 7343 变成 7819**。改用 `[IO.File]::ReadAllBytes` 后 md5 与本地完全一致、`ast.parse` 通过。**凡是 `.py`（docstring/注释多是中文）一律用 ReadAllBytes**。

  - **base64 通道实测逐字无损、且不带 BOM**：含中文 + `%{http_code}` 的脚本往返后远端执行结果与本地一致（`确认 磁盘落点 并行` 原样保留、`%{size_download}` 正常展开）。
  - **但 base64 会把体积放大 4/3、且整串要塞进 ssh 的命令行**：本机实测过"命令行走长即溢出/截断"（见 `pwsh-on-windows`）。**脚本超过约 20KB 就不要内联**——改用 `scp`（注意本机 `Set-Content -Encoding UTF8` 会带 BOM，要用 `[System.IO.File]::WriteAllText($p,$s,[Text.UTF8Encoding]::new($false))`），或把 base64 按 ~6000 字符分块 append 再校验 `md5sum`。
  - **不要再无脑加 `tail -c +4`**：本机 `$OutputEncoding` 实测是**无 BOM 的 UTF-8**（`GetPreamble().Length` = 0），管道给 ssh **不注入 BOM** → `tail -c +4` 会**吃掉脚本前 3 个字符**（实测把 `#!/bin/bash` 削成 `bin/bash`；因为接着显式 `bash /tmp/x.sh` 才没报错，改成 `./x.sh` 直接坏）。只有当 `$OutputEncoding` 被显式设成带 BOM 的 `[Text.Encoding]::UTF8` 时才会多出 BOM，那时才需要剥 3 字节——**先探再决定**：
  - **另一条独立的风险线：源文件自己带 BOM**（2026-10-09 实测）——base64 会把源字节**原样**带过去，**base64 之前要先剥掉 UTF-8 BOM**（首 3 字节 `EF BB BF`），否则远端解出来的脚本首行带 BOM：`bash /tmp/x.sh` 报 `bash: /tmp/x.sh: line 1: ﻿#!/bin/bash: No such file or directory`。**修法**：编码前先看首 3 字节（`[IO.File]::ReadAllBytes($f)[0..2]` 是否为 `239 187 191`），是就先剥；**通道不会替你去掉它**。

    ```powershell
    "PROBE" | ssh root@192.168.13.188 "od -An -c | head -1"   # 首字节出现 357 273 277（EF BB BF）= 有 BOM
    ```
  - **多行 + 中文的脚本经 PowerShell 管道直推正文会静默损坏**（2026-10-08 实测：同一份脚本直推后远端**丢行**，且 `确认` 变成私用区字符 `U+E1BF U+E17B`，bash 照跑不报错）→ **不要写 `(Get-Content -Raw …) | ssh … "… > /tmp/x.sh"`**，一律走上面的 base64。
  - `scp` **已升级为首选通道（见上）**，**但注意本地文件的 BOM**：PS 5.1 `Set-Content -Encoding UTF8` 会写 BOM，scp 会把 BOM 一起带过去 → 远端报 `bash: /tmp/x.sh: line 1: ﻿#!/bin/bash: No such file or directory`。要么用 `[System.IO.File]::WriteAllText($p,$s,[Text.UTF8Encoding]::new($false))` 落本地文件，要么干脆 base64。
- ★ **sshd 被饿死时，唯一稳的通道是「一条 paramiko 长连接跑完所有命令」（2026-10-22 实测，`.188` load ≈ 290）**：失败发生在**连接建立阶段**，不是命令本身——
  ```text
  ssh: connect to host 192.168.13.188 port 22: Connection timed out
  banner exchange: Connection timed out
  ```
  同批 `scp` 报 `Connection closed`、md5 对不上。根因与 §1 的 `.190` 假死同源（sshd 排不上 CPU），但**逐条重试的失败率高到没法干活**：本轮单命令 `ssh`/`scp` 失败十几次，而**建一条连接跑完全部命令一次没断**。
  - 做法：本机 `python`（paramiko **5.0.0** 已装）建一条 `Transport`，之后 `put / run / bg / tail / md5` 全复用它；连接失败就整体重连（重试 12 次）。
  - **必须显式放大 `banner_timeout` 与 `auth_timeout`**（默认 15 s 不够）；**`paramiko.Transport` 没有 `settimeout` 方法**（写了报 `AttributeError`，看着像连通性问题），超时参数给 `SSHClient.connect(..., timeout=, banner_timeout=, auth_timeout=)`。
  - 判据不变：**推送看远端 `md5sum`**、**执行看产物**（`.188` 的 ssh 退出码恒 1，见 §4）。
  - 固化下来的五个动作足够覆盖全部远端活：`put`（带 md5 回比）、`run`（前台等结果）、`bg`（`setsid nohup … < /dev/null &`）、`tail`（轮询日志）、`md5`。
- **heredoc 只在「脚本先落盘、再执行」时可用**。用上面 base64 落盘 + `ssh -n ... "bash /tmp/x.sh"` 的模式下，脚本内的 heredoc（`python - <<'PY'`）**完全正常**，本套件多个 skill 的示例都这么写。
  **禁止的是把带 heredoc 的脚本直接经 ssh stdin 送进去**（`ssh root@192.168.13.188 "bash -s" < x.sh`、`cat x.sh | ssh root@192.168.13.188 bash`）：heredoc 会与脚本本身争抢 stdin，**永久挂起且不报错**。
- **`ssh -n` 与「脚本走 stdin」互斥**：`-n` 只用于执行**远端已存在的文件**；任何 `$body | ssh … "… bash -s"` 的写法**绝不能加 `-n`**——stdin 被 `/dev/null` 占掉后脚本空跑且**不报错**，你只会看到输出为空（实测：`ssh -n … "od -An -c"` 读到的是空）。
- 长任务：`ssh -n root@192.168.13.188 "setsid nohup bash /path/x.sh > /path/x.log 2>&1 < /dev/null &"`，然后轮询日志；别把长任务塞进一条会超时的 ssh。
- 读远端中文文件/脚本一律显式 UTF-8（`[System.IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)`）；PowerShell 5.1 默认按 GBK 解码，会把中文读成乱码。
- 需要密码登录时用本机 `python` 的 **paramiko**（已装 5.0.0）非交互式登录，比找 sshpass 可靠。
- **查「谁占着卡 / 谁占着文件」时，你自己的 ssh 包装进程必然自匹配**：`grep -l <pat> /proc/[0-9]*/cmdline` 这类命令的 cmdline 里就含整条命令串，于是 `bash -c ...` 包装进程会被自己命中，得出**假阳性**。必须再用 `ps -ef | grep -v grep` 与 `ls -l /proc/<pid>/fd/` 交叉复核才能判真占用（实测踩过：一度以为 `pid 140974` 是残留安装进程，实为自己那条 ssh）。
- **base64 推送后要核对「最终目的地」的 md5，不是 `/tmp` 的**（2026-10-08 实测）：`printf '%s' '$b64' | base64 -d > /tmp/x.sh` 只保证 **`/tmp/x.sh`** 正确。若该脚本本该落在 `$ROOT/`（env 脚本就是这种），只核 `/tmp` 的 md5 会让你**误以为推送成功**——本轮实测 `source $ROOT/env_sv0230.sh` **静默失败**，导致整条 S3 在 **CANN 环境变量未设置**的情况下运行。纪律：写完必须 `md5sum <最终路径>`，与本地 `(Get-FileHash -Algorithm MD5 $f).Hash` 逐字比对。
- **ssh 里永远不要丢弃 stderr（不要 `2>$null`）**：那会丢掉唯一能解释"进程为什么立刻退出"的 traceback——本轮正是它把 `libhccl.so` 的真因藏了起来。改为 `> x.log 2>&1` 落盘再 `grep`。
- **`curl -o <目标文件>` 连接失败时「什么都不写」**（2026-10-09 实测）：`curl -s -o /tmp/x.txt <url>` 因连接失败**根本不创建** `/tmp/x.txt` ⇒ 紧跟的 `grep … < /tmp/x.txt`（或 `cat`）报 **`No such file or directory`**，**看起来像"数据里没有这个东西"，实际是"文件根本不存在"**（这就是"下游报错离根因很远"的机制）。
  - **修法**：`curl` 取文件**必须配重试循环**（`for i in 1 2 3 …` + `curl -fsS -o …`，`-f` 让 HTTP 错误码也非零），**并在消费之前做格式校验**；实测有效写法是取 40 位 commit SHA 时**校验 `^[0-9a-f]{40}$`**，不匹配即失败——**`exit 1`，绝不让下游拿空文件继续跑**。
  - **这条的价值在错误归因**：同一个「文件不存在」报错，可能是**网络失败**、也可能是**数据问题**，必须**在取数那一步就把二者分开**（`[ -s /tmp/x.txt ] || echo CURL_EMPTY >&2; exit 1`）。
- **重启长任务前先确认旧实例真的死了**：`pgrep -af <name>` 期望输出 `(none)`。本轮出现过**两个同名长任务实例同时写同一个日志文件**，新实例启动时截断了旧文件，据此做出了错误判断（理由：脚本里某段 kill 落在输出被截断处、**实际未生效**）——旧实例还在跑，日志却已经被清空。
- **`github.com:443` 在 `.188` 上实测不可达，但被封的只有它的 git 端点**（2026-10-10 实测）：`curl https://github.com` 超时（rc=28）、`git ls-remote https://github.com/...` rc=124、`gnutls` 报握手失败；而 **`api.github.com` / `raw.githubusercontent.com` / `codeload.github.com` 三个都可达**（REST API 与 raw 取文件照旧能用）⇒ 别据此判"整台机器连不上 GitHub"。**`git 2.20.1 + gnutls` 那串握手报错是"域名被封"的伪装——不要去动 `sslVerify`**（关掉校验也没用，是网络层不通）。
  - **修法（git 取对象）**：走反代 clone `git clone https://ghfast.top/https://github.com/<owner>/<repo>.git`，然后 **`git remote set-url origin <规范 URL>` 把 origin 改回规范 URL**（否则后续 `git fetch` 会白等一轮超时）；再**留一个反代 remote 备用**（`git remote add ghproxy https://ghfast.top/https://github.com/<owner>/<repo>.git`），要拉更新时显式 `git fetch ghproxy`。
- **用 `ssh … 2>&1 | Out-String` 取 base64 会把 stderr 噪声混进通道**（2026-10-09 实测）：本地 `[Convert]::FromBase64String(...)` 抛 `The input is not a valid Base-64 string as it contains a non-base 64 character, more than two padding characters, or an illegal character among the padding characters.`；且**本地文件不存在时 `-match ""` 会假报 MATCH**（空串恒匹配）。
  - **修法三条**：① ssh 侧加 `2>$null`（只在这一处，取 base64 通道时；其它场合仍按上面那条"不要丢弃 stderr"）；② **先正则校验 base64**（`'^[A-Za-z0-9+/=\r\n]+$'`）再解码；③ **MD5 比对前先确认本地文件真的生成了**（`Test-Path` + 非零长度），否则比的是"两个都不存在"。
- **PS 5.1 里 `ssh -n … "echo \$VAR"` 的 `\$` 不是转义**（2026-10-10 实测）：远端收到的是 `echo \`，**输出空行**，并报 `bash: -c: line 0: unexpected EOF while looking for matching '"'`。
  - **修法**：**传给 ssh 的参数一律用单引号**（`ssh -n root@192.168.13.188 'echo $VAR'`），别指望 `\$`。
  - **判断纪律：「输出空」不等于「变量为空」**——先怀疑引号/转义/`2>$null` 吃掉了报错，再怀疑远端真的没设这个变量（本轮据此误判过一次）。
- **远端 / 共享文件可能正被并发写手改**（2026-10-10 实测：目标文件在 **25 分钟内被保存 4 次**，**23500 → 24842 B**）：要审计、复跑或再推送别人**可能还在编辑**的文件时，**先等它稳定 → 取快照 → 记快照 md5 → 只审计并只运行快照**，并用 md5 闸门**拦下中间态推送**；**不要覆盖或删除与自己版本不同的并发产物**，改用**新目录**锁存（本轮用 `/tmp/fv2_lock/`，md5 闸门拦下 2 次中间态推送）。完整配方见 `orchestrating-subagents` §9.17（单一归属，本节只留指针）。

## 6. 不要做什么

- **不要按 §3.4 一条一条顺序跑**——那会把 P1~P4 四条本可并行的 lane 串起来，白等 4.2G 的下载与两仓 clone。**先发 lane，再等 barrier**。
- **不要让两条 lane 写同一个 wheelhouse 的同一组包**：triton-ascend 的 whl 只在 `ascend-triton-ascend` 步骤 ⓪ 下，torch 三件套 / torch_npu 只在 `ascend-torch-npu` 步骤 3 下。
- **不要给子代理放权**：4 条 lane 的子代理只能下载 / clone / 建目录，**不得 `pip install`、不得 `conda activate`、不得 `source set_env.sh`、不得改 `PATH` 或 `/etc`**（§3.3）。
- 不要往 `.188` 的 `/`、`/mnt/share`、`/mnt/weight`、`/tmp`、`/root` 写大文件——**这几个路径全都在同一块系统盘上**（`nvme0n1p2`，多租户共用、长期紧张、随时可能被写满）；**大文件与大环境只写 `/home/vllm`**（独立大容量盘）。**本套 skill 一律不记剩余空间数字，动手前自己 `df -h <目标路径>` 现场取数**。详见 `ascend-server-layout`。
- 不要跳过 CANN 的 `source set_env.sh` 就去装 torch_npu 或编算子。
- 不要为了排障而 `pip install -U triton`（会覆盖 triton-ascend 的文件，见 `ascend-triton-ascend`）。
- 不要在共享机器上把 `MAX_JOBS` 打满、或占用别人正在用的卡（先 `npu-smi info`）。
- **不要把整个 `$CONDA_PREFIX/lib` 加进 `LD_LIBRARY_PATH`**。需要 conda 环境的新版 `libstdc++` 时（`.188` 的 gcc-8 场景），只建一个**只放 `libstdc++` 的 `compat_lib` 目录**前置即可，见 `ascend-torch-npu`。（整目录前置在 `.190` 上有过 `git` 崩的历史记录，2026-09-23 在 `.188` 实测未复现——详见 `ascend-conda-env` 坑 5，别把它当通用结论。）
- 改动用户环境前先想好回滚路径；破坏性动作（删文件、改 `/etc/Ascend`、强推）先确认。

## 7. 维护记录

- **2026-10-22（服务器清单全面复核：三台机器 + `.188` 现状重采）**：
  1. **§1 机器表改为三行并带状态列**：`a3=.188`（可用）、`a3b=.190`（**整机不可达**）、`a5=177.8.21.1`（当时判为不可达，**同日已更正：需先连 A5 VPN**）。同时**证伪旧断言「`.188` load ~20，稳定」**——2026-10-22 实测 `load average: 281.25`（256 核），2026-10-08 也是 ~277；同一份文件 §3.1 早写着 ~277，两处自相矛盾，现统一为「重载机」。
  2. **新增 §1.1「接一台没见过的机器」**：三层（ICMP / TCP / 认证）分开测、`Test-NetConnection` 对不通地址会挂几分钟（改用短超时 `TcpClient`）、别扫全端口、**「连不上」≠「不存在」**（规格只能标 `未采`）。
  3. **`.190` 结论更新**：本机与 `.188` **双向** `ping` 100% 丢包 + TCP 22 超时（各 3 次重试），不是 9-22 那种"重试即可"的假死；保留 10-08 可达记录。
  4. **`.188` 复核通过项**：免密仍有效（`hostname` → `node-zj-110-132`）、密码 `AUTH_OK`（paramiko）、`/dev/davinci*` = 17、`npu-smi` 8 NPU × 2 die 全 `Health OK`、`source env_batch_inv.sh` 后 `torch.npu.is_available()=True` / `device_count()=16`、`/usr/local/Ascend/ascend-toolkit` 是**空目录**（bashrc 第 36 行断链的真因）。
  5. 采集通道再次验证：`scp` + `md5sum` 逐字相符后执行，5 个只读脚本全部一次通过（含中文注释），**没有走 base64**；其中 1 次 `scp` 报 `Connection closed`，原样重试即成功（已写进 §5）。
- **2026-10-08（第四批：§4 补 2 条判据 + §5 补 3 条硬规则 + 1 处再修正，全部实测）**：
  1. **新增 §4「完成标记不是证据」**：lane 脚本的 `LANE_Px_DONE` / `S4_DONE` **失败也照打**（实测两起：P4 clone 失败仍打 DONE、S3 被打断后仍打标记）；判完成只看产物（文件存在/大小/条数、`rc=` 行、真跑过的验收命令）。并补「shell 退出码也不可靠」——该机器每次 ssh 都因 `/root/.bashrc` 那行失效 `set_env.sh` 以 exit 1 结束。
  2. **§5 第一条补全机制**：单引号内的双引号会被本机 PS 5.1 重新转义成 `\"`，远端 bash 收到**字面引号** ⇒ `grep`/`pgrep`/`awk` 模式**静默零匹配**；逐字症状 `bash: -c: line 0: syntax error near unexpected token '('`；本轮复发 **6 次**、两次据此误判"进程已死"。规则收紧为：内联 ssh 只做无引号简单命令，模式匹配一律 base64 推 `.sh`。
  3. **新增 §5「核对最终目的地的 md5」**：只核 `/tmp/x.sh` 的 md5 会让你误以为推送成功——本轮 `source $ROOT/env_sv0230.sh` **静默失败**，整条 S3 在 CANN 变量未设置下运行；写完必须 `md5sum <最终路径>`。
  4. **新增 §5「ssh 里永远不要 `2>$null`」**：丢弃 stderr 会丢掉唯一能解释"进程为何立刻退出"的 traceback（本轮正是它把 `libhccl.so` 真因藏起来）；改为落盘再 grep。
  5. **新增 §5「重启长任务前先确认旧实例死了」**：`pgrep -af <name>` 期望 `(none)`；本轮两个同名实例同写一个日志，新实例截断了旧文件 → 据此误判（脚本里那段 kill 落在输出被截断处、**实际未生效**）。
  6. **再修正上文第 3 条那处 `VLLM_VERSION` 结论**：它只对仍读取该变量的 vllm 版本成立；vllm `v0.23.0` 上该变量已不被读取，`vllm_version_is("0.23.0")` 不设任何变量本就为 `True`（版本线判定）。

- **2026-10-08（执行方式大改：并行编排 + 下发通道勘误，用户要求"大刀阔斧"）**：把 §3 从「一条条按顺序跑」改成**先并行后串行**的编排——新增 §3.1 依赖图与 P1~P4 四条并行 lane（CANN 三包并发下载 / conda 建环境 / torch 栈 whl 预下载到 wheelhouse / 两仓 clone+切 commit）、§3.2 barrier 与"为什么 S1~S3 必须串行"、§3.3 子代理边界（只下不下、写盘白名单、禁止事项）、§3.4 与子 skill 的衔接；§3.4 末补**版本不纠结**纪律（只参考 vllm-ascend 的 requirements，vllm 的不参考，冲突不管）。
  - **本次 `.188` 实测取证**（2026-10-08，全部只读或落在 `/home/vllm`）：`pip download -d <wh>` → `pip install --no-index --find-links <wh>` 离线往返**通过**（`OFFLINE_INSTALL_OK six 1.17.0`），且 wheelhouse 里没有的包在 `--no-index` 下**必然失败**（证明真断网）；三条 `curl` 后台 `&` + `wait` 并发**全部 200**；`raw.githubusercontent.com/.../vllm-main-verified.commit` 免 clone 取到 `ced6857af…`（所以两个 clone 能真并行）；`curl --parallel` / `-Z` **不支持**（本机 curl 7.64），`aria2c` / `axel` **不存在**（并行只能 `&`+`wait`）。
  - **§5 勘误（原规则被证伪）**：旧文写「PowerShell 管道给 ssh 会自己注入 UTF-8 BOM，所以 `tail -c +4` 基本是必需的」——实测本机 `$OutputEncoding` 是**无 BOM UTF-8**（`GetPreamble().Length`=0），管道**不注入 BOM**，`tail -c +4` 会吃掉脚本前 3 字符（把 `#!/bin/bash` 削成 `bin/bash`）；且**多行含中文脚本直推会静默损坏**（丢行 + `确认` → `U+E1BF U+E17B`）。§5 已改为 **base64 通道**并给"先探有无 BOM 再决定剥不剥"的判据。
  - **第二轮（独立子代理对抗性复核后修的 4 处，全部有实证）**：
    1. **P3 由 3 组改为 1+1 组**（`ascend-torch-npu` 步骤 3）：原写法把 `torch-npu==2.12.0` 单独发一组且不带 `--no-deps`，而 torch_npu 依赖 `torch==2.12.0` → pip 会从 PyPI 拉**无 `+cpu` 的 CUDA 版 torch（GB 级）**，与坑 1 的 `+cpu` 纪律相反。改为「torch 三件套 + torch_npu **合为一条命令** + `-c constraints.txt`（`torch==2.12.0+cpu`）」。**约束语义已实测**（`packaging`：`==2.12.0+cpu` 不匹配 `2.12.0`、匹配 `2.12.0+cpu`；`==2.12.0` 匹配 `2.12.0+cpu`）；**两个索引已实测**（whl/cpu 只有 `+cpu` 形态、aliyun 只有无 local label 形态）。
    2. **P2 白名单物理上不成立**（`ascend-conda-env` 步骤 4）：`conda create -p` 只改环境落点、**不改包缓存落点**，共享 `.condarc` 的 `pkgs_dirs=/mnt/share/vllm/conda_pkgs` 在系统盘上 → lane 脚本补 `export CONDA_PKGS_DIRS=$L/conda_pkgs`，并把 `CPKGS` 写进 §3.1 白名单。
    3. **§3.1 标题把未验证写成结论**：删掉"实测各条命令可用"，改为显式「证据边界」块——实测的是**原语**（并发 curl 200、离线往返只验过 `six`、raw 免 clone 可读），**端到端整链没跑过**；§3.2 的 `--no-index` 也从"一律"降为"推荐 + 缺包按在线回退"。
    4. 顺手修掉真缺陷：`vllm` 那条 lane 的重定向原先只罩住最后一条命令（`init/fetch` 日志会丢）→ 改为罩整个子 shell；`<你的目录>` 这类占位符在 bash 里是重定向符（照抄即语法错）→ 全部换成可直接粘贴的 `envbuild` 路径。
    - 另：写进 skill 的 **6 段 lane/串行脚本已逐段 `bash -n` 校验通过**（在 `.188` 上跑，不下载不建环境）。注意 `bash -n` **抓不到占位符类错误**（`<lane>.sh` 语法合法、运行必错），所以占位符要单独清。
  - **第三轮（第二轮复核的回修）**：
    5. **`constraints.txt` 改为单一写者**：§3.1 落点块统一 `echo` 创建，两个下载组（torch 栈 / triton）都改成**只读校验**（`[ -s … ] || exit 1`）。原先两组各自 `echo >` 会构成同一文件双写、且把车道 B 的 pin 硬编码进 triton 组（车道 A 会写出错版本约束）；极端时序下 pip 还可能读到被截断的空文件 → 约束静默失效。
    6. **占位符全族清理**：`<lane>.sh`/`<lane>.log`（§3.3）、`<WORK>`（`ascend-torch-npu` 坑 3）、`<x>`/`<本 skill 目录>`（`vllm-ascend-source-install` §0/§3）、`<name>`/`<user>`（`ascend-conda-env` 步骤 4）全部换成可粘贴的实例值 + 就地警告。并补 §5 的「脚本 >20KB 别内联 base64，改 scp / 分块」。
    7. **`ascend-torch-npu` 步骤 2 与步骤 4 的 `ENVP` 对齐**：步骤 2 原先建 `torch_test/envs/torch_latest`、步骤 4 却用 `envbuild/envs/vllm312`（线性照抄会装进不存在的 env）→ 统一到 `$ROOT/envs/vllm312`，并补 `CONDA_PKGS_DIRS`。
    8. 复核确认：①②③ 三项均已真修好；`conda create -p` 只剩 `~/.conda/environments.txt`（几十字节）在白名单外，已就地标注（机制推断、未实测）。
- **建立（2026-09-23）**：把原 `ascend-vllm-env` 单体 skill **删除并拆为「本总纲 + 7 个子 skill」**——`ascend-server-layout` / `ascend-cann-env` / `ascend-conda-env` / `ascend-torch-npu` / `ascend-triton-ascend` / `ascend-vllm-serve` 六个新建，`vllm-ascend-source-install` 为既有（已同步交叉引用）。旧文件内容按职责重分配，无丢失。
- 本次新增的实装验证：CANN 全新路径安装（合一包 + 独立 toolkit 包两分支）、torch / torch_npu / triton-ascend 商发版本安装。逐条证据见各子 skill 的「坑与修法」。
- **2026-10-08 凭据与免密复核**：两台 root 密码换成新值（旧密码已作废，不要再试），新值只写在 `credentials.txt`、**不写进本正文**，并已用 paramiko 实测 AUTH-OK。免密复核：`.188` 直接通过；`.190` **免密失效**（`Permission denied (publickey,password)`，机器本身可达）→ 用新密码把本机公钥追加进 `/root/.ssh/authorized_keys`（5 → 6 行）后 `ssh -n -o BatchMode=yes root@192.168.13.190` 返回 `zj-131` 恢复。同次勘误：**本机并无 `a3` / `a3b` ssh 别名**，已把 §1 的示例改成直连 IP。
- **2026-10-08（M92 lane：vllm/vllm-ascend 双 v0.23.0 tag + CANN 9.2.0-beta.2 实装，4 处勘误）**：
  1. **§5 的 base64 示例自己就是坏的**（原样照抄会静默损坏脚本）：`(Get-Content -Raw $f)` 在 PS 5.1 按 **GBK** 解码，含中文的 `.py` 推过去后**字节数都变了**（`strip_torch_pins.py` 7343 → 7819），远端 `python` 报 `SyntaxError: invalid non-printable character U+E15E`（`閲屽舰濡` 类乱码）。已改为 `[IO.File]::ReadAllBytes($f)`，并把「**`md5sum` 与本地 md5 一致才算推送成功**」写成硬判据——这一条能同时兜住 GBK 改坏 / CRLF / 截断三种坏法。
  2. `ascend-cann-env` 坑 11 的「公开源最高 = 9.1.0，9.2.0-beta.1/2 全 403」**被证伪**：真因是**桶内目录名不是版本号**（9.2.0-beta.2 在 `CANN 9.2.T3/`，按 `CANN 9.2.0-beta.2/` 探才 403）；Referer 头**非必需**。同时**确认「9.2.0 商发公网不存在」这条结论成立**（同目录下 `…_9.2.0_linux-x86_64.run` 403，对照 beta.2 = 200）。
  3. `ascend-vllm-serve` 坑 4 原写「同理别设 `VLLM_VERSION`」**是错的**：它正是 vllm 版本串非纯 `x.y.z`（脏树 / `VLLM_TARGET_DEVICE=empty` 的 `.empty`）时 `vllm_version_is()` 全线误判的逃生口；不设就崩在 `AttributeError: module 'vllm.v1.engine.utils' has no attribute 'get_physical_gpu_ids_for_local_dp_rank'`。完整机理归 `vllm-ascend-source-install` §5 / §6 坑 10。
      > **2026-10-08 再修正（本条只对「仍读取该变量」的 vllm 版本成立）**：在 vllm `v0.23.0` 上 `VLLM_VERSION` **已不被 `setup.py` 读取**——`grep -n VLLM_VERSION setup.py` 逐字只剩 `VLLM_VERSION_OVERRIDE` 两行（见 `vllm-ascend-source-install` §5.1）；且**不导任何变量时** `vllm_version_is("0.23.0")` 本来就为 `True`（它是**版本线**判定，不是等值判定）。⇒ 别再把它当"必须 export 的逃生口"；该版本的修法是 `VLLM_VERSION_OVERRIDE` 或核对配对版本。
  4. `ascend-conda-env` 补 pip 源限速判据：阿里云**只对 HTTP/1.1** 限到 185 KB/s，同 URL `curl`(HTTP/2) 14.2 MB/s、`curl --http1.1` 181 KB/s、`mirrors.huaweicloud.com`(HTTP/1.1) 7.9 MB/s → 「同 URL 三连对照」是定性方法，不是"网慢"。
