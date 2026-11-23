---
name: ascend-server-layout
description: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
whenToUse: 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。
---

# 昇腾共享工作区与权重

按 [服务器访问](../ascend-server-access/SKILL.md) 确认本轮目标和认证，再采集当前磁盘、设备和进程状态。

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

- 余下判据（dtype/量化布局判读、revision 与下载纪律、硬链、长任务与清理）见 [权重验真判据](references/weights-verification.md)。

参考依据见 [references/site-and-sources.md](references/site-and-sources.md)。

## 判空卡取证：进程名 ≠ 占卡，落 davinci fd 与设备级进程表

判"某张卡现在能不能用"时，**先分清"主机上有 vLLM/ray 进程"和"卡上有进程"**——这两件事在多租户 A5 上几乎总是同时出现，但含义完全相反。

### 判据顺序（三重独立信号，缺一即 UNKNOWN）

1. **设备级进程表**：`npu-smi info -t proc-mem -i <id>`（A5 单 chip，`-i` 就是卡号；A3 双 chip 要 `-i <npu> -c <chip>`）。空卡返回 `No process in device.`。
2. **HBM 绝对量**：`npu-smi info` 里 `<used> / 98304`（A5）或 `/ 65536`（A3）。A5 空机实测落在 4.8G 量级、A3 落在 2.9~3.2G 量级——**只作旁证，不当判据**（历史阈值 3500/6000 会漏掉低占用任务）。
3. **Health**：`OK` 才可调度；`Alarm`（含 UB/RAS `Error Code 81AF8000` 一类的链路告警）按 UNKNOWN，不是"空卡可用"。

- 完整取证命令与判读（davinci fd 核验、probe_hosts.py 入口、Windows 远端采证写法）见 [判空卡取证](references/idle-card-forensics.md)。

### 坑

- A5（`npu-smi 25.1.rc3`）**没有 `-t proc` 子命令**：`npu-smi info -t proc -i 0` 报 `Error parameter of -t`。设备级进程用 `-t proc-mem`。
- `npu-smi info -t usages` 的 `HBM Usage Rate(%)` 与 `info` 的 MB 口径不一致（实测约 2 倍差），别拿百分比下判断。
- 未验证：容器内进程打开设备时，宿主侧 `/proc/<pid>/fd` 是否总能直接看到 davinci 句柄（本轮抽到的都是宿主 cgroup 进程）。

## 判「最近 N 小时有没有用过卡 / 机器上在跑什么」

回答「这台**最近 N 小时**有没有用过卡 / 现在到底在跑什么」，不能只看当前 `npu-smi`（它不保存历史）。要按三层分别取证：**现在**（见上一节三重信号）→ **窗口内有没有作业启停** → **窗口内有人在做什么**。

- 三层取证的具体命令与判读（全机 davinci 扫描、docker events、etime 分档、容器内在跑什么、登录/日志痕迹）见 [活动取证](references/activity-forensics.md)。

### 坑与局限

- **`npu-smi` 没有历史占用曲线**，也没有 NPU 使用审计。"最近 N 小时没占用"只能由「容器启停 + 进程生命周期 + 日志/登录痕迹」三重旁证推出，**不等于读了历史数据**，回答时要写清这是推断。
- 容器内 `docker exec` 跑的东西不会进 `ps` 之外的容器外视图，别用"宿主 `ps` 没有 python"就断言"没人操作"——要看 `docker events` 的 exec 记录。
- `watch -n 1.0 npu-smi info` 这类常驻轮询会让 `/var/log/nputools_LOG_INFO.log` 持续增长、`journalctl | grep -c npu` 到十万级：**那是查询噪声，不是占用证据**，别拿命中数当活跃度。

## 从 npu-smi 进程名反查真实服务（含 proc-mem 判据）

判「卡上在跑什么」不能只看 `npu-smi` 的 `Process name`：它是内核 comm、截断到 15 字符（`sglangschedul` 同时代表 `sglang::scheduler_TP0..N`），读不出模型、TP、端口。要点：

1. 用 `ps -eo pid,ppid,etime,args` 取全量命令行与父进程，才拿到 `--model-path` / `--tp-size` / `--port` / `--mem-fraction-static`。
2. 用 `cat /proc/<pid>/cgroup` 的 64 位 ID 前 12 位对 `docker ps`，判是宿主还是容器；容器内进程的 `Process id in container` 可能仍是 `NA`。
3. `curl /health` + `/get_model_info` 才证明服务在服务；`Util 0%` 只表示此刻没请求。
4. **判「谁占卡」以设备级 `npu-smi info -t proc-mem -i N` 为准**；`-lname '*davinci*'` 扫描会误中 `<defunct>` 与跨机等待的 `torchrun bench_*`，它们持 fd 但不占 HBM，列为「吃 CPU 不占卡」单说。

完整命令、实测样例与判读见 [前向取证](references/serve-forensics.md)。
