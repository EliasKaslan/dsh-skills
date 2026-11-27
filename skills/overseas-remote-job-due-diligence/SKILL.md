---
name: overseas-remote-job-due-diligence
description: 核查海外远程岗真伪、用工形式与薪资水位：ATS公开API反查、LCA付薪基线、时区与on-call取证
whenToUse: 收到海外（尤其美国 AI infra/云厂商）招聘邮件或猎头私信，需要判断真伪、用工形式、薪资水位与工时真实形态时。
disable-model-invocation: true
warm-triggers: 收到海外公司招聘邮件 / 猎头私信值不值得谈 / 远程岗给多少钱什么形式
warm-reason: 招聘类尽调是一次性场景，不是日常开发任务；但用户已被海外 AI infra 公司主动 sourcing，可能数月复用一次
---

# 海外远程岗尽调：ATS 反查真伪、用工形式与薪资水位

# 海外远程岗尽调

## 何时调用
收到海外公司（尤其美国 AI infra / 云厂商）的招聘邮件或猎头私信，要回答「是不是真岗、给多少钱、什么用工形式、值不值得谈」。
不适用：改简历、模拟面试、纯查某公司百科背景。

## 1. 先钉原件，别信转述
确认 JD 域名是公司自有 ATS（`job-boards.greenhouse.io` / `jobs.lever.co` / `jobs.ashbyhq.com`），不是聚合站转载。
真伪的硬证据：JD 的 job id 能在公司 ATS 上打开，且发件人域名与 JD 内 hiring manager 邮箱同域。

## 2. 用 ATS 公开 API 一次看清"真在招吗、招几个、谁在招"
board 名从 JD URL 取（`job-boards.greenhouse.io/<board>/jobs/<id>`）：

```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/<board>/jobs" \
  | jq -r '.meta.total, (.jobs[] | [.title, .location.name, .first_published] | @tsv)'
```

- 逐个看 `location.name`：全公司只有 1 个「China - Remote」，那「founding China team」就是字面意义的 0 人团队。
- `first_published` 距今 >2 个月仍未下架：要么门槛高，要么钱不够，要么没人接 —— 这是你的谈判杠杆。
- 单条详情里能挖到 **Hiring Manager 姓名与邮箱**：

```bash
curl -s "https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>" | jq -r '.metadata'
```

拿这个名字去搜职位（`"<name>" <company> VP`）。**architect 岗汇报给产品 VP 而非工程负责人，是黄灯**：说明缺能评估你技术决策的工程管理层级。

## 3. 用工形式：看 JD 自己列的实体清单
JD 里「we have hiring entities in ...」是作者无意交的底：**名单里没有的国家就不是本地雇佣**，只能是 EOR 或离岸 contractor。
首轮必须问死：

> Is this a contractor engagement or employment through an EOR? Which entity signs, and who handles local tax and social insurance?

contractor 名义额要打折才可比：中国口径 **×0.77–0.83 ≈ 等价本地雇员总包**（无公积金/年终/N+1，自负个税社保）。

## 4. 薪资：三条锚，缺一条别报数
1. **JD 是否明码**。不写、反而在申请表要你「state your expectations in USD」= 结构性压价信号，先报价的人输。
2. **公司自身付薪水位**：美国 H-1B LCA 公开数据可按雇主查（`h1bdata.info`），看中位 base 和有没有 >$200k 的样本。中位低 + 零高薪样本 = 这家不按硅谷价付。
3. **所在地在岸锚点**：同技能栈本地岗明码区间（猎聘/拉勾）+ 大厂同级总包。

输出一个区间 + 三个门槛：低于 X 别接 / Y 是中位 / Z 才算有竞争力。**注明汇率取数日**，别用记忆里的旧汇率。

## 5. 工时只信两类证据
- **时区算术**：总部时区 vs 中国 = 几小时差。差 ≥10h 且 JD 只说 "async-friendly"、无 overlap 承诺 → 默认「白天异步 + 晚上开会」。
- **on-call**：跑生产系统的岗位必然有。搜 Glassdoor/Blind 的 `on-call` 原话，别看 WLB 均分（会被非工程岗拉高）。

## 坑
- `levels.fyi` 返 **HTTP 202 空响应**、`Glassdoor` 直连 **403 "Humans only"**、`天眼查` **419**、`LinkedIn Jobs` **429**。这些只能标「未检出」，**不能当"查无此岗"的证据**。
- 聚合站（remotesource / alion / seedtable）上的薪资多是 `estimated`，引用必须标「第三方估算 ±15%」，别和美国 LCA 实测混在一张表比。
- 「Founding XX」是 GTM 扩张的标准话术，不是独一无二的席位；数数同批开了几个 founding 岗就知虚实。

## 输出
一页纸：真伪结论（证据强度）→ 用工形式 → 薪资区间 + 三个门槛 → 工时真实形态 → 3 个必问问题 → 建议动作。
