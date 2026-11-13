---
name: ascend-server-layout
description: 昇腾个人根与目录红线：环境/项目/数据放哪、模型软链、npu-smi 选卡。适用于"新项目写哪个盘 / 环境放哪 / 磁盘满了 / 哪张 NPU 空闲 / 复用现成环境"。
whenToUse: 上机第一步——确认个人根 /home/x00886548 的落位、模型与数据集公共空间、新项目/脚本/环境各写哪里、哪张 NPU 空闲、能否复用现成环境时。CANN 见 ascend-cann-env，conda 见 ascend-conda-env，起服务见 ascend-vllm-serve。
---

# 昇腾服务器个人根 / 目录地图 / 磁盘红线

**默认 `ssh a3` = root@192.168.13.188（`node-zj-110-132`，Debian 10，256 核，多租户共用）；备用 `ssh a3b` = root@192.168.13.190（`localhost.localdomain`，openEuler 22.03，64 核）。**
从 Windows 驱动远端的硬规则（PowerShell 引号、禁 heredoc、`ssh -n` 与 stdin 互斥）不在本文件，见 `ascend-env` §5。

## 何时调用

**加载本 skill 当：**
- 要新建项目 / 脚本 / 环境目录，不确定该写哪块盘。
- 不知道 `/home/x00886548`、`env/`、`work/`、`agent/` 各放什么。
- 不知道模型权重 / 数据集在哪，或要判断"这个大文件能写哪"。
- 磁盘告警（`/` 已 96%）、想复用现成环境（`batch_inv_qwen35` / `xmz_0921`）。
- 要看哪张 NPU 空闲，或怀疑卡被别人占了。

**不要用本 skill（转交）：**
- 要装 / 换 / 查 CANN 或版本不对 → 用 `ascend-cann-env`。
- conda 或 python 版本、环境该建在哪个盘 → 用 `ascend-conda-env`。
- 已装好环境要挑卡起服务、处理 LFS 指针模型 → 用 `ascend-vllm-serve`。
- torch / torch_npu 装不上、版本不匹配或 NPU 不可用 → 用 `ascend-torch-npu`。

**前置**：能 `ssh a3`（免密已配）。 ／ **后继**：`ascend-cann-env` → `ascend-conda-env`。

## 前置检查

```bash
# ① 个人根与盘：先确认 /home/x00886548 落在哪块盘
ssh -n a3 "ls -ld /home/x00886548; readlink -f /home/x00886548; df -h /home/x00886548 / /home/vllm"
#   .188 期望：lrwxrwxrwx ... /home/x00886548 -> /home/vllm/x00886548；盘是 6.9T 那个
#   .190 期望：drwxr-xr-x ... /home/x00886548；盘是 openeuler-home 6.9T
# ② 公共空间入口（软链指向本机公共盘）
ssh -n a3 "ls -l /home/x00886548/models /home/x00886548/datasets"
# ③ 卡：npu-smi 25.5.1，8 NPU × 2 chip = 16 个 Ascend910_9382，每 chip HBM 65536MB
ssh -n a3 "npu-smi info | head -14; npu-smi info | tail -30"
ssh -n a3 "ls /dev/davinci* | wc -l"      # 期望 17（davinci0..15 + davinci_manager）
```

## 步骤

### 步骤 1：个人根 /home/x00886548 —— 唯一工作入口
**规矩（一句话）**：工作内容（项目、脚本、agent 中间件、环境、日志）全部放 `/home/x00886548`；模型权重 / 数据集放公共空间，个人根里只留 `models` / `datasets` 两个软链入口。

| 路径 | 用途 | 说明 |
|---|---|---|
| `env/` | **环境专放** | 所有环境只建这里，别再散到 `/mnt/share`、`/tmp`、项目目录 |
| `env/conda3/` | conda base 安装根 | `.188` 是实体（从 `/mnt/share/x00886548/miniconda3` 迁入）；`.190` 共用 `/mnt/share/miniconda3` |
| `env/conda_envs/<name>/` | conda 环境 | `conda create -p /home/x00886548/env/conda_envs/<name>` |
| `env/venvs/<name>/` | python venv | 非 conda 的隔离环境 |
| `env/cann/<版本>/` | CANN 多版本 | `.188` 现有 `cann_9_1_0/` |
| `env/pkgs/` | conda/pip 缓存 | `pkgs/conda`、`pkgs/pip` |
| `env/env.sh` | 统一入口 | `source` 后得到 `XH`/`XH_ENV`/`XH_WORK`，并载入 conda |
| `work/<项目>/` | 项目工作区 | 一个项目一个目录 |
| `agent/scripts/` `agent/bin/` `agent/lib/` | agent 生成的脚本 / 小工具 / 中间件 | 可复用脚本放这里，别写 `/tmp` |
| `agent/logs/` | agent 运行日志 | |
| `data/` `tmp/` `logs/` | 个人数据 / 临时 / 通用日志 | `tmp` 可清 |
| `models` → 公共权重盘 | 只读用 | `.188`/`.190` 都指向 `/home/vllm/weights` |
| `datasets` → 公共数据集盘 | 只读用 | `.188` → `/mnt/dataset`；`.190` → `/mnt/share/dataset` |

**建 / 修结构（幂等脚本，本 skill 自带 `scripts/init-home-layout.sh`）**：
```bash
# 本机 Windows 上：先 scp 脚本（别用 ssh 内联 base64，长脚本会被截断）
scp "D:\...\skills\ascend-server-layout\scripts\init-home-layout.sh" root@192.168.13.188:/tmp/
ssh -n root@192.168.13.188 "bash /tmp/init-home-layout.sh --root /home/x00886548 \
  --link-target /home/vllm/x00886548 --models /home/vllm/weights --datasets /mnt/dataset"
# 只检查不写：加 --check；末尾打印 RESULT: PASS/FAIL
```
验证：`ls /home/x00886548` 有 `env work agent data tmp logs models datasets README.md`；`source /home/x00886548/env/env.sh` 后 `echo $XH` = `/home/x00886548`。

**各机落位（2026-11-10 实测）**：

| 服务器 | 个人根形态 | 公共模型 | 公共数据集 | 备注 |
|---|---|---|---|---|
| `.188`（a3） | **软链** → `/home/vllm/x00886548` | `/home/vllm/weights`（2.8T，20 个模型） | `/mnt/dataset`（Math-500） | `/home` 在 96% 的系统盘上，**不能**建真实目录 |
| `.190`（a3b） | **真实目录**（`/home` 6.9T） | `/home/vllm/weights`（305G）+ `/mnt/weight`（NFS 281T 公共权重农场） | `/mnt/share/dataset`（coco / imagenet / dapo-math；另有 `/mnt/share/datasets`） | `/home/vllm/x00886548` 已改为指向个人根的兼容软链 |
| A5（177.x，4 台） | **待落地**（2026-11-13 已能登进去，见 `ascend-server-access` §13） | 未验证 | 未验证 | **`/home` 与 `/` 同一块盘**（2026-11-13 四台实测），`/` 已用到 70~100%、余 19G~1016G ⇒ 先 `df -h /home`；个人根落位（软链到共享盘）**仍未验证** |

> `.188` 兼容软链（2026-11-10 迁入，勿删）：`/mnt/share/x00886548/miniconda3` → `env/conda3`、`/mnt/share/x00886548/cann` → `env/cann`、`/mnt/share/x00886548/workspace` → `work`。老脚本里的绝对路径仍可用，但**新内容一律写个人根**。

### 步骤 2：能往哪写（写任何大文件之前）
**判据只有一条：`df -h <你要写的路径>` 看挂载点与余量。**

| 服务器 | 路径 | 设备 / 挂载点 | 容量 / 已用 | 能写大文件吗 |
|---|---|---|---|---|
| `.188` | `/home/x00886548`（= `/home/vllm/x00886548`） | `nvme1n1p3` → LVM `ubuntu--vg-ubuntu--lv` | 6.9T，76%，**剩 1.6T** | ✅ **推荐** |
| `.188` | `/`（含 `/home`、`/mnt/share`、`/mnt/weight`、`/tmp`、`/root`） | `nvme0n1p2` | 2.9T，**96%，剩 139G** | ❌ 红线 |
| `.188` | `/home/vllm/weights` | 同 `/home/vllm` | 2.8T | ✅ 只读权重 |
| `.190` | `/home/x00886548` | `openeuler-home` | 6.9T，10%，剩 6.0T | ✅ **推荐** |
| `.190` | `/` | `openeuler-root` | 69G，68%，剩 22G | ❌ 别放大文件 |
| `.190` | `/mnt/share` / `/mnt/weight` | NFS `suzblue.server:/share` / `:/weight` | 285T / 281T，各剩 ~168T | ✅ 公共数据 / 权重，只读为主 |
| A5 | `/`（含 `/home`） | 本地 `nvme*p4` 单盘 | 3.5T，2026-11-13 实测 70~100% | ⚠️ 与 `/home` **同盘**，已接近/打满；写之前 `df -h`，别把权重落这 |

验证：`ssh -n a3 "df -h /home/x00886548 /mnt/weight"`——`.188` 上 `/mnt/weight` 必须回显 `/dev/nvme0n1p2 … 96% /`（不是独立盘）。

### 步骤 3：模型在哪（两处，别只看一处）
```bash
ssh -n a3 "du -sh /mnt/weight/* /home/vllm/weights/* 2>/dev/null | sort -h | tail -20"
ssh -n a3 "ls -la /home/vllm/weights/Qwen3.5-35B-A3B"
# LFS 指针判别（★ 必做，0 才是真权重）：期望 0
ssh -n a3 "head -c 200 /home/vllm/weights/Qwen3.5-35B-A3B/model-00001-of-00004.safetensors | grep -c git-lfs"
```
| 路径 | 大小 | 备注 |
|---|---|---|
| `/home/vllm/weights/*` | 2.8T（`.188`）/ 305G（`.190`） | **权重农场**，20 个模型；`.188` 有 Qwen3.8-Flash-Next 336G、MiniMax-M3 258G、Qwen3.5-122B-A10B 234G、DeepSeek-V4-Flash 149G 等 |
| `/mnt/weight/*` | `.188` 4 个（Qwen2.5-0.5B/7B、Qwen3-0.6B/30B-A3B，**在 `/` 上**）；`.190` NFS 281T | `.190` 是公共农场；`.188` 别往里写 |
| `/home/vllm/Qwen3-235B-A22B` | 438G | 在 `/home/vllm` 根下，不在 `weights/` |

验证：`du` 有该目录且体积 GB 级 + `grep -c git-lfs` = **0**。`*-layer3/-layer4/-layer8` 后缀目录**未验证**是否为完整可加载权重，别直接起服务。

### 步骤 4：复用现成环境（优先复用，别重建）
- **`.188` 已验证工作区** `/home/x00886548/work/batch_inv_qwen35/`（7.5G，自定义 vllm + vllm-ascend，批次不变性版）：
  `BUILD_REPORT.md`、`env_batch_inv.sh`（一键激活）、`bi_validation/`、`compat_lib/`、`vllm/`、`vllm-ascend/`。
```bash
ssh -n a3 "source /home/x00886548/work/batch_inv_qwen35/env_batch_inv.sh && python -c 'import vllm,torch_npu;print(torch_npu.npu.is_available())'"
```
验证：打印 `True`。已验证组合（2026-09-22 实测）：python 3.12.14 / torch 2.10.0+cpu / torch_npu 2.10.0.post4 / triton 3.2.0 / triton-ascend 3.2.2 / numpy 1.26.4 / transformers 5.14.1 / fastapi 0.123.10 / starlette 0.50.0 / batch_invariant_ops 1.0.0。
- **`.188` 共享 conda 环境** `/mnt/share/vllm/conda_envs/xmz_0921`（py3.12.14，3.7G，历史环境，未迁入个人根，可继续用）与 `ops_nightly_agent`。
- 环境搭建脚本：`/home/x00886548/env/setup_conda.sh`（幂等）；conda 细节见 `ascend-conda-env`。
- `.190` 历史工作区（2026-11-03 后）：`bi_261103/`、`bi_261104/`、`glm52bi_1026/`、`mrv2_k3/`、`smoke2620/`——都在个人根下，属历史项目，**新项目仍建 `work/`**。

### 步骤 5：看哪张 NPU 空闲

> **先读文末「共享机占用铁律与断点续跑」再动手**：卡上有别人 ⇒ 整张卡不可用（含"只用剩余显存"），这是唯一判据出处，本节只给命令。

```bash
ssh -n a3 "npu-smi info | head -14; echo ===; npu-smi info | tail -30; echo ===; uptime; who | wc -l"
```
- **判空闲**：`HBM-Usage(MB)` 形如 `used / 65536`。`used ≈ 2900–3200` 且 `AICore(%) = 0` = **空闲**（~3G 是驱动基线）；`used` 上万 = 有负载；再核对进程段该 NPU 是否列出 `Process id/name`。
- ⚠️ **Process 段的 `NPU` 列是 NPU id、不是扁平 die id**（一张 NPU 含 2 个 chip/die）→ 拿那一列判"第几号 die 忙"会判错。
- **要判某个物理 die 上有没有进程，用 HBM 段的 `Bus-Id`**（形如 `0000:F4:00.0`）唯一匹配最稳。
- `.188` 是**多租户共用机**：`uptime` 实测 load 17–28，`who` 11–12 个 root 会话。→ 挑卡、限 `MAX_JOBS`、别杀别人的进程。起服务挑卡见 `ascend-vllm-serve`。

### 步骤 6：下载权重（写成"能复制就对"的形式）
```bash
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1      # ★ 必须显式设，全局为空
/home/x00886548/env/conda3/bin/hf download <repo_id> --local-dir /home/vllm/weights/<name>
```
验证：落盘后 `ls -la <dir>/*.safetensors` 是 GB 级，且 `head -c 200 <file> | grep -c git-lfs` = 0。
> 临时文件与 pip 缓存别落在 `/`：先 `source /home/x00886548/env/env.sh`（已把 `TMPDIR`/`PIP_CACHE_DIR`/`HF_HOME` 指到个人根）。

## 坑与修法

| # | 错误原文 / 现象 | 修法 |
|---|---|---|
| 1 | `df -h /mnt/weight` → `/dev/nvme0n1p2  2.9T 2.6T 139G 96% /`——**看着像独立盘，其实在满盘上** | 写大文件前**永远先** `df -h <目标路径>`；`.188` 只写 `/home/x00886548`（= `/home/vllm`） |
| 2 | 在 `.188` 建了真实目录 `/home/x00886548` 后，写几个 G 就把 `/` 顶到 97% | `/home` 在系统盘上 → 个人根必须是软链到 `/home/vllm/x00886548`；用 `readlink -f /home/x00886548` 复核 |
| 3 | `modelscope --help` → `File "/usr/local/lib/python3.7/dist-packages/modelscope/utils/file_utils.py", line 238 while byte_chunk := f.read(buffer_size): ^ SyntaxError: invalid syntax` | `/usr/local/bin/modelscope` 装在 py3.7，**该 CLI 已损坏**。改用 conda env 里 `pip install modelscope`，或走 `hf download` |
| 4 | 不关 xet 时下载报 **401**（`cas-server.xethub.hub.co`）；全局 `HF_ENDPOINT=[]` | 每次显式 `export HF_ENDPOINT=https://hf-mirror.com` **且 `export HF_HUB_DISABLE_XET=1`** |
| 5 | `grep -rln <pat> /home/x00886548` **120s 超时**（含 conda site-packages，数十万文件） | 加 `--include=*.sh --include=*.md` 限定；或只查 `work/`、`agent/` |
| 6 | 模型是 git clone 的 LFS 指针（134B）时，起服务报 `parse_safetensors_file_metadata` **MemoryError** | 先判别：`ls -la *.safetensors` 是否 GB 级 + `grep -c git-lfs`（**0 才是真权重**）；运行时处理见 `ascend-vllm-serve` |
| 7 | `ssh a3` stderr 每次一行 `/root/.bashrc: line 36: /usr/local/Ascend/ascend-toolkit/set_env.sh: No such file or directory` | 真实断链（`latest -> /usr/local/Ascend/cann-9.1.0/cann` 不存在）。**默认路径的噪声，忽略**；CANN 用 `/home/x00886548/env/cann/cann_9_1_0` |
| 8 | `/home/vllm/weights` 归 root 但同盘混着他人目录（`skhalid` 706G / `w00893744` 331G / `fyf` 123G） | **写自己的东西前先确认命名空间**，一律用 `/home/x00886548/...`，别覆盖同名他人目录 |
| 9 | 迁移后老路径 `/mnt/share/x00886548/workspace/...` 还能用，但 `df -h` 显示的是 `/home/vllm` | 正常：那是兼容软链。**别把它当新落点**，新内容写 `/home/x00886548/work/...` |

## 不要做什么

- 不要在个人根下、`/mnt/share`、`/tmp`、`/root` 新建项目目录或环境——个人根之外只允许公共权重 / 数据集。
- 不要把新 conda 环境建到 `/mnt/share/vllm/conda_envs`（`.188` 上与 `/` 同盘，只剩 139G）。
- 不要把 `/mnt/weight` 当 `.188` 的独立大盘（它只是 `/` 上的普通目录）。
- 不要删 `.188` 上三条兼容软链（miniconda3 / cann / workspace），老脚本和 CANN 的 `set_env.sh` 还依赖它们。
- 不要用 `/usr/local/bin/modelscope`（py3.7 语法错，见坑 3）。
- 不要在 `.188` 上杀别人的进程 / 占别人正在用的卡 / 把 `MAX_JOBS` 打满。
- 不要在 A5 上凭空套用 `.188`/`.190` 的盘位结论——A5 尚未实测。

## 验收标准

1. `readlink -f /home/x00886548` 在 `.188` 返回 `/home/vllm/x00886548`，在 `.190` 返回 `/home/x00886548`；`df -h /home/x00886548` 落在 6.9T 盘上。
2. `ls /home/x00886548` 能看到 `env work agent data tmp logs models datasets README.md` 九项。
3. `ls -l /home/x00886548/models` 指向公共权重盘，`datasets` 指向公共数据集盘；两个软链都 `test -e` 为真。
4. `source /home/x00886548/env/env.sh` 后 `echo $XH` 为 `/home/x00886548`，`conda --version` 有输出。
5. `.188` 上 `/` 可用空间不再被新内容消耗（写前后各跑一次 `df -h /` 对比）。
6. 你能说出"新项目写 `work/<name>`、新环境写 `env/conda_envs/<name>`、agent 脚本写 `agent/scripts/`、权重写 `/home/vllm/weights`"。

## 共享机占用铁律与断点续跑（2026-11-13）

用户 2026-11-13 明确要求，适用于**所有共享昇腾机**（`.188` / `.190` / `177.8.21.1` / `177.11.25.1` / `177.11.26.1` / `177.11.27.1`）。本节是"能不能用这张卡"的唯一出处，`ascend-server-access` §12 与 `ascend-vllm-serve` 只留指针。

### 1. 别人在用 → 整张卡不可碰

**判据是"有没有人"，不是"还剩多少显存"。** 下面任一条成立就整卡跳过：

- `npu-smi info` 的 `Process` 段出现**非本会话**的 PID（别人的进程、别人的容器、别人的评测，都算）；
- `HBM-Usage(MB)` 明显高于驱动基线（`/ 65536` 上形如 `20000` 甚至 `60000`）而进程段看着是空的 → 按"已占用"处理（多为容器内或残留），**别去试**；
- `AICore(%)` 有非 0 波动。

**严禁**（这些都是在偷别人的公共资源）：

- "反正只剩 40 G，我塞个小模型 / 跑个小评测"；
- 靠 `--gpu-memory-utilization` / `--mem-fraction-static` 把余量吃满；
- 改 `ASCEND_RT_VISIBLE_DEVICES` 绕开已被占用的卡去蹭剩余显存；
- kill 别人进程、`npu-smi set ...` 重置别人的卡、`reset` 整机。

理由（用户原话）：要防止影响**其他人正在跑的性能与精度**——共享卡上多一个进程，别人的 TPOT / 吞吐 / 精度复现全部作废。

### 2. 挑卡前先看这三样（在目标机上执行）

```bash
npu-smi info | head -20                                   # HBM-Usage 与 AICore
npu-smi info | tail -40                                   # Process 段：谁的 PID、在哪张卡
who; uptime; ps -eo user,pid,pcpu,comm --sort=-pcpu | head -10   # 有几个会话、机器负载
```

判空闲：`HBM-Usage` ≈ 驱动基线 + `AICore = 0` + 进程段无该卡。**基线按卡型不同**：`.188`/`.190`（64 GB die）实测 `2900–3200 / 65536`；**A5（98304 MB 卡）实测 `4791–4833`**（2026-11-13 四台一致）——拿 3 GB 去判 A5 会把空卡误判成"有残留"；反过来 A5 上 `HBM > 4.9 GB` 就当已占用。

- 判某个**物理 die** 上有没有进程，用 HBM 段的 `Bus-Id`（形如 `0000:F4:00.0`）唯一匹配最稳；`Process` 段的 `NPU` 列是 NPU id、**不是**扁平 die id，拿它判会错。
- 全机没有空闲 die ⇒ **换机器或等**，不要"挤一点"。挑机顺序：先 A5（4 台，`ascend-server-access` §12 在册），再看 `.190`，最后 `.188`（多租户重载机，load 实测 17~800）。

### 3. 长任务默认"可断点续跑"

共享机随时可能被抢占 / 重启 / 隧道掉线，一次性长任务 = 大概率白跑。开跑前先确认**中断后能接着跑**：

| 任务 | 要求 |
|---|---|
| 训练 | 每 N step `save_checkpoint`（含 optimizer / global step / rng），入口支持 `--resume <ckpt>`；**先小步验证 resume 真能接上**，再开长跑 |
| 评测 / 精度 | 按样本写 `*.jsonl`（一行一条、带唯一 `uid`），重跑时 `--skip-done` 幂等跳过；中断只补缺的 |
| 性能 benchmark | 每轮结果 **append** 到 CSV/JSONL，不覆盖；输出目录带时间戳 |
| 权重下载 | `hf download --local-dir`（自带续传）或 `wget -c` / `curl -C -` |
| 任何 > 30 min 的活 | `nohup ... > logs/<name>.log 2>&1 &` 或 `tmux new -s <name>`，日志落个人根 `agent/logs/`，别落 `/tmp` |

配套：先 `source /home/<用户>/env/env.sh`（把 `TMPDIR` / `PIP_CACHE_DIR` / `HF_HOME` 指到个人根，见步骤 6）；脚本里不要 `rm -rf` 共享输出目录，只清自己的。

## A5 上的权重农场与 dsv4.1flash 权重落位（2026-11-13 实测）

## A5 上的权重农场与 dsv4.1flash 权重落位（2026-11-13 实测，替换旧"未验证"）

**A5 四台（`177.8.21.1` / `177.11.25.1` / `.26.1` / `.27.1`）的本机盘都没有大模型权重**，权重全在共享 NFS（同一台 `172.27.1.1`，两个导出）：

```bash
findmnt -no TARGET,SOURCE,FSTYPE,USE% | grep -E '/mnt/(share|weight)'
# /mnt/share  <- 172.27.1.1:/Share    公共盘（含 ds_weights/ 与各人目录）
# /mnt/weight <- 172.27.1.1:/Weight   权重农场（147 个条目，含各模型各精度）
```

### DeepSeek-V4.1-Flash（dsv4.1flash）的精度谱

| 路径 | 体积 | 分片 | 性质 |
|---|---|---|---|
| `/mnt/share/g00815994/dsv41/dsv41-flash-bf16` | 1.39 TiB | 525 | **唯一完整 bf16**，反量化产物（非官方） |
| `/mnt/share/g00815994/dsv41/DeepSeek-V4.1-Flash-top32-bf16` | 493 GiB | 505 | bf16 但裁剪到 32 专家（`n_routed_experts: 32`） |
| `/mnt/weight/DeepSeek-V4.1-Flash-1017` | 475 GiB | 48 | **官方本体**：`quant_method: fp8` + `expert_dtype: fp4` |
| `/mnt/share/ds_weights/DeepSeek-V4.1-Flash` | 381 GiB | 48 | 官方本体副本（同 fp8/fp4 配置） |
| `/mnt/weight/DeepSeek-V4.1-Flash-1017-BF16-msmodelslim` | 52 GiB | 52 | msModelSlim 量化（`quant_model_weights-*`） |
| `/mnt/share/ds_weights/DeepSeek-V4.1-Flash-1017-w4a8` | — | 87 | w4a8 量化 |

- **官方从未发 bf16**：V4.1-Flash 发布即 fp8 稠密 + fp4 专家。bf16 是 2026-10-30 由他人（`g00815994`）从 fp4/fp8 反量化来的，体积 ≈ 官方的 **2.99×**（fp4 专家×4 + fp8 稠密×2），数值继承量化误差，**不能当精度基线**。
- 分片权限 `-rw------- root root` ⇒ 只有 root 能读；目录属他人，只读使用。
- V4（非 4.1）Flash 的 bf16 现成：`/mnt/weight/DeepSeek-V4-Flash-BF16`（543 GiB / 46 分片）。

### 空壳陷阱：目录名会骗人

`/mnt/weight/DeepSeek-V4.1-Flash-1017-BF16`（**空目录 4.0K / 0 分片**）、`/mnt/weight/DeepSeek-V4.1-Flash`（空）、`/mnt/weight/Deepseekv4.1_weight_hg_bf16`（只有 config + index，无权重）。**判"有没有权重"必须落到分片数 + 体积 + 头部 dtype，不能看目录名或 config 字段。**

### 判权重精度的固定取证顺序

```bash
D=<目录>
ls $D/*.safetensors | wc -l                     # 分片数，0 = 空壳
du -chs $D/*.safetensors | tail -1              # 体积
grep -oE '"(dtype|torch_dtype|expert_dtype)"[^,]*' $D/config.json
grep -c quantization_config $D/config.json      # 0 = 未量化
# 头部 dtype：至少抽最大/中/最小三个分片，别只看 shard0
python3 -c 'import json,struct,sys,collections;f=open(sys.argv[1],"rb");n=struct.unpack("<Q",f.read(8))[0];h=json.loads(f.read(n));print(collections.Counter(v.get("dtype") for k,v in h.items() if k!="__metadata__"))' $D/$(ls -S $D/*.safetensors | head -1 | xargs -n1 basename)
# index 一致性
python3 -c 'import json,os,sys;D=sys.argv[1];i=json.load(open(D+"/model.safetensors.index.json"));s=set(i["weight_map"].values());print(len(s),"shards; missing",[x for x in s if not os.path.exists(D+"/"+x)][:3])' $D
```

### 坑

| 现象 | 修法 |
|---|---|
| `-iname '*deepseek*'` 命中一堆源码树（`vllm_ascend/models/deepseek_v41`、`csrc/*flash_attention`） | 反查：`find /mnt/weight /mnt/share -maxdepth 3 -name '*.safetensors' -printf '%h\n' \| sort \| uniq -c \| sort -rn \| head` |
| **只看 shard0 的头部 dtype 会把 fp8 判成 bf16**（`-1017` 的 `model-00001` 头部 263 个张量全 BF16，整体 48 分片是 F8_E8M0/F8_E4M3 主体） | 头部统计必须对**全部分片求和**，或至少抽最大/中/最小三个 |
| `du -sh /mnt/share/*` 120s 跑不完（350T） | NFS 上禁止整层 du，先 `ls` 再定点 `du -s <目标>` |
| Windows 上 `ssh host "..."` 内联脚本里的引号/括号被 PowerShell 吞（`bash: -c: line 1: syntax error near unexpected token '('`） | 本地写脚本 → `Get-Content x.py -Raw \| ssh host python3 -`；或 base64 后远端 `base64 -d \| bash` |

## 共享权重池与 ModelScope 全量下载（2026-11-13 实测）

2026-11-13 实测，适用于 `177.x` 四台 A5。

### 1. 四台 A5 的"共享存储"是**同一份**

四台都挂 `172.27.1.1:/Weight` → `/mnt/weight`（350T，用 47T，**余 304T**）与 `172.27.1.1:/Share` → `/mnt/share`（350T，用 129T，余 222T），**root 可写**，inode 用 1%。⇒ 往 `/mnt/weight` 下一次，四台同时可见，不用重复下载。
**别和蓝区混**：`.190` 挂的是 `suzblue.server:/share` + `:/weight`（另一套 NFS），`.188` 一个 NFS 都没挂。

### 2. 权重池现状（2026-11-13 核对）

| 路径 | 内容 | 判定 |
|---|---|---|
| `/mnt/weight/GLM-5.2` | BF16 / 1.4T（1506.7 GB）/ 282 shards | ✅ 真权重、分片齐（282/282，59585 tensors） |
| `/mnt/weight/GLM-5.3-BF16` | BF16 / 1.4T / 282 shards | ✅ 真权重 |
| `/mnt/weight/GLM-5.1-w4a4c8-mxfp4` | 391G / 102 shards | ⚠️ **量化件**，不是 BF16 |
| `/mnt/weight/glm51-parity-131` | 95G，`quant_model_weights-000NN-of-00101` | ⚠️ 量化件 |
| `/mnt/weight/GLM-5.1` | 从 ModelScope `ZhipuAI/GLM-5.1` 下的 BF16（282 shards） | 2026-11-13 起下 |

### 3. 判"是不是 BF16 真权重"：**只看 config.json 必错**

量化件的 `config.json` 同样写 `"dtype": "bfloat16"`（实测 `GLM-5.1-w4a4c8-mxfp4/config.json` 就这么写）⇒ 391G 的 MXFP4 会被误判成 BF16。三步定死：

```bash
grep -m1 '"dtype"' <dir>/config.json                    # 只能参考，不能当证据
head -c 200 <dir>/<任一>.safetensors | grep -c git-lfs   # 必须 0（1 = LFS 指针，不是权重）
python - <<'PY'                                        # 真证据：读 safetensors header 的张量 dtype
import json,struct,sys
p=sys.argv[1] if len(sys.argv)>1 else None
PY
```

更省事的判法：`head -c 8 <shard>` 读到前 8 字节是 header 长度，再 `strings` / 读 JSON 看 `"dtype":"BF16"`；出现 `F8_E4M3` / `U8` / `I8` 就是量化。另对分片数：`ls <dir>/model.safetensors.index.json` 里 `weight_map` 的 shard 集合数 必须等于目录里实际 `*.safetensors` 数。

### 4. 从 ModelScope 下全量权重（实测跑通）

```bash
ssh root@<A5> 'MODELSCOPE_CACHE=/mnt/weight/.cache-modelscope setsid nohup \
  /root/miniconda3/envs/dxq_swift/bin/modelscope download <org>/<repo> \
  --local-dir /mnt/weight/<repo> --cache-dir /mnt/weight/.cache-modelscope \
  --max-workers 8 --continue-on-error --tracker-path /mnt/weight/.download-logs/<repo>-tracker.json \
  >> /mnt/weight/.download-logs/<repo>-$(date +%Y%m%d-%H%M%S).log 2>&1 < /dev/null &'
```

要点：
- **`--local-dir` 直接落盘，绕过 `~/.cache/modelscope`**：不显式指 `--cache-dir` / `MODELSCOPE_CACHE` 到 NFS，1.5T 的活会把本地 `/`（`/home` 同盘）撑爆。
- `setsid nohup … < /dev/null &`：ssh 一断就死的下载没有意义；PID 与日志路径当场记下。
- `--max-workers 8`（该版本默认 4）；公共 NFS + 别人也在跑，别上 16+。
- 实测 8 并发 ≈ **55 MB/s**（单流 15 MB/s），1.5T 约 **7–10 h**。
- 出口：`modelscope.cn` 通（可用）、`hf-mirror.com` 慢（~4 MB/s）、`huggingface.co` / `github.com` 直接不通 ⇒ 优先 ModelScope；`modelscope` 在 `/root/miniconda3/envs/dxq_swift/bin/`（不是 `/root/miniconda3/bin`）。

### 5. 坑：DEFERRED 会静默漏 shard，完成判据不是退出码

- 现象：日志 `[E1020] File recovery budget exhausted`，该 shard 被标 **DEFERRED**（并发抢占让连接快速失败、单文件恢复预算耗尽即放弃）。进程**不会自己重试**，结束时退出码 **3 = PARTIAL**。
- 修法：跑完再跑一轮补漏（**必须带 `--retry-failed`**，否则 DEFERRED 的 shard 会被跳过；可能要连补 2–3 轮）：

```bash
ssh root@<A5> 'MODELSCOPE_CACHE=/mnt/weight/.cache-modelscope setsid nohup \
  /root/miniconda3/envs/dxq_swift/bin/modelscope download <org>/<repo> \
  --local-dir /mnt/weight/<repo> --cache-dir /mnt/weight/.cache-modelscope \
  --max-workers 8 --continue-on-error --retry-failed \
  --tracker-path /mnt/weight/.download-logs/<repo>-tracker.json \
  >> /mnt/weight/.download-logs/<repo>-retry-$(date +%Y%m%d-%H%M%S).log 2>&1 < /dev/null &'
```

- **完成判据**：`ls /mnt/weight/<repo>/*.safetensors | wc -l` = `index.json` 的 282，且 `model.safetensors.index.json` 存在。**不要看 exit code**——`modelscope` 退出时还会 `Segmentation fault (core dumped)`（`--version`/`--help` 也复现），属退出期崩溃，不影响产物。
- 续传本身是自动的（`Range` + `.incomplete`），中断后重跑同一条命令即可接着下。
