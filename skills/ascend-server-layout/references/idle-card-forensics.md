# 判空卡取证：davinci fd / 设备级进程表 / 远端采证（自 SKILL.md 逐字迁移）

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
