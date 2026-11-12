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
| A5（177.x，4 台） | **待落地**（2026-11-10 隧道未通） | 未验证 | 未验证 | 先 `df -h /home`；`/home` 若在 `/`（3.5T 已 86–95%）则用 `--link-target` 指向 `/mnt/share/x00886548`（待验证） |

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
| A5 | `/` | 本地盘 | 3.5T，86–95% | ❌ 未验证，先 `df -h` |

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
