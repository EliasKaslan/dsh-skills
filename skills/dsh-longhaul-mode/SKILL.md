---
name: dsh-longhaul-mode
description: 长线工程模式 Longhaul（dsh-longhaul）——跨小时/跨天、需要交接的工程任务该用哪个模式、怎么开、完成了凭什么算完成：三角色（计划 / 执行 / 只读审计）、`.longhaul` 状态与哈希链账本、密封验收命令、契约审计 → feature 审计 → run 审计 → close 四道闸、审计 REVISE 怎么改、没给 adversarial probe 为什么降级；含 v2 闸门（can-fail 红绿证明 / 改动范围 / 标尺封印 / 探针）、安装位置、重启与回滚。适用于"长线任务用哪个模式 / 怎么开 Longhaul / 这个功能做完了吗凭什么 / 审计说 REVISE 怎么办 / .longhaul 是什么 / Longhaul 装哪了 / 怎么关掉这个模式"。不适用：改 preset 挂载与生效时机 → 用 `dsh-agent-customization`；起隔离 host 实测 → 用 `dsh-isolated-web-host`；写或改 skill → 用 `dsh-skill-authoring`。
whenToUse: 用户要做跨小时/跨天、需要中断续做或交接的工程任务，问该用哪个模式、怎么开、完成判定凭什么，或已经有 Longhaul 会话需要读懂 .longhaul 状态与审计裁决时用。模型看不到本节。
---

# Longhaul 长线工程模式

> 交付物在 `D:\workspace\261102_新模式探索\`：包 `longhaul\`、设计说明 `Longhaul-长线模式-设计与验证.md`、调研 `long-horizon-agent-evidence.md`。

## 何时调用

**加载本 skill 当：**

- 用户要做的任务明显跨小时/跨天，或中途会压缩上下文、换会话、交给别人接手。
- 用户问"这个功能做完了吗 / 凭什么说完成 / 谁来验收"，而任务不是一次会话能收尾的。
- 已有 Longhaul 会话，需要读懂 `.longhaul/` 的状态、审计裁决或 `RUN_REPORT.md`。
- 需要装、升级、回滚这个模式。

**不要用本 skill（转交）：**

- 只是改 preset 的挂载、配置键、生效时机 → 用 `dsh-agent-customization`。
- 要起隔离 host 做挂载实测 → 用 `dsh-isolated-web-host`；会话级验收 → 用 `dsh-agent-preset-verification`。
- 单文件、单命令的小任务 → 不要用 Longhaul，直接用默认模式。

**前置**：模式已安装（见下"安装位置"），会话创建时选了 `longhaul`。／ **后继**：任务收尾时用 `longhaul_close`，不要用"我完成了"代替。

## 它是什么

一个 DSH agent preset：把"完成"从模型的自述，变成**密封命令 + 独立只读审计者**共同签字的结论。

| 角色 | 载体 | 边界 |
|---|---|---|
| 计划者 | 主会话（可开 plan mode） | 写 SPEC、拆 feature、定可观察的验收标准与命令 |
| 执行者 | 主会话 | 写契约、实现、跑验证、记账本 |
| 审计者 | `longhaul-auditor` 独立子会话 | 6 个工具，**无** `write`/`edit`、**无** `longhaul_*` |

关键点：审计者是**另一个 preset 的独立会话**，没有主会话的对话历史，只看 `.longhaul/` 的证据与工作区。

## 怎么开

1. 新建会话时在模式列表选 **Longhaul 长线工程**（id `longhaul`）。
2. 如果列表里没有：重启 DeepSeek Harness（preset 声明在宿主启动时装配）。`longhaul-auditor` 是内部角色，不要手选。
3. 第一条消息就把目标、非目标、验收方式说清楚；模式会先 `longhaul_init` 落盘，再要求写契约。

## 协议（照做，不要跳）

```
longhaul_init → 写 .longhaul/contracts/<id>.md → longhaul_audit scope=contract
→ longhaul_feature status=in_progress → 实现 → longhaul_verify
→ longhaul_audit scope=feature → longhaul_feature status=done
→ longhaul_audit scope=run → longhaul_close
```

七个工具：`longhaul_init` / `longhaul_status` / `longhaul_record` / `longhaul_feature` / `longhaul_verify` / `longhaul_audit` / `longhaul_close`。

## 完成凭什么算：五道闸 + 三道机械闸

五道闸（代码强制，绕不过）：

1. **密封**：`acceptance + commands` 一起哈希；手改 `features.json` → `seal mismatch`，验证与审计直接拒绝。要改标准只能 `longhaul_feature action=update` 并给 `reason`，代价是契约批准、验证、审计全部清空。
2. **契约先于实现**：`in_progress` 需要一次通过的 contract 审计。
3. **独立审计**：`done` 需要一次通过的 feature 审计，且覆盖该范围全部维度、每维 ≥2、无 blocking finding；审计期间工作树若被改动，结论自动降级为 `revise`（`workspaceMutated`）。
4. **新鲜证据**：验证与审计记录的工作树指纹都必须等于当前树；改过代码就重跑。
5. **关门重跑**：`longhaul_close` 重跑全部密封命令，要求 run 审计指纹仍匹配，才写 `RUN_REPORT.md` 并置 `closed`。

### v2 追加的三道机械闸

`longhaul_verify` 里另有三道**代码**闸，判据不是审计者的自由心证：

| 闸 | feature 字段 | 判据 | 失败长什么样 |
|---|---|---|---|
| can-fail | `baseline`（`git@<sha8>` / `copy`） | 在基线上重跑同一批密封命令，**至少一条必须变红** | `can-fail=green` → `no-red-baseline`；基线树起不来 → `baseline-unavailable`（都不算通过）。只有"基线本来就该全绿"才用 `allowGreenBaseline.reason` 豁免 |
| scope | `writable`（工作区相对 glob 数组） | 基线 → 当前树的改动全部落在 `writable` 内 | `scope=violation`，列出越界路径（前 20 条） |
| yardstick | `yardstick`（工作区相对 glob 数组） | 只读标尺（测试、校验脚本）一个字节都没动 | `scope=yardstick` → `yardstick-modified`，验证直接失败、不进审计 |

- 基线在 `status=in_progress` 时抓取；之后改 `acceptance`/`commands`/`writable`/`yardstick`/`allowGreenBaseline` 任何一项，封印与基线一起作废。
- 报告里固定一行 `- Gates: can-fail=red · scope=ok · git@64b73691 · 2 baseline run(s)`；`disabled` 与 `legacy-run` 是唯二表示"没判"的值（`legacy-run` = v1 run，没有 `gateVersion`）。
- 证据核对（不起 host、不花 token）：`node tools/gauntlet.mjs --check-baseline` 核对 round-1 基线，`node tools/gauntlet.mjs --check-round 2` 重算 round-2 记录并比对 `gauntlet/COMPARISON.md`。

## 状态自查

```powershell
Get-Content .longhaul\run.json
Get-Content .longhaul\features.json | ConvertFrom-Json | % features | Select id,status,commands
Get-Content .longhaul\ledger.jsonl | Measure-Object -Line     # 哈希链，BROKEN 会在 longhaul_status 里报
Get-ChildItem .longhaul\audits
Get-Content .longhaul\RUN_REPORT.md
```

不要用 `write`/`edit` 改 `.longhaul/` 下任何文件——那是篡改，审计会抓。

## 审计说 REVISE 怎么办

1. 读 `audits/A-####.json` 的 `requiredFixes`，**逐条**改 `.longhaul/` 里被点名的产物（通常是契约或实现）。
2. 不要重跑同一份材料赌一次 PASS；不要在 `longhaul_record` 里把 finding 说成"minor"。
3. 契约改了要重新 `longhaul_audit scope=contract`；实现改了要重新 `longhaul_verify` 再 `longhaul_audit scope=feature`。
4. 审计者的典型有效发现：验收命令可被伪造（如查表硬编码）、测试被弱化、证据与工作树不符、契约缺证伪方法、越出声明范围。这些都不是格式问题，要真改。

## 成本与适用边界

- 一次 feature 审计通常是 5–15 次工具调用、几分钟；四次审计跑一个小功能约 20 分钟。小任务不划算。
- 它值钱的地方：跨会话/跨天、需要交接、错误"完成"的代价远高于审计成本。
- 它不替代人类合并，也不保证正确；它保证**不可自证**。

## 安装位置（本机）

```
C:\Users\admin\.dsh\profiles\desktop\local-bundles\longhaul\       包本体
C:\Users\admin\.dsh\profiles\desktop\node_modules\dsh-longhaul     junction → 上面
C:\Users\admin\.dsh\profiles\desktop\package.json                   dependencies + dsh.profile.bundles
```

- 升级：覆盖 `local-bundles\longhaul\` 里的文件，重启应用。覆盖前后都跑 `node tools/install-check.mjs`（逐文件 sha256、junction 指向、包名/版本、文档标记、`backup-desktop-profile/longhaul-*`）；它只读，失败会打印 junction 的重建命令。
- 回滚：`plugin_manager remove_bundle dsh-longhaul`，或恢复 `D:\workspace\261102_新模式探索\backup-desktop-profile\` 里的两个备份与 `longhaul-<stamp>\` 目录。
- `@deepseek-ai/*` 是可选 peer，由 host 的 profile resolution 从安装目录供给，**不要**往包里放 `node_modules`。

## 已知坑

- **审计者也会跑偏**：它可能去反编译 harness 或枚举内部哈希。`lib/rubric.js` 已写入"不要调查 harness、5–15 次工具调用、超过 25 次返回 blocked"的约束；改提示词时保留这三条。
- **只读是文件工具层的**：审计者的 `pwsh` 技术上能写文件；审计前后指纹会抓到，并降级结论。不要据此说"绝对不会写"。
- **`.longhaul/` 不进指纹**：所以记账、写审计不会让验证过期；反过来，删掉 `.longhaul/` 就等于丢掉全部证据。
- **`!!js` 表达式**：patch 里 `disabled: !!js ...` 是 Loader 方言，YAML 解析器直接读会报错，校验时先降级成字符串。

## v2 闸门（比 v1 多拦的四件事）

v1 只验"命令 exit 0 + 审计者说 pass"，于是"红测试从未真红过""改到不该改的文件""事后偷偷放宽判据"都能过。v2 在代码层补了四道，注意它们各自的**可观察信号**：

- **can-fail 红绿证明**：验收命令必须先在**基线树**上跑出失败（红）再在实现树上跑出通过（绿），记录 `baseline.results`。只跑绿 = 不成立；命令在基线上退出 0 说明它从没能力证伪。`longhaul_feature` 里 `canFail.allowGreenBaseline` 是给"基线本来就不该过"的场景开口子的，别默认打开。
- **改动范围（writable）**：`longhaul_run` 声明本 feature 允许改的路径，写到声明外会在 verify 时被抓。契约里写清"改哪些、为什么"。
- **标尺封印（yardstick）**：acceptance 与 commands 一起算 sha256。改任何一个字都要 `longhaul_feature action=update` 并给 `reason`；手改 `features.json` 等同篡改。
- **审计探针（probe）**：feature 审计的 `pass` 必须带至少一条真实对抗探针（`input`/`expected`/`observed` 三个字段都非空）；没有就被机械降级成 `revise`，`probeGate.reason` 会是 `no-adversarial-probe`，而不是审计者心情问题。

## 操作经验（v2 实测，2026-11）

- **审计调用要限长**：`longhaul_audit` 的 `focus` 写成"只回结构化 verdict、最多 3 条、别引用契约全文"能显著降低 `verdict: error` / `stopReason=max-tokens`（本机实测：不限长连续 3 次 error，限长后一次过）。error 不是 finding，重试一次比改材料划算。
- **一次契约文字修正 = 一次完整重审**：改契约文件会让 `contract-stale` 生效，verify 与 feature 审计都被挡住，直到重新 `scope=contract` 审过。所以改契约要"一次改净"（把审计者点的每条都在同一轮改完），否则每轮多付 12–20 分钟。
- **指纹方言取决于跑它的 host 进程**：`.longhaul` 与日志类产物是否计入指纹，由当时加载的模块版本决定；老进程与新代码会算出不同 hash。**结论：verify 与审计必须在同一个新起的 host 上跑**，否则"同一棵树两个指纹"会被判过期。
- **审计者会看工作区里的凭据**：`.dsh-lab/.credentials.yaml`、带 token 的会话日志都算泄露面。实验环境放 `%TEMP%`，别放在被审计的树里。
- **别把会误报的检查塞进闸门**：本轮试过"transcript 判决必须等于记录判决"，在干净树上就误报 3 条（审计者 transcript 里出现的 `verdict:pass` 来自它读过的别的审计 JSON）。闸门加严前先在未篡改的树上跑通，否则等于自毁验收命令。
