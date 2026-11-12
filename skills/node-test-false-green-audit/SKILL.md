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

## 断言指向了未被构建使用的文件（第 7 类假绿）

**第 7 类假绿：断言指向了根本不参与构建的文件。**

仓库里出现同名或近似文件时（例如 `web/sw.js` 与 `remote/sw.js`），很容易改到、也断言到
那个**被构建脚本跳过**的副本。症状极其隐蔽：

- 测试全绿；
- 真机行为完全没变；
- 代码评审看 diff 也"看起来改对了"。

**判据：核对构建产物，而不是源文件。**
把改动后的产物打开，搜你新写的符号（函数名、注释里独有的短语）。
产物里没有 → 你没改到实际被使用的源。这一步比读十遍源码都快。

**定位方法**：先看构建脚本从哪读文件（`readAsset(join(REMOTE, 'sw.js'))` 这类调用），
再看它的 skip 列表（`WEB_SKIP`、`ignore`、glob 排除）。构建脚本的"输入路径 + 跳过列表"
才是唯一真相，`git ls-files` 只是列出所有文件。

**防线（三条）**
1. 断言必须指向**构建真正读取的源**；在测试里写一句注释说明为什么是这个路径，
   防止后来的人"顺手"改回那个更好找的文件名。
2. 断言要能区分"顺序/结构"而不是只断言"包含"：例如"`fetch` 必须出现在 `caches.match` 之前"，
   比"文件里包含 `fetch`"可靠得多——后者在改错分支时依然通过。
3. 构建号的输入范围要覆盖所有会改变行为的源。若哈希在写入某个产物**之前**就算完，
   "只改那个产物对应的源"的发布会得到同一个构建号，客户端与灰度判断都察觉不到。
   自检方法：只改目标源 → 构建 → 构建号必须变；还原 → 必须回到原值（确定性）。

**一句话**：绿了不等于生效。凡是带构建/生成步骤的项目，
"产物里有我写的代码"才是完成的证据。
