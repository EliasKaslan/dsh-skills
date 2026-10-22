# DSH Skills

本仓库是我本机 DeepSeek Harness（DSH）全部 skill 的只读镜像，由 `skills/dsh-skills-publish/publish-dsh-skills.ps1` 自动生成并推送，请勿手工修改（下一次同步会覆盖）。

## 分支约定

| 分支 | 含义 |
| --- | --- |
| `main` | 最近一次同步的完整快照，也是默认分支 |
| `<YYYY-MM-DD>` | 每日快照分支。每天凌晨 2:00 的同步会新建（或快进）当天日期分支，并让 `main` 与它指向**同一个 commit**，即内容逐字节一致 |

## 使用

```bash
git clone https://gitcode.com/EliasKaslan/dsh-skills.git
```

本仓库公开可克隆，但只有仓库所有者可以推送。需要改动请 fork 后自行维护，或直接 `git pull` 跟随每日快照。

## 清单

共 **37** 个 skill、**60** 个文件、**1365931** 字节。凭据文件（`credentials.txt`、`*.key`、`*.pem` 等）按规则排除，不入库。

| # | Skill | 说明 | 文件 |
|---:|---|---|---:|
| 1 | [`aidd-report-reader`](skills/aidd-report-reader/SKILL.md) | 读华为 AIDD（aidd.huawei.blue）文档质量扫描报告并导出问题清单——gitcode OAuth 登录（DevUI 复选框要直接注入 Vue 状态）、REST API 免爬 DOM 批量拉 issues。适用于"检查 AID... | 1 |
| 2 | [`ai-vendor-official-source-audit`](skills/ai-vendor-official-source-audit/SKILL.md) | AI 厂商官方信息源真伪与覆盖面判定——产品名≠API model id（按官方模型列表逐名计数）；官方新闻页与详情页信息不同，两页都抓；响应体 <10KB 判 catch-all SPA 空壳（配假 slug 对照 + 真/假字节比）；H... | 1 |
| 3 | [`arxiv-paper-deep-read-and-claim-verification`](skills/arxiv-paper-deep-read-and-claim-verification/SKILL.md) | arXiv 论文精读 + 开源声称独立核查（实测 2606.13392v2）——web_fetch 抓 /html 会在正文中段被 (Content truncated.) 截断，改用 pwsh Invoke-WebRequest -Use... | 1 |
| 4 | [`ascend-cann-env`](skills/ascend-cann-env/SKILL.md) | 昇腾 CANN 的检测/安装/激活/换版本/卸载（默认 a3=192.168.13.188，备用 a3b=.190）——权威定位看 /etc/Ascend/ascend_cann_install.info，toolkit+ops+nnal ... | 1 |
| 5 | [`ascend-conda-env`](skills/ascend-conda-env/SKILL.md) | 昇腾服务器 conda 环境的检测 / 新建 / 激活与换 python 版本（默认 a3=192.168.13.188，备用 a3b=.190）——共享 miniconda3 在 /mnt/share/x00886548/minicond... | 1 |
| 6 | [`ascend-env`](skills/ascend-env/SKILL.md) | 昇腾 NPU 服务器环境搭建入口总纲（a3=192.168.13.188 默认 / a3b=.190 备用）——**先并行再串行**的 4 lane 编排（CANN 包下载 ∥ conda 建环境 ∥ torch 栈 whl 预下载 ∥ 两... | 1 |
| 7 | [`ascend-model-adaptation-recon`](skills/ascend-model-adaptation-recon/SKILL.md) | 判定某模型在昇腾/vllm-ascend 生态里的适配程度（实测 MiniMax-H3）——一次全树 API 判「主仓有无代码」、追 import 链定位跨仓分工（vllm-ascend 基座 ↔ vllm-omni NPU 平台层）、查镜... | 1 |
| 8 | [`ascend-moe-ep-capacity-planning`](skills/ascend-moe-ep-capacity-planning/SKILL.md) | 昇腾 64GB 卡跑 MoE 大模型前的显存容量与并行几何规划——EP 没有独立开关（EP = TP × DP × PCP），按卡数 N 选型必须随 N 重推 TP；64GB 卡真实预算只有 56.378 GiB，用 64GB 或 64×1... | 2 |
| 9 | [`ascend-server-layout`](skills/ascend-server-layout/SKILL.md) | 昇腾服务器目录地图与磁盘红线——找模型在哪、磁盘满了该写哪个盘（a3=.188 默认 / a3b=.190 备用）——.188 只有两块真盘：系统盘 /（/mnt/share、/mnt/weight、/tmp、/root 全压在它上面，多租... | 1 |
| 10 | [`ascend-torch-npu`](skills/ascend-torch-npu/SKILL.md) | 昇腾 NPU 上 torch + torch_npu 的检测 / 安装 / 验证 / 排障（默认 a3=192.168.13.188，备用 a3b=.190）——先定车道：A（跑 vllm-ascend，默认）torch 2.10.0+cp... | 1 |
| 11 | [`ascend-triton-ascend`](skills/ascend-triton-ascend/SKILL.md) | 昇腾 NPU（a3=.188 / a3b=.190）上 triton-ascend 的检测 / 安装 / 验证 / 排障——商发版 3.2.2 必须从 osinfra 专用源装（PyPI 上没有）；官方覆盖式共存，import triton... | 1 |
| 12 | [`ascend-vllm-serve`](skills/ascend-vllm-serve/SKILL.md) | 在昇腾 A3（.188/.190）上把装好的 vllm + vllm-ascend 跑起来——三层自检、按 HBM 挑空闲 die、起 OpenAI 兼容服务、离线推理冒烟、sleep/wake_up 显存释放与重载、运行时排障。适用于"在... | 1 |
| 13 | [`dingxiang-slider-captcha`](skills/dingxiang-slider-captcha/SKILL.md) | 顶象（dx）拼图缺口滑块验证码在 Android 模拟器上的实测结构与破解结论——含 DOM/几何参数、块与手指位移 1:1、块是半透明混合渲染（NCC 定位失效根因）；结论：成功率极低（实测 0/6）。适用于"过一下顶象滑块验证码 / 提... | 1 |
| 14 | [`dsh-agent-customization`](skills/dsh-agent-customization/SKILL.md) | DSH「改造 agent 行为」入口总纲——五层何时生效 + `settings.yaml` 是导入源 + 上线纪律（热重载≠冷启动、坏 row 冷启动静默、要看门狗）。适用于"改 DSH 的行为该改哪一层 / 改了 AGENTS.md 为... | 1 |
| 15 | [`dsh-agent-preset-live-verification`](skills/dsh-agent-preset-live-verification/SKILL.md) | DSH agent preset 在线会话级验收——已起隔离 host 且真建会话才能做：RPC 核对 agentPreset、persona、权威工具清单，真跑一次委派核对子代理 config/persona/toolFilter 与父会... | 1 |
| 16 | [`dsh-agent-preset-verification`](skills/dsh-agent-preset-verification/SKILL.md) | DSH agent preset 离线静态校验——0.2.0-rc.2 起载体是 bundle patch 里的 @deepseek-ai/dsh-agent-preset 声明行（目录式 .agent-presets 已死，healthy... | 2 |
| 17 | [`dsh-isolated-web-host`](skills/dsh-isolated-web-host/SKILL.md) | 起第二个 DSH web host 做隔离实验（重定向 DSH_HOME）——建测试 home 骨架、必加 --no-open、启动先落盘 pid 与端口、不带 token 的 401 判就绪、taskkill /PID 收尾；本机端口枚举... | 1 |
| 18 | [`dsh-repo-sync`](skills/dsh-repo-sync/SKILL.md) | DSH 配置到私仓的确定性同步机制——脚本 sync-dsh-repos.ps1 把 `C:\Users\admin\.dsh` 与编排 preset 用 robocopy 快照进 `D:\repos\deepseek-harness`，根... | 3 |
| 19 | [`dsh-skill-authoring`](skills/dsh-skill-authoring/SKILL.md) | DSH skill 文件本身的写法契约——skill 没被触发或加载不上时先看这条：模型每步只看到目录里的一行「`name` + 半角冒号 + description」（正文与 whenToUse 都不进目录），description 被折... | 3 |
| 20 | [`dsh-skill-self-audit`](skills/dsh-skill-self-audit/SKILL.md) | DSH skill 集合的每日无人值守自检——静默满 1 小时且距上次自检 ≥20h 才跑；Windows 计划任务 DSH-Skill-SelfAudit 每小时轮询、headless 真跑；体检含 YAML round-trip、交叉引... | 5 |
| 21 | [`dsh-skills-publish`](skills/dsh-skills-publish/SKILL.md) | 把本机 ~/.dsh/skills 的全部 skill 每天凌晨 2 点发布到 GitCode 公开仓 EliasKaslan/dsh-skills——脚本 publish-dsh-skills.ps1 先快照再扫活密钥，然后提交 main... | 5 |
| 22 | [`external-buzz-magnitude-check`](skills/external-buzz-magnitude-check/SKILL.md) | 外部热度量级取证——这事在外网真的火吗（HN points/评论、HF likes/下载量、Artificial Analysis/OpenRouter 体验指标、社区情绪分级）——判某事在外网是否真热、某模型是否真难用，给可复现量级数字；... | 1 |
| 23 | [`gitcode-pr-flow`](skills/gitcode-pr-flow/SKILL.md) | GitCode 上任意昇腾社区仓提 PR（MindSpeed-Ops 与 MindSpeed-Agent 均已完整验证）从个人 fork 到合入全流程——compile 评论触发门禁（任何 head 变化后须补发）、双 CI 判读与标签审计... | 4 |
| 24 | [`github-org-delta-watch`](skills/github-org-delta-watch/SKILL.md) | GitHub 组织增量追踪——基准日之后谁在动：rate_limit 的 Date 头取"今天"、orgs/{org}/repos?sort=pushed 覆盖全组织找活性、pushed_at 冻结即内容冻结、issues 要 create... | 1 |
| 25 | [`github-pr-flow`](skills/github-pr-flow/SKILL.md) | 向 GitHub 上游开源仓（如 vllm-project/vllm-ascend）从 fork 提 PR 的全 API 流程（classic PAT）——token 验证与 403/401 判因、DCO 签名提交、REST API 创建/... | 1 |
| 26 | [`korea-official-source-research`](skills/korea-official-source-research/SKILL.md) | 韩国（济州）官方一手信息源抓取与端点配方——web_fetch 对韩国站点普遍不可用，python urllib 按站点分档，pwsh 直连最稳；含出入境/入境申告官方源结构（e-AC 的 bbsId=文章id / flId=附件id、列表... | 1 |
| 27 | [`orchestrating-subagents`](skills/orchestrating-subagents/SKILL.md) | 编排手册——两通道模型：生产动作（读文件、跨模块检索、跑命令、联网、试错、写代码/文档、改配置）一律下发给子代理，主 Agent 保留全套工具、只做交付前独立复核（真跑验收命令、核"文件:行号"、读本体与 exit code）；判据权威出处... | 1 |
| 28 | [`outlook-mailbox-control`](skills/outlook-mailbox-control/SKILL.md) | Outlook.com（个人 MSA）邮箱接管——MS365 MCP discovery 直调：15 项能力配方（工具名＋最小 parameters JSON）、三条个人账户硬规则（authority 必须 consumers／只支持 de... | 1 |
| 29 | [`pwsh-on-windows`](skills/pwsh-on-windows/SKILL.md) | 本机命令行（pwsh 实为 Windows PowerShell 5.1，非 PS7）——默认按 GBK 解码、写 BOM、PS7 语法是解析期错误，一整套静默坏结果：中文乱码、行数/CR 数少算或暴增、skill frontmatter ... | 1 |
| 30 | [`qq-mail-control`](skills/qq-mail-control/SKILL.md) | QQ 邮箱接管（stdio MCP `qqmail`，IMAP/SMTP）——12 个工具的最小参数配方、文件夹名编码（`qqmail_folders` 回显中文原文、UTF-8 原文直传可用，传 `&UXZO1mWHTvZZOQ-` 这类... | 1 |
| 31 | [`sedimenting-skills`](skills/sedimenting-skills/SKILL.md) | Skill 沉淀协议——先过目录税预算（目录字符总量 ≤ 20,000，默认值可调），每次非平凡运行收尾都**自动**复盘，并**全库匹配**找归属（三段决策 ①融合已有 skill ②建/更新总纲 ③都没有才新建）——默认首选融合：有归属... | 1 |
| 32 | [`subagent-toolset-precheck`](skills/subagent-toolset-precheck/SKILL.md) | 子代理工具集预检——子代理说没有 web_fetch、工具受限怎么办：派活前先让它如实回报函数清单，避免把联网调研或要求落盘的任务派给工具受限的 `explore` 子代理（2026-10-09 实测只拿到 glob/grep/read/s... | 1 |
| 33 | [`univpn-vpn`](skills/univpn-vpn/SKILL.md) | UniVPN（联软 Leagsoft，C:\Program Files (x86)\UniVPN）——188 连不上、177.8.21.1 怎么连就看这条：蓝区网关(x00886548)推 192.168.0.0/16 → a3=192.1... | 2 |
| 34 | [`upstream-docs-refresh-audit`](skills/upstream-docs-refresh-audit/SKILL.md) | 上游开源仓库 docs 刷新审计（实测 vllm-project/vllm-ascend main）——输入一批中文内部需求或中文转测文档，判 docs/source 是否需要刷新，产出六节结论清单 + 逐条刷新方案：三件前置产物先行、只读... | 5 |
| 35 | [`vllm-ascend-e2e-ci-wiring`](skills/vllm-ascend-e2e-ci-wiring/SKILL.md) | vllm-ascend e2e 用例进 CI 的落位与登记——tests/e2e/pull_request 下新增 test 必须登记 estimated_times.yaml，否则 coverage.py 打印 ✗ MISSING 后 s... | 1 |
| 36 | [`vllm-ascend-source-install`](skills/vllm-ascend-source-install/SKILL.md) | 从源码装 vllm + vllm-ascend 配对流程——main 按 `.github/vllm-main-verified.commit` 配 vllm（VLLM_TARGET_DEVICE=empty）；release tag 配同... | 2 |
| 37 | [`win-scheduled-task-forensics`](skills/win-scheduled-task-forensics/SKILL.md) | Windows 计划任务/持久化项取证与安全退役——五处侦察面（计划任务全量、schtasks 旁证、Run 键、两个启动文件夹、WMI 事件订阅）缺一处就漏；退役顺序固定为 Export-ScheduledTask 留档 → Disabl... | 1 |
