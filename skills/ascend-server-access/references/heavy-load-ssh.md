# 重载主机连接受阻：Paramiko 接手 + base64 分片传文件

实测 2026-11-23，`192.168.13.188`（node-zj-110-132，Debian 10，256 核，**load average 286**）。
判断依据：`ping` 155ms 通、TCP:22 可连、`echo ALIVE` 偶尔成功，但 OpenSSH 常报
`ssh_dispatch_run_fatal: Connection to 192.168.13.188 port 22: Connection timed out`。
**这是目标机 CPU 被别人的作业压满导致 sshd 拿不到调度，不是隧道/路由问题**，别重启 VPN。

## 1. OpenSSH 卡 KEX 时改用 Paramiko

同一窗口下 Paramiko 能稳定登录（长超时给了 sshd 喘息空间）：

```python
import paramiko, os
c = paramiko.SSHClient()
c.load_host_keys(os.path.expanduser("~/.ssh/known_hosts"))
c.set_missing_host_key_policy(paramiko.RejectPolicy())   # 仍严格校验 host key
c.connect(HOST, port=22, username="root",
          key_filename=os.path.expanduser("~/.ssh/id_ed25519"),
          timeout=25, banner_timeout=45, auth_timeout=45,
          allow_agent=False, look_for_keys=False)
```

要点：`banner_timeout`/`auth_timeout` 必须放大到 40s 以上；`RejectPolicy` 不要换成 AutoAdd。

## 2. 大文件/长命令会被捱断 → base64 分片追加

现象：
- `sftp.put()` 传 1.6KB 脚本 → `paramiko.ssh_exception.SSHException: Server connection dropped`；
- 441B 的脚本却能成功 → **与体积相关**，不是权限或路径问题。
- 同理，长 inline 命令会直接 `ConnectionResetError: [WinError 10054]`（在 `chan.exec_command()` 就断）。

可用做法（单个持久连接，每片失败重连重试）：

```python
CHUNK = 400          # 解码后的字节数；实际命令约 540 字符
c = connect()
for i in range(0, len(data), CHUNK):
    b64 = base64.b64encode(data[i:i+CHUNK]).decode()
    c.exec_command(f"printf %s {b64} | base64 -d >> {remote}")
```

实测：13108B / 33 片、6989B / 18 片均成功，`md5sum` 与本地逐字节一致。
CHUNK 取 240 更保险（命令更短），代价是次数变多。

## 3. 长任务别占着会话

重载机上把编译/装包放到后台，命令本身保持短小、立即返回：

```
cat > /root/x.sh && setsid nohup bash /root/x.sh > /root/x.sh.out 2>&1 < /dev/null & echo LAUNCHED
```

注意：**不要**把整个 `cat ... && setsid ...` 用 `&` 后台化——那样 `cat` 会抢不到 stdin，写出 0 字节文件（实测踩过）。
正确姿势是分两步：先 base64 写入脚本文件，再用一条短命令 `setsid nohup bash ... &` 启动；之后用
`tail -n N /root/x.sh.out` 轮询。

## 4. 两个会话自杀陷阱

- `pkill -f '<串>'`：串只要出现在自己这条 ssh 命令行里，就会把会话自己杀掉 → `RC=-1`、无任何输出。
  用 PID 精确杀，或写成 `[a]3_188_fix` 这种不自匹配的模式。
- PowerShell 里把远端命令用**双引号**传时，`$(...)` 会被**本地**执行（报 `pgrep : 无法将…识别为 cmdlet`），
  `|` 与 `)` 也会被本地吞掉。远端命令一律写成 `.sh` 文件或单引号字符串。
