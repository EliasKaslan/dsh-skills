---
name: git-tag-diff-audit
description: 两个 git tag 之间做实质变更审计——两 tag 无共同祖先时 merge-base 静默返回空、git log A...B 静默给出两段历史之和，取数一律改两点 git diff A B；用 name-status 的 A/M/D/R 列判新增还是修改，用 git cat-file -e <导入根>:<path> 把变更分「有 commit / 导入边界」两类；接口下线要全树 git grep -w、平台矩阵用报错字符串集合做差集、测试假绿查构建侧闸门、文档真删除不能用 -M 判。适用于『两个 tag 之间改了什么 / 版本对比 / 发版审计 / diff 怎么取数 / 无共同祖先 / merge-base 是空的 / 这条变更有没有 commit 能归因 / 接口是不是被删了 / 支持矩阵变了没 / 测试是不是假绿 / 文档是不是真删了』。不适用：只审单个 PR 是否等价改写 → 用 pr-change-equivalence-audit；要按版本矩阵装环境跑 UT 与 ATK 精度 → 用 mindspeed-ops-smoke。
whenToUse: 要对一个仓的两个 release tag（尤其两 tag 无共同祖先、历史被重建或整树导入过）做发版差异审计、判「版本之间到底改了什么」时使用：取数口径（两点还是三点 diff）、新增/修改/删除判定、变更能否归因到 commit、接口下线、平台与架构支持矩阵、构建配套版本号、测试假绿、文档真删除。也用于回答「merge-base 为空还能不能比 / 这条变更有没有 commit / diff 该用两点还是三点」。
disable-model-invocation: true
warm-triggers: 两个 tag 之间改了什么 / 无共同祖先 / 发版审计
warm-reason: 低频审计方法论
---

# 无共同祖先的两个 git tag 之间做实质变更审计

**主线**：两 tag 的比较只依赖**树对象**，与 commit 图无关；而「谁改的」只能靠 commit 图。
两 tag 无共同祖先时，前者照样成立、后者会静默失真 —— **把取数与归因当成两件事分开做**，是这一类审计唯一的方法论核心。
下文 `<A>`/`<B>` 为旧/新 tag；命令统一带 `git -C <repo>` 前缀，pwsh 里把 `<repo>` 写成 `$R`。

## 何时调用

- **触发信号**：`两个 tag 之间改了什么` / `版本对比` / `发版审计` / `升级前后差异` / `diff 怎么取数` / `merge-base 是空的` / `这条变更有没有 commit` / `接口是不是被删了` / `支持矩阵变了没` / `测试是不是假绿` / `文档是不是真删了`。
- **前置条件**：`<repo>` 里两个 tag 都已 fetch；**只读**（`--no-pager`、不 checkout、不动工作树，需要干净树就另建 worktree）。
- **不适用**：只审单个 PR 是否等价改写 → 用 `pr-change-equivalence-audit`；要按版本矩阵装环境跑 UT / ATK 精度 → 用 `mindspeed-ops-smoke`；只判 Node 侧测试假绿 → 用 `node-test-false-green-audit`。
- **产出**：一页事实基线（tag → commit → 提交日期）+ 分域清单（新增 / 修改 / 删除）+ **每条变更的归因标签**（有 commit / 导入边界）+ 缺口与风险清单。所有数字必须能追到一条可重跑的命令。

## 0. 先判祖先关系，再决定能不能用 log

```bash
git -C <repo> --no-pager merge-base <A> <B>                  # rc=1 且空输出 = 无共同祖先
git -C <repo> --no-pager log --oneline --max-parents=0 <B>    # 找历史重建的导入根
git -C <repo> --no-pager rev-parse <A> <B>                    # 落盘 tag 的 commit 与提交日期
```

| 观察 | 判定 | 后果 |
|---|---|---|
| `merge-base` rc=1，stdout 与 stderr 都空 | 无共同祖先 | `A...B` 家族全部禁用（见坑 1、2） |
| `--max-parents=0 <B>` 只有一个不相关的根提交 | 历史被重建 / 整树导入 | 归因必须区分「有 commit」与「导入边界」 |
| `git diff <A>...<B>` 报 `no merge base` | 同上 | 改两点 diff |

## 1. 取数：一律两点 diff

```bash
git -C <repo> --no-pager diff <A> <B> --stat                        # 总量
git -C <repo> --no-pager diff --name-status <A> <B> -- <subdir>     # A/M/D/R ← 判增删改的唯一权威
git -C <repo> --no-pager diff --numstat    <A> <B> -- <subdir>      # 只用来排行数，别用来判新增/修改
git -C <repo> --no-pager diff --raw        <A> <B> -- <subdir>      # 判文件模式变更
git -C <repo> --no-pager ls-tree -r --name-only <A> -- <dir>        # 与 <B> 的存在性集合做差
```

按域拆开跑（代码 / 构建 / 文档 / 测试），每个域独立落盘，别把全量 diff 一次灌进上下文。

## 2. 归因：每条变更要么有 commit，要么是导入边界

```bash
git -C <repo> --no-pager log --no-merges --pretty=format:'%h %ad %s' --date=short <A>..<B> -- <path>
git -C <repo> cat-file -e <导入根>:<path>    # rc=0 说明该状态在导入根已存在 => 无区间内 commit
```

`git log <A>..<B>` 只反映 **B 分支自身历史**，和「两棵树差多少」无关，两个数字不要混着写。
命中为空不代表没变更：先看 `cat-file -e`，再在结论里显式标注 **【导入边界，无 commit】**，不要默认归给某个提交。

## 3. 判据表

| 看到的现象 | 判定 | **不要**判成 |
|---|---|---|
| `--name-status` 行为 `A` | 整文件新增 | 「旧文件 +N 行」 |
| 行为 `M`，但 diff 首行是 `new file mode 100644` | 实为新增 | 同上 |
| `--numstat` 为 `0 0` | 空文件（常见于补 `__init__.py` 修打包） | 别当「注释级改动」，也别计入实质变更 |
| `git log -- <path>` 为空 | 变动在导入根，**无 commit** | 「文件没变」 |
| 行为 `D` | 待定：删除 / 重命名 / 改名拆分 | 「删除了某能力」 |
| 全树 `grep -w <符号> <B>` 为 0 | 符号确实消失 | 「某 .cpp 被删了所以接口下线」（单文件不足证） |

## 4. 五条专线

### 4.1 接口下线：必须全树 grep
```bash
git -C <repo> --no-pager grep -w -c <symbol> <A> -- .
git -C <repo> --no-pager grep -w -c <symbol> <B> -- .
```
两 tag 各取「文件 → 命中数」再求差。旧版有、新版全 0 = 真下线（Python wrapper、C++ 绑定、测试、文档、CI 全线都要看）。
单文件被删不等于接口下线：**同名符号可能已迁到新文件重新注册**，必须回到新树确认。

### 4.2 平台 / 架构支持矩阵：用报错字符串反推
```bash
git -C <repo> --no-pager grep -n "not supported in this platform" <A> -- <code_root>
git -C <repo> --no-pager grep -n "not supported in this platform" <B> -- <code_root>
```
取两 tag 的**命中文件集合**做差：只在旧 tag 出现 = 该算子这版**放开了**；新版仍留着同一处 `NotImplementedError` = 仍不支持。
「放开支持」只等于「不再拒绝」，**不等于**「为新架构调过优」——这两句必须分开写。

### 4.3 配套版本号：逐字取自文件，留意两套口径
```bash
git -C <repo> --no-pager show <tag>:docker/Dockerfile | python -c "import sys;d=sys.stdin.buffer.read().decode('utf-8','replace').splitlines();[print('%4d| %s'%(i+1,l)) for i,l in enumerate(d) if l.strip().startswith(('ARG ','ENV '))]"
```
版本号只认 `ARG`/`ENV` 的赋值行：别抄 `--help` 文本（常年过期），别抄声明后从未使用的**死 ARG**（多阶段构建的生效值常在另一个 stage）。
同一仓内 `docker/` 与 `ci/` 可能是两套不一致的配套；发布说明的版本表要与 `docker/OVERVIEW*`、构建脚本变量三方对账，冲突就写「矛盾」，不要二选一。

### 4.4 测试假绿：查构建侧，不查装饰器
```bash
git -C <repo> --no-pager grep -n -E "skip|importorskip|hasattr\(torch\.ops" <B> -- <tests>
git -C <repo> --no-pager show <B>:<ci 脚本>                        # export 开关在 pip install 之前还是之后
git -C <repo> --no-pager grep -n -A6 "def .*soc" <B> -- setup.py   # SoC 闸门是否对该平台直接关掉
git -C <repo> --no-pager grep -n "FATAL_ERROR" <B> -- <cmake>
```
判绿三步：① CI 脚本是否真 `export <开关>=1` 且在 `pip install -e .` **之前**；② `setup.py` / CMake 的 SoC 闸门对该平台是否放行；③ `pytest` 全 skip 仍 `exit 0` 且 `-x` 不拦。三条同时成立 = **结构性假绿**，CI 绿不能当证据。

### 4.5 文档真删除：不信 `-M`，信存在性
```bash
git -C <repo> --no-pager diff --name-status -M <A> <B> -- docs
```
对每个 `D` 的旧路径 `docs/<rest>`，逐语言查新树里 `docs/<lang>/<rest>` 是否存在：
```bash
git -C <repo> cat-file -e <B>:docs/<lang>/<rest>   # 命中 = 改名拆分，不是删除
```
全部命中即「结构重排，真删除 0」。整页重写会把相似度压到阈值以下退化成 `D`+`A`，所以 `D` 的条数**不能**当删除条数。

## 5. 坑与修法（附错误原文 / 现象）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | `git diff A...B` → `fatal: v...: no merge base`（rc=128） | 三点 diff 需要 merge-base | 改两点 `git diff A B`（`A..B` 在 diff 下与其等价） |
| 2 | `git log A...B` **不报错**，却列出两段无关历史之和 | 无共同祖先时 `...` 退化为并集 | 绝不用 `A...B` 数「改了多少提交」；只在 `--left-right` 且两侧都非空时用它**证明**无共同祖先 |
| 3 | `git merge-base A B` rc=1，stdout 与 stderr 全空 | 空结果是正常返回值，不是失败 | 判据写成「rc=1 且空输出」，别等报错 |
| 4 | `git log -- <path>` 为空 → 误判「没变更」 | 变更落在导入根，`--no-merges` 再过滤一次 | 补 `git cat-file -e <导入根>:<path>`；仍空再用 `blame` 定位 |
| 5 | `cat-file -e` 报 `fatal: path '...' does not exist in '<rev>'` | 该路径在新 tag 确实不存在 | 这正是「无区间内 commit 的删除」的反证，照实写进结论 |
| 6 | `--numstat` 显示 `105 0 <path>`，像是「旧文件加了 105 行」 | 整文件新增同样输出 `+105` | 用 `--name-status` 的 A，或 `git diff A B -- <path> \| head -3` 期望 `new file mode 100644` |
| 7 | 做矩阵集合差得到 `only-in-old = {tag 名}` | `git grep <rev> -- <path>` 每行前缀是 `<rev>:<path>:<line>:`，按首个 `:` 切会把 tag 当路径 | 按 `split(':', 3)` 取第 2 段为 path |
| 8 | `-M` 报一堆 `D`，看着像大规模删文档 | 整页重写使相似度低于阈值，退化为 `D`+`A` | 见 §4.5：对每个 `D` 查各语言目标路径是否存在 |
| 9 | `git diff --no-index a b` 有差异即 `exit 1`，脚本抛异常 | 与 `diff` 同义，有差异就是非零 | 显式忽略 returncode，只取 stdout |
| 10 | `cmd /c "git ... --pretty=format:'%h\|%ad'"` → `'%ad' is not recognized as an internal or external command` | `cmd` 展开 `%` 且不认单引号 | 交给 Python `subprocess` 以 argv 传参 |
| 11 | 全量 diff 落盘后 `read` 报 `binary file` | PowerShell `>` / `Out-File` 默认 UTF-16LE | Python 取 bytes 后 `open(...,'wb').write()`（git 输出本身即 UTF-8） |
| 12 | 本机 PowerShell 5.1 的 GBK 解码、BOM、管道计数、`Select-Object -First` 假退出码 | 见专 skill | → `pwsh-on-windows` |

## 6. 交叉引用

- 要在指定版本矩阵上真跑 UT / ATK 精度、判冒烟是否全绿 → `mindspeed-ops-smoke`
- 要判上游 docs 相对一批内部需求该不该刷新（不是 tag 差分） → `upstream-docs-refresh-audit`
- 本机 PowerShell 的编码 / 重定向 / 计数坑 → `pwsh-on-windows`
- 本审计要按域拆给多个子代理并行、落盘只回路径、校验其结论 → `orchestrating-subagents`
- 只审单个 PR 是否等价改写 → `pr-change-equivalence-audit`
