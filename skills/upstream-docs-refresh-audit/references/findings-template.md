# findings/REQ-XX.md 模板（≤60 行，每个需求子代理落盘用）

实测取自 `D:\workspace\260928_vllm资料确认\findings\REQ-03.md`（57 行）。子代理只回 JSON，正文写本文件。

```
# REQ-XX <需求原文> — 资料核查

仓库：<repo 绝对路径，正斜杠> @ <commit>（detached HEAD，<日期>，worktree 干净）

## 结论
- 映射是否成立 / code_status / docs_status / needs_refresh 取值
- 需业务澄清的一句话（若有）

## 映射与证据
- 实测关键词全集（把搜过的每一个别名都列出来，含反例）
- 别名误命中落在哪些无关实体上（file:line）
- 明确排除的死路（如 nav_titles.py 不是代号映射表——它是**用户可见页名**表，判「用户看到的页名」时才是权威）

## 代码证据（file:line）
- `path:line` — 该行是什么
- `git status --porcelain` → 0 行 ⇒ 检索覆盖全部文件

## 资料现状（逐文件说明已有 / 缺什么）
- 每个相关文档页：已有 :行 什么；缺什么

## 刷新方案（文件 + 章节 + 具体补什么内容）
- 逐条：`docs/source/...md`（`:<line>` 锚点）→ 具体改/加什么；映射未建立则写「无（空）」

## 坑与不确定
1. ...
```

硬要求：needs_refresh 只能取 `yes` / `partial` / `no` / `unclear`；`unclear` 时「刷新方案」必须为空并写明「若用户确认 X 则按三步补：教程页 / 矩阵行 / mkdocs.yml + nav_titles.py 登记」。
