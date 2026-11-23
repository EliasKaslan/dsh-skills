---
name: "vllm-ascend-e2e-ci-wiring"
description: "vLLM Ascend E2E：用例落位、时长登记、marker 与 CI 车道。适用于\"新增E2E/CI报MISSING/本地收集全吗\"。不适用：源码安装 → vllm-ascend-source-install。"
whenToUse: "处理vLLM Ascend E2E用例目录、时长、marker和硬件CI车道核验时加载；模型看不到本节，触发以description为准。"
---

# vLLM Ascend E2E与CI接线

## 何时调用

**触发**：新增E2E怎么落位 / CI报MISSING / 时长怎么登记 / 用例进哪条车道 / 本地收集全吗。

**转交**：源码安装与重编见 [vllm-ascend-source-install](../vllm-ascend-source-install/SKILL.md)。

**前置**：恢复当前任务目标、输入与范围；缺少必需证据时如实标明。**后继**：交付可追溯结果与未覆盖项；编写或调整skill契约见 [dsh-skill-authoring](../dsh-skill-authoring/SKILL.md)。

固定目标checkout、base/head、模型/机制、硬件与图模式。先读该版本test selector、coverage脚本、runner mapping、estimated times、taxonomy、manifest和workflow触发链；历史文件路径是检索入口，不是永久schema。CI集成与本地服务启动、模型能力和数值验收分开。

核对两个方向：配置pattern实际命中测试，以及每个新增测试被正确runner接收。时长key存在不证明selector真的派发，目录存在也不证明有对应硬件分区。PR、nightly、weekly、accuracy可能是不同通道，不能只查PR目录宣称某能力无覆盖。

marker、运行参数、实际硬件/图模式一致；AST读取marker的工具可能只接受字面量，查当前实现。CPU UT、E2E时长登记和覆盖schema按目标配置分别处理。Windows路径分隔符会影响旧coverage脚本；先运行基线并核对规范化逻辑，不能把所有Windows MISSING一概忽略或要求用登记键迎合错误路径。

在与CI一致的环境执行实际coverage与selector，验证新case出现于预期partition，解析stdout/stderr和退出码。工具可能输出日志+对象而非纯JSON，遵守其当前输出接口；门禁PASS不是用例执行PASS。保存收集/执行/skip/cancelled、rank与车道的证据，检查运行绑定当前head。

模型依赖区分本地合成config/tokenizer、dummy机制测试和真实checkpoint精度测试。用例不需要权重时不登记巨型下载；要测量化/多模态时不能为了起服务删quantization/vision字段从而丢目标语义。config override深合并、text_config提取、checkpoint映射/张量融合都查当前loader行为。自包含测试仍受祖先conftest影响，独立文件不保证插件未导入。

先估权重、KV、activation、通信、graph、FIA workspace等并记录实际profile。减层单full-attention层可能改变workspace/cache比例，旧“2倍cache”只属特定实现观察，不能固定util<0.5或强行关graph来规避用户目标。共享物理卡先准入，资源事件与数值失败分开。

新增硬件测试可通过评论触发、标签选择或workflow dispatch，具体权限/规则读本版配置。只按本次明确授权触发评论/CI；手工/e2e成功可能不是required gate消费的那组job。所有required车道与检查绑定当前head，cancelled是未完成证据，不能未经日志归因为基础设施。

完成局部lint/collection/selector和可用的目标运行，交付路径、注册改动、实际runner、head/run、未执行项；提交/PR操作用github-pr-flow，不因技能调用自动发表评论或改维护者标签。

来源：DSH vllm-ascend-e2e-ci-wiring，2026-11-16去除固定marker维数、硬件路由、门禁标签/时长、源码行号及凭据URL。目标仓一手入口：[CI源码](https://github.com/vllm-project/vllm-ascend/tree/main/.github/workflows)。
