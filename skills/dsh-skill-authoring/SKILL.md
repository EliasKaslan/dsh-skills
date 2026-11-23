---
name: "dsh-skill-authoring"
description: "编写、验证和精简DSH skill：触发字段、调用策略、资源路由、去重归档、目录预算与批量发布边界。"
whenToUse: "新建或改写SKILL.md、判断融合还是新增、查失效指针与重复正文、维护冷备索引或批量审计时。"
---


# DSH skill写作、沉淀与审计

## 何时调用

新建/改写SKILL.md、整理已有经验、判断融合还是新增、查失效指针/重复正文、维护冷备索引或批量审计时使用。技术内容的真伪仍需对应领域取证；DSH插件配置问题用 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)。沉淀选址、周期体检、归档查找三个模式见 [审计与归档](references/audit-archive.md) 的同名章节。

先确定目标根、适用用户/仓库、实际loader和现有相近skill；此次用户授权改正文时可重写技术内容，不能被旧“技术正文一字不改”规则阻止。保留每个入口自己的disable-model-invocation/user-invocable策略，不因融合就把所有入口改成手动或自动。

## 写作流程

1. 确定可复用决策：什么信号触发、前置条件、行动顺序、如何知道成功、失败如何回退。一次性地址、旧版本断言和会话流水账不直接升级为普遍规则。
2. 先找能容纳的方法根；同一完整能力保留一个canonical入口，旧名称写精确模式短路由，链接必须真实可解析。领域不同或触发条件实质不同时才新建。技能目录本身不能取得发送、发布、账号读取或系统变更授权。
3. name采用稳定的小写连字符名，建议目录同名；description用一行写领域、可观测触发和边界，把关键差异放前面。whenToUse保留为人/API导航，不能依赖它触发模型。正文用何时调用、边界、步骤、判据组织，命令和案例按需放references/scripts/assets，不复制重复总纲。
4. 事实区分静态源码、隔离fixture、真实运行和用户偏好。保留非显然的机制、关键负例与版本条件；别把某次报错、速度数字或工具数量当永恒规律。脚本先审顶层副作用，用合成输入在隔离根验证；不为试--help就启动真实任务。
5. 读 [DSH文件契约与发现](references/native-contract.md) 校验字段和当前loader；读 [审计与归档](references/audit-archive.md) 做引用、重复、覆盖和内容摘要检查。
6. 在stage上完成YAML/类型/路由/静态语法与必要fixture，保留源→目标及逐文件摘要；交付标注未验项。当前可用的skill工具按实际schema加载精确name，确认读到目标正文；自动发现还要看权威catalog，不靠模型说“我已记住”。

## 批量写入

先查看 [发布事务边界](../dsh-agent-customization/references/publisher-transaction.md)：本机可能在turn/end和poll自动发布。自造.lock不能暂停；先用可验证的最窄暂停方案隔离发布和并发编辑，再应用与复核全部文件。此skill不要求额外询问已经明确授权的修改；如果需要改变任务外的运行时/外发状态，准确指出具体操作和原因。

本机 `skills` 目录是 DSH-Guard 哨兵：快照里有、工作树没有的文件会被自动还原，`keep` 也不覆盖哨兵判定（2026-11-23 实测：删除后 2 分钟内 restored=2）。所以合并/归档先按「盘上文件不能删」设计——降 warm、改正文、留旧名短路由；确需删除要停守护并改 CANON。热/冷预算与 `skills-archive/INDEX.json` 用 `skill_budget.py --write-index` 一次对齐，别手改索引里的数字。

检查器 `scripts/validate_skills.py <skills-root>` 只读，依赖Python和PyYAML，缺依赖以exit2明确失败；用--report写指定审计路径，不能写被审树。它检查实际YAML、name/description/调用策略/Markdown本地链接和逐文件hash，不验证技术事实、实际装载或自动触发。

无frontmatter的归档入口只能由caller显式声明 `--archived <name>`（可重复），保留文件hash并单列归档；未声明的缺frontmatter仍是错误。含字面token `{op}` 的Python模板必须逐个 `--python-template <相对路径>` 声明，否则按普通语法错误被拒（tilelang 两个模板即属此类）；声明只证明替换token后AST可解析，不证明模板逻辑、依赖或算子正确。

旧check-skill-frontmatter.ps1/diff-skills.ps1与旧self-audit daily runner均已同路径退役、调用返回exit78；用只读Python checker和原始字节摘要替代，gate/scan/budget需按当前参数单独审查后使用。历史树的旧reference断链单列遗留发现，不为全绿改未授权的历史材料。

## 重构后验收：五查

批量删改 skill 后，"体积降了九成"不等于"内容搬对了"。下面五查全部只读，按顺序做，能挡住"只删不验"留下的空指针。

1. 导航链接 ≠ 散文路径。markdown 链接（`](...)`）通常会被工具校验；反引号里的 `references/…`、`scripts/…` 不会被任何检查器发现，真正的断链藏在这里（典型：少写 `../兄弟-skill/` 前缀、路径按散文相对当前文件解析）。逐个 stat，路径不存在时再查同名文件是否在本 skill 内，区分"写法松"与"真悬空"。

2. 转交型入口做空指针扫描。正文很短、首跳指向兄弟 SKILL.md 的入口，要确认目标文件里真有被点名的章节（如"模式为 X"）。只看链接能解析不够——链接指向的文件可能在裸转交，被指的章节根本不存在。

3. 退役脚本三件套。脚本换成失败桩后，正文必须留墓碑（为什么退役、调用会怎样），且**退出码与正文写的一致**；同类桩不要混用多个退出码，否则调用方按文档判断会误判成功。

4. 预算与索引同源。description 字符预算、热目录条目数、冷备 `INDEX.json` 的 hotCount/warmCount/catalogChars 是同一组事实，改完要为同一时刻对账；索引头部数字最容易在批量改描述后漂移。

5. 命令与实现对账。正文出现的每条 `python x.py --flag`、每个参数名，用该脚本的 argparse/`--help` 核一遍；脚本默认路径不能硬编码 `C:\Users\<某人>\`，否则换机器或换用户即失效。检查器/扫描器还要查它默认调用的下游工具是否已退役——指向墓碑的扫描器会稳定产出假绿报告。

坑：净丢失只能靠"减法"看出来。把入口正文的减少量与 references 的增加量相减，差额就是被删且无人承接的量；差额大时不要相信"内容只是搬到 references 了"的说法。

## 正文预算与去臃肿

成本有两层：目录行（每请求都发）与**正文**（每次加载全文进上下文）。`distill_skill` 在写入时强制：

- 热目录 ≤40 条 / ≤7000 字符；单条 description ≤120 字符。
- 正文：热 ≤8000 字节 / ≤8 个 `##` 段；冷备 ≤16000 字节。

正文只放「路由 + 判据 + 坑」，长清单放 `references/`（不计预算、不自动加载），正文留指针。

同一主题已有章节、或相似度 ≥55% → `mode=replace + targetSection=<标题>`，不要追加。
超预算按代价整改：① replace ② 移 references ③ 拆总纲+子 skill ④ 降 warm。

**写入前四条自查**：① 净增 ≤ 8000 − 现有 + 被替换；② `title` 已生成标题，body 别再写 `##`；③ JSON 单行、不用 ASCII 双引号、换行写 `\n`；④ 一次一个 references。细则 → `references/tool-call-hygiene.md`

体检：`python %USERPROFILE%\.dsh\skills\dsh-skill-self-audit\scripts\skill_budget.py`（只读，0=预算内）。
