---
name: ascend-server-layout
description: 昇腾服务器目录地图与磁盘红线——找模型在哪、磁盘满了该写哪个盘（a3=.188 默认 / a3b=.190 备用）——.188 只有两块真盘：系统盘 /（/mnt/share、/mnt/weight、/tmp、/root 全压在它上面，多租户共用、长期紧张）与独立大盘 /home/vllm（大文件与大环境唯一推荐落点）；**不记剩余空间数字与空闲 die 号，动手前现场 df -h / npu-smi 取**；模型分两处（/mnt/weight + /home/vllm/weights），另有工作目录约定与现成环境；npu-smi 判空闲，Process 段是 NPU id 不是 die id（判 die 用 Bus-Id）。适用于"找模型在哪 / 新项目和大文件该写哪个盘 / 磁盘满了 / 看哪张 NPU 空闲 / npu-smi 判哪张卡忙 / 复用现成环境 / 工作目录在哪"。不适用：装或换 CANN 版本 → 用 `ascend-cann-env`；conda 环境与 python 版本 → 用 `ascend-conda-env`。
whenToUse: 上机第一步——确认模型与权重在哪、新项目和大文件该写哪个盘、哪张 NPU 空闲、能否复用现成环境时。CANN 见 ascend-cann-env，conda 见 ascend-conda-env，起服务挑卡见 ascend-vllm-serve。模型看不到本节。
---

# 昇腾服务器目录地图 / 模型在哪 / 磁盘红线

**默认机器 `root@192.168.13.188`（`node-zj-110-132`，Debian 10，256 核，**多租户共用**）；备用 `root@192.168.13.190`（`zj-131`，**2026-10-22 整机不可达**）；A5 `root@177.8.21.1`（**需连 A5 VPN 后可达**，见 `univpn-vpn`）。三台的准入状态与复现命令见 `ascend-env` §1。**
**本机 `~/.ssh/config` 里没有 `a3` / `a3b` / `a5` 别名**（2026-10-08 实测 `ssh a3` → `Could not resolve hostname a3`；2026-10-22 复核仍只有两段 Host）：`a3` / `a3b` / `a5` 只是文档代称，**下面所有命令一律直连 IP**（本文件原有的 `ssh a3` 已全部改写为 `ssh root@192.168.13.188`，映射见 `ascend-env` §1）。
从 Windows 驱动远端的硬规则（PowerShell 引号、禁 heredoc、`ssh -n` 与 stdin 互斥）**不在本文件**，见 `ascend-env` §5。

## 何时调用

**加载本 skill 当：**
- 不知道模型 / 权重在哪，或不知道工作目录约定、要新建项目目录。
- 磁盘告警（系统盘快满，`df -h` 见红）、要判断"这个大文件能写哪"。
- 想复用现成环境（`env_batch_inv.sh` / `xmz_0921`）而不是从零搭。
- 要看哪张 NPU 空闲，或怀疑卡被别人占了。**判空闲只认现场 `npu-smi info` 的 `HBM-Usage`——本文件不记、也不许引用任何固定空闲 die 号**（空闲 die 面两小时内能变三次，见步骤 4 ★ 与坑 9）。

**不要用本 skill（转交）：**
- 要装 / 换 / 查 CANN 或版本不对 → 用 `ascend-cann-env`。
- conda 或 python 版本、环境该建在哪个盘 → 用 `ascend-conda-env`。
- 已装好环境要挑卡起服务、处理 LFS 指针模型的运行时问题 → 用 `ascend-vllm-serve`。
- torch / torch_npu 装不上、版本不匹配或 NPU 不可用 → 用 `ascend-torch-npu`。

**前置**：能免密 `ssh` 进 `root@192.168.13.188`（本机无 `a3` 别名，见 `ascend-env` §1）。 ／ **后继**：`ascend-cann-env` → `ascend-conda-env`。

## 前置检查

```bash
# ① 能写哪块盘：★ /mnt/weight、/mnt/share 必须用 df -h <路径> 单独验（它们没有独立挂载点）
ssh -n root@192.168.13.188 "df -h; echo ---; df -h /mnt/share /mnt/weight /home/vllm /tmp"
#   期望：/mnt/share、/mnt/weight、/tmp 回显的挂载点都是 "/"（= 没有独立盘，全压在系统盘上）；/home/vllm 有独立挂载点
#   ★ 具体容量/百分比现场看就行，**本文档故意不记剩余空间数字**（盘是多租户共用的，别人随时可能大量写入）
# ② 卡：npu-smi 25.5.1，8 NPU × 2 chip = 16 个 Ascend910_9382，每 chip HBM 65536MB
#   2026-10-22 现场佐证：soc_version = 253、Board ID 0x71、firmware 7.8.0.2.212、driver 25.5.1；**npu-smi 名字列只打 `Ascend910`**（别以为少个后缀就是别的卡）
#   卡型号/代号以 `python -c "import torch_npu;print(torch_npu.npu.get_soc_version())"` 为准（253 = A3）
ssh -n root@192.168.13.188 "npu-smi info | head -14; npu-smi info | tail -30"
ssh -n root@192.168.13.188 "ls /dev/davinci* | wc -l"      # 期望 17（davinci0..15 + davinci_manager）
```

## 步骤

> **本 skill 是 `ascend-env` §3 编排里的 P0**：先在这里把「能往哪写 / 模型在哪 / 哪张卡空」问清楚，**再把 P1~P4 四条并行 lane 发出去**（目录与磁盘决定 lane 的落点）。并行编排见 `ascend-env` §3.1。

### 步骤 1：先确定"能往哪写"（写任何大文件之前）
目的：避开那块长期紧张的系统盘。**判据只有一条：`df -h <你要写的路径>` 回显的挂载点是 `/` 还是 `/home/vllm`——看挂载点，不看数字。**

> **本文件不写任何剩余空间数字**：这块盘多租户共用，别人随时可能大量写入，任何写死的数字第二天就是错的。
> **每次动手前现场取数**：`df -h <目标路径>`（要的是挂载点 + 当前可用量，而不是和本文档比对）。
> **2026-10-22 状态（只给量级，别当数字引用）**：系统盘 `/` 的 `Use%` 已是**两位数高值（九成以上）**，大盘 `/home/vllm` 仍有**数 T** 余量 ⇒ **「红线」不是理论**：再往 `/mnt/share`、`/mnt/weight`、`/tmp` 写几 GB 就可能把它推到 100%，而写满会连带 ssh 登录、conda、pip 全部失败。

| 路径 | 设备 / 挂载点 | 盘的性质 | 能写大文件吗 |
|---|---|---|---|
| `/home/vllm` | `nvme1n1p3` → LVM `ubuntu--vg-ubuntu--lv` | 独立大容量数据盘 | ✅ **唯一推荐**，写 `/home/vllm/x00886548/<你的项目目录>/`（**占位符别照抄进 bash**，`<` `>` 会被当重定向；实际用如 `envbuild`） |
| `/` | `nvme0n1p2` | 系统盘：多租户共用、长期紧张，随时可能写满 | ❌ 红线 |
| `/mnt/share` | **无独立挂载** → 落在 `/` | 同 `/`（系统盘） | ⚠️ 只放源码/小脚本（现成工作区在此），**别放权重、大 env** |
| `/mnt/weight` | **无独立挂载** → 落在 `/` | 同 `/`（系统盘） | ❌ **假独立盘**，往里写 = 压垮系统盘 |
| `/root` `/tmp` `/opt` `/var` | 全在 `/` | 同 `/`（系统盘） | ❌ |
| `/boot/efi` | `nvme0n1p1` | 小引导分区 | ❌ 别动 |
| `/dev/shm` | tmpfs | 内存盘（容量随内存，重启即失） | ⚠️ 别当存储 |

验证：`ssh -n root@192.168.13.188 "df -h /mnt/weight"` 输出的**挂载点必须是 `/`**（看着像独立盘，其实在系统盘上）；若真出现独立设备名，说明拓扑变了，重新盘点。

### 步骤 2：模型在哪（两处，别只看一处）
```bash
ssh -n root@192.168.13.188 "du -sh /mnt/weight/* /home/vllm/weights/* 2>/dev/null | sort -h"
ssh -n root@192.168.13.188 "ls -la /mnt/weight/Qwen2.5-7B-Instruct"
# LFS 指针判别（★ 必做，0 才是真权重）：期望 0
ssh -n root@192.168.13.188 "head -c 200 /mnt/weight/Qwen2.5-7B-Instruct/model-00001-of-00004.safetensors | grep -c git-lfs"
```

| 路径 | 大小（2026-10-22 实测 `du -sh`） | 备注 |
|---|---|---|
| `/mnt/weight/Qwen2.5-0.5B` | 954M | 真权重；带 `.msc`/`.mv`/`._____temp` → ModelScope 下载 |
| `/mnt/weight/Qwen2.5-7B-Instruct` | 15G | 真权重，4 shard |
| `/mnt/weight/Qwen3-30B-A3B` | 57G | 真权重，16 shard |
| `/home/vllm/weights/Qwen3-0.6B` | 1.5G | 1 shard |
| `/home/vllm/weights/Qwen3-30B-A3B` | 57G | 16 shard（与 `/mnt/weight` 那份同名，两处各一份） |
| `/home/vllm/weights/Qwen3.5-35B-A3B` | 67G | 14 shard，在独立大盘上 |
| `/home/vllm/weights/Qwen3.5-35B-A3B-layer8` | 16G | 4 shard，**层裁剪产物**（见下条） |
| `/home/vllm/weights/DeepSeek-V4-Flash` | 149G | 46 shard |
| `/home/vllm/weights/DeepSeek-V4-Flash-w4a8-mtp` | 151G | 38 shard，量化版 |
| `/home/vllm/weights/DeepSeek-V4-Flash-BF16-layer4` | 64G | 7 shard，层裁剪 |
| `/home/vllm/weights/DeepSeek-V4-Flash-BF16-layer3` | 39G | 10 shard，层裁剪 |
| `/home/vllm/weights/Qwen3.5-122B-A10B` | 234G | 39 shard |
| `/home/vllm/weights/MiniMax-M3` | 796G | 59 shard，**大盘上最大的一份**（旧文写 258G 已作废：该目录被扩过） |
| `/home/vllm/weights/Qwen3.8-Flash-Next` | 336G | 131 shard |
| `/home/vllm/weights/Qwen3.8-Flash-Next-layer8` | 143G | 77 shard，层裁剪 |
| `/home/vllm/Qwen3-235B-A22B` | 438G | **在 `/home/vllm` 根下、不在 `weights/`**（分片数未复核） |

`/home/vllm/weights` 合计约 **2.0T**（2026-10-22 实测）。**别只看 `weights/`**：`/home/vllm` 根下还有多个租户目录（同次 `du -sh /home/vllm/*`：`skhalid` 699G、`w00893744` 331G、`fyf` 123G、`x00886548` 119G，加上根下的 `Qwen3-235B-A22B` 438G）——判「盘上还剩多少、谁占的」必须全量看这一层。

验证：`du` 输出有该目录且体积 GB 级 + `grep -c git-lfs` = **0**。`*-layer3/-layer4/-layer8` 后缀目录（如 `Qwen3.5-35B-A3B-layer8`）**未验证：**内部是否为完整可加载权重（可能是层裁剪/调试产物），别直接拿去起服务。**2026-10-22 复核**：这些 layer 目录确实装着 4–77 个 `*.safetensors` 分片（不是空壳），但「能否直接 `vllm serve`」仍未验证。
**分片数比体积更能判"是不是完整权重"**：`for d in /home/vllm/weights/*; do echo "$(ls "$d"/*.safetensors 2>/dev/null | wc -l) $d"; done | sort -n`——同族模型分片数差一个量级（如 4 vs 131）时，少的那份基本就是裁剪/半截产物。

**未下载权重时也要能拿官方逐分片字节数**（本地只有 HF 元数据，没有权重；想先判"这仓要占多少盘 / 分几片 / 每片覆盖哪些层"时）：

- HF cache 目录 `~/.cache/huggingface/hub/models--<org>--<name>/` 在**只下了元数据**时：`trees/*.json` 里就有**逐文件字节数**，`snapshots/<rev>/*` 是指向 `blobs/` 的符号链接，`snapshots/<rev>/model.safetensors.index.json` 是**真文件**（含 `weight_map`，可判每个分片覆盖哪些层）。
- 本轮实测：拿到官方 **96 分片**逐文件字节数 + `metadata.total_size = 1,560,860,324,864`（≈1.56 TB）。
  ```bash
  python3 -c "import json,glob;d=json.load(open(glob.glob('<hub>/trees/*.json')[0]));print(len(d['files']))"
  ```
- ⚠ **别用 `find -printf '%s'` 量这些链接**：它报的是 **link 长度**。实测官方 `model.safetensors.index.json` 显示 **76 B**，几乎被误判成空壳，真值 **59,764,096 B**。⇒ **必须 `find -L`**：`find -L <dir> -printf '%y %s %p -> %l\n'`（`-L` 跟随符号链接）才拿到真体积；或干脆用上面 `trees/*.json` 的官方字节数，不碰文件系统。
- 要往下算"几张卡 / 显存够不够" → 用 `ascend-moe-ep-capacity-planning`（本文件只管"盘上有什么、多大"）。

### 步骤 3：工作目录约定 + 复用现成环境（优先复用，别重建）
- 源码/构建/验证工作区：`/mnt/share/x00886548/workspace/<项目名>/`（该盘是长期紧张的系统盘，**新项目建议改放 `/home/vllm/x00886548/`**；动手前 `df -h` 看当前余量）。
- 环境搭建脚本与日志：`workspace/<项目名>/` 根 + `xmz_0921/`（纯日志：`01_create_env.log` … `19_solve_test.log` + `env.sh`）。
- 大权重：`/home/vllm/weights/` 或 `/home/vllm/x00886548/` 下。构建脚本命名模式：`build188_<阶段>_<组件>.sh`。
- **`.188` 现成已验证工作区** `/mnt/share/x00886548/workspace/batch_inv_qwen35/`（7.5G）：`BUILD_REPORT.md`、`env_batch_inv.sh`（一键激活）、`bi_validation/`、`compat_lib/`、`vllm/`、`vllm-ascend/`。

```bash
# 一键激活（vllm 84030bbe + vllm-ascend bf439330c，批次不变性版，2026-09-21 编译）
ssh -n root@192.168.13.188 "source /mnt/share/x00886548/workspace/batch_inv_qwen35/env_batch_inv.sh && python -c 'import vllm,torch_npu;print(torch_npu.npu.is_available())'"
```
验证：打印 `True`（**2026-10-22 复跑仍通过**：`ASCEND_HOME_PATH=/mnt/share/x00886548/cann/cann_9_1_0/cann-9.1.0`、`python` = `xmz_0921/bin/python`、`npu_ok True 16`）。已验证组合（2026-09-22 实测）：python 3.12.14 / torch 2.10.0+cpu / torch_npu 2.10.0.post4 / triton 3.2.0 / triton-ascend 3.2.2 / numpy 1.26.4 / transformers 5.14.1 / fastapi 0.123.10 / starlette 0.50.0 / batch_invariant_ops 1.0.0。共享 conda 装机脚本 `/mnt/share/x00886548/workspace/setup_conda.sh`（幂等），conda 细节见 `ascend-conda-env`。
> **其它现成环境（2026-10-22 实测 7 个，全部 py3.12）**：`/home/vllm/x00886548/{batch_inv_glm52,xmz_1009_k3,vllm_0230,zero_v0230,sv0230}/envs/*`（多为 `vllm312`，3.12.15）+ `/mnt/share/vllm/conda_envs/xmz_0921`（3.12.14）。**清单与建/换版本规则归 `ascend-conda-env`**，本节只提醒「先 `ls` 别急着重装」。
> `.190`（备用）历史记录（**2026-09-23 与 2026-10-22 均未能复核；10-22 整机不可达**）：工作区 `/home/vllm/x00886548/vllm_build_0917`（`env.sh`、编号脚本 `07/21/24/37/43/52_*.sh`、`models/Qwen3-0.6B` 真权重 1.5G），gcc 10.2，64 核，vllm-ascend `cb79183`。其目录/磁盘/NPU **全部未查清**，不得沿用或编造。

### 步骤 4：看哪张 NPU 空闲
```bash
ssh -n root@192.168.13.188 "npu-smi info | head -14; echo ===; npu-smi info | tail -30; echo ===; uptime; who | wc -l"
```
- **判空闲**：`HBM-Usage(MB)` 形如 `used / 65536`。`used ≈ 2900–3200` 且 `AICore(%) = 0` = **空闲**（~3G 是驱动基线）；`used` 上万 = 有负载；再核对进程段该 NPU 是否列出 `Process id/name`。
- ★ **不要记录、也不要向任何人给出"固定的空闲 die 号"**（这是步骤 1「不记剩余空间数字」在 **die 维度**上的同一条纪律）。空闲 die 面**变化极快**：2026-10-10 实测同一台 `.188` **两小时内至少变三次** —— 10:21 空闲仅 `Phy 8~15`；10:59 见到 `Phy 0~3`（其中 **4 已被占**，51652/65536）；11:00 实拍空闲 `Phy 0,1,2,3,8~15` **共 12 张**，占用者是**他人作业**的 `VLLMWorker_TP`（各 ≈51 GB）。
  ⇒ **判空闲只认现场 `npu-smi info` 的 `HBM-Usage`（明显低于 65536）**：与本文档、与上一次快照、与别人的结论**一律比对不得**；任何 die 号写进交付物/派活指令之前都要**当次重取**。
- 2026-09-23 实测 `.188`：**只有 NPU 0 被占**（`| 0 | 0 | 174904 | VLLMWorker | 28907 |`，HBM 32123/65536），**NPU 1–7 全空闲**（HBM 2874/65536）。`ls /dev/davinci* | wc -l` = 17，`npu-smi info | grep -c 'Ascend910'` = 16。
- ⚠️ **Process 段的 `NPU` 列是 NPU id、不是扁平 die id**（一张 NPU 含 2 个 chip/die）→ 拿那一列判"第几号 die 忙"会判错。
- ⚠️ **读反的后果（2026-10-09 Lead 实测踩坑并勘误一次）**：照 Process 段**行首两列**（= `NPU id` + `Chip`，**不是 die id**）判"哪几个 die 空闲"，会**把忙/闲整批读反**——实测把 8/9/10 三张空 die 读成"忙"、把真正忙的读成"空闲"。**正确算法**：die 号取**主表的 `Phy-ID` 列**，再用 **`Bus-Id`** 对齐到 Process 段（就是下面那条）。本机**2026-10-09 一次快照**（**只是快照、不是固定答案**，见上一行 ★）：`Phy-ID` **8 / 9 / 10** 空闲（各 3102 / 2868 / 3108 MB of 65536）；**0–7 与 11–15 忙**（各约 56362–56657 / 65536，由 `VLLMWorker_TP` 每张占 53.5 GB、`VLLMEngineCor` 占 53513 持有）。
- ⚠️ **误读的来源**：进程是**按 NPU 粒度**报的（一个 NPU 含 2 个 die）——对 NPU 4 跑 `npu-smi info` 会打印 `No running processes found`，看着像"整张 NPU 空"，**不能据此判 die 忙闲**，仍要回到 `Phy-ID` + `Bus-Id`。**后果举例**：把验收任务派到忙 die 上会 OOM，而该 OOM **不是环境问题**，极易被误判成"环境没搭好"。
- **要判某个物理 die 上有没有进程，用 HBM 段的 `Bus-Id`**（形如 `0000:F4:00.0`）唯一匹配最稳：同一个 Bus-Id 在 NPU 段、HBM 段、Process 段都能对上，不受 id 编号口径影响。
  - 验证：`npu-smi info | grep -n 'Bus-Id'` 先定位 HBM 段，再拿该 Bus-Id 去 Process 段反查有无同名行。
- `.188` 是**多租户共用机**：`uptime` 与 `who` 现场取，**本文件不记 load 数字**。两条实测口径供参考（都只是快照）：2026-10-22 `load average: 281.25, 280.32, 278.82`、`who | wc -l` = 6（来源 `192.168.201.196` / `.206.55` / `.202.193` 等）；2026-09-23 是 `up 22 days, 11 users, load ~17–28`。⇒ **这台机器的 load 会在 17 与 280 之间大幅漂移，别人在跑大作业时它就是重载机**；挑卡前同时看 `uptime`（load）、`npu-smi`（HBM）与 `who`（几个会话），→ 挑卡、限 `MAX_JOBS`、别杀别人的进程。起服务挑卡见 `ascend-vllm-serve`。

### 步骤 5：下载权重（写成"能复制就对"的形式）
```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1      # ★ 必须显式设，全局为空
REPO_ID=Qwen/Qwen3-32B                       # ← 换成目标仓；**变量形式，别把 <repo_id> 尖括号粘进 shell**
NAME=qwen3-32b
/root/miniconda3/bin/hf download "$REPO_ID" --local-dir /home/vllm/weights/"$NAME"   # hf 1.32.0（xmz_0921 里也叫 hf）
# 历史可用写法（/root/miniconda3 里 hf 0.36.2）：
/root/miniconda3/bin/huggingface-cli download --resume-download --hf-mirror https://hf-mirror.com \
    "$REPO_ID" --local-dir /home/vllm/weights/"$NAME" --local-dir-use-symlinks False
```
验证：落盘后 `ls -la /home/vllm/weights/$NAME/*.safetensors` 是 GB 级，且 `head -c 200 <首个 safetensors> | grep -c git-lfs` = 0。

## 坑与修法

| # | 错误原文 / 现象 | 修法 |
|---|---|---|
| 1 | `df -h /mnt/weight` → 挂载点是 `/dev/nvme0n1p2 … /`——**看着像独立盘，其实在系统盘上** | 写大文件前**永远先** `df -h <目标路径>`（认挂载点，不认路径名）；大权重只写 `/home/vllm/` |
| 2 | `modelscope --help` → `File "/usr/local/lib/python3.7/dist-packages/modelscope/utils/file_utils.py", line 238 while byte_chunk := f.read(buffer_size): ^ SyntaxError: invalid syntax` | `/usr/local/bin/modelscope` 装在 **py3.7** dist-packages，代码用了 3.8+ 海象运算符 → **该 CLI 已损坏，别用**。改用 conda env 里 `pip install modelscope`，或走 `hf download` |
| 3 | 不关 xet 时下载报 **401**（`cas-server.xethub.hub.co`）；全局 `HF_ENDPOINT=[]`、`HF_HOME=[]`（无任何全局镜像配置） | 每次显式 `export HF_ENDPOINT=https://hf-mirror.com` **且 `export HF_HUB_DISABLE_XET=1`** |
| 4 | `grep -rln <pat> /mnt/share/x00886548/workspace` **120s 超时**（目录含 conda site-packages，数十万文件） | 加 `--include=*.sh --include=*.md` 限定；或改查 `/root/.bash_history`、`/mnt/share/x00886548/miniconda3/.condarc`。同理**别** `du -sh /`、别全盘 `grep -r` |
| 5 | 模型是 git clone 的 LFS 指针（134B）时，起服务报 `parse_safetensors_file_metadata` **MemoryError**（头部长度字段按指针文本解析成天文数字） | 先判别：`ls -la *.safetensors` 看是否 GB 级 + `head -c 200 <file> \| grep -c git-lfs`（**0 才是真权重**，`.188` 实测 `/mnt/weight` 全部为 0 ✅）；运行时处理见 `ascend-vllm-serve` |
| 6 | `ssh root@192.168.13.188` stderr 每次一行 `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory` | 真实断链：`/usr/local/Ascend/ascend-toolkit` 是**空目录**（2026-10-22 复核：无 `set_env.sh`、无 `latest` 软链）。**默认路径的噪声，忽略**；CANN 用 `/mnt/share/x00886548/cann/cann_9_1_0`，见 `ascend-cann-env` |
| 7 | `ssh root@192.168.13.190` → `ssh_dispatch_run_fatal: Connection to 192.168.13.190 port 22: Connection timed out` | 2026-09-23 实测 9 次尝试全败；**2026-10-22 复核升级为「整机不可达」——`ping` 100% 丢包（本机与 `.188` 双向），不是"重试即可"的 sshd 假死**。排查顺序见 `ascend-env` §1；**`.190` 全部条目标「未复核」，不得编造**；降级用 `.188` |
| 8 | `/home/vllm/weights` 归 root 但同盘混着他人目录（`skhalid` 699G / `w00893744` 331G / `fyf` 123G） | **写自己的东西前先确认命名空间**，一律用 `/home/vllm/x00886548/`，别覆盖同名他人目录 |
| 9 | 照抄"上一轮哪几张 die 空闲"去挑卡 → 挑到别人刚占上的 die（`.188` 实测**两小时内空闲 die 面至少变三次**：`Phy 8~15` → 含 `0~3`（4 已被占 51652/65536）→ `0,1,2,3,8~15` 共 12 张） | **不记、也不信任何固定 die 号**：动手前现场 `npu-smi info`，只按 `HBM-Usage`（明显低于 65536）判空闲，并用 `Bus-Id` 对齐复核；写进派活指令前再取一次 |

## 不要做什么

- 不要往 `/`、`/mnt/share`、`/mnt/weight`、`/tmp`、`/root`、`/opt` 写大文件或大 conda env——**它们全在同一块系统盘上**（`nvme0n1p2`，多租户共用、长期紧张、随时可能被写满）。
- 不要把 `/mnt/weight` 当独立大盘来放新权重（它只是 `/` 上的一个普通目录）。
- 不要用 `/usr/local/bin/modelscope`（py3.7 语法错，见坑 2）。
- 不要依赖 `/usr/local/Ascend/ascend-toolkit`（断链壳）。
- 不要在 `.188` 上杀别人的进程 / 占别人正在用的卡 / 把 `MAX_JOBS` 打满（多租户共用，当前几个会话现场 `who | wc -l` 看：2026-10-22 是 6 个）。
- 不要对 `.190`（2026-10-22 整机不可达）或 A5（`177.8.21.1`，需先连 A5 VPN）编造任何目录、磁盘、模型、NPU 事实。

## 验收标准

1. `ssh -n root@192.168.13.188 "df -h /mnt/weight /home/vllm"` 输出的挂载点分别是 `/` 与 `/home/vllm`；**剩余空间数字现场取、不与文档比对**（本文件故意不记数字），并能说出当前余量大概是多少。
2. 你能说出"新权重该写 `/home/vllm/weights/<name>`"，并给出该路径的 `df -h` 证据。
3. 模型盘点命令返回 `/mnt/weight` 3 个 + `/home/vllm/weights` **12 个以上**目录（2026-10-22 实测 13 个），LFS 判别 `grep -c git-lfs` = 0。
4. `npu-smi info` 能读出 16 个 `Ascend910`，并明确报出"哪几个 NPU 的 HBM ≈ 3000/65536 且 AICore 0"（= 空闲），**且把这些 die 号标注成"现场快照"**——交付物里不得出现"固定空闲 die 号"（见步骤 4 的 ★ 条）。
5. `source .../batch_inv_qwen35/env_batch_inv.sh` 后 `python -c "import vllm, torch_npu"` 无报错。
6. 交付中每条 `.190` 事实都带「未复核」，每条推断都带「未验证：」。
