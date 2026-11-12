---
name: node-test-false-green-audit
description: Node 测试与 CI 的「假绿」排查——六类会让你以为跑过其实没跑的陷阱：CI 里写死测试目录或空 glob 静默跳过、await 一个 unref 定时器让 Node 22 把整个文件判 cancelledByParent（fail 仍是 0）、fetch 设 host 头被 undici 静默丢弃导致伪造 Host 的断言恒真、断言里写死版本号每次发版必假红、改名字段后旧断言读 undefined 而空转通过、把平台相关行为当统一行为（大小写折叠只在 win32）。适用于「CI 绿了但本地没跑 / 测试数对不上 / Node 22 全 cancelled / 某个文件后面的测试全没执行 / 这条断言真的会红吗 / 变异测试怎么验 / 发版后测试突然红 / 改名之后测试还绿」。不适用：PowerShell 自身的编码与执行策略坑 → 用 `pwsh-on-windows`；把跑通的流程沉淀成 skill → 用 `sedimenting-skills`。
disable-model-invocation: true
warm-triggers: CI 绿了但没跑 / 测试数不对 / 变异测试怎么验
warm-reason: 低频方法论
---

# Node 测试 / CI 的假绿排查

## 何时调用

- 你说「测试全绿」，但你要确认这 400 条**真的执行了**、且断言**真的会红**。
- CI 红了本地绿，或反过来；尤其涉及 Node 22 与 24 两个版本时。
- 发版、改名、升级依赖之后，测试数字没变（本该变）。

## 六类陷阱（都实测踩过）

### 1. CI 里写死目录 / 空 glob → 静默跳过

```yaml
run: node --test "test/unit/*.test.mjs" "test/protocol/*.test.mjs"   # 新增目录永远不跑
```

- 新增 `test/domain/`、`test/integration/` 后，这条路**本地绿、CI 也绿**，但 CI 根本没跑。
- 反过来也危险：把**目录**当 positional（`node --test test/unit`）会 `MODULE_NOT_FOUND` 退 1；
  匹配不到任何文件的 glob **静默退 0**。
- 判据：CI 的测试数必须等于本地 `node --test "test/**/*.test.mjs"` 的数，差一个就是漏跑。

### 2. await 一个 unref 的定时器 → Node 22 取消整个文件

```js
const delay = (ms) => new Promise((r) => { const t = setTimeout(r, ms); t.unref?.(); });
```

`await delay(5)` 时事件循环在这 5ms 里没有任何活要干就兜底退出，Node 22 的 runner 报

```
failureType: 'cancelledByParent'
error: 'Promise resolution is still pending but the event loop has already resolved'
```

并把该文件**从这一条起的所有测试取消**。Node 24 不复现 —— 于是本地全绿、CI 全红。

- 只看 `fail` 会误判成没事：`ℹ pass 11 / ℹ fail 0 / ℹ cancelled 50`。**cancelled 必须一起看。**
- 定位：本地装同版本 Node（`https://nodejs.org/dist/latest-v22.x/node-vXX-win-x64.zip`）复现，
  比盲改快一个数量级。若 `process._getActiveHandles()` 只剩 runner 自己的两个 `Socket`、
  `_getActiveRequests()` 为 0，说明**没有真泄漏**，问题就是被 await 的 unref 定时器。
- 修法：被 await 的定时器一律不 unref；只有「靠别的句柄（socket / interval）撑住循环」的
  超时兜底才 unref。

### 3. fetch 设 host 头 → 断言恒真

```js
const r = await fetch(url, { headers: { host: 'evil.example.com' } });  // host 被丢弃
```

`Host` 是 forbidden header，undici 静默忽略，请求照旧带真 Host 发出 → 「伪造 Host 被拒」永远
"通过"。伪造 Host 只能用裸 http：

```js
const status = await new Promise((resolve, reject) => {
  const req = http.request({ host: '127.0.0.1', port, path: '/api/v1/health',
    headers: { host: 'evil.example.com' } }, (res) => { res.resume(); resolve(res.statusCode); });
  req.on('error', reject); req.end();
});
```

同类：任何「给原生协议喂保留头/保留字段」的断言，先确认客户端**真的发出去了**。

### 4. 断言里写死版本号 → 每次发版假红

`assert.equal(body.version, '1.0.0')` 这种，升级到 1.0.1 立刻红。改成读 `package.json`
（`JSON.parse(readFileSync(new URL('../../package.json', import.meta.url)))`）——
要钉的是「接口报的版本 = 包版本」，不是某个具体数字。

### 5. 改名字段 → 旧断言读 undefined 而空转

把 `auth.sessionsMtime` 改名成 `sessionsSignature` 后，`assert.notEqual(auth.sessionsMtime, x)`
变成 `undefined != x` → **永远通过**。这种假绿比红危险得多。

- 改名后必须 `grep` 旧字段名（含测试）。
- 涉及字段的断言先断类型：`assert.equal(typeof auth.sessionsSignature, 'string', '字段不在就别空转')`。

### 6. 平台相关行为被当成统一行为

`lib` 只在 win32 折叠大小写（POSIX 里 `/Foo` 与 `/foo` 是两个目录），测试却断言"算同一个" →
Linux CI 必红。断言按平台给期望：

```js
const expected = process.platform === 'win32' ? 1 : 2;
```

同类：路径分隔符、`stat.mode` 权限位、文件名大小写敏感、`realpath` 行为。

## 验证测试「真的会红」

改一处 `lib/` 的关键判定（去掉穿越闸、改上限、删 AAD），跑目标文件 → 必须红；改回 → 必须绿。
拿不到红就说明这条测试是空的。`git checkout -- <file>` 还原，还原后确认 `git diff` 只剩你的预期改动。

## 坑

- 本机 Node 是 24 而 CI 跑 22 时，"本地绿"完全不能证明 CI 会绿，反之亦然；两个版本都要跑。
- `node --test` 的输出里 `pass` 与 `cancelled` 是两个独立计数，别只看 fail。
- 空 glob 的静默 exit 0 也会出现在 `npm run` 脚本里，检查 `package.json` 的 test 脚本是否用了 glob 字符串。
