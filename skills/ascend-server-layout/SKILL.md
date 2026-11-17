---
name: ascend-server-layout
description: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
whenToUse: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
---

# 昇腾共享工作区与权重

## 磁盘和目录

对目标路径先 `readlink -f`、`findmnt -T`、`df -h`，不存在时检查最近的已存在父目录。目录名 share/home/weight 不证明独立大盘或 NFS，跨主机同名路径不证明同一份数据。按下载、解压、编译、Docker layer 与缓存峰值一起估算写入。

沿用用户已有布局；需要新布局时可采用 `<个人根>/{env,work,agent,data,tmp,logs}`，权重/数据集用明确的公共入口。不要为统一目录搬动工作中的 conda/CANN 或改共享 shell 配置。CANN 安装树可能内嵌绝对路径，软链也不能证明可搬迁。

将 TMPDIR、PIP_CACHE_DIR、CONDA_PKGS_DIRS、HF_HOME、ModelScope 缓存按目标盘显式配置。`/home` 在大盘上并不保证 Docker root 也在大盘；查 `docker info` 的根目录和对应挂载。挂容器时包含软链的真实目标，核对容器内可见设备、驱动库及路径；不要默认需要 privileged 或挂所有人的目录。

## 挑卡

用户的共享机约束：有别人进程的物理卡整张不可用，不以剩余 HBM 为可用量。采集完整 `npu-smi info`、健康、进程和当前基线；发起任务前再采一次。A3 的物理 NPU、chip/die、运行时 logical ID 与 A5 的单 chip 映射可能不同，要用当前工具核实。`/dev/davinci*` 包含 manager，不能直接数作卡数。

Util=0、进程表为空、低 HBM 三者各自不足以判空。隐藏容器进程、未知映射、异常 HBM、解析失败、告警都标为 UNKNOWN/不可调度；不能把没解析到进程算作空闲。若进程行只有物理 NPU、无法分到两个 chip，保守排除整卡。旧 A3 3500 MiB/A5 6000 MiB 阈值只是历史筛选线，不能排除低占用任务。

先用无 NPU 上下文的工具筛选，确认资源归属后才对选定设备运行 torch 探针。`ASCEND_RT_VISIBLE_DEVICES` 在新进程 import 前设置，记录物理与重映射 logical ID。CPU load、磁盘和设备健康也需满足本轮任务。

## 权重验真

使用 [scripts/inspect_weights.py](scripts/inspect_weights.py)：

```bash
python inspect_weights.py /path/to/model > weights-report.json
```

它只读 config/index 和所有 safetensors 头部，检查 LFS 指针、分片存在性、张量索引映射、dtype/shape、offset 与文件长度，限制 header 分配。退出码 0 只表示这些结构检查通过；没有下载源校验和时不能证明 payload 正确，也不能证明模型可加载。退出码 1 表示完整性失败，2 表示输入错误或检查不完整（如缺配置、多分片缺索引、未知 dtype）；结合 JSON 的 verdict/errors/warnings 解读。

config 的 dtype 不证明每个张量的存储精度，首分片也不代表全部。结合所有分片的 dtype/shape、量化配置、scale/packed 权重布局和 loader 判断实际格式；U8 单独不证明量化类型。反量化 BF16 继承原量化误差，不能当作原生 BF16 基线。

下载固定模型 revision 和目标目录，记录唯一 PID、日志及失败列表；同目录单写者，失败重试不能删另一进程已完成的产物。完成以索引覆盖、结构和上游校验和为准，退出码/分片数量/目录名只是一部分证据。先读当前 CLI `--help`，不要继承旧 ModelScope 私有参数和固定镜像配置。

硬链只在同文件系统且分片保持不可变时复用；修改硬链会改到原文件，小 config/index/tokenizer 应实体复制。`du` 逻辑体积与新增物理占用分别报告。

长任务按需求保存 checkpoint/RNG、逐样本 uid 或追加结果，验证恢复点后再长跑。清理只针对本任务明确记录的 PID/文件；不 prune 共享 Docker、不 reset 他人设备。

历史现场线索与来源见 [references/site-and-sources.md](references/site-and-sources.md)。

## 判空卡取证：进程名 ≠ 占卡，落 Davies fd 与设备级进程表

判"某张卡现在能不能用"时，**先分清"主机上有 vLLM/ray 进程"和"卡上有进程"**——这两件事在多租户 A5 上几乎总是同时出现，但含义完全相反。

### 判据顺序（三重独立信号，缺一即 UNKNOWN）

1. **设备级进程表**：`npu-smi info -t proc-mem -i <id>`（A5 单 chip，`-i` 就是卡号；A3 双 chip 要 `-i <npu> -c <chip>`）。空卡返回 `No process in device.`。
2. **HBM 绝对量**：`npu-smi info` 里 `<used> / 98304`（A5）或 `/ 65536`（A3）。A5 空机实测落在 4.8G 量级、A3 落在 2.9~3.2G 量级——**只作旁证，不当判据**（历史阈值 3500/6000 会漏掉低占用任务）。
3. **Health**：`OK` 才可调度；`Alarm`（含 UB/RAS `Error Code 81AF8000` 一类的链路告警）按 UNKNOWN，不是"空卡可用"。

### 关键：进程名会骗人，要看它有没有 davinci fd

同一台机器上常年挂着别人的 `VLLM::Worker_TP` / `VLLM::Worker_DP` / `ray::IDLE`（etimes 可达数天），`ps` 一眼看过去像"整机被占"。真实判据是**这个进程有没有打开设备**：

```bash
pid=$(ps -eo pid,comm | grep -F 'VLLM::Worker_TP' | head -1 | awk '{print $1}')
ls -l /proc/$pid/fd | grep -c davinci          # 0 = 没占卡；>0 = 占着
cat /proc/$pid/cgroup | head -2                # 13:misc:/ 12:devices:/ = 宿主 cgroup，不是容器内设备占用
ps -o etime= -p $pid
```

实测：`davinci_fds=0` + 宿主 cgroup + etime 数天的 worker，与 `proc-mem` 的 `No process in device.` 完全一致 ⇒ **确实是残留，卡是空的**。反过来，只要某个 pid 的 `davinci` fd 数 > 0，就按"卡被占用"整卡让路。

容器侧可以用 `docker inspect -f '{{range .HostConfig.Devices}}{{.PathOnHost}}\n{{end}}' <ctr> | grep -c davinci` 看"谁挂了设备"，但**挂了设备 ≠ 正在用**（大量 running 容器挂着设备却空跑），不能拿它判占用。

### 受支持的采集入口

```powershell
python C:\Users\admin\.dsh\skills\ascend-server-access\scripts\probe_hosts.py --inventory root@177.11.27.1
```

`probe_hosts.py` 只做**显式目标**的只读采集：要求 `user@IPv4-or-hostname`（不接受选项/元字符），走系统 `ssh -n -o BatchMode=yes -o StrictHostKeyChecking=yes`（只用既有 key 与已验证 host key），`--inventory` 采 `hostname; uname -m; nproc; df -h / /home /mnt/share /mnt/weight; npu-smi info`，输出 JSON，`exit 0` 表示所有目标 `ssh_rc=0`。**它不给出 free-card 分类**，"空/占用/UNKNOWN"要按上面三条自己判。

### 从 Windows 驱动远端采证的固定写法

PowerShell 5.1 里把带引号/反引号的 bash 内联进 `ssh host "..."` 会在**解析期**直接失败（`UnexpectedToken`，整条命令一行都不执行），不要拼转义。固定做法：

```powershell
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes("D:\tmp\probe.sh"))   # 本地写好 .sh（LF）
ssh -n -o BatchMode=yes root@<ip> "echo $b64 | base64 -d > /tmp/p.sh; bash /tmp/p.sh; rm -f /tmp/p.sh" 2>$null
```

配套两个坑：`2>$null` 而不是 `2>&1`（登录横幅走 stderr，会往 stdout 插一行 `System.Management.Automation.RemoteException`）；用 `>` 把 python 输出重定向到文件时 PS 5.1 写的是 **UTF-16LE**，下一位 `json.load` 会报 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0`——读的时候先看 BOM（`ff fe` → `utf-16`）。

### 坑

- A5（`npu-smi 25.1.rc3`）**没有 `-t proc` 子命令**：`npu-smi info -t proc -i 0` 报 `Error parameter of -t`。设备级进程用 `-t proc-mem`。
- `npu-smi info -t usages` 的 `HBM Usage Rate(%)` 与 `info` 的 MB 口径不一致（实测约 2 倍差），别拿百分比下判断。
- 未验证：容器内进程打开设备时，宿主侧 `/proc/<pid>/fd` 是否总能直接看到 davinci 句柄（本轮抽到的都是宿主 cgroup 进程）。

## 判「最近 N 小时有没有用过卡 / 机器上在跑什么」

回答「这台**最近 N 小时**有没有用过卡 / 现在到底在跑什么」，不能只看当前 `npu-smi`（它不保存历史）。要按三层分别取证：**现在**（见上一节三重信号）→ **窗口内有没有作业启停** → **窗口内有人在做什么**。

### 1. 全机找"谁打开着 davinci"（比逐 pid 扫 fd 快，也不会撞 ARG_MAX）

```bash
find /proc -maxdepth 3 -lname '*davinci*' 2>/dev/null | head -20
find /proc -maxdepth 3 -lname '*davinci*' 2>/dev/null | wc -l      # 0 = 当前无任何进程占卡
```

`-lname` 匹配的是 `/proc/<pid>/fd/<n>` 这条软链的**目标**（fd 名是数字，用 `-name` 永远匹配不到）。**0 是唯一可判"现在没人占卡"的硬信号**，配合 `npu-smi -t proc-mem -i N` 与 HBM 基线交叉。

### 2. 窗口内有没有作业启停（最硬的一条证据）

```bash
docker events --since '2h' --until '1s' --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' | head -30
docker ps -a --format '{{.Names}}|{{.Status}}' | grep -E '[0-9]+ (second|minute|hour)'
```

判读：**只有 `exec_create/exec_start/exec_die` = 没人在窗口内起停任务**（exec 是"进容器敲命令"，不是跑作业）；出现 `start` / `die` / `stop` 且时间落在窗口内，才算有作业启停。`--until '1s'` 必须给，否则 `docker events` 会一直挂着等新事件。

`docker ps -a` 的 `Status` 文本本身就带时间（`Up 2 days`、`Exited (137) 6 hours ago`），拿它做窗口初筛比逐容器 `inspect` 快得多。

### 3. 窗口内新起的进程（etime 分档）

```bash
ps -eo pid,etime,comm --sort=etime | awk 'NR>1{n=split($2,a,":"); if(n==2 || (n==3 && a[1]<2)) print}' | head -20
```

- `etime` 有**两种格式**：`MM:SS`（<1 小时）和 `HH:MM:SS`（≥1 小时）、`D-HH:MM:SS`（≥1 天）。只判 `n==3` 会把 2~59 分钟的进程当成"刚启动"，只判分钟字段会把 `2:04:21`（2 小时 4 分）读成 2 分钟。上面这条同时覆盖 `n==2` 与 `n==3 && HH<2`。
- 注意结果里会混进 `kworker/*` 和**你自己的探测进程**（`ps`/`awk`/`head`），先剔掉再下结论。

### 4. 容器里"在跑什么"——running ≠ 在干活

```bash
for c in $(docker ps --format '{{.Names}}'); do
  rows=$(docker top "$c" 2>/dev/null | tail -n +2 | grep -Ev 'sleep infinity|rsyslogd|/bin/bash$|sshd')
  [ -n "$rows" ] && { echo "### $c"; printf '%s\n' "$rows" | awk '{print "  " $1,$2,$7,$8}' | head -3; }
done
```

多租户机上几十个 `Up N days` 的容器，`docker top` 里常常只有一个 `sleep infinity` + `rsyslogd` —— 那是"占着容器名但没跑东西"，**不构成占卡**。只有真正出来的 python/torch/vllm/sglang 进程才需要继续查它的 davinci fd。

### 5. 人做过什么（没有审计系统时的替代证据）

```bash
last -n 8                                  # 谁在什么时候登录/退出
ls -l --time-style=+%m-%d_%H:%M /root/.bash_history   # 最后一次落盘时间 = 那个人退出的时间
tail -5 /root/.bash_history                # 最后几条命令（常见的是 watch npu-smi info / docker ps）
grep -E 'Nov 17 (21|22|23):' /var/log/secure | grep -Ei 'session opened|Accepted' | tail
journalctl -k --since '2 hours ago' --no-pager | grep -iE 'davinci|svm|hisi|ascend' | tail
ls -lt /var/log/npu/slog; find /var/log/npu -newermt '-2 hours' -type f
```

判读：`.bash_history` 停在 `watch npu-smi info` + `docker ps`、且 `last` 显示该会话刚退出 ⇒ **有人一直在盯卡但没在用卡**；`/var/log/npu/slog` 无近 2 小时文件、`journalctl -k` 无设备消息 ⇒ 驱动侧也没有活动。

### 坑与局限

- **`npu-smi` 没有历史占用曲线**，也没有 NPU 使用审计。"最近 N 小时没占用"只能由「容器启停 + 进程生命周期 + 日志/登录痕迹」三重旁证推出，**不等于读了历史数据**，回答时要写清这是推断。
- 容器内 `docker exec` 跑的东西不会进 `ps` 之外的容器外视图，别用"宿主 `ps` 没有 python"就断言"没人操作"——要看 `docker events` 的 exec 记录。
- `watch -n 1.0 npu-smi info` 这类常驻轮询会让 `/var/log/nputools_LOG_INFO.log` 持续增长、`journalctl | grep -c npu` 到十万级：**那是查询噪声，不是占用证据**，别拿命中数当活跃度。
- `npu-smi info -t proc` 在 A5 25.1.rc3 不存在（`Error parameter of -t`），设备级进程用 `-t proc-mem`。
