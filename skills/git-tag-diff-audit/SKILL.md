---
name: "git-tag-diff-audit"
description: "Git版本与PR实质变更审计，区分树差、历史归因和等价性。适用于\"两个tag改了什么 / 无共同祖先能比吗 / 接口删了吗 / 是纯重构吗 / 精度性能变了吗\"。不适用：提交或跟进PR → 用 `github-pr-flow`。"
whenToUse: "处理Git版本与PR实质变更审计，区分树差、历史归因和等价性时加载；模型看不到本节，触发以description为准。"
disable-model-invocation: true
warm-triggers: "两个 tag 之间改了什么 / 无共同祖先 / 发版审计"
warm-reason: "低频审计方法论"
---

# 仓库变更与等价性审查

## 何时调用

**触发**：两个tag改了什么 / 无共同祖先能比吗 / 接口删了吗 / 是纯重构吗 / 精度性能变了吗。

**转交**：提交或跟进PR见 [github-pr-flow](../github-pr-flow/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

固定仓库、base/head完整commit、比较目的和工作树状态。发布树比较与PR相对目标分支的差异不是同一口径；保留用户选定基线。取证不需要切换或覆盖当前工作树。

## 先取树差，再作归因

`git diff A B` 比较两个端点的树，不要求共同祖先；`git diff A...B` 比较merge-base到B，需先确认merge-base。`git log A...B` 是可达提交集合的对称差，不能拿来当树差或单凭两边非空证明无共同祖先。浅克隆找不到merge-base时先区分历史缺失和真正独立根。

取 `--name-status -z`、`--numstat -z`、模式/对象变化及相关全文。A/M/D/R来自当前rename检测配置，重命名是相似度推测；D+A也可能是搬迁重写。0/0可能是空文件、模式或二进制等变化，新增 `__init__.py` 仍可影响打包/导入。接口下线需追注册、别名、生成代码和调用方，符号grep为0只是有限搜索范围内的阴性证据。

提交归因只在历史覆盖足够时用log/blame/pickaxe。导入根已有路径不等于该路径的当前内容自根以来没改；比较root blob及后续修改。不同历史导入的改动可以标“端点差异确定，导入前归因未知”，不能强分成“有commit/无commit”两类。

平台报错分支被删除说明入口拒绝条件改变；还需核对替代检查、实际派发、构建与目标平台运行，不能据报错字符串差集直接写“已支持”。构建版本沿生效ARG/ENV、stage、调用参数和产物metadata追溯，不把声明未使用的默认值当实际配套。

## PR等价性

分别回答接口契约、普通输入数值、边界/非有限语义和性能。读取base/head完整相关函数与caller，不只读patch摘要。浮点cast、融合、归约顺序、舍入点、符号零、NaN/Inf、subnormal及FTZ/fast-math都可能改变等价性。

`where(mask,x,0)`→`x*mask` 在masked负数可能产生-0，在Inf/NaN上可能传播NaN；只看allclose/数值equal不能证明位模式相同。有效区乘1是否保持位模式，还取决于dtype和实际编译路径。有限输入的范围应按真实维度和中间运算逐项界定，不宣称“fp16输入+fp32累加永不溢出”。编译器是否把改写折回select需看目标IR/设备代码。

对同一输入做base/head A/B，再与独立reference分别比较；通过reference阈值不证明A=B。先固定指标/有效区域/误差预算。性能以同设备同栈、预热/同步、重复采样和分布为证据；结构分析不是性能测量，改前崩溃的形状没有改前耗时基线。

结论逐项标“源码推导”“作者自述”“独立运行”“未验证”，绑定SHA和触发条件。新的实现需回到原失败场景，不能用简化场景的PASS替代。

来源：DSH git-tag-diff-audit、pr-change-equivalence-audit，2026-11-16修正；本地无共同祖先fixture与IEEE signed-zero/NaN示例复现，设备编译和性能未测。语义参考 [Git diff](https://git-scm.com/docs/git-diff)。
