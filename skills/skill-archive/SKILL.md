---
name: skill-archive
description: 冷备 skill 索引：读 skills-archive/INDEX.json 找不在目录里的能力。适用于"目录里没有对应的专门流程 / 生图 / 长尾调研 / PR 审计 / 想找旧 skill"。
whenToUse: 任务明显需要一个专门流程，但当前会话目录里没有对应条目时，先查冷备索引。
---

# 冷备 skill 索引（warm tier）

## 何时调用

- 触发信号：用户点名的能力（例如生图、韩国官方源、PR 等价性审计、上一轮 agent 产物验收）在当前会话的 skill 目录里**没有**对应条目；或用户说"我记得以前有个 skill 是做这个的"。
- 转交边界：目录里已有的 skill → 直接用 `skill` 工具加载，不要来查这里；需要新建/融合一条 skill → 用 `sedimenting-skills`。
- 前置：`%USERPROFILE%\.dsh\skills-archive\INDEX.json`（或 `$DSH_HOME\skills-archive\INDEX.json`）可读。
- 后继：按 `INDEX.json` 里的 `path` 用 `read` 打开对应 `SKILL.md`，按它的步骤执行。

## 机制（一句话）

DSH 的 skill 目录**每个请求都要重发**，条目越多、description 越长，成本越高。所以低频/过期/兴趣类 skill 在 frontmatter 写
`disable-model-invocation: true`：它不再进目录（模型看不到），但文件仍在磁盘，可按需 `read` 加载。
这份索引就是那些"冷备"条目的地图。

## 步骤

1. 读索引：

   ```
   read %USERPROFILE%\.dsh\skills-archive\INDEX.json
   ```

2. 在 `entries[]` 里按 `triggers` / `name` 找到匹配项，拿到 `path`。
3. 读该路径的 `SKILL.md`（必要时再读同目录的 `scripts/`、`references/`），按正文执行。
4. 如果这个能力开始高频使用：把它改回热目录——删掉 frontmatter 里的 `disable-model-invocation: true`、
   `warm-triggers`、`warm-reason` 三行，并把 `description` 压到 <= 120 字符；同时确认热目录没有超预算
   （`distill_skill` 的报错会告诉你当前用量）。

## 维护

- 索引由插件在写 `tier=warm` 的 skill 时自动更新；手工改了某个 skill 的冷备标记后，可以调一次
  `distill_skill(decision=merge, target=<某个 warm skill>, title=索引刷新, body=... )` 触发重写，或直接改 `INDEX.json`。
- 不要再新建第二条"索引"skill：单一归属，冷备地图只在这里。

## 不要做什么

- 不要把冷备 skill 的名字直接喂给 `skill` 工具——它会被拒（`is not available for model invocation`）；只能 `read`。
- 不要把高频能力长期放冷备：每次都 `read` 一遍同样违背"低成本、可发现"的设计。
