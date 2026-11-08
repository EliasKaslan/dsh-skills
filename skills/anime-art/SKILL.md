---
name: anime-art
description: "本地离线画二次元图（SDXL Animagine XL 4.0 Opt + diffusers 自建管线，不调在线画图 API）——一条命令约 8 秒出 832×1216：角色预设（鲸鱼娘／DeepSeek 拟人、Q 版、通用少女、子午）、中文场景直出（200+ 词表，超 77 token 自动裁剪并报告裁了什么）、画风（赛璐璐／柔光／电影感／单色线稿／贴纸）、景别与画幅、批量抽卡与拼图、hires 精修、可复现种子与 PNG 内嵌提示词。含 16 项自检与 4 篇参考文档。适用于「画一张二次元图／画鲸鱼娘／生成动漫头像立绘／出表情包／给文档配二次元插图／这张图用的什么提示词／批量出同一角色多张图／要单色线稿」。不适用：只是把现成图片排进 Word／PPT／PDF → 用 `office-render`；要改 skill 的 frontmatter 写法 → 用 `dsh-skill-authoring`；要把 skill 发布到公开仓 → 用 `dsh-skills-publish`。"
whenToUse: "要生成或重画二次元图、动画风插画、角色立绘头像或表情包时用；也用于复现某张图的提示词。模型看不到本节。"
---

# anime-art · 二次元图像生成

本技能把「画二次元图」变成一条本地命令：SDXL 动漫模型 + 角色/风格/构图预设 + 中文场景转译 + 可复现种子。全程离线，不调用任何在线画图 API。

**产出物默认落在当前工作目录的 `anime-out/`**（PNG + 同名 `.json` 元数据 + 可选拼图）。

## 何时调用

**加载本 skill 当：**
- 用户说「画一张…」「生成个二次元/动漫头像」「出个表情包」「给我画鲸鱼娘」「配张插画」，或给出中文画面描述让你出图。
- 要批量出同一角色的多张候选（抽卡挑图）、要做线稿/设计稿底图、要放大精修到高清大图。
- 要问「这张图是怎么生成的 / 用的是什么提示词」，或要照某张图的风格再出一张（读 PNG 内嵌元数据 + 同 seed 复现）。

**不要用本 skill（转交）：**
- 只是把已有图片排进 Word / PPT / PDF、导出文档 → 用 `office-render` / `office-export-pdf`。
- 要改 skill 的 frontmatter、description、「何时调用」写法 → 用 `dsh-skill-authoring`。
- 要把本 skill 发布到 GitCode / GitHub 公开仓 → 用 `dsh-skills-publish`。

**前置**：运行时 `$env:DSH_HOME\venvs\anime-art` 与权重 `$env:DSH_HOME\models\anime-art` 就位（缺了先跑 `scripts\setup_runtime.ps1`，约 8GB 一次性下载）。 ／ **后继**：出图后必须用 `read_image` 亲自看图，别凭命令成功就交付（见 §6 验收红线）。

---

## 1. 最快路径（先读这段就够）

```powershell
$py = "$env:DSH_HOME\venvs\anime-art\Scripts\python.exe"
$gen = "$env:DSH_HOME\skills\anime-art\scripts\anime_gen.py"

# 出图：鲸鱼娘、雨中电车站、2 张、拼图
& $py $gen --preset whale-chan --scene "雨天的电车站，撑着伞回头看" --count 2 --grid

# 只出提示词不跑模型（秒回，用来核对 tag）
& $py $gen --scene "海边夕阳微笑" --dry-run
```

- 运行时缺失（`$py` 不存在）→ 先跑一次安装脚本（约 8GB 下载，一次性）：
  `powershell -ExecutionPolicy Bypass -File "$env:DSH_HOME\skills\anime-art\scripts\setup_runtime.ps1"`
- 生成 1 张 832×1216 / 30 步实测 **7~8 秒**（RTX 4070 Ti SUPER）；加 `--hires 1.5` 精修到 1048×1528 约再 **20~35 秒**。换显卡按算力线性估。
- **出图后必须用 `read_image` 亲眼看**（见第 6 节验收红线），不要凭"命令成功"就交付。

---

## 2. 参数速查

| 参数 | 说明 | 常用值 |
|---|---|---|
| `--preset` | 角色预设 | `whale-chan`（鲸鱼娘女仆装）·`whale-chan-chibi`（Q 版）·`anime-girl`（通用）·`whale-boy`（子午） |
| `--scene` | 中文/英文画面描述 | 「樱花树下微笑」「夜晚的天台，星空，回头」 |
| `--style` | 画风 | `anime`（默认，不加词）·`soft`·`cinematic`·`sketch`（真·单色铅笔稿）·`sticker` |
| `--composition` | 景别 | `bust`（默认）·`headshot`·`half`·`full`·`back`·`sit` |
| `--aspect` / `--size` | 画幅 | `portrait` 832×1216 ·`square` 1024×1024 ·`landscape` 1216×832 ·`portrait_tall` ·`card` ·`wide` · 或 `832x1216` |
| `--count` | 张数（种子递增） | 1~16 |
| `--seed` | 种子，-1 随机 | 复现某张图时用元数据里的 seed |
| `--steps` / `--cfg` / `--sampler` | 采样参数 | 28~32 步 / 5~7 / `euler_a`（默认）·`dpmpp_2m_karras` |
| `--hires` / `--hires-denoise` | 放大精修 | `1.5` + `0.45`（全身图建议开） |
| `--tags` | 追加 danbooru tag | `looking at viewer, wind, smile` |
| `--grid` | 出拼图 | 多张时用 |
| `--json` | 机器可读输出 | 程序化调用时用 |

完整清单：`& $py $gen --help`；预设列表：`--list-presets`；环境体检：`--doctor`。

---

## 3. 提示词机制（决定画质的关键）

管线按固定优先级拼装，**越靠前权重越高**：

```
质量词 → 评级词 → 角色核心特征 → 画风 → 用户 --tags → 场景(中文转译) → 构图 → 角色细节
```

- 质量词固定为 Animagine 官方的 `masterpiece, high score, great score, absurdres` + 评级 `safe`；负面词用官方那套（含 `bad anatomy / bad hands / watermark` 等），默认再叠一层 NSFW 过滤（`--no-safety` 可关）。
- **SDXL 文本编码器硬上限 77 token**，超出的部分会被截断。所以场景描述要"准"不要"长"：一个概念一个 tag 最好。超预算时管线从尾部裁剪并在 stderr 报告裁掉了什么——看到警告就说明该简化场景或换更小的 `--style`。
- 中文不必翻英文：`cn_tags.py` 里有 200+ 常用词（天气/地点/构图/动作/服装/光影/道具）。没有的词会以「未收录」警告列出，用 `--tags` 补 danbooru tag，或往词表里加一条。
- `(tag:1.2)` 权重语法当前不解析，会被剥掉并提示；要强调就把它写靠前。
- 画风可以声明 `drop` 列表（`presets/styles.json`）：命中的 tag 会从最终提示词里删掉。`sketch` 就靠这个把「蓝发/蓝瞳」删掉，否则模型夹在"单色"和"蓝发"之间会输出褪色彩图。

写场景的经验：
- 主体动作放前面（`回头`/`微笑`/`撑着伞`），环境放后面。
- `--composition full` 全身图脸部像素少，配 `--hires 1.5` 补细节。
- 想要"海报感"用 `--style cinematic`；想要"治愈日常"用 `--style soft`；想要线稿/立绘设计稿用 `--style sketch`。
- 同一批图尽量用同一画幅：切来切去会让 cuDNN 反复重选卷积算法，偶发明显变慢。

---

## 4. 复现与批处理

每张 PNG 内嵌 `prompt / negative_prompt / seed / steps / cfg / sampler / model / preset` 等 tEXt 字段，同名 `.json` 再存一份完整记录（含图像体检指标）。

```powershell
# 复现某一版
& $py $gen --preset whale-chan --scene "..." --seed 123456789 --hires 1.5

# 批量做 8 张候选，再挑
& $py $gen --preset whale-chan-chibi --scene "得意地吃白饭" --aspect square --count 8 --grid

# 固定种子扫风格（对比用）
foreach ($s in "anime","soft","cinematic") { & $py $gen --style $s --seed 42 --out "anime-out/style-$s" }
```

---

## 5. 常见故障

| 现象 | 处理 |
|---|---|
| `找不到模型` / `模型文件不存在` | 跑 `scripts/setup_runtime.ps1`；或把 `.safetensors` 放进 `%DSH_HOME%\models\anime-art\`；或用 `--model` 指路径 |
| `CUDA out of memory` | `--offload`（CPU offload，慢 2~3 倍）；或降画幅、关 `--hires` |
| 出图很慢（>60s/张） | 说明在跑 CPU：`--doctor` 确认 `cuda_available`；装 cu128 版 torch |
| 图是纯黑/纯白/糊成一团 | 元数据里 `blank_suspect` 会是 true；换 seed，或 `--offload`，或降 cfg |
| 手/眼崩了 | 重抽（`--count 4` 里挑）；或改 `--composition bust` 让脸占比更大；负面词加 `extra digits, fused fingers` |
| 出现文字/水印 | 负面词已含 `text, watermark, signature`；仍有就降到 `--steps 28` 重抽 |

更多见 `references/troubleshooting.md`。

---

## 6. 验收红线（每次交付前自查）

命令成功 ≠ 图能看。**必须**：

1. `read_image` 打开生成结果亲眼确认：
   - 五官/手指正常，没有多余肢体；
   - 角色特征对（鲸鱼娘：深蓝渐变长发 + 呆毛 + 鳍状耳 + 深蓝白女仆装 + 鲸尾）；
   - 没有文字、水印、签名；
   - 构图与描述一致（说"回头看"就不能是正面）。
2. 多张时用 `--grid` 拼图一次看全。
3. 不满意就调参重抽，**不要把坏图当成"生成成功"交付**。
4. 引用他人角色形象要带授权说明（见下）。

---

## 7. 角色与合规

- **鲸鱼娘**：原型「溟月」by 上善无形（CC BY-NC-SA 4.0），DeepSeek 化女仆装版本由 B 站 @ZipZipPipe 推广，现为 B 站「AI 模型娘」中受众最广的版本。**CC BY-NC-SA 4.0：署名 + 非商用 + 相同方式共享**。商用前必须换成自有形象或取得授权。
- 基座模型 Animagine XL 4.0 Opt 为 CreativeML Open RAIL++-M。
- 默认开启安全过滤，不要绕过它生成违规内容。

---

## 8. 文件地图

```
scripts/anime_gen.py        CLI 入口（生成 / dry-run / 体检）
scripts/setup_runtime.ps1   一次性搭运行时（venv + torch + 权重）
scripts/selftest.py         10 项单元测试 + 5 项集成测试
scripts/artlib/             cn_tags(中文词表) presets prompts render meta
presets/*.json              角色 / 风格 / 构图预设（可直接改）
references/                 角色设计卡、提示词手册、故障排查、验收报告
```

更深的内容按需读：`references/whale-chan-design.md`（鲸鱼娘设定与可复现提示词）、`references/prompt-cookbook.md`（提示词配方）、`references/acceptance.md`（验收记录与硬指标）。
