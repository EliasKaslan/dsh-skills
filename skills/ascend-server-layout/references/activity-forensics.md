# 判「最近 N 小时有没有用过卡 / 机器上在跑什么」：三层取证命令与判读（自 SKILL.md 逐字迁移）

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
grep -E 'session opened|Accepted' /var/log/secure | tail -20   # 时窗对齐 .bash_history 的退出时间，不要写死日期
journalctl -k --since '2 hours ago' --no-pager | grep -iE 'davinci|svm|hisi|ascend' | tail
ls -lt /var/log/npu/slog; find /var/log/npu -newermt '-2 hours' -type f
```

判读：`.bash_history` 停在 `watch npu-smi info` + `docker ps`、且 `last` 显示该会话刚退出 ⇒ **有人一直在盯卡但没在用卡**；`/var/log/npu/slog` 无近 2 小时文件、`journalctl -k` 无设备消息 ⇒ 驱动侧也没有活动。
