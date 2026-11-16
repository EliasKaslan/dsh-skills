# VPN 并存时的 DNS/TLS 诊断

原 DSH skill 于2026-11-16新增“双 VPN 后 DSH/ChatGPT 不通”案例。它提供 DNS 注入、NRPT、接口优先级与重连的排查线索，但不能把该案例提升为固定根因。

## 收集证据

分别记录目标路由/接口、`Get-DnsClientServerAddress`、`Get-DnsClientNrptRule`、`Get-DnsClientNrptPolicy -Effective`、代理与 hosts；比较系统解析和明确选定解析器在相近时间的结果，并保留 CNAME/TTL/查询类型。接口 metric 可以影响选择，但不足以独自证明 Windows 多接口解析实际走哪台服务器。CDN/地理位置/缓存可以造成正常答案差异，不能以“与8.8.8.8不同”直接判投毒，也不能钉死某组 Cloudflare IP 为永远正确。

在目标域名/SNI不变、证书校验正常的条件下区分DNS、TCP、TLS和HTTP阶段；若应用请求失败，检查其实际域名/代理/错误，不以另一个域名返回401证明应用恢复。网卡流量无法判断DSH是否有任务在跑，应从任务/进程的实际状态判断。

## 修改与回退

修复仅在本轮任务确实需要改变网络配置时进行，先保存精确接口配置、有效策略和要改规则的标识。企业内网DNS与目标域名策略可能不同，不一律把TAP DNS换公共解析器。新建规则应带本任务可识别注释/名称；已有同namespace规则要核实来源、解析器和策略优先级，不能只因namespace存在便跳过。用有效策略与原失败请求验证生效，并考虑重连后的实际情况。

回滚只恢复本次改动：按记录规则ID移除本次新增项，恢复原接口静态DNS/DHCP设置；禁止原文 `Get-DnsClientNrptRule | Remove-DnsClientNrptRule -Force` 全删其他人的规则。失败应返回非零并保留未完成项，不用“写了日志/命令返回”表示成功。

## 原脚本的独立核查

`fix-vpn-openai-dns.ps1` 已停用、未对真实网络运行。只在隔离PowerShell进程中把全部网络cmdlet替换为内存fixture，复现：已有`.chatgpt.com`规则指向不同resolver时被直接SKIP；所有写操作抛异常时仍执行到结尾并退出0。脚本不支持精确owner回滚，原文回滚会删除全部NRPT规则。证据在本批审查`prior/dns-delta-tests.json`，不是DNS事故根因复现。

一手命令语义：[Get-DnsClientNrptPolicy](https://learn.microsoft.com/en-us/powershell/module/dnsclient/get-dnsclientnrptpolicy)、[Remove-DnsClientNrptRule](https://learn.microsoft.com/en-us/powershell/module/dnsclient/remove-dnsclientnrptrule)。
