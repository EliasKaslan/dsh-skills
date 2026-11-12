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

共 **60** 个 skill、**239** 个文件、**26501426** 字节。凭据文件（`credentials.txt`、`*.key`、`*.pem` 等）按规则排除，不入库。

| # | Skill | 说明 | 文件 |
|---:|---|---|---:|
| 1 | [`ai-musume-4k-art`](skills/ai-musume-4k-art/SKILL.md) |  | 51 |
| 2 | [`ai-vendor-official-source-audit`](skills/ai-vendor-official-source-audit/SKILL.md) | AI 厂商官方源真伪与覆盖面判定——产品名≠API model id（按官方列表计数）；新闻页/详情页信息不同都抓；HF &full=true 拿时间、401=not found、createdAt≠发布日；判 BF16/FP8 版本只看 ... | 1 |
| 3 | [`aidd-report-reader`](skills/aidd-report-reader/SKILL.md) | 读华为 AIDD（aidd.huawei.blue）文档质量扫描报告并导出问题清单——gitcode OAuth 登录（DevUI 复选框要直接注入 Vue 状态）、REST API 免爬 DOM 批量拉 issues。适用于"检查 AID... | 1 |
| 4 | [`anima-ai-musume-lora`](skills/anima-ai-musume-lora/SKILL.md) | 用 Anima 底模 + AI 娘 LoRA 在昇腾 192.168.13.190 出图（ComfyUI on torch_npu，单 die 约 10 GB）——Aesthetic 1024×1536/32 步约 21 秒，Turbo 1... | 6 |
| 5 | [`anime-art`](skills/anime-art/SKILL.md) | 已停用（2026-11-11）——本 skill 的 SDXL 本地生图链路已被 minimax-ai-musume-4k-art（昇腾 192.168.13.190 上的 MiniMax-H3-Image）整体取代，任何新需求请改用 mi... | 16 |
| 6 | [`arxiv-paper-deep-read-and-claim-verification`](skills/arxiv-paper-deep-read-and-claim-verification/SKILL.md) | arXiv 论文精读 + 开源声称独立核查（实测 2606.13392v2）——web_fetch 抓 /html 会在正文中段被 (Content truncated.) 截断，改用 pwsh Invoke-WebRequest -Use... | 1 |
| 7 | [`ascend-cann-env`](skills/ascend-cann-env/SKILL.md) | CANN 检测/安装/换版/卸载：install.info 定位、三件套序列。适用于"装 CANN / import acl 报错 / ASCEND_HOME_PATH 为空 / Permission denied / 该用哪个包"。 | 1 |
| 8 | [`ascend-conda-env`](skills/ascend-conda-env/SKILL.md) | 昇腾 conda 环境：共享 miniconda3、环境目录、NJU 镜像、免激活调用。适用于"建 conda 环境 / 换 python 版本 / 环境该放哪 / conda 官方源太慢 / python -V 不对"。 | 1 |
| 9 | [`ascend-env`](skills/ascend-env/SKILL.md) | 昇腾环境入口总纲：进机器 → 目录/CANN/conda/torch/triton/vllm 的顺序与三层验收。适用于"在昇腾上装环境 / 不知先做哪步 / 该用哪个子 skill / 机器进不去或 ssh 假死"。 | 1 |
| 10 | [`ascend-model-adaptation-recon`](skills/ascend-model-adaptation-recon/SKILL.md) | 判模型在昇腾/vllm-ascend 的适配度：全树代码、跨仓分工、镜像、缺口。适用于"H3 在昇腾能不能跑 / 适配到什么程度 / 缺口在哪 / Day-0 是真的吗 / 该用哪个镜像"。 | 1 |
| 11 | [`ascend-moe-ep-capacity-planning`](skills/ascend-moe-ep-capacity-planning/SKILL.md) | MoE 显存与 EP/TP 几何：64GB 卡实际 56.378 GiB、EP=TP×DP×PCP。适用于"几张卡才跑得起来 / EP 设多少 / TP 怎么配 / OOM 前先估 / 按卡数选型"。 | 2 |
| 12 | [`ascend-server-access`](skills/ascend-server-access/SKILL.md) | 昇腾服务器准入清单：a3/.188、a3b/.190、A5 各 IP、UniVPN、免密。适用于"188 连不上 / 177.x 怎么连 / 该连哪个 VPN / 凭据在哪 / 新机器怎么配免密"。 | 6 |
| 13 | [`ascend-server-layout`](skills/ascend-server-layout/SKILL.md) | 昇腾个人根与目录红线：环境/项目/数据放哪、模型软链、npu-smi 选卡。适用于"新项目写哪个盘 / 环境放哪 / 磁盘满了 / 哪张 NPU 空闲 / 复用现成环境"。 | 3 |
| 14 | [`ascend-torch-npu`](skills/ascend-torch-npu/SKILL.md) | torch + torch_npu 装/验/排障：A/B 车道、版本配对、验收 True 16 253。适用于"装 torch_npu / NPU 不可用 / pip 卡死 / GLIBCXX 缺失 / 该走哪条车道"。 | 1 |
| 15 | [`ascend-triton-ascend`](skills/ascend-triton-ascend/SKILL.md) | triton-ascend 装/验/排障：3.2.2 走 osinfra 源、覆盖式共存。适用于"装 triton-ascend / import 版本不对 / 被 pip -U triton 覆盖后崩"。 | 1 |
| 16 | [`ascend-vllm-serve`](skills/ascend-vllm-serve/SKILL.md) | 在昇腾上起 vllm 服务：三层自检、选空闲 die、serve/离线/sleep、运行时排障。适用于"起 vllm 服务 / OOM / 输出乱码 / reload_weights / 该占哪张卡 / 模型太大要 TP=2"。 | 1 |
| 17 | [`batch-invariance-acceptance`](skills/batch-invariance-acceptance/SKILL.md) | 验证 vLLM Ascend 的 batch 不变性：BS=1 与 BS=N 逐位一致、TP 矩阵、长输入输出、数据集验收。适用于"验证/回归 batch 不变性 / logprobs 是否一致 / 算子白名单"。 | 8 |
| 18 | [`batch-invariant-weekly-digest`](skills/batch-invariant-weekly-digest/SKILL.md) | Batch 不变性周报：四仓已合入 PR 的概览表 + 转发形态邮件发黄区。适用于"跑 BI 周报 / 不变性有什么进展 / vLLM 这周合了哪些不变性 PR / 把周报改成列表"。 | 1 |
| 19 | [`dingxiang-slider-captcha`](skills/dingxiang-slider-captcha/SKILL.md) | 顶象（dx）拼图缺口滑块验证码在 Android 模拟器上的实测结构与破解结论——含 DOM/几何参数、块与手指位移 1:1、块是半透明混合渲染（NCC 定位失效根因）；结论：成功率极低（实测 0/6）。适用于"过一下顶象滑块验证码 / 提... | 1 |
| 20 | [`dsh-agent-customization`](skills/dsh-agent-customization/SKILL.md) | DSH 改造入口总纲：五层生效时机、插件 bundle、上线纪律与回滚。适用于"改 DSH 行为该改哪一层 / 插件行坏了怎么回滚 / MCP 怎么挂 / 恢复后会话打不开 / 自己写 host 插件"。 | 2 |
| 21 | [`dsh-agent-preset-live-verification`](skills/dsh-agent-preset-live-verification/SKILL.md) | DSH agent preset 的在线会话级验收——已起隔离 host 并真建会话才能做：RPC 核对 agentPreset 挂载、system prompt persona、session/page 权威工具清单，真跑一次委派核对子代... | 1 |
| 22 | [`dsh-agent-preset-verification`](skills/dsh-agent-preset-verification/SKILL.md) | DSH agent preset 离线静态校验（$DSH_HOME/.agent-presets/<id>/agent.cordis.yml）——不起会话也能验挂载：scanRoot 权威健康检查、逐行 Config/resolveConf... | 1 |
| 23 | [`dsh-home-guard`](skills/dsh-home-guard/SKILL.md) | 保护 ~/.dsh 不被误删：分钟快照 + 外置裸库 + 哨兵自愈。适用于"防止 agent 删 .dsh / .dsh 被清空了怎么救 / 会话日志丢了 / 想装看门狗 / 恢复后会话变少"。 | 1 |
| 24 | [`dsh-isolated-web-host`](skills/dsh-isolated-web-host/SKILL.md) | 起隔离 DSH host（重定向 DSH_HOME）：401 判就绪、落盘 pid 收尾、端口枚举恒空。适用于"起个隔离 host 试试 / 不污染真实环境验插件 / 真实 host 占着端口不能重启"。 | 1 |
| 25 | [`dsh-longhaul-mode`](skills/dsh-longhaul-mode/SKILL.md) | DSH 的 Longhaul 长线工程模式——longhaul 插件 7 个工具把「完成」改成密封命令与独立审计者双签，靠 .longhaul 账本哈希链与五道闸挡住改测试、改标尺、绿基线和自评放行。适用于"长线任务用哪个模式 / long... | 1 |
| 26 | [`dsh-phone-remote-relay`](skills/dsh-phone-remote-relay/SKILL.md) | 手机远程接管电脑上的 DSH：公共 broker 中继 + 端到端加密；多标签互斥、外壳/插件版本分列核对、任务分组落到未分组、偶发断连排查。 | 1 |
| 27 | [`dsh-repo-sync`](skills/dsh-repo-sync/SKILL.md) | 已退役——~/.dsh 私仓同步机制（DSH-Repo-Sync 任务与镜像仓均已删除）。仅留作历史记录与令牌形态参考。 | 3 |
| 28 | [`dsh-skill-authoring`](skills/dsh-skill-authoring/SKILL.md) | skill frontmatter 写法契约：description 才是触发字段、字符预算、拒载键。适用于"skill 没被触发或加载不上 / description 超限 / 改新建 skill / 校验脚本报错"。 | 3 |
| 29 | [`dsh-skill-self-audit`](skills/dsh-skill-self-audit/SKILL.md) | skill 集合定时自检：YAML、交叉引用、重复正文、目录预算。适用于"自检我的 skill / 有没有该合并的重复 / 哪些 skill 触发不了 / skill 目录多久没动"。 | 6 |
| 30 | [`external-buzz-magnitude-check`](skills/external-buzz-magnitude-check/SKILL.md) | 外部热度量级取证——这事在外网真的火吗（HN points/评论、HF likes/下载量、Artificial Analysis/OpenRouter 体验指标、社区情绪分级）——判某事在外网是否真热、某模型是否真难用，给可复现量级数字；... | 1 |
| 31 | [`git-tag-diff-audit`](skills/git-tag-diff-audit/SKILL.md) | 两个 git tag 之间做实质变更审计——两 tag 无共同祖先时 merge-base 静默返回空、git log A...B 静默给出两段历史之和，取数一律改两点 git diff A B；用 name-status 的 A/M/D/... | 1 |
| 32 | [`gitcode-pr-flow`](skills/gitcode-pr-flow/SKILL.md) | GitCode 仓提 PR：compile 门禁、双 CI、标签审计、OpenAPI、backport。适用于"向 GitCode 提 PR / 冲突 rebase / 补门禁 / pre-commit 抖动"。 | 4 |
| 33 | [`github-org-delta-watch`](skills/github-org-delta-watch/SKILL.md) | GitHub 组织增量 + 发行差集：pushed_at、releases、compare 取证。适用于"基线日后谁在动 / 主线有哪些没发版 / 这仓是不是死仓"。 | 1 |
| 34 | [`github-pr-flow`](skills/github-pr-flow/SKILL.md) | 向 GitHub 上游仓提 PR 全 API 流程：PAT、DCO、REST 创建与回读、CI 判读。适用于"提 PR / fork 推分支 / 403 没权限 / DCO 不过 / CI 挂的是不是我 / run_id 怎么拿"。 | 1 |
| 35 | [`korea-official-source-research`](skills/korea-official-source-research/SKILL.md) | 韩国（济州）官方一手信息源抓取与端点配方——web_fetch 对韩国站点普遍不可用，python urllib 按站点分档，pwsh 直连最稳；含出入境/入境申告官方源结构（e-AC 的 bbsId=文章id / flId=附件id、列表... | 3 |
| 36 | [`login-credential-autofill`](skills/login-credential-autofill/SKILL.md) | 登录凭据自动填充的本地凭据库与防封号护栏——页面要登录时按账号取凭据填入、先复用已有登录态、每账号24小时最多1次密码提交、遇验证码/2FA/风控页立刻停手交人；凭据库里没有该站时，先在本机浏览器密码库与邮箱里反查账号身份，附字段读取与额度... | 5 |
| 37 | [`lora-weekly-report`](skills/lora-weekly-report/SKILL.md) | LoRA 周报：vLLM/vLLM-Ascend/SGLang 近 7 天已合入 PR，四节 Markdown 发黄区。适用于"跑这周 LoRA 周报 / LoRA 特性跟踪 / SGLang 的 LoRA 进展"。 | 4 |
| 38 | [`mindspeed-ops-interface-compat-audit`](skills/mindspeed-ops-interface-compat-audit/SKILL.md) | MindSpeed-Ops 仓面核查：跨仓接口兼容（AST 盘点/周边仓实跑/缺口报告）+ 算子增量（近 N 天新增哪些算子、四件套判定）。 | 1 |
| 39 | [`mindspeed-ops-smoke`](skills/mindspeed-ops-smoke/SKILL.md) | MindSpeed-Ops 冒烟：按版本矩阵建环境、UT + ATK 精度双读判绿。适用于"跑 26.2.0 冒烟 / ATK 精度怎么判 / 冒烟全绿了吗 / CI 镜像配套对不对"。 | 1 |
| 40 | [`mindspeed-ops-whl-build`](skills/mindspeed-ops-whl-build/SKILL.md) | 打 MindSpeed-Ops whl 并验收：cmake/clang、SOC_VERSION、CATLASS。适用于"打 ops 的 whl / cmake 版本报错 / GCC 太旧 / 验证 whl"。 | 1 |
| 41 | [`minimax-ai-musume-4k-art`](skills/minimax-ai-musume-4k-art/SKILL.md) | 用 MiniMax-H3-Image 在昇腾 192.168.13.190 出 AI 娘插画（1696×2528 六步约 8 秒，4 die）——五位 AI 娘（Claude／DeepSeek／GPT／Grok／Gemini）的形象已按 B... | 51 |
| 42 | [`model-endpoint-identity-audit`](skills/model-endpoint-identity-audit/SKILL.md) | 同一供应商多个 model id 是否同一个模型 + 能力/速度实测——支撑说"都是某版本"靠不靠谱、四个渠道哪个快哪个贵：用前缀缓存互通矩阵判是否同一后端（决定性证据）、tokenizer 与图像 token 指纹、短贪心输出指纹、随机 ... | 1 |
| 43 | [`node-test-false-green-audit`](skills/node-test-false-green-audit/SKILL.md) | Node 测试与 CI 的「假绿」排查——六类会让你以为跑过其实没跑的陷阱：CI 里写死测试目录或空 glob 静默跳过、await 一个 unref 定时器让 Node 22 把整个文件判 cancelledByParent（fail 仍... | 1 |
| 44 | [`orchestrating-subagents`](skills/orchestrating-subagents/SKILL.md) | 子代理编排手册：拆解、并行下发、校验结论、上下文预算。适用于"任务太大一次读不完 / 该不该派子代理 / 帮我并行跑几件事 / 子代理答错了要不要重派 / 上下文快满了"。 | 1 |
| 45 | [`outlook-mailbox-control`](skills/outlook-mailbox-control/SKILL.md) | Outlook.com 邮箱接管（MS365 MCP）：登录、搜读、回信、草稿。适用于"接管 outlook 邮箱 / 查收件箱 / 读附件 / 以我的名义回信 / outlook 工具报错"。 | 1 |
| 46 | [`pr-change-equivalence-audit`](skills/pr-change-equivalence-audit/SKILL.md) | 审计「这个 PR 是否只是等价改写、功能/精度/性能是否不变」——先锁 diff 与 dtype 链，再按 IEEE 穷举 ±0/NaN/FTZ，证明有效区逐位等价与掩码区差异，最后给出「代码可证 / PR 自述 / 未验证」三级证据表。适... | 1 |
| 47 | [`prior-agent-artifact-audit`](skills/prior-agent-artifact-audit/SKILL.md) | 前代 agent 产物目录（「上一轮交付」）的真实完成度取证——证据分四层标注【自测/落盘/文档/复核】，部署/工作区现实分开判（线上入口与本地候选逐字节比对、判装没装看运行时清单与包目录而非源码），档案行号自证矛盾即降为线索，产品化完成度... | 1 |
| 48 | [`pwsh-on-windows`](skills/pwsh-on-windows/SKILL.md) | 本机 pwsh 实为 Windows PowerShell 5.1：GBK 解码、BOM、PS7 语法静默坑。适用于"中文乱码 / 行数或 CR 数不对 / 计数总是 0 / 执行策略拦 / PS7 语法报错"。 | 1 |
| 49 | [`qq-mail-control`](skills/qq-mail-control/SKILL.md) | QQ 邮箱接管（IMAP/SMTP）：发信、搜读、归档、黄区/私人别名。适用于"发 QQ 邮件 / 查收件箱 / 搜邮件 / 读某封 / 建夹归档 / 只能读不能发"。 | 1 |
| 50 | [`sedimenting-skills`](skills/sedimenting-skills/SKILL.md) | skill 沉淀协议：三段决策（融合/总纲/新建）、单一归属、目录成本预算。适用于"这条经验要不要写成 skill / 该并进哪个已有 skill / 怎么防重复 / 什么该做成总纲 / 目录预算怎么算"。 | 1 |
| 51 | [`skill-archive`](skills/skill-archive/SKILL.md) | 冷备 skill 索引：读 skills-archive/INDEX.json 找不在目录里的能力。适用于"目录里没有对应的专门流程 / 生图 / 长尾调研 / PR 审计 / 想找旧 skill"。 | 1 |
| 52 | [`subagent-toolset-precheck`](skills/subagent-toolset-precheck/SKILL.md) | 子代理工具集预检——子代理说没有 web_fetch、工具受限怎么办：派活前先让它如实回报函数清单，避免把联网调研或要求落盘的任务派给工具受限的 `explore` 子代理（实测只拿到 glob/grep/list_subagent_mod... | 1 |
| 53 | [`tilelang-op-generator`](skills/tilelang-op-generator/SKILL.md) | 写/迁移 TileLang 算子到昇腾：kernel + 分层 golden + Triton-Ascend 同卡对比。适用于"用 TileLang 写算子 / 生成 softmax kernel / 把算子迁到 NPU / 修精度"。 | 16 |
| 54 | [`upstream-docs-refresh-audit`](skills/upstream-docs-refresh-audit/SKILL.md) | 上游 docs 刷新审计：需求/转测文档 → 存在性普查 → 六节清单。适用于"这批需求 docs 里能查到吗 / 要刷新吗 / 内部代号叫什么 / 启动参数主线有没有"。 | 5 |
| 55 | [`vllm-ascend-e2e-ci-wiring`](skills/vllm-ascend-e2e-ci-wiring/SKILL.md) | vllm-ascend e2e 进 CI：estimated_times 登记、coverage 门禁、目录归属。适用于"新增 e2e / CI 报 MISSING / 本地全 MISSING"。 | 1 |
| 56 | [`vllm-ascend-source-install`](skills/vllm-ascend-source-install/SKILL.md) | 源码装 vllm + vllm-ascend 配对版本：读 verified commit、注释 pin 复用 torch。适用于"重装 vllm-ascend / 按 commit 配 vllm / build deps 不满足"。 | 2 |
| 57 | [`vuln-scan-report-verification`](skills/vuln-scan-report-verification/SKILL.md) | 核实第三方漏洞扫描报告：锁 commit、回溯可达性、张冠李戴、定级。适用于"这个高危是真的吗 / 行号对不对 / 注入能不能用 / 定级高不高 / 有没有漏报"。 | 1 |
| 58 | [`web-ui-contrast-audit`](skills/web-ui-contrast-audit/SKILL.md) | 网页字看不清/浅色主题对比度：真浏览器逐节点算 WCAG 比值，避开渐变与半透明误报，先修继承根。 | 1 |
| 59 | [`win-scheduled-task-forensics`](skills/win-scheduled-task-forensics/SKILL.md) | Windows 计划任务/持久化项取证与安全退役——谁给我装了每日定时程序、把每日签到任务停掉、这个定时任务是谁加的：五处侦察面（计划任务全量、schtasks 旁证、Run 键、两个启动文件夹、WMI 事件订阅）缺一处就漏；退役顺序固定为... | 1 |
| 60 | [`yb-blue`](skills/yb-blue/SKILL.md) | 蓝区主控端（YB-Bridge）——把活拆成黄区弱模型能照做的任务包，经私有 GitHub 仓下发，轮询取回报告并按四要素验收；黄→蓝单次≤100KB 自动分块，蓝→黄不限。适用于"给黄区派活 / 收黄区报告 / 黄蓝协同 / 跨区接力 /... | 3 |
