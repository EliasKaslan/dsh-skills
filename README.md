# DSH Skills

本仓库是我本机 DeepSeek Harness（DSH）全部 skill 的只读镜像，由 `skills/dsh-skills-publish/publish-dsh-skills.ps1` 自动生成并推送，请勿手工修改（下一次同步会覆盖）。

## 分支约定

| 分支 | 含义 |
| --- | --- |
| `main` | 最近一次同步的完整快照，也是默认分支 |
| `<YYYY-MM-DD>` | 每日快照分支。每天凌晨 2:00 的同步会新建（或快进）当天日期分支，并让 `main` 与它指向**同一个 commit**，即内容逐字节一致。**只保留最近 15 个**日期分支，更早的会被自动删除（`main` 永不删除） |

## 使用

同一份内容同步到多个公开站点，任意一个都能克隆：

```bash
git clone https://gitcode.com/EliasKaslan/dsh-skills.git
git clone https://github.com/EliasKaslan/dsh-skills.git
```

本仓库公开可克隆，但只有仓库所有者可以推送。需要改动请 fork 后自行维护，或直接 `git pull` 跟随每日快照。

## 站点

- [GitCode](https://gitcode.com/EliasKaslan/dsh-skills)
- [GitHub](https://github.com/EliasKaslan/dsh-skills)

## 清单

共 **36** 个 skill、**74** 个文件、**1442648** 字节。凭据文件（`credentials.txt`、`*.key`、`*.pem` 等）按规则排除，不入库。

| # | Skill | 说明 | 文件 |
|---:|---|---|---:|
| 1 | [`aidd-report-reader`](skills/aidd-report-reader/SKILL.md) | 读华为 AIDD（aidd.huawei.blue）文档质量扫描报告并导出问题清单——检查 AIDD 扫描报告、解析 AIDD 问题、导出 issue 数据：gitcode OAuth 登录（DevUI 复选框要直接注入 Vue 状态）、R... | 1 |
| 2 | [`ai-vendor-official-source-audit`](skills/ai-vendor-official-source-audit/SKILL.md) | AI 厂商官方源真伪与覆盖——这家厂商官方报告有哪些来源、这个文档链接是真的吗、抓下来是空壳还是真页：产品名≠API model id（按官方列表逐名计数）、新闻页与详情页都抓；体积极小或与假 slug 同档判空壳；HF &full=tru... | 1 |
| 3 | [`arxiv-paper-deep-read-and-claim-verification`](skills/arxiv-paper-deep-read-and-claim-verification/SKILL.md) | arXiv 论文精读 + 开源声称独立核查——精读这篇论文、论文说的开源仓真实存在吗、论文数字能复现吗：web_fetch 抓 /html 会在正文中段被 (Content truncated.) 截断，改用 pwsh Invoke-Web... | 1 |
| 4 | [`ascend-cann-env`](skills/ascend-cann-env/SKILL.md) | 昇腾 CANN 的检测/安装/激活/换版本/卸载（默认 a3=192.168.13.188，备用 a3b=.190）——权威定位看 /etc/Ascend/ascend_cann_install.info，toolkit+ops+nnal ... | 1 |
| 5 | [`ascend-conda-env`](skills/ascend-conda-env/SKILL.md) | 昇腾服务器 conda 环境的检测 / 新建 / 激活与换 python 版本（默认 a3=192.168.13.188，备用 a3b=.190）——共享 miniconda3 在 /mnt/share/x00886548/minicond... | 1 |
| 6 | [`ascend-env`](skills/ascend-env/SKILL.md) | 昇腾 NPU 服务器环境搭建入口总纲（a3=192.168.13.188 默认 / a3b=.190 备用）——**先并行再串行**的 4 lane 编排（CANN 包下载 ∥ conda 建环境 ∥ torch 栈 whl 预下载 ∥ 两... | 2 |
| 7 | [`ascend-model-adaptation-recon`](skills/ascend-model-adaptation-recon/SKILL.md) | 判定某模型在昇腾/vllm-ascend 生态里的适配程度（实测 MiniMax-H3）——一次全树 API 判「主仓有无代码」、追 import 链定位跨仓分工（vllm-ascend 基座 ↔ vllm-omni NPU 平台层）、查镜... | 1 |
| 8 | [`ascend-moe-ep-capacity-planning`](skills/ascend-moe-ep-capacity-planning/SKILL.md) | 昇腾 64GB 卡跑 MoE 大模型前的显存容量与并行几何规划——EP 没有独立开关（EP = TP × DP × PCP），按卡数 N 选型必须随 N 重推 TP；64GB 卡真实预算只有 56.378 GiB，用 64GB 或 64×1... | 2 |
| 9 | [`ascend-server-layout`](skills/ascend-server-layout/SKILL.md) | 昇腾服务器目录地图与磁盘红线——找模型在哪、磁盘满了该写哪个盘（a3=.188 默认 / a3b=.190 备用）——.188 只有两块真盘：系统盘 /（/mnt/share、/mnt/weight、/tmp、/root 全压在它上面，多租... | 1 |
| 10 | [`ascend-torch-npu`](skills/ascend-torch-npu/SKILL.md) | 昇腾 NPU 上 torch + torch_npu 的检测 / 安装 / 验证 / 排障（默认 a3=192.168.13.188，备用 a3b=.190）——先定车道：A（跑 vllm-ascend，默认）torch 2.10.0+cp... | 1 |
| 11 | [`ascend-triton-ascend`](skills/ascend-triton-ascend/SKILL.md) | 昇腾 NPU（a3=.188 / a3b=.190）上 triton-ascend 的检测 / 安装 / 验证 / 排障——商发版 3.2.2 必须从 osinfra 专用源装（PyPI 上没有）；官方覆盖式共存，import triton... | 2 |
| 12 | [`ascend-vllm-serve`](skills/ascend-vllm-serve/SKILL.md) | 在昇腾 A3（.188/.190）上把装好的 vllm + vllm-ascend 跑起来——三层自检、按 HBM 挑空闲 die、起 OpenAI 兼容服务、离线推理冒烟、sleep/wake_up 显存释放与重载、运行时排障。适用于"在... | 2 |
| 13 | [`dingxiang-slider-captcha`](skills/dingxiang-slider-captcha/SKILL.md) | 顶象（dx）拼图缺口滑块验证码在 Android 模拟器上的实测结构与破解结论——过一下顶象滑块验证码、用 adb 拖、拿 dx_captcha_basic 的 DOM 和坐标：含 DOM/几何参数、块与手指位移 1:1、块是半透明混合渲染... | 1 |
| 14 | [`dsh-agent-customization`](skills/dsh-agent-customization/SKILL.md) | DSH 改造 agent 行为的入口总纲——改了 AGENTS.md 为何不生效、插件行坏了怎么回滚、settings.yaml 改了为何没反应、这次改动属于哪一层；含五层生效时机、热重载≠冷启动、坏 row 三形态、MCP 挂载与会话日志... | 5 |
| 15 | [`dsh-agent-preset-verification`](skills/dsh-agent-preset-verification/SKILL.md) | DSH agent preset 验收两阶段——preset 没生效但看不出哪错了、到底挂载对没对、改完先离线确认；离线过了但插件行为不对、persona 与工具在真会话里对不对、委派为什么失败；headless 不能验 preset 且会... | 3 |
| 16 | [`dsh-isolated-web-host`](skills/dsh-isolated-web-host/SKILL.md) | 起个隔离 DSH host 做实验——想不污染真实 ~/.dsh 就验证插件行或 patch、真实 host 占着 3080 不能重启时用它：必加 --no-open、启动先落盘 pid 与端口、不带 token 的 401 判就绪、tas... | 1 |
| 17 | [`dsh-repo-sync`](skills/dsh-repo-sync/SKILL.md) | 我的 DSH 私仓同步——现在同步一次、昨天同步没成功、私仓内容少了或不对、ALERT.md 出现了、计划任务 DSH-Repo-Sync 报错：脚本 sync-dsh-repos.ps1 把 ~/.dsh 与编排 preset 用 rob... | 3 |
| 18 | [`dsh-skill-authoring`](skills/dsh-skill-authoring/SKILL.md) | DSH skill 文件本身的写法契约——skill 没被触发或加载不上时先看这条：模型每步只看到目录里的一行「`name` + 半角冒号 + description」（正文与 whenToUse 都不进目录），description 被折... | 3 |
| 19 | [`dsh-skill-self-audit`](skills/dsh-skill-self-audit/SKILL.md) | DSH skill 集合的每日无人值守自检——静默满 1 小时且距上次自检 ≥20h 才跑；Windows 计划任务 DSH-Skill-SelfAudit 每小时轮询、headless 真跑；体检含 YAML round-trip、交叉引... | 5 |
| 20 | [`dsh-skills-publish`](skills/dsh-skills-publish/SKILL.md) | 把本机 ~/.dsh/skills 的全部 skill 每天凌晨 2 点同步发布到 GitCode 与 GitHub 两个公开仓 EliasKaslan/dsh-skills——脚本 publish-dsh-skills.ps1 先快照再扫... | 6 |
| 21 | [`external-buzz-magnitude-check`](skills/external-buzz-magnitude-check/SKILL.md) | 外部热度量级取证——这事在外网真的火吗（HN points/评论、HF likes/下载量、Artificial Analysis/OpenRouter 体验指标、社区情绪分级）——判某事在外网是否真热、某模型是否真难用，给可复现量级数字；... | 1 |
| 22 | [`gitcode-pr-flow`](skills/gitcode-pr-flow/SKILL.md) | GitCode 上任意昇腾社区仓提 PR（MindSpeed-Ops 与 MindSpeed-Agent 均已完整验证）从个人 fork 到合入全流程——compile 评论触发门禁（任何 head 变化后须补发）、双 CI 判读与标签审计... | 4 |
| 23 | [`github-org-delta-watch`](skills/github-org-delta-watch/SKILL.md) | GitHub 组织增量追踪——基准日之后这个组织谁在动、这仓是不是死仓、官方那个承诺兑现了没：rate_limit 的 Date 头取"今天"、orgs/{org}/repos?sort=pushed 覆盖全组织找活性、pushed_at ... | 1 |
| 24 | [`github-pr-flow`](skills/github-pr-flow/SKILL.md) | 向 GitHub 上游开源仓（如 vllm-project/vllm-ascend）从 fork 提 PR 的全 API 流程（classic PAT）——token 验证与 403/401 判因、DCO 签名提交、REST API 创建/... | 1 |
| 25 | [`korea-official-source-research`](skills/korea-official-source-research/SKILL.md) | 韩国（济州）官方一手信息源——官方页面怎么抓、没日期怎么看：web_fetch 对韩国站点多数不可用，urllib 按站点分档，pwsh 最稳；含出入境/入境申告官方源结构（e-AC 的 bbsId / flId、mofa.go.kr 详情... | 1 |
| 26 | [`orchestrating-subagents`](skills/orchestrating-subagents/SKILL.md) | 编排手册——两通道模型：生产动作（读文件、跨模块检索、跑命令、联网、试错、写代码/文档、改配置）一律下发子代理，主 Agent 保留全套工具、只做交付前独立复核（真跑验收命令、核"文件:行号"、读本体与 exit code）；判据权威出处是... | 2 |
| 27 | [`outlook-mailbox-control`](skills/outlook-mailbox-control/SKILL.md) | Outlook.com（个人 MSA）邮箱接管——接管我的 outlook 邮箱、查收件箱、按关键词搜邮件、读正文和附件、以我的名义回信、存草稿：MS365 MCP discovery 直调的能力配方（工具名＋最小 parameters J... | 1 |
| 28 | [`pwsh-on-windows`](skills/pwsh-on-windows/SKILL.md) | 本机命令行一整套静默坏结果（pwsh 实为 Windows PowerShell 5.1，非 PS7）——中文乱码、行数或 CR 数对不上、计数总是 0、目录看着空其实不空、执行策略拦住脚本、传 JSON 报 Expecting value... | 1 |
| 29 | [`qq-mail-control`](skills/qq-mail-control/SKILL.md) | QQ 邮箱接管（IMAP/SMTP，`mcp__qqmail__*`）——发一封 QQ 邮件、查收件箱、搜邮件、读某封邮件的参数配方与坑：文件夹名编码（回显中文原文、UTF-8 原文直传可用，传 `&UXZO1mWHTvZZOQ-` 这类 ... | 1 |
| 30 | [`sedimenting-skills`](skills/sedimenting-skills/SKILL.md) | Skill 沉淀协议——先过目录税预算（目录字符总量 ≤ 20,000，默认值可调），每次非平凡运行收尾都**自动**复盘，并**全库匹配**找归属（三段决策 ①融合已有 skill ②建/更新总纲 ③都没有才新建）——默认首选融合：有归属... | 1 |
| 31 | [`univpn-vpn`](skills/univpn-vpn/SKILL.md) | UniVPN（联软 Leagsoft，C:\Program Files (x86)\UniVPN）——188 连不上、177.8.21.1 怎么连就看这条：蓝区网关(x00886548)推 192.168.0.0/16 → a3=192.1... | 3 |
| 32 | [`upstream-docs-refresh-audit`](skills/upstream-docs-refresh-audit/SKILL.md) | 上游仓库 docs 刷新审计——这批需求在 docs 里都能检索到吗、这版主线资料要不要刷新：输入一批中文内部需求或中文转测文档，判 docs/source 是否需要刷新，产出六节结论清单 + 逐条刷新方案：三件前置产物先行、只读 work... | 5 |
| 33 | [`vllm-ascend-e2e-ci-wiring`](skills/vllm-ascend-e2e-ci-wiring/SKILL.md) | vllm-ascend e2e 用例进 CI 的落位与登记——tests/e2e/pull_request 下新增 test 必须登记 estimated_times.yaml，否则 coverage.py 打印 ✗ MISSING 后 s... | 2 |
| 34 | [`vllm-ascend-source-install`](skills/vllm-ascend-source-install/SKILL.md) | 从源码装 vllm + vllm-ascend 配对流程——main 按 `.github/vllm-main-verified.commit` 配 vllm（VLLM_TARGET_DEVICE=empty）；release tag 配同... | 3 |
| 35 | [`win-scheduled-task-forensics`](skills/win-scheduled-task-forensics/SKILL.md) | Windows 计划任务/持久化项取证与安全退役——谁给我装了每日定时程序、把每日签到任务停掉、这个定时任务是谁加的：五处侦察面（计划任务全量、schtasks 旁证、Run 键、两个启动文件夹、WMI 事件订阅）缺一处就漏；退役顺序固定为... | 1 |
| 36 | [`yb-blue`](skills/yb-blue/SKILL.md) | 蓝区主控端（YB-Bridge）——把活拆成黄区弱模型能照做的任务包，经私有 GitHub 仓下发，轮询取回报告并按四要素验收；黄→蓝单次≤100KB 自动分块，蓝→黄不限。适用于"给黄区派活 / 收黄区报告 / 黄蓝协同 / 跨区接力 /... | 3 |
