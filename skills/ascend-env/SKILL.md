---
name: ascend-env
description: 昇腾环境入口总纲：进机器 → 目录/CANN/conda/torch/triton/vllm 的顺序与三层验收。适用于"在昇腾上装环境 / 不知先做哪步 / 该用哪个子 skill / 机器进不去或 ssh 假死"。
whenToUse: 任务涉及 192.168.13.188/.190 上的昇腾环境搭建、升级或排障，或需要决定"该用哪个子 skill"时，先加载本总纲，再由它指向具体子 skill。
---

# 昇腾 NPU 环境总纲

**这是入口 skill，不是操作手册。** 本文件只负责三件事：**机器怎么进**、**该按什么顺序调用哪个子 skill**、**全局验收与共用硬规则**。具体步骤一律在子 skill 里，别在本文件里找细节。

## 何时调用

**加载本 skill 当：**
- 要在 `a3` / `a3b` 上从零搭昇腾环境，或不知道先做哪一步、该用哪个子 skill。
- 要按顺序调度：服务器目录 → CANN → conda → torch_npu → triton-ascend → vllm 安装 → 起服务。
- 需要全局三层验收（`npu-smi` / `torch.npu.is_available()` / `NPUPlatform`），或要 `ssh` 从 Windows 驱动远端（避免 PowerShell 引号、heredoc 导致的静默失败）。

**不要用本 skill（转交）：**
- 目录地图、磁盘红线、模型在哪、哪张卡空闲 → 用 `ascend-server-layout`。
- 装 / 换 / 查 CANN → 用 `ascend-cann-env`；conda 与 python 版本 → 用 `ascend-conda-env`。
- torch / torch_npu / triton-ascend / vllm-ascend 安装 → 用 `ascend-torch-npu`、`ascend-triton-ascend`、`vllm-ascend-source-install`；起服务跑推理 → 用 `ascend-vllm-serve`。
- 卡在本机 PowerShell 命令本身的坑（编码 / 计数 / BOM / PS7 语法） → 用 `pwsh-on-windows`。

**前置**：无（本 skill 是入口，先把 §1 的机器访问与 §5 的远端硬规则读掉）。 ／ **后继**：`ascend-server-layout` → `ascend-cann-env` → `ascend-conda-env`。

## 1. 机器与访问

| 机器 | ssh 别名 | 主机名 / 系统 | 角色 |
|---|---|---|---|
| `root@192.168.13.188` | **`a3`** | `node-zj-110-132` / Debian 10，256 核 | **默认**（load ~20，稳定，16 die A3） |
| `root@192.168.13.190` | `a3b` | `localhost.localdomain` / **openEuler 22.03 LTS-SP4**，64 核 | 备用（**2026-11-09 复核：机器已重装，系统由 Debian 11 换成 openEuler，root 口令改为 `Dauto1!2@`，公钥已重配，实测可达、load ~25、8 NPU / 16 die**；旧镜像上的 ssh 假死见下方注） |

```bash
ssh -n -o BatchMode=yes a3 "hostname; npu-smi info | head -12"     # 免密已配好，直接用
```

- 密码 fallback：本 skill 目录的 `credentials.txt`（正常情况下用不到；换机器 / 公钥被清时才用）。
- **`.190` 的 ssh 假死（旧镜像现象，2026-11-09 重装后未复现）**：`ssh_dispatch_run_fatal: Connection to 192.168.13.190 port 22: Connection timed out`（卡在 `expecting SSH2_MSG_KEX_ECDH_REPLY`）是 load ~90 导致 sshd 排不上 CPU，**多数情况重试即可，不是宕机**（2026-09-22 实测同一分钟内先连败 6 次、随后连胜 4 次）。排查顺序：`ping` → TCP 22 → 读 sshd banner → 再 ssh。**但 2026-09-23 那次是连续 9 次全败（见上表），别把「重试就行」当成必然。**
- **`.188` 每条 ssh 都会在 stderr 打一行** `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory`。这**不是偶发噪声，是真实断链**（2026-09-23 复验：`readlink -f /usr/local/Ascend/ascend-toolkit/latest` 返回空，`latest -> /usr/local/Ascend/cann-9.1.0/cann` 而该目录不存在）。
  - 影响范围**仅限「默认路径」**：`.188` 真正在用的 CANN 9.1.0 在 `/home/x00886548/env/cann/cann_9_1_0`，只要显式 source 它就不受影响；`/usr/local/Ascend/cann-9.0.0/set_env.sh` 是另一套确实可用的旧安装。
  - **别依赖 `/usr/local/Ascend/ascend-toolkit`**（它只是个兼容软链壳）。修法与判据见 `ascend-cann-env`。

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

## 3. 标准顺序（从零到能跑模型）

1. **进机器、看目录与磁盘** → `ascend-server-layout`（先知道模型在哪、能往哪写）
2. **CANN 就绪**（`source <path>/cann/set_env.sh` + `nnal/atb/set_env.sh`）→ `ascend-cann-env`
3. **conda 环境就绪** → `ascend-conda-env`
4. **torch 栈就绪**（torch → torch_npu → triton-ascend，顺序不能换）→ `ascend-torch-npu`、`ascend-triton-ascend`
5. **vllm + vllm-ascend 就绪** → `vllm-ascend-source-install`
6. **起服务 / 冒烟** → `ascend-vllm-serve`

**已有环境优先复用，别重建**：`.188` 上 `source /home/x00886548/work/batch_inv_qwen35/env_batch_inv.sh` 就能拿到一套已验证的 vllm + vllm-ascend（清单见 `ascend-server-layout`）。

## 4. 全局三层验收（逐层来，别一上来就跑模型）

```bash
npu-smi info | head -12                                    # ① 卡在、驱动在
python3 -c "import torch, torch_npu; print(torch.npu.is_available(), torch.npu.device_count(), torch.npu.get_soc_version())"   # ② 期望 True 16 253
python3 -c "from vllm.platforms import current_platform as p; print(type(p).__name__, p.device_type)"                          # ③ 期望 NPUPlatform npu
```

- ② 的 `253` = A3（soc version），`16` = 16 die。
- 每层的完整判据、期望值、常见报错见对应子 skill。**②不过就别做 ③**。

## 5. 从 Windows 驱动远端（所有子 skill 共用；违反会**静默失败**）

- **内联 ssh 命令里禁用 `<`、`"`、`$()`**：PowerShell 会解析错误或吃掉内层引号（实测 `grep -E "a|b"` 的引号被剥掉，远端把 `|b` 当成了管道）。
- 复杂命令一律**本地写 .sh/.py → 管道传过去**：

  ```powershell
  (Get-Content -Raw .\x.sh) -replace "`r`n","`n" | ssh a3 "tr -d '\r' | tail -c +4 > /tmp/x.sh"
  ssh -n a3 "bash /tmp/x.sh"
  ```

  **PowerShell 管道给 ssh 会自己注入 UTF-8 BOM**（不是源文件带的），所以这个 `tail -c +4` 基本是必需的（否则 bash 报 shebang 错）；推**含中文**的脚本还要先 `$OutputEncoding=[Text.Encoding]::UTF8`。
- **heredoc 只在「脚本先落盘、再执行」时可用**。上面那种 `... | ssh a3 "tr -d '\r' | tail -c +4 > /tmp/x.sh"` + `ssh -n a3 "bash /tmp/x.sh"` 的模式下，脚本内的 heredoc（`python - <<'PY'`）**完全正常**，本套件多个 skill 的示例都这么写。
  **禁止的是把带 heredoc 的脚本直接经 ssh stdin 送进去**（`ssh a3 "bash -s" < x.sh`、`cat x.sh | ssh a3 bash`）：heredoc 会与脚本本身争抢 stdin，**永久挂起且不报错**。
- **`ssh -n` 与「脚本走 stdin」互斥**：`-n` 只用于执行**远端已存在的文件**；`$body | ssh a3 "tr -d '\r' | bash -s"` 这种写法**绝不能加 `-n`**——stdin 被 `/dev/null` 占掉后脚本空跑且**不报错**，你只会看到输出为空。
- 长任务：`ssh -n a3 "setsid nohup bash /path/x.sh > /path/x.log 2>&1 < /dev/null &"`，然后轮询日志；别把长任务塞进一条会超时的 ssh。
- 读远端中文文件/脚本一律显式 UTF-8（`[System.IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)`）；PowerShell 5.1 默认按 GBK 解码，会把中文读成乱码。
- 需要密码登录时用本机 `python` 的 **paramiko**（已装 5.0.0）非交互式登录，比找 sshpass 可靠。
- **查「谁占着卡 / 谁占着文件」时，你自己的 ssh 包装进程必然自匹配**：`grep -l <pat> /proc/[0-9]*/cmdline` 这类命令的 cmdline 里就含整条命令串，于是 `bash -c ...` 包装进程会被自己命中，得出**假阳性**。必须再用 `ps -ef | grep -v grep` 与 `ls -l /proc/<pid>/fd/` 交叉复核才能判真占用（实测踩过：一度以为 `pid 140974` 是残留安装进程，实为自己那条 ssh）。

## 6. 不要做什么

- 不要往 `.188` 的 `/`、`/mnt/share`、`/mnt/weight`、`/tmp`、`/root` 写大文件——**这几个路径全都在同一块盘上**（`nvme0n1p2` 2.9T，已 96%，仅剩 139G）；**唯一能写大文件的是 `/home/vllm`**（6.9T，剩 1.6T）。详见 `ascend-server-layout`。
- 不要跳过 CANN 的 `source set_env.sh` 就去装 torch_npu 或编算子。
- 不要为了排障而 `pip install -U triton`（会覆盖 triton-ascend 的文件，见 `ascend-triton-ascend`）。
- 不要在共享机器上把 `MAX_JOBS` 打满、或占用别人正在用的卡（先 `npu-smi info`）。
- **不要把整个 `$CONDA_PREFIX/lib` 加进 `LD_LIBRARY_PATH`**。需要 conda 环境的新版 `libstdc++` 时（`.188` 的 gcc-8 场景），只建一个**只放 `libstdc++` 的 `compat_lib` 目录**前置即可，见 `ascend-torch-npu`。（整目录前置在 `.190` 上有过 `git` 崩的历史记录，2026-09-23 在 `.188` 实测未复现——详见 `ascend-conda-env` 坑 5，别把它当通用结论。）
- 改动用户环境前先想好回滚路径；破坏性动作（删文件、改 `/etc/Ascend`、强推）先确认。

## 7. 维护记录

- **建立（2026-09-23）**：把原 `ascend-vllm-env` 单体 skill **删除并拆为「本总纲 + 7 个子 skill」**——`ascend-server-layout` / `ascend-cann-env` / `ascend-conda-env` / `ascend-torch-npu` / `ascend-triton-ascend` / `ascend-vllm-serve` 六个新建，`vllm-ascend-source-install` 为既有（已同步交叉引用）。旧文件内容按职责重分配，无丢失。
- 本次新增的实装验证：CANN 全新路径安装（合一包 + 独立 toolkit 包两分支）、torch / torch_npu / triton-ascend 商发版本安装。逐条证据见各子 skill 的「坑与修法」。
