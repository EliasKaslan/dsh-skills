# 半死链路：判据、修复与两个坑

## 症状形态

- 桌面日志：`详情请求收到 …` + `详情响应 原始 X KB → 发送 Y KB（gzip），几 ms` —— 说明请求到了、也答完了。
- 手机：等了很久 →「中继请求超时」；`/api/v1/cloud/status` 的 `nackRepairs=0`（不是分片问题）。
- 结论：回包丢失，链路处于「上行通、下行死」——锁屏唤醒、WiFi↔蜂窝切换后最常见（TCP 半边已死，mqtt 客户端还以为连着）。

## 先做算术：谁先到点，谁定义症状

| 计时器 | 含义 |
|---|---|
| `rpcBudgetMs(attempts, timeout)` | 单条请求的绝对预算（= Σbackoff + 最后一次 timeout；每次 attempt 只是重装计时器，不是累加） |
| `PC_STALE_MS` | 看门狗判「下行静默」后才 `restart('下行静默')` |

若 `预算 < 看门狗阈值`，则**每一次**半死都必然是请求先判死、报 `relay_timeout`（而 `net.js` 又常把它当不可重试的定论）—— 救它的重建永远晚到。用户体感就是「第一个会话很慢、第二个会话直接超时」。

## 修法

1. 看门狗增加第二条判据：**有请求在途 + 下行静默 ⇒ 立刻重建**；重建后由既有的 `resendPending()` 用**同一个 request id** 重发（桌面按 id 幂等回放，不会重复执行）。
2. `relay_timeout` 的 **GET/HEAD** 在链路**确实重建过之后**允许自动补一次（用递增的 `linkEpoch` 判「重建过」）；写方法不重试（新 fetch 会换 request id，语义不同）；`decompress` / 用户取消照旧不重试。

## 判据必须严（否则误重建会拆 ws 隧道、作废正在拼的分片）

```js
// 不要只看「静默 > N」：桌面 beat 8s 一跳，阈值只有 2s 余量时，丢一拍 beat 就误触发。
// 要求「这条请求开始之后一帧下行都没收到」：健康链路不可能这么久不来一拍 beat。
ready && pending.size > 0
  && (now - Math.max(stats.lastRxAt, pcSeenAt, readyAt)) > RPC_STALL_REBUILD_MS
  && (oldestPending.startedAt > lastDownAt)   // 必须用 at 之外的时间戳，见下
  && (now - lastRestartAt) > RESTART_COOLDOWN_MS
```

条目缺 `startedAt` 时退回「只看静默」：宁可多建一次，也不要把自救关掉。

## 两个必踩的坑

1. **别用 `hello` 当保活探针。** 桌面的 `case 'hello'` 是 `if (this.sayHello()) this.beat();`，而 `sayHello(force=false)` 受 `HELLO_MIN_GAP_MS`（10s）限流 —— 被限流时**不回 beat**，探针自己就会制造误判。
2. **`entry.at` 每次 attempt 都会刷新**（`entry.at = Date.now()` 在 `attemptOnce` 里），拿它算「最老的请求」得到的是「最近没发过的请求」——而真正丢片的受害者会一路挂到预算耗尽。判「开始时刻」必须另存 `startedAt`（创建时赋值，之后不再变）。

## 现场判读

新增计数 `stallRebuilds`（静默重建次数），进诊断快照与「复制诊断文本」。

- 它 ≥1 且「RPC 超时未回包」= 0 ⇒ 自救生效。
- 两者同涨 ⇒ 重建也没救回回包，转查桌面侧（此时「迟到的回包」通常也涨）。
- 健康链路上应恒为 0；若莫名增长，把阈值抬高一档或改「连续丢两拍 beat」判据。
