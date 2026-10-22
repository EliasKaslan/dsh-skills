# 会话日志取证：回收被覆盖的旧版本 + 全会话扫错误串（原 §2.12 / §2.12.1 原样拆出）

> 从 `dsh-agent-customization/SKILL.md` 正文原样拆出（2026-10-22）：内容一字未改，只搬了位置。

### 2.12 从会话日志回收被覆盖的旧版本（DSH 自身的记录面，实测）

文件被**覆盖 / 没备份**时，**旧版本仍能从会话日志里逐字节重建**——日志记着每一次 `read` 的**逐行快照**。

**1) 日志在哪、什么形状**

- 路径：`$DSH_HOME\sessions\<workspace-slug>\<agentId>\session.v4.jsonl.zstd`（实测形态 `--D-workspace-agent-dsh_base--\<uuid>\session.v4.jsonl.zstd`；**一个会话一个目录，子代理也各有一份**）。
- 它是**多帧 zstd 拼接**（每帧 magic `28 B5 2F FD`）⇒ **`zstdDecompressSync` 单次只解第一帧**，只拿到开头那一小段；必须按 magic **切帧循环**解压再拼。本仓现成工具 `tools\session\read-session-log.mjs` 已这么做（实测一次解出 **126 帧 / 235 条记录 / 1283123 字节**），但它**只按 pattern 打印行**，要取证得自己解析 JSONL。
- 日志是 JSONL，逐行一条：`tool/call`（`data.callId` / `data.name` / `data.arguments` 是 **JSON 字符串**，还得再 `JSON.parse` 一次）与 `tool/result`（用 `data.message.toolCallId` 配对）。

**2) `read` 的结果就是一份可逐字节重建的快照**

关键字段是 **`tool/result` 里的 `data.meta`**（不是 `message.meta`，实测那里是 `null`）：

- `meta.path` / `meta.totalLines` / `meta.lang` / **`meta.offset`** / **`meta.lines` = `[{number, text}]`**。
- 重建写法：**`meta.lines.map(l => l.text).join('\n') + '\n'` 逐字节等于当时的文件**（本轮实测 sha256 对上）。
- **注意 `meta.lines` 可能是"窗口"而不是全文**：带 `offset` 的读只回一段（实测 `lines` 40 项而 `totalLines` 是 234）⇒ 直接 `join` 会**静默**产出 40 行的假文件（4690 B 冒充 234 行）。**重建前必须断言 `offset === 1 && lines.length === totalLines`**。
- `content[0].text` 里那份带 `N: ` 行号前缀的正文是**给人看的**，要重建得先剥前缀；**优先用 `meta.lines`**。

**3) 用途 + 自证（本轮实测：`orchestrating-subagents`）**

- 用途：取"**该写手在首次写入之前的那次 `read`**"，就是被覆盖前的旧版本。
- **自证必须双向，只对一个方向不算证明**：
  - **正向** = 对**写手自己在磁盘上实测的** `bytes` / `sha256`（日志原文：`bytes=22962 sha256=3f6a9dd800b622fb BOM=False CR=0 LF=234`）。
  - **反向** = 把日志里它的每一次 `edit`（`old_string` / `new_string`；`replace_all` 决定全替换还是只中首个）**依次回放**到重建文本上，看能否精确复现它**改后**的状态。
- 本轮两个方向都命中：重建 **12860 B**（153 行）+ **5 次 `edit` 全部命中、0 失败** ⇒ 回放终态 **22962 B / sha256 `3f6a9dd800b622fb…c89916`**，与写手自测、以及**我在 PowerShell 里独立算的**磁盘哈希**三者逐字节一致**。顺带一条判据纪律：真值是实测的 **12860 B**，而不是任何"估算的尺寸带"——拿自己估的区间当验收判据会把**正确的交付误判为失败**（见 `orchestrating-subagents` §9.7）。
- 边界：最后一帧可能在追加中被截断 ⇒ 单帧解压失败要**容忍并跳过**，别把整次取证判失败；日志只记**被读写过的内容**——从没被 `read` 过的文件不在里面。

> 会话 id / 隔离 home 路径等属**会话专属证据**，留报告，不进本 skill。

### 2.12.1 全会话扫某个错误串的复现配方（zstd 流式精确匹配）

**要回答"这个报错在本机历史上出过几次、命中哪些会话"** 时用它。会话文件散布在 `C:\Users\admin\.dsh\sessions\<工作区转义名>\<agentId>\` 下，名字有 `session.jsonl.zstd` / `session.v3.jsonl.zstd` / `session.v4.jsonl.zstd` 三种以上 ⇒ **按扩展名 `.zstd` 全树扫**最稳，别按文件名猜。

**必须用精确 JSON 模式匹配**：`content_filter` 这类子串会在**排查会话自己的正文里**反复出现（本轮实测：子串命中 49 行，其中 **39 行**是排查会话里的普通文本巧合）⇒ 裸子串计数会把"我自己的排查过程"当成事件数。

```powershell
$code = @'
import os, zstandard
d = zstandard.ZstdDecompressor()
for dp, _, fn in os.walk(r"C:\Users\admin\.dsh\sessions"):
    for f in fn:
        if f.endswith(".zstd"):
            p = os.path.join(dp, f)
            lines = d.stream_reader(open(p, "rb")).read().split(b"\n")
            for i, l in enumerate(lines, 1):
                if b'"Provider finish_reason: content_filter"' in l:
                    print(p, i, len(lines))
'@
$code | python -X utf8 -
```

- **匹配用 bytes 字面量**（`b'"…"'`）而不是子串技巧：抓的是日志里那个**带引号的 JSON 字段值**，这正是"精确模式"的落地方式。
- **必须流式**（`stream_reader`）：会话日志是**多帧拼接** zstd，单帧 API 只回第一帧且不报错（假否定，逐字配方与证据 → `pwsh-on-windows` 陷阱表"多帧拼接 zstd"行）；`stream_reader` 顺带满足**不落盘**。
- **事件计数判据：行数 ÷ 2 = 事件数**——真实事件在一条 `assistant/attempt` 里**成对出现**（`finish` chunk 行 + 紧随的 `turn/end` 行）⇒ 别把命中行数直接当次数报。本轮实跑：**677 个文件 / 264,383,956 B → 10 行 / 5 事件 / 4 会话**。
- **依赖**：python 的 `zstandard` 模块（无它直接 ImportError）。**本机 zstd 会话合计约 260 MB 量级**（时刻值）⇒ 耗时在解压、不在匹配。
- **坑**：别用 `d.decompress(b)`（单帧，多帧文件只有第一帧）；别按文件名（`session.v4.jsonl.zstd`）找，要按扩展名扫；别忘"÷2"。
- 本节的**下游**：拿到命中的会话后再判"这错误是不是 DSH 的 bug"→ 见 **2.17**（错误串的实装链路行号**单一归属在 2.17**，本节只写扫描配方、不复制链路）。

