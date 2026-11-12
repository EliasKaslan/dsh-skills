---
name: model-endpoint-identity-audit
description: 同一供应商多个 model id 是否同一个模型 + 能力/速度实测——支撑说"都是某版本"靠不靠谱、四个渠道哪个快哪个贵：用前缀缓存互通矩阵判是否同一后端（决定性证据）、tokenizer 与图像 token 指纹、短贪心输出指纹、随机 nonce 强制冷预填充、capability 矩阵逐项探测（上下文上限原文 / json_schema / logprobs / n>1 / 关思考开关）。适用于"这几个 model id 是不是同一个模型 / 支撑说都是 1017 版靠谱吗 / 同一模型四个渠道哪个快 / 哪个便宜哪个贵 / 换个渠道质量会掉吗 / 上下文到底是多大 / 为什么 logprobs 返回 null"。不适用：查厂商官方有没有发布这个模型 → 用 `ai-vendor-official-source-audit`；只评估外部热度与口碑量级 → 用 `external-buzz-magnitude-check`。
whenToUse: 多 endpoint / 多 model id 的身份核验与同口径能力速度对比（不含官方源真伪与外部热度）。
disable-model-invocation: true
warm-triggers: 多个 model id 是否同一模型 / 渠道速度与价格
warm-reason: 一次性调研方法论，低频
---

# 多端点模型身份核验与能力对比

## 何时调用

**加载本 skill 当：**
- 用户说"这几个 model id 是不是同一个模型 / 支撑说都是 XX 版 / 四个渠道有什么区别 / 哪个快哪个便宜"。
- 手里有一个 OpenAI 兼容网关，同一模型挂了多个 id（原生 id + `vendor/` 前缀 id），要判它们是不是同一后端。
- 要给一份"能力矩阵 + 速度 + 质量"的实测对比，而不是照抄 `/v1/models` 的元数据。

**不要用本 skill（转交）：**
- 判断厂商官方文档/发布是否真实 → `ai-vendor-official-source-audit`
- 只看外部口碑与热度量级 → `external-buzz-magnitude-check`

**前置**：能直连端点（不要走 agent 框架，框架的提示词与工具注入会污染指纹）。
**后继**：把结论落成"按场景选型表"，别只给一张平均分表。

---

## 1. 什么能当证据，什么不能

| 证据 | 能用吗 | 说明 |
|---|---|---|
| `response.model` 回显 | 弱证据 | 上游 id 串不同可能只是接入层改名；相同也不代表权重相同 |
| `/v1/models` 的 name / price | 弱证据 | 名字是运营填的；价格只能当相对倍率 |
| `credit` 字段的量纲 | 需自证 | 见 §5.1：客户端不算钱，字段含义只能靠价格阶梯反推 |
| tokenizer `prompt_tokens` | **强证据** | 同一 tokenizer 才会逐项相同 |
| 图像 `prompt_tokens` | **强证据** | 视觉前端（切图/patch）相同 |
| 短输出贪心逐字一致 | **强证据** | 几十 token 内可复现 |
| 长输出逐字一致 | **不可用** | 见 §6.1，同端点重跑就不一致 |
| 前缀缓存互通 | **最强** | 见 §2，直接证明同一推理后端 |
| 模型自述 | **不可用** | 见 §6.4 |

---

## 2. 前缀缓存互通矩阵（最硬的一条）

思路：前缀缓存是**后端进程/集群级**的。若 A 刚写下的 KV 前缀，B 首次请求就报命中，则 A、B 打到同一套后端。

做法（对每一对有序 (A,B)）：
1. 生成一段**唯一**的长 prompt（≥8k token，开头带随机 tag），先打 A。
2. 原样打 B，读 `usage.prompt_tokens_details.cached_tokens`。
3. 反向再做一次（避免"先到先得"的方向偏差）。

实测样例（某网关 4 个 id）：

```
base   -> volc   cached=12544     volc   -> base   cached=12544
base   -> baidu  cached=0         base   -> dash   cached=0
dash   -> base   cached=0         dash   -> volc   cached=0
```

判据：
- **只有一对互通** ⇒ 这两个 id 是同一后端，其余是独立部署。
- 全互通 ⇒ 缓存做在网关层（不是同一后端），此证据作废。
- 全不互通且第二次同 id 也不命中 ⇒ 该家没开前缀缓存（或不上报），不能据此判"不同后端"。

坑：有的接入层**根本不上报** `cached_tokens`（恒 0），拿它当第二跳时永远看不到命中——这是"不报"，不是"没有"。

---

## 3. 指纹三件套

### 3.1 文本 tokenizer
选 6 类文本：英文、中文、代码、符号+emoji、长数字串、JSON。`max_tokens=1`，读 `prompt_tokens`。逐项相同才判同一 tokenizer。

### 3.2 图像 tokenizer
同一张图（base64 data URL）在不同端点的 `prompt_tokens` 应完全相同（如 9 张图全部 251/234/248/…）。这同时验证"`/models` 声称支持 image 输入"是真的。

### 3.3 短贪心输出
`temperature=0`，问**唯一答案且极短**的东西：π 前 40 位、前 40 个素数、元素符号表、固定单词排序。逐字比对。
**别用需要长篇推理的题**——见 §6.1。

---

## 4. 冷预填充怎么测才不假

同一条长 prompt 打多个端点，第二个一定命中第一个的缓存（§2），测出来的是缓存速度。

修法：**每次请求在 prompt 最前面插入随机 nonce**（`[a8Fk2pQ1] `），让第 1 个 token 就不同，强制冷启动；每个 rep 换一个 nonce。

同理，测 1M 级上下文时，四家若用同一 seed 生成同一条 prompt，第二家的延迟数字全部作废——要么换 nonce，要么在报告里显式标注"缓存命中"。

---

## 5. capability 矩阵探测清单

逐项发最小请求，记录**成功/失败 + 错误原文**（错误原文比 ✓/✗ 有用得多）：

| 项 | 探法 | 常见差异 |
|---|---|---|
| 上下文上限 | 发超限请求，读报错里的数字 | 名义 1,048,576 实际常是 1,048,568；有的接入层砍到 1,000,000 |
| `max_tokens` | 逐级抬高 | 131072 通常都能收 |
| `max_completion_tokens` 别名 | 同上 | 多数兼容 |
| 关思考 | `reasoning_effort:"none"` 与 `thinking:{type:"disabled"}` **分开测** | 有的只认后者；有的 `none` 被静默忽略 |
| `reasoning_effort` 档位 | 同一题跑 none/minimal/low/medium/high/max，看 `reasoning_tokens` | 多数**不是长度旋钮**，除 none 外无单调关系 |
| `json_object` | 发一个 schema 提示 | 普遍支持 |
| `json_schema` | `response_format:{type:"json_schema",...}` | 部分接入层直接 400 "unavailable now" |
| `logprobs` | **开思考与关思考各测一次** | 见 §6.2、§6.3 |
| `top_logprobs` 范围 | 传 8 | 有的上限 5 |
| `n>1` | 传 2 | 有的静默只回 1 条，有的明确 400 |
| 流式工具调用 | `stream:true` + tools，拼 `delta.tool_calls` | 有的会先吐几段 content 再吐工具调用 |
| 多轮工具 | 真 agent 循环：按模型**实际调用的工具**返回对应结果 | 别把 A 工具的结果喂给 B 调用，会造出假失败 |
| 视觉 | 9 张图：颜色/计数/OCR/算术/左右/图表/双图/表格/大图小字 | 全部应通过，且 token 数逐张相同 |

### 5.1 `credit` 字段的量纲：客户端不算钱，只能反推

`/v1/models` 里的 `credit` + `credit_history`（带生效日期）是**价目表**，不是余额。实测要点：

- 响应正文与 header 里**没有**任何计费字段（只有 `usage` 的 token 三件套），网关也没有 `/v1/balance`、`/v1/usage`（全 404）。
- DSH 客户端**不**用这个字段算钱：全 asar 扫描 `credit`，命中的只有账户设置页的 UI 文案；宿主侧没有本地计价代码 ⇒ 计价在服务端。
- 量纲只能看价格阶梯：同族模型 0.15 / 0.22 / 0.33 / 0.46 / 0.99 / 1.46 / 1.85。按"每 1M token 单价"解释才是这些模型的合理价位（按每 1K 解释会得到 $150~$1850/M，没有任何厂商这么定价）。
- 于是 `可用 token ≈ 余额 ÷ credit × 1e6`。要精确，做一次校准：记余额 → 跑一轮已知 token 的任务 → 再记余额。

---

## 6. 容易自欺的六个坑

### 6.1 `temperature=0` 不是严格贪心，长输出不可复现
同端点、同 prompt 连跑三次，长度就不同（实测 3618 / 3854 / 3847 字符；另一家 3866 / 3474 / 3930）。MoE 路由 + 批处理数值噪声。
⇒ **不能**用"两家长输出不一样"证明"权重不同"；也别把单次长输出当回归基线。

### 6.2 开思考时 logprobs 可能是垃圾
某接入层在 reasoning 开启时返回：被选中 token `logprob = -1e+38`，top-1 却是 `<think>`（`0.0`）。关思考后同一请求完全正常。
⇒ logprobs 必须**分开关/开思考两态**验证；拿它算置信度前先看一眼数值范围。

### 6.3 有的接入层 logprobs 恒 null
不报错、静默降级。判据只能是"读到的 `choices[0].logprobs.content` 是否为 null"，不能看 HTTP 200。

### 6.4 模型自述身份不可信
实测四家都自称 "Claude 3.5 Sonnet"（模型本身是别家的）。自述一致只能当"同源"旁证，绝不能当版本判据。

### 6.5 推理会吃满 `max_tokens`
给 6000 让它写长代码，四家把 6000 全花在 reasoning 上，`content` 为空、`finish=length`。
⇒ 对比质量时 `max_tokens` 至少 8192；看到空回答先查 `completion_tokens_details.reasoning_tokens`。

### 6.6 工具测试的假失败
把"天气结果"塞给模型误调的 `get_current_time`，模型会发现矛盾再调一次，脚本判失败——**是测试装置的错**。
⇒ 用真循环（按实际调用返回对应结果），统计"几步收敛"而不是"第一次调用对不对"。

### 6.7 接进 agent 框架后报 `developer is not one of [...]`
同一网关的四个 id，直连都正常，但把客户端切到某一家后整轮失败：
`400 {"message":"developer is not one of ['system','assistant','user','tool','function']"}`。

原因不在模型，在**接入层对角色的宽容度**：
- DSH 的 pi-ai 通道在 `model.reasoning` 为真时，用 `developer` 承载系统提示词（`@earendil-works/pi-ai/dist/api/openai-completions.js` 的 `instructionRole = model.reasoning && compat.supportsDeveloperRole ? "developer" : "system"`）。
- Volcengine / 百度网关会把 `developer` 归一成 `system`（实测 200）；DashScope 严格校验角色白名单，直接 400。
- 实测对照：`role:"developer"` → base/volc/baidu 200、dash 400；`role:"system"` → 四家全 200。

修法（不用改代码，改 profile 的 model 条目即可）：
```yaml
          - id: dashscope/deepseek-v4.1-flash
            compat:
              supportsDeveloperRole: false
```
`compat` 可逐路由、逐模型配置，且**允许只写一个字段**（其余沿用目录检测）。改完 patch 需**重启**（冷启动验证一次），已存在会话不会自动恢复。
排查口诀：看到"某角色不在白名单"，先查客户端**发了什么角色**，再查该网关**收不收**，别去怀疑模型权重。

---

## 7. 脚本骨架

```python
# 身份三连
pt = chat(model, [{"role":"user","content":text}], max_tokens=1)["usage"]["prompt_tokens"]
cached = chat(model, [{"role":"user","content":same_prompt}])["usage"]["prompt_tokens_details"]["cached_tokens"]
short = chat(model, [{"role":"user","content":"pi 前40位"}], temperature=0)["choices"][0]["message"]["content"]

# 冷预填充
prompt = f"[{random_tag()}] " + body      # 每次换 tag
t0 = time.time(); stream(...); ttft = first_chunk_time - t0

# 质量判分：全部程序化（数值匹配 / 精确串 / 代码跑单测），不要 LLM 当裁判
```

报告结构建议：结论速览 → 被测对象表（含 price/credit）→ 身份核验（证据分级）→ capability 矩阵（带错误原文）→ 速度（TTFТ/生成速率/冷预填充/并发）→ 质量（分类别 + 压测）→ 坑 → 按场景选型表 → 复现脚本清单。
