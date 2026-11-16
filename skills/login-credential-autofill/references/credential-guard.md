# 原登录 helper 的边界

原 Get-LoginCredential.ps1 会读取 JSON 账号库；Reveal 把密码直接输出到 stdout。原 LoginGuard 以非原子 JSON 更新本地 ledger，未加并发锁；`check` 会判断预算/lockedUntil，但 `attempt` 自身不调用 check，因此单独执行两次 attempt 均可成功记账。本轮仅用独立合成 ledger 验证，不读取真实账号库。

其 sample JSON 只有 demo，而 helper 的 Account ValidateSet 只允许 microsoft/github；“样例能自测”的说法不成立。演示 HTML 会把输入值显示到 DOM，不能当安全登录模板。

若用户另行要求修复守护器，应把检查和记账放在同一原子加锁事务，校验参数范围、并发与时钟边界，并在 fixture 测锁定/解锁/失败/成功状态。此处只留审查结论，不安装旧脚本，也不把本地 ledger 当服务器认证控制。

验证码可保留的经验是识别 iframe/页面上下文、加载失败与风控阶段、保留非敏感错误码及人工完成后检查状态。验证码通过不等于业务操作已完成，需验证最终账号和目标页面。
