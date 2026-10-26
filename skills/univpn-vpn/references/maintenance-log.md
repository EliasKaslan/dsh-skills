# univpn-vpn 维护记录（原 §7 原样拆出）

> 从 `univpn-vpn/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

## 7. 维护记录

- **2026-10-22 创建**。当天纠正了一个关键误判：原先用 `x00886548` 去连 A5 全部 `LOGIN_FAIL`，且因为 §4 的 `Select()` 无效问题，几次「以为连了 A5」其实连的还是蓝区网关（日志 `send the last connect name is 蓝区网关.ini`），一度错误地得出「A5 也到不了 177.8.21.1」的结论。**换 A5 专属账号 `vpn_xmz` 登录后 `177.8.21.1:22` 立刻可达**。
- **同一天证伪了 7 个 `ascend-*` skill 里「A5 已登记凭据但不可达、规格未采」的断言**——那些结论是在**没连 A5**的情况下测 `177.8.21.1` 得出的。真值是：**必须先连 A5，才可达**；`ascend-env` §1 已改，其余 skill 的同一句话以 `ascend-env` §1 与本 skill §2 为准。
- **2026-10-26 补 §7（双 VPN 同时在线）**。装了 `univpn-multi` 的第 2 个实例（`UVP002` / `univpn2` / `29191`+`19061` / `UVP002Service` / `本地连接 2`），第一次让 `192.168.13.188` 与 `177.8.21.1` **同时** `ping` + `tcp 22` 通。当天修正三处旧断言：①「两配置互斥」只在**原生单客户端**成立（§7 的多实例可并存）；②A5 早已是 `RemPwd=1`/`AutoLogin=1`（本文 §2 旧表写 `RemPwd=0`，错）；③「自动填登录表单没跑通」已跑通（`le_username`/`le_password` 必须 `SendKeys`，`ValuePattern.SetValue` 写不进去）。新增可复用脚本 `scripts\univpn-instance.ps1`（State/Connect/Disconnect，按 `instance-00N.json` 取 Product 与 TapGuid）。关键取证：副本 `ClientServerCheck=1` 会导致 `certificate verify failed`（认证前失败，不消耗登录次数）；副本连接列表由**引擎**启动时生成，只重启 GUI 不刷新；勾上「记住密码 + 自动登录」后凭据落进 `%APPDATA%\UVP002\sysconfig.ini` 的 `[Session0] ProfileInfo`，重启 GUI 也能自动连回。

