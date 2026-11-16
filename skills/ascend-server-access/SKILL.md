---
name: ascend-server-access
description: 诊断 Windows 经 UniVPN 访问昇腾服务器时的隧道、路由、TCP、SSH 与跨机通信问题；适用于机器连不上、A3/A5 双隧道和 SSH 握手卡住，不处理 CANN 安装。
whenToUse: 诊断 Windows 经 UniVPN 访问昇腾服务器时的隧道、路由、TCP、SSH 与跨机通信问题；适用于机器连不上、A3/A5 双隧道和 SSH 握手卡住，不处理 CANN 安装。
---

# 昇腾服务器访问

先分清失败层：本机客户端与 TAP → 目标路由 → TCP/SSH 握手 → 身份认证 → 远端命令。一个层面的成功不能代替后一层；ICMP 被禁也不能据此否定 TCP 可达。

## 入口与诊断

- 用户现有服务器与隧道线索见 [本地环境](references/local-site.md)。这些是带日期的候选目标，使用前核实本轮范围与当前状态。
- 查 `Get-NetAdapter -IncludeHidden`、`Get-NetRoute -AddressFamily IPv4`。用接口 GUID 和目标网段关联实例，`ifIndex`、虚拟 IP、网卡显示名都会变化。TAP Up、非 APIPA 地址和目标网段路由同时成立，才说明该隧道具备目标路径；还需测目标端口。
- TCP 探测要有短超时并关闭 socket；异步 `WaitOne()` 为真仅代表操作结束，还须 `EndConnect()` 才能判成功。`Test-NetConnection` 本身有效，但逐主机调用可能较慢。
- SSH 使用现有公钥和已核对的 host key，设置连接超时与 `BatchMode=yes`。别名先用 `ssh -G <alias>` 核实，未配置就用明确的账号和 IP。
- 批量只读探测可用 [scripts/probe_hosts.py](scripts/probe_hosts.py)：`python probe_hosts.py user@IP1 user@IP2 --inventory`。必须显式列目标；无密码回退、无 host-key 绕过，保留原始遥测而不自动判空卡。TCP socket 与 SSH alias/proxy 的路径可能不同，分别解释结果。
- 握手卡在 KEX 时，比较小包/大包、直连/已准入跳板、不同客户端，保存 `ssh -vv` 的失败阶段。Windows IPv4 `ping -f -l N` 的报文长通常为 `N+28`；通 1416、丢 1424 只提供条件性 PMTU 线索，不能独自证明 MTU 黑洞或排除服务端负载。
- 同一隧道其他主机可达、仅一台失败时，先查该主机/路径；不因单机失败重建整个 VPN。
- 双隧道后网页/API出现DNS或TLS异常时，按 [VPN DNS诊断](references/vpn-dns.md) 分层取证；不用固定IP或简单答案差异直接认定根因，网络策略变更保留精确回退。

## 恢复的边界

客户端进程消失且 TAP 完好时，可按本轮访问需求启动已配置的客户端，再等待目标路由。进程存在但已 logout 时，重复启动不能代替连接。缺 TAP 时先核对实例元数据与实际 GUID；修驱动、重打二进制补丁或切走现用隧道是单独的变更，先把影响与回退做成可审查方案。

遇 `AUTH_MSGCODE_LOGIN_FAIL` 停止自动重试，核对账号/配置与凭据来源，避免锁号。host key 改变需先核实重装记录和新指纹；不要直接删 `known_hosts` 或用 `AutoAddPolicy` 绕过。TLS 证书失败优先修 CA、名称和证书链，不继承旧经验中关闭证书校验的做法。

配公钥仅在用户要求接入/配钥时执行：保留已有 `authorized_keys` 内容，追加前检查完整 key 的存在性，避免读后整文件覆盖造成并发丢 key；完成后独立验证 key-only 登录。凭据不写入 skill、日志、命令行或生成的脚本。

## 跨机任务

分别验证管理网、双向身份认证、共享存储的实际来源，以及目标通信后端的设备互联、IP/链路和兼容矩阵。不能从 `ssh` 或 1GbE 灌流成功推出 HCCL 可用；也不能把某次缺 Mellanox 网卡推成所有昇腾跨机必须有该网卡。以目标硬件的互联拓扑、HCCL 版本和实际 collective 冒烟为准。大流量测试需要任务确实需要，避免以“只读检查”名义压测共享网络。

## Windows 传脚本

复杂 Bash/Python 经本地 UTF-8 无 BOM、LF 文件，用 `scp`/SFTP 传到本任务目录，核对 hash 后执行；执行已有远端文件可加 `ssh -n`。脚本经 stdin 发送时不可加 `-n`。Bash heredoc 本身合法，风险在多层 shell 引号和多个消费者抢 stdin；不要无条件 `tail -c +4`（无 BOM 时会截掉三个正文字符）。

长任务记录本任务 PID、日志、退出码及恢复点。停止时核对 PID 的启动时间与命令，不用宽泛 `pkill -f`。Git 下载先区分 DNS/TCP/TLS/认证，代理仅进程级或仓库级；不把旧的第三方镜像域名当固定依赖，也不向它转发凭据。

来源与未迁入项见 [取舍记录](references/provenance.md)。
