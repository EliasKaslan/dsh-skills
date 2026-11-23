# 来源与取舍

沉淀日 2026-11-16，底本 `D:/workspace/share`，原始快照 SHA-256 21/21 匹配。逐项清单与证据在 `D:/workspace/share/codex-review/REVIEW.md`、`D:/workspace/share/codex-review/evidence.json`。

迁入：原 ascend-server-access 的分层诊断、路由关联、A3/A5 隔离、远程传脚本、有限重试与身份认证边界；原 ascend-env 的远程执行经验。

不迁入：vpnctl.ps1 / univpn-instance.ps1 的坐标注入、配置修改与二进制补丁依赖；install-pubkey.py 的自动信任 host key、密码参数和读后整文件覆盖；node-pair-check.py 的静态主机/端口、旧根因及大流量测试。这四个脚本与 fix-vpn-openai-dns.ps1 仍留在 `../scripts/` 作墓碑，调用即以 `BLOCKED_LEGACY_ENTRY` 失败、退出码 2，不是可执行入口。原维护日志留在底本。

更正：ICMP payload 加 IPv4+ICMP 头通常是 28 字节；KEX 超时不能仅凭 ping 定因；host-key 变化不等于已证实重装；GUI 活着不等于隧道在线；一次缺特定 NIC 不能推出所有 HCCL 后端不可用。
