---
name: dsh-longhaul-mode
description: DSH 的 Longhaul 长线工程模式——longhaul 插件 7 个工具把「完成」改成密封命令与独立审计者双签，靠 .longhaul 账本哈希链与五道闸挡住改测试、改标尺、绿基线和自评放行。适用于"长线任务用哪个模式 / longhaul_init 怎么开局 / 审计 REVISE 了怎么办 / 契约里写什么 / can-fail 红基线怎么证明 / yardstick 标尺被改为什么被拒 / .longhaul 目录是什么 / --check-baseline 怎么复算基线"，也适用于"装没装 / 装机后为什么没有 longhaul_ 工具"。不适用：只要个干净实验环境起隔离 host → 用 `dsh-isolated-web-host`；判断该不该沉淀成 skill → 用 `sedimenting-skills`。
disable-model-invocation: true
warm-triggers: Longhaul 长线模式 / longhaul_ 工具 / .longhaul 账本
warm-reason: longhaul bundle 未装配到 profile，工具不存在
---

# Longhaul 长线工程模式

> **重建说明**：本文件 2026-11-04 按 v2 run 的审计记录、设计文档与装机校验器重建。原版（12,002 字节）随 DSH 崩溃丢失，工作区与备份里都没有副本。重建版保留被机械校验的三处标记（`can-fail` / `--check-baseline` / `yardstick`）与全部可复现命令，但**行文不是原文**。

解决的问题不是「某一步不会做」，而是**过程失真**：压缩后忘进度、后期爱宣布完成、测试绿≠功能对、写改动的人自己裁决改动是否有效。Longhaul 的办法是把「完成」的判定权从模型手里拿走。

## 何时调用

**加载本 skill 当：**
- 用户要在一个跨多轮 / 跨多个 feature 的工程任务上用 Longhaul，或问「长线任务用哪个模式」。
- 已经在一个 run 里，遇到 `longhaul_audit` 返回 REVISE、`done` 被拒、`contract-stale`、`yardstick-modified`、`no-red-baseline`、`legacy-run` 这类判定，要知道下一步。
- 要写契约（`contracts/F-00x.md`）、要证明红基线（`can-fail`）、要冻标尺（`yardstick`）。
- 要复算 / 校验历史 run 的度量（`--check-baseline`、`--check-round`、`--tamper-probe`）。
- 装机或卸载后问「为什么没有 longhaul_ 工具」——多半是宿主没重启。

**不要用本 skill（转交）：**
- 只要一个干净实验环境起第二个 host → `dsh-isolated-web-host`
- 改 DSH 行为该动哪一层（AGENTS.md / skills / preset / patch）→ `dsh-agent-customization`
- 写本 skill 自己的 frontmatter → `dsh-skill-authoring`
- 本机 PowerShell 的编码 / 计数 / PS7 语法坑 → `pwsh-on-windows`

**前置**：`~/.dsh/profiles/desktop` 里装好 bundle 且**宿主已重启**（插件在宿主启动时装配，之后不热替换）。 ／ **后继**：跑完一个 run 后把摩擦写进 `friction-log.md`，值得复用的方法交给 `sedimenting-skills`。

## 1. 角色与工具

**三角色**：计划者/执行者 = 主会话（写 SPEC、契约、实现、跑验证）；**审计者 = 独立子会话**（`longhaul-auditor` preset），只有 6 个只读工具，**无 write/edit、无 longhaul_*、无 subagent**，拿不到主会话历史，裁决是结构化对象。

**7 个工具**：`longhaul_init` / `_status` / `_record` / `_feature` / `_verify` / `_audit` / `_close`。

**状态目录 `.longhaul/`**：`run.json`、`SPEC.md`、`features.json`、`ledger.jsonl`（只追加，`seq`/`prev`/`hash` 哈希链，断开即 BROKEN）、`audits/`、`contracts/`、`backup/`。该目录**排除在树指纹外**，否则写账本会让自己的验证立刻过期。

## 2. 一次 run 的正确顺序

1. `longhaul_init objective=… spec=<全文> features=[…]`；`reset=true` 会把旧 `.longhaul/` 归档成 `.longhaul.backup-<stamp>`。
2. 写 `contracts/F-00x.md` → `longhaul_audit scope=contract`（**必须 PASS 才能动实现**）。
3. 测试**先于实现**写好并提交，让基线是红的（这是 `can-fail` 的前提）。
4. `longhaul_feature id=F-00x status=in_progress` → 实现 → `longhaul_verify`（密封命令必须真跑）。
5. `longhaul_audit scope=feature` → PASS 才 `status=done` → 提交 checkpoint。
6. 全部 feature 后 `scope=run`，再 `longhaul_close`（**重跑全部密封命令**，不信历史）。

**纪律**：`status=in_progress` 之前契约必须获批；实现后改契约 = 重新预检 + 重审，预算不清零。

## 3. 五道闸（判据都是机械的）

| 闸 | 判据 | 失败长什么样 |
|---|---|---|
| 密封 acceptance | `sha256(acceptance + commands)`，直改 JSON 即 mismatch | `contract-stale` |
| 契约先于实现 | 无 approved contract 就不能 `in_progress` | 拒绝状态迁移 |
| 证据新鲜 | `done` 要求验证指纹 = 当前树 | `stale-verification` |
| 独立审计 | 每维 ≥2 分、无 blocking、审计期间树变自动降 revise | `REVISE` / `blocking` |
| 关门重跑 | close 时重跑全部密封命令 | 任一非 0 即失败 |

**`can-fail`（红基线）**：命令必须在改前**红**、改后**绿**。HEAD 本来就是绿的 → `no-red-baseline`，等于这条断言没证明任何东西。
**`yardstick`（标尺封印）**：回归标尺文件（既有测试、评测记录）一字节都不许改，改了 verify 直接 `yardstick-modified` 失败，**审计都不会启动**。

## 4. 常用命令

**`--preserve-symlinks --preserve-symlinks-main` 不能省**——`@deepseek-ai/schemastery` 只在 `.dsh-src\dsh\node_modules` 里，靠 junction 解析，不加会 `ERR_MODULE_NOT_FOUND`。

```powershell
cd D:\workspace\261102_新模式探索

# 闸门可证伪（42 case；注意：没有 --help，传了也不报错，会静默跑全套约 2 分钟）
node --preserve-symlinks --preserve-symlinks-main tools/gate-selftest.mjs        # 321 passed / 0 failed

# 集成测试 / 探针闸 / 续跑简报
node --preserve-symlinks --preserve-symlinks-main tools/test-longhaul.mjs        # 43
node --preserve-symlinks --preserve-symlinks-main tools/audit-gate-selftest.mjs  # 10
node --preserve-symlinks --preserve-symlinks-main tools/resume-selftest.mjs      # 78

# 度量与反作弊对照（--check-baseline 重算历史 run 的基线，改一个数字就 exit 1）
node --preserve-symlinks --preserve-symlinks-main tools/gauntlet.mjs --check-baseline
node --preserve-symlinks --preserve-symlinks-main tools/gauntlet.mjs --check-baseline --tamper-probe
node --preserve-symlinks --preserve-symlinks-main tools/gauntlet.mjs --check-round 2

# 装机校验（真实模式只读，exit 1 表示没装好并逐条点名）
node --preserve-symlinks --preserve-symlinks-main tools/install-check.mjs
python tools/validate-bundle.py
```

## 5. 装机与回滚

```
C:\Users\admin\.dsh\profiles\desktop\local-bundles\longhaul\      ← 包本体
C:\Users\admin\.dsh\profiles\desktop\node_modules\dsh-longhaul    ← junction 指向它
package.json:  "dsh-longhaul": "link:C:/Users/admin/.dsh/profiles/desktop/local-bundles/longhaul"
dsh.profile.bundles 追加 "dsh-longhaul"
~\.dsh\skills\dsh-longhaul-mode\SKILL.md                          ← 文档，install-check 会查
```

- 装：复制 `longhaul\*` → `local-bundles\longhaul\`；`cmd /c mklink /J` 建 junction；改 `package.json` 两处；放 SKILL.md；跑 `install-check`（期望 `INSTALL ok 9 files`）；**重启宿主**。
- 撤（三种，任选）：`plugin_manager remove_bundle dsh-longhaul`；或还原 `backup-desktop-profile\package.json.*.bak` 后删 `local-bundles\longhaul`；或只退安装副本。
- 装机副本被运行中的 host 占用时，先复制到临时文件再改名替换，失败时旧副本与备份都还在。

## 6. 坑与修法

1. **判版本别看 `package.json` 的 `version`（一直是 1.0.0）** → 看 `lib/index.js` 的 `GATE_VERSION`（v2 = 2）与 `lib/rubric.js` 的 `RUBRIC_VERSION`（v2 = `2.0.0`）。
2. **宿主启动时装配插件，之后不热替换** → 装完不重启，会话里根本没有 `longhaul_*`；反过来，宿主比安装更早启动时，加载的是**旧版代码**（v2 报告里「代码是 v2、跑的工具是 v1」就是这么来的）。
3. **`gate-selftest.mjs` 没有 `--help`** → 传了会被静默忽略并跑全套，只能看尾部 `N passed, M failed`。
4. **工作区不是 git 仓库时 scope 闸门永不真判** → 每份审计记 `legacy-run`，`changed-path` 从未机械校验。开 run 前先 `git init` + 提交基线。
5. **审计输出超 `max-tokens` 会白等一次完整审计** → 该次记 `verdict=error`、`effectiveVerdict=revise`；报告里若只印 effective 值，会把「审计器崩了」看成「审计不通过」。约束 findings 数量与措辞长度可缓解。
6. **一次审计约 5–12 分钟且是阻塞调用** → 等审计时去写下一份契约，别空等；真流水线要等新版本。
7. **`auditId` 可能被多份记录复用**（历史遗留），`gauntlet --check-round` 只比对记录自身、不回查 `.longhaul\audits` → 别把 auditId 当唯一键。
8. **判「装没装」要两侧同时成立** → 清单里有该包 **且** 包目录存在；只查一边会把「源码里有完整实现」当「已装」。

## 7. 成本

每 feature ≥1 次契约审计 + 1 次 feature 审计，每 run 1 次 run 审计；比裸跑**贵一个数量级**，小任务不划算。换来的是：删掉的断言、改过的标尺、本来就是绿的基线、自评放行，这四类在结构上做不到。
