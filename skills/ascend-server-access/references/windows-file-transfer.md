# Windows 传脚本、跳板与掉线判别

## 1. 传脚本（原有纪律）

复杂 Bash/Python 经本地 UTF-8 无 BOM、LF 文件，用 `scp`/SFTP 传到本任务目录，核对 hash 后执行；执行已有远端文件可加 `ssh -n`。脚本经 stdin 发送时**不可**加 `-n`。Bash heredoc 本身合法，风险在多层 shell 引号和多个消费者抢 stdin；不要无条件 `tail -c +4`（无 BOM 时会截掉三个正文字符）。

PowerShell 5.1 不支持 `<<<` here-string 重定向（报 `MissingFileSpecification`），也不要把远端命令塞进双引号（`$(...)`、`|`、`)` 会被本地展开）。稳妥做法固定为三步：

```bash
# 1) 本地写 .sh（LF、无 BOM；首 3 字节应为 35,33,47 即 "#!/"）
# 2) 上传
scp -o BatchMode=yes local.sh root@HOST:/tmp/x.sh
# 3) 执行并自清
ssh -o BatchMode=yes root@HOST "bash /tmp/x.sh; rm -f /tmp/x.sh"
```

## 2. 跳板：ssh -J / scp -J

本机到目标机路径不通、但同网段的另一台可达时，用 OpenSSH 自带跳板：

```bash
ssh  -o BatchMode=yes -J root@JUMPHOST root@TARGET "hostname; uptime"
scp  -o BatchMode=yes -J root@JUMPHOST local.sh root@TARGET:/tmp/x.sh
```

密钥仍由本机出示，因此 TARGET 上要已授权同一把 key；不需要在 JUMPHOST 上存 key。

### 坑：paramiko 的 ProxyCommand 在 Windows 上必挂

```
OSError: [WinError 10038] 在一个非套接字上尝试了一个操作。
paramiko.ssh_exception.ProxyCommandFailure: ProxyCommand("ssh ... -W %h:%p ...") returned nonzero exit status
PermissionError: [WinError 5] 拒绝访问。   # close() 里 os.kill(pid, SIGTERM)
```

原因：paramiko 用 `select()` 读 `process.stdout`，Windows 上管道句柄不是 socket。**不要**在 Windows 走 `paramiko.ProxyCommand`；要么用 CLI 的 `-J`，要么让 paramiko 直连（目标本身可达时）。

## 3. 判「目标机掉线」还是「本机路径断了」

同一台机器可能只有你这条路径断（VPN/Tailscale 掉线），它其实活着。分层判：

```bash
# 在 Windows：ping + 端口
ping -n 3 192.168.13.188
Test-NetConnection -ComputerName 192.168.13.188 -Port 22 -InformationLevel Quiet

# 在「同网段的邻机」上判主机是否真的不在（最有力）
ip neigh del 192.168.13.188 dev eth0; ping -c 1 -W 1 192.168.13.188 >/dev/null; ip neigh show 192.168.13.188
```

- `INCOMPLETE`：二层都拿不到 MAC，主机确实关机/宕机（与防火墙无关）。
- `REACHABLE` + 端口 OPEN，而本机仍连不上：主机在线，是**本机这条路径**的问题，换跳板而不是去查目标机。
- 邻机连 ICMP 都不通但 ARP 可解：内核活着、sshd 被压满，按重载主机处理（见 `heavy-load-ssh.md`）。

本机 Tailscale 失效时会报 `Unable to connect to the Tailscale coordination server`、`unexpected state: NoState`；依赖 tailnet 子网路由的路径随之消失。

## 4. 别把「能 ping」当「能干活」

主机重启会清掉一切会话。用 `uptime` 两次采样确认是否在反复重启（本轮 40 分钟内两次 reboot），再决定能不能跑长任务。
