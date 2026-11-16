---
name: "dsh-skill-authoring"
description: "编写、验证和精简DSH skill；核对触发字段、调用策略、资源路由、去重归档、目录预算与批量发布边界。"
whenToUse: "编写、验证和精简DSH skill；核对触发字段、调用策略、资源路由、去重归档、目录预算与批量发布边界。 模型触发仍以description为准。"
---


# DSH skill写作、沉淀与审计

## 何时调用

新建/改写SKILL.md、整理已有经验、判断融合还是新增、查失效指针/重复正文、维护冷备索引或批量审计时使用。技术内容的真伪仍需对应领域取证；DSH插件配置问题用 [dsh-agent-customization](../dsh-agent-customization/SKILL.md)。

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

检查器 `scripts/validate_skills.py <skills-root>` 只读，依赖Python和PyYAML，缺依赖以exit2明确失败；用--report写指定审计路径，不能写被审树。它检查实际YAML、name/description/调用策略/Markdown本地链接和逐文件hash，不验证技术事实、实际装载或自动触发。旧check-skill-frontmatter.ps1/diff-skills.ps1的阈值/换行/YAML_SKIP局限见reference，不再把旧checker的“跳过”算通过。

已知无frontmatter的归档入口只能由caller显式声明，例如 `--archived ai-musume-4k-art`（可重复）；它保留文件hash并单列归档，不计active。未显式声明的缺frontmatter仍是错误。完整历史树的旧reference断链须单独标为遗留发现；active overlay和新入口可达资源另行验收，不为全绿改未授权的历史材料。

Python模板只能逐文件显式声明，例如 `--python-template tilelang-op-generator/assets/compare_template.py --python-template tilelang-op-generator/assets/test_template.py`。声明必须是根内现存UTF-8 `.py`文件并含字面token `{op}`；检查器只将该token替换成`validation_op`后做AST解析，记录`TEMPLATE_RENDER_PARSE_PASS`及“未执行”，原文件hash仍按未渲染字节计算。未声明模板及普通语法错误照常拒绝；非法路径、缺文件、非`.py`或没有token的声明也拒绝。此结果只证明替换后的Python语法，不证明模板生成逻辑、依赖、运行或算子正确。

旧check-skill-frontmatter.ps1和diff-skills.ps1本次同路径退役并返回exit78；用本入口的只读Python checker和原始字节摘要替代。旧self-audit的daily runner也已退役，纯gate/scan/budget脚本需按当前参数单独审查后使用。
