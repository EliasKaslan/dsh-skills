# DSH Skills

本仓库是本机 DeepSeek Harness（DSH）全部 skill 的只读镜像，由 DSH 插件 `dsh-plugin-skill-publish` 在检测到 skill 变化后自动生成并推送，请勿手工修改（下一次同步会覆盖）。

## 分支约定

| 分支 | 含义 |
| --- | --- |
| `main` | 最近一次同步的完整快照，也是默认分支 |

历史遗留的 `<YYYY-MM-DD>` 日期分支是旧发布脚本的产物，已停止新增，仅作存档，不再更新。

## 使用

同一份内容同步到多个公开站点，任意一个都能克隆：

```bash
git clone https://gitcode.com/EliasKaslan/dsh-skills.git
git clone https://github.com/EliasKaslan/dsh-skills.git
```

本仓库公开可克隆，但只有仓库所有者可以推送。需要改动请 fork 后自行维护，或直接 `git pull` 跟随同步。

## 站点

- [GitCode](https://gitcode.com/EliasKaslan/dsh-skills)
- [GitHub](https://github.com/EliasKaslan/dsh-skills)

## 清单

共 **69** 个 skill、**279** 个文件、**13266313** 字节。凭据文件（`credentials.txt`、`*.key`、`*.pem` 等）按规则排除，不入库。

| # | Skill | 说明 | 文件 |
|---:|---|---|---:|
| 1 | [`ace-step-music-gen-on-ascend`](skills/ace-step-music-gen-on-ascend/SKILL.md) | 在用户指定ACE-Step等自托管音乐模型时规划权重组件、CPU/NPU路径、批量生成与音频验收；适用于本地歌曲实验和生成排障，不依赖旧服务器固定目录。 | 1 |
| 2 | [`ai-musume-4k-art`](skills/ai-musume-4k-art/SKILL.md) | 已归档的AI娘旧管线：只保留路由，指向 minimax-ai-musume-4k-art 与 anime-art 两条现行链路。 | 1 |
| 3 | [`ai-vendor-official-source-audit`](skills/ai-vendor-official-source-audit/SKILL.md) | 核查 AI 厂商发布、技术报告、模型仓、API model id、能力与价格的官方依据，并比较模型版图；适用于链接真伪、是否发布和选型取证，不代替实测模型身份或基准复现。 | 2 |
| 4 | [`aidd-report-reader`](skills/aidd-report-reader/SKILL.md) | 读取AIDD等文档质量扫描报告，校验分页、项目范围与问题聚合，并将报告命中对账到仓库交付件；适用于扫描分数、fatal/critical清单和公网地址声明覆盖核查。 | 2 |
| 5 | [`anima-ai-musume-lora`](skills/anima-ai-musume-lora/SKILL.md) | Anima/ComfyUI与AI娘LoRA的场景入口，转自托管图像方法并按需复用角色参考。 | 6 |
| 6 | [`anime-art`](skills/anime-art/SKILL.md) | 维护用户明确选择的SDXL、Anima/ComfyUI、H3等自托管图像与LoRA工作流，核对版本、设备、生成与训练结果。 | 18 |
| 7 | [`app-release-version-recon`](skills/app-release-version-recon/SKILL.md) | 核查某 App 今天是否发版、更新了什么：Microsoft Store / iTunes lookup / Homebrew cask 三处版本取证，区分构建重发与服务端功能放量，全程不动本地安装。 | 1 |
| 8 | [`arxiv-paper-deep-read-and-claim-verification`](skills/arxiv-paper-deep-read-and-claim-verification/SKILL.md) | 精读论文并独立核查其代码、模型发布与实验声称，区分文献支持、材料可得性、口径一致和实际复现；适用于arXiv中文技术解读及开源声称核查。 | 1 |
| 9 | [`ascend-cann-env`](skills/ascend-cann-env/SKILL.md) | 在昇腾 Linux 上搭建或诊断 CANN、conda/Python、torch_npu、triton-ascend 的兼容栈；适用于版本配对、动态库/ABI 错误、解释器错位和 Triton 被覆盖，不负责 vLLM 源码构建。 | 5 |
| 10 | [`ascend-conda-env`](skills/ascend-conda-env/SKILL.md) | 昇腾Python与conda环境建立、激活和解释器错位排障；冷备兼容入口，正文在 ascend-cann-env。 | 1 |
| 11 | [`ascend-env`](skills/ascend-env/SKILL.md) | 昇腾环境入口：按当前问题选择服务器访问、工作区、运行栈、源码构建、服务或数值一致性验证。 | 1 |
| 12 | [`ascend-model-adaptation-recon`](skills/ascend-model-adaptation-recon/SKILL.md) | 核实指定模型及变体在昇腾推理或训练生态中的实现、跨仓分工、硬件/精度支持与未闭合缺口；适用于能否跑、适配成熟度、镜像和 Day-0 宣称取证。 | 1 |
| 13 | [`ascend-moe-ep-capacity-planning`](skills/ascend-moe-ep-capacity-planning/SKILL.md) | 在昇腾 MoE 部署前核算每 rank 权重、KV/线性注意力状态与运行峰值，筛选合法 TP/DP/PCP/EP 组合；适用于需要几张卡、并行配置和显存余量，不替代真机可运行验收。 | 4 |
| 14 | [`ascend-server-access`](skills/ascend-server-access/SKILL.md) | 按用户维护的当前服务器资源选机、匹配账号和连接 SSH，诊断 Windows 经 UniVPN 访问昇腾时的双隧道、路由、握手和跨机通信。 | 12 |
| 15 | [`ascend-server-layout`](skills/ascend-server-layout/SKILL.md) | 在共享昇腾服务器上选择项目、环境、缓存与权重落点，核实磁盘、NPU 占用及 safetensors 分片完整性；适用于写哪盘、找真权重、挑空卡和容器挂载问题。 | 10 |
| 16 | [`ascend-torch-npu`](skills/ascend-torch-npu/SKILL.md) | 昇腾torch与torch_npu版本配对、动态库和NPU可用性排障；冷备兼容入口，正文在 ascend-cann-env。 | 1 |
| 17 | [`ascend-triton-ascend`](skills/ascend-triton-ascend/SKILL.md) | 昇腾Triton同名文件覆盖、版本来源与真实kernel验证；冷备兼容入口，正文在 ascend-cann-env。 | 1 |
| 18 | [`ascend-vllm-serve`](skills/ascend-vllm-serve/SKILL.md) | 在已安装的昇腾 vLLM 环境中做离线推理、启动 OpenAI 服务及定位 OOM/初始化失败，并验证 sleep、唤醒与权重更新；不负责源码安装或训练数值一致性适配。 | 2 |
| 19 | [`batch-invariance-acceptance`](skills/batch-invariance-acceptance/SKILL.md) | 昇腾批次不变性与训推数值一致性适配、定位、验证。适用于\"验批次不变性 / 训推logprob对不上 / prefill和decode不同 / 梯度怎么验证 / 更新后不同步\"。不适用：仅启动推理服务→ascend-vllm-serve。 | 23 |
| 20 | [`batch-invariant-weekly-digest`](skills/batch-invariant-weekly-digest/SKILL.md) | BI批次不变性周报与窗口内已合入PR清单。适用于\"跑BI周报 / 不变性有什么进展 / 这周合了哪些PR / 周报改成列表 / 查确定性进展\"。不适用：模型数值验收 → 用 `batch-invariance-acceptance`。 | 1 |
| 21 | [`bilibili-video-forensics`](skills/bilibili-video-forensics/SKILL.md) | B站视频取证：412 风控下用浏览器上下文调 API 拿标题、统计、评论、弹幕与封面 | 1 |
| 22 | [`codex-cache-hitrate-forensics`](skills/codex-cache-hitrate-forensics/SKILL.md) | 用 Codex 会话日志复算 prompt cache 命中率；适用于 cached_tokens 下降、新版模型缓存或成本变差的传闻取证 | 1 |
| 23 | [`cross-framework-support-survey`](skills/cross-framework-support-survey/SKILL.md) | 横向调研某机制在哪些框架或模型受支持：术语对齐、结构量判据、语义分层与来源分级。 | 1 |
| 24 | [`dingxiang-slider-captcha`](skills/dingxiang-slider-captcha/SKILL.md) | 顶象滑块验证码的合法交互与故障识别入口；转登录流程的人工交接模式，保留加载/iframe观察，停止脚本绕过。 | 1 |
| 25 | [`dsh-agent-customization`](skills/dsh-agent-customization/SKILL.md) | DSH配置、插件与运行时维护总纲；定位改哪层、何时生效、隔离验证、preset取证与守护恢复，按模式转入具体参考。 | 9 |
| 26 | [`dsh-agent-preset-live-verification`](skills/dsh-agent-preset-live-verification/SKILL.md) | DSH preset 在线验收：从真实请求头取 persona、工具清单与子会话 provider/model，核父 turn/end。 | 1 |
| 27 | [`dsh-agent-preset-verification`](skills/dsh-agent-preset-verification/SKILL.md) | DSH preset/overlay 离线核查：声明行是否进组合树、Config 语义与工具策略；不取会话证据。 | 1 |
| 28 | [`dsh-home-guard`](skills/dsh-home-guard/SKILL.md) | DSH home备份与自愈排查：外置守护、失败不固化删除、隔离恢复与hash核验。 | 1 |
| 29 | [`dsh-isolated-web-host`](skills/dsh-isolated-web-host/SKILL.md) | DSH隔离host入口；独立DSH_HOME、profile与loopback端口启动并验证身份，转总纲隔离host模式。 | 1 |
| 30 | [`dsh-longhaul-mode`](skills/dsh-longhaul-mode/SKILL.md) | 检查用户明确采用的 DSH Longhaul 工程契约、红基线、yardstick 与独立审计，或诊断既有 .longhaul run；只用于 Longhaul，不自动接管普通 DSH 任务。 | 1 |
| 31 | [`dsh-phone-remote-relay`](skills/dsh-phone-remote-relay/SKILL.md) | 诊断或维护 DSH Pocket 手机远程中继的建联、分片、重复请求、WebSocket 回放与版本生效；用于既有手机接管场景，需要区分出站中继与本机监听状态。 | 2 |
| 32 | [`dsh-plugin-market`](skills/dsh-plugin-market/SKILL.md) | DSH插件市场与安装包审查入口；核对索引schema、来源固定、版本匹配及ASAR有界解析。 | 1 |
| 33 | [`dsh-repo-sync`](skills/dsh-repo-sync/SKILL.md) | 退役DSH仓库同步审查入口；定位旧脚本/任务并保留镜像和凭据排除经验，不恢复旧自动发布。 | 3 |
| 34 | [`dsh-skill-authoring`](skills/dsh-skill-authoring/SKILL.md) | 编写、验证和精简DSH skill：触发字段、调用策略、资源路由、去重归档、目录预算与批量发布边界。 | 7 |
| 35 | [`dsh-skill-self-audit`](skills/dsh-skill-self-audit/SKILL.md) | DSH skill集合体检：字段、引用、重复、预算与文件摘要核对，用只读校验器出结论。 | 6 |
| 36 | [`external-buzz-magnitude-check`](skills/external-buzz-magnitude-check/SKILL.md) | 核查事件或模型的外部热度、社区反馈与体验量级，区分平台计数、实测、转述和检索缺口；适用于真的火吗、社区口碑和速度抱怨取证，不以仓库提交活性代替外部影响。 | 1 |
| 37 | [`git-tag-diff-audit`](skills/git-tag-diff-audit/SKILL.md) | Git版本与PR实质变更审计，区分树差、历史归因和等价性。适用于\"两个tag改了什么 / 无共同祖先能比吗 / 接口删了吗 / 是纯重构吗 / 精度性能变了吗\"。不适用：提交或跟进PR → 用 `github-pr-flow`。 | 1 |
| 38 | [`gitcode-pr-flow`](skills/gitcode-pr-flow/SKILL.md) | GitCode PR交付、门禁与评审跟进。适用于\"GitCode提PR / 双CI怎么判 / PR冲突 / 门禁标签 / backport\"。不适用：仅核实代码是否等价 → pr-change-equivalence-audit。 | 5 |
| 39 | [`github-org-delta-watch`](skills/github-org-delta-watch/SKILL.md) | GitHub组织与发行差集入口，按既有基线追踪仓库、PR、commit和release变化。 | 1 |
| 40 | [`github-pr-flow`](skills/github-pr-flow/SKILL.md) | GitHub/GitCode PR 交付与 CI 核验：提 PR、改正文、修冲突、看红。适用于\"提PR / 改PR正文 / CI为什么红 / 修PR冲突 / 处理评审意见\"。不适用：仅审版本差异 → git-tag-diff-audit... | 2 |
| 41 | [`gold-price-rmb-quote`](skills/gold-price-rmb-quote/SKILL.md) | 抓黄金实时行情、换算人民币每克、拆解内外盘溢价；用于查金价、判断跌幅构成与短期区间 | 1 |
| 42 | [`korea-official-source-research`](skills/korea-official-source-research/SKILL.md) | 检索韩国与济州的主管机关、交通及旅游一手资料，核对现行政策、时刻表、营业与票价信息；适用于官方信息难抓取、日期与废止状态不清，历史端点只作线索。 | 2 |
| 43 | [`llm-landscape-recon`](skills/llm-landscape-recon/SKILL.md) | 模型对比、速度与选订阅取证入口：官方来源、effort/tok/s 口径、编码 agent 与限额。 | 6 |
| 44 | [`login-credential-autofill`](skills/login-credential-autofill/SKILL.md) | 在用户授权的账号登录流程中复用已登录会话、辨认失败阶段和处理验证码/二次验证交接；适用于网页登录卡住或已有登录守护脚本审查，凭据填充须匹配用户指定账号和当前授权，验证码交接给用户。 | 6 |
| 45 | [`lora-weekly-report`](skills/lora-weekly-report/SKILL.md) | 按明确时间窗和基线核查GitHub组织、仓库、LoRA或批次不变性进展并生成增量简报；适用于周报、观察点变化和已合入清单，生成报告不自动发信或创建定时任务。 | 8 |
| 46 | [`mindspeed-ops-interface-compat-audit`](skills/mindspeed-ops-interface-compat-audit/SKILL.md) | MindSpeed-Ops跨仓接口兼容与实际调用核查。适用于\"接口兼容吗 / 周边仓能调用吗 / 导入通过算过吗 / 新增了哪些算子 / 别名绑定对吗\"。不适用：只做版本树差 → 用 `git-tag-diff-audit`。 | 1 |
| 47 | [`mindspeed-ops-smoke`](skills/mindspeed-ops-smoke/SKILL.md) | MindSpeed-Ops接口兼容、wheel验收及UT/ATK冒烟（含A3双机26.2.0配套）。适用于\"跑Ops冒烟 / ATK精度怎么判 / UT全绿了吗 / 跨仓接口兼容吗\"。 | 7 |
| 48 | [`mindspeed-ops-whl-build`](skills/mindspeed-ops-whl-build/SKILL.md) | MindSpeed-Ops wheel构建与独立环境验收。适用于\"打Ops的whl / CMake报错 / 编译器太旧 / SOC怎么选 / 验证wheel\"。不适用：只配置CANN运行环境 → 用 `ascend-cann-env`。 | 1 |
| 49 | [`minimax-ai-musume-4k-art`](skills/minimax-ai-musume-4k-art/SKILL.md) | 整理AI娘角色参考、身份与画风并验收插画；生成时使用当前DSH已配置图像工具，指定H3等自托管后端时另核接口与设备。 | 54 |
| 50 | [`model-endpoint-identity-audit`](skills/model-endpoint-identity-audit/SKILL.md) | 比较多个模型端点或model id的行为、能力、缓存和性能，评估是否共享服务路径及身份声明的证据强度；适用于渠道是否同模型、兼容性和速度成本测试，不从行为指纹断言权重相同。 | 1 |
| 51 | [`node-test-false-green-audit`](skills/node-test-false-green-audit/SKILL.md) | Node测试与CI假绿、漏跑和断言有效性审查。适用于\"CI绿了却没跑 / 测试数对不上 / cancelled算过吗 / 这条断言会红吗\"。不适用：PowerShell编码故障 → `pwsh-on-windows`。 | 1 |
| 52 | [`orchestrating-subagents`](skills/orchestrating-subagents/SKILL.md) | 派发子代理：任务边界、工具能力、可写范围、产物与验收契约。 | 1 |
| 53 | [`outlook-mailbox-control`](skills/outlook-mailbox-control/SKILL.md) | Outlook邮箱任务入口；以当前DSH邮件MCP schema检索/读附件/草稿/发送并核验证据，转邮件总纲Outlook模式。 | 1 |
| 54 | [`overseas-ai-service-cn-availability`](skills/overseas-ai-service-cn-availability/SKILL.md) | 分别核查AI服务的网络可达、账号与地区资格、API/企业渠道、支付账单及数据处理条件；适用于大陆或跨地区可用性与采购研究，不把一次连通或旧条文当长期结论。 | 1 |
| 55 | [`pr-change-equivalence-audit`](skills/pr-change-equivalence-audit/SKILL.md) | PR改前改后的接口、数值边界与性能等价性审查。适用于\"PR是等价改写吗 / mask乘法安全吗 / 精度变了吗 / 性能没变化吗 / bugfix有副作用吗\"。不适用：提交PR与跟进门禁 → 用 `github-pr-flow`。 | 1 |
| 56 | [`prior-agent-artifact-audit`](skills/prior-agent-artifact-audit/SKILL.md) | 前序交付与测试CI证据核查，区分源码、构建、安装和运行版本。适用于\"上一轮真做完了吗 / 报告全绿可信吗 / 线上是哪一版 / 测试漏跑了吗\"。不适用：漏洞报告复核 → `vuln-scan-report-verification`。 | 1 |
| 57 | [`pwsh-on-windows`](skills/pwsh-on-windows/SKILL.md) | 在 Windows 排查 PowerShell 版本、编码/BOM、原生命令参数与退出码、管道和文本计数问题；名为 pwsh 的工具在本机实为 Windows PowerShell 5.1。 | 2 |
| 58 | [`qq-mail-control`](skills/qq-mail-control/SKILL.md) | DSH的QQ与Outlook邮件任务总纲；核对搜索覆盖、邮件身份、正文/附件编码、草稿和发送结果，使用当前邮箱MCP schema及用户账号约定。 | 3 |
| 59 | [`sedimenting-skills`](skills/sedimenting-skills/SKILL.md) | 经验沉淀选址：融合已有skill还是新建，保留验证层级并压缩目录成本。 | 1 |
| 60 | [`skill-archive`](skills/skill-archive/SKILL.md) | 冷备skill查找：按INDEX核实路径与正文再加载，不凭摘要编造能力。 | 1 |
| 61 | [`subagent-toolset-precheck`](skills/subagent-toolset-precheck/SKILL.md) | 子代理工具能力预检：按实际schema与只读probe核对网络/命令/落盘。 | 1 |
| 62 | [`tilelang-op-generator`](skills/tilelang-op-generator/SKILL.md) | TileLang-Ascend 算子开发：内存同步、独立 golden、性能验证。适用于\"写算子 / 迁到NPU / 修kernel精度 / 尾块越界 / 测性能\"。不适用：环境安装 → 用 ascend-cann-env。 | 18 |
| 63 | [`upstream-docs-refresh-audit`](skills/upstream-docs-refresh-audit/SKILL.md) | 上游文档与需求、代码、参数、导航及多语言一致性审计。适用于\"这批需求有文档吗 / docs要刷新吗 / 参数主线有没有 / 内部代号叫什么 / 导航漏页面了吗\"。不适用：启动推理服务 → 用 `ascend-vllm-serve`。 | 5 |
| 64 | [`vllm-ascend-e2e-ci-wiring`](skills/vllm-ascend-e2e-ci-wiring/SKILL.md) | vLLM Ascend E2E：用例落位、时长登记、marker 与 CI 车道。适用于\"新增E2E/CI报MISSING/本地收集全吗\"。不适用：源码安装 → vllm-ascend-source-install。 | 1 |
| 65 | [`vllm-ascend-source-install`](skills/vllm-ascend-source-install/SKILL.md) | 将指定 checkout 的 vLLM 与 vLLM Ascend 从源码配对构建到已有昇腾环境，控制依赖替换、编译器与 BI 算子产物；适用于源码安装、重编和 build dependency 错误。 | 5 |
| 66 | [`vuln-scan-report-verification`](skills/vuln-scan-report-verification/SKILL.md) | 第三方漏洞扫描报告的基线、可达性、攻击输入和严重性复核。适用于\"这个高危是真的吗 / 行号对不对 / 注入能用吗 / 定级高不高 / 有没有漏报\"。不适用：仅审文档扫描分数 → 用 `aidd-report-reader`。 | 1 |
| 67 | [`web-ui-contrast-audit`](skills/web-ui-contrast-audit/SKILL.md) | 定位网页主题切换后文字与背景难辨的问题，按实际渲染背景计算WCAG文本对比并复测修复；适用于浅色/深色主题可读性，不以静态颜色值替代复杂背景检查。 | 2 |
| 68 | [`win-scheduled-task-forensics`](skills/win-scheduled-task-forensics/SKILL.md) | 在 Windows 只读追查定时弹窗、后台进程和开机启动来源，关联计划任务、Run 项、启动目录、服务与 WMI，并在明确授权后验证单项禁用或恢复。 | 1 |
| 69 | [`yb-blue`](skills/yb-blue/SKILL.md) | 审查或操作用户明确指定的 GitHub 文件式 YB 跨区任务桥，验证任务信封、分片完整性、游标与结果归因；用于已有 yb-blue 协议，不自动向任何远端发送任务或文件。 | 4 |
