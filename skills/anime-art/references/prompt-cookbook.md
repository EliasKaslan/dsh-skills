# 提示词手册（anime-art）

## 1. 只有 77 个 token

SDXL 的两个文本编码器各自只吃 77 个 CLIP token（含首尾标记），超出的部分**直接丢弃**。这就是为什么：
- 管线会按优先级拼装，超预算时从尾部裁剪并报出裁掉了什么；
- 角色核心特征永远排在最前，场景/画风排在中间，角色细节排在最后。

一个 tag 通常占 1~3 token。经验值：**一条好提示词 ≈ 20~30 个 tag**。
另外**每个 `", "` 分隔符本身约 1 token**：`--max-tokens 77` 里还有首尾特殊标记，实际只有约 75 个内容 token，
27 个 tag 大约要吃掉 26 个分隔符 —— 这就是"26 个 tag 就顶到上限"的原因。

## 2. 优先级顺序（管线内置）

```
质量词(4) → 评级 safe(1) → 角色核心(8~12) → 用户 --tags → 场景转译 → 构图(2) → 画风(1~4) → 角色细节(4~8)
```

- 想让某个元素更强：把它写进 `--tags`（排位比场景词更靠前）。
- 想省 token：`--scene` 里一个概念只写一次，别堆近义词。

## 3. 各档参数

| 目标 | 参数 |
|---|---|
| 稳定可交付 | `--steps 30 --cfg 6 --sampler euler_a`（默认） |
| 更锐利细节 | `--sampler dpmpp_2m_karras --steps 32` |
| 更"演出感" | `--style cinematic --aspect landscape` |
| 头像/表情包 | `--aspect square --style sticker --composition bust` |
| 全身立绘 | `--composition full --hires 1.5 --hires-denoise 0.45` |
| 线稿 | `--style sketch`（预设里带 `drop`，会自动剔掉蓝发蓝瞳等颜色词） |

> **步数是质量红线**：28~32 步是甜区；12 步会出"拼贴怪图"（多张脸糊在一起），不要用低步数出最终图，低步数只适合验证流程是否跑通。
> CFG 超过 8 会让动漫模型出现"高对比死黑"；低于 4.5 会糊。5~7 是甜区。

## 4. 场景配方（已按预算裁剪）

| 需求 | `--scene` |
|---|---|
| 日常校园 | `教室窗边，微笑，阳光` |
| 夏日海边 | `海边，泳装，风吹头发` |
| 雨中街景 | `下雨，街道，撑着伞，回头看` |
| 夜樱 | `夜晚，樱花飘落，灯笼` |
| 咖啡店 | `咖啡馆，托腮，喝咖啡` |
| 雪国 | `下雪，积雪，围巾，微笑` |
| 赛博都市 | `赛博朋克，霓虹灯，夜晚，街道` |
| 神社参拜 | `神社，鸟居，和服，双手合十` |
| 星空天台 | `天台，星空，回头` |
| 打游戏 | `房间，打游戏，得意` |
| 夜间打游戏 | `--style gaming-night --composition half --tags "holding controller, looking at viewer, smile, sitting, maid headdress"` |
| 生日 | `蛋糕，蜡烛，微笑` |
| 樱花雨 | `樱花飘落，伸手，微笑` |

需要更精细的控制时，直接用 danbooru tag：`--tags "looking at viewer, wind, dutch angle"`。

## 5. 负面词

默认（Animagine 官方 + 安全过滤）：

```
lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits,
cropped, worst quality, low quality, low score, bad score, average score, signature,
watermark, username, blurry, nsfw, explicit, nude, nipple, cleavage
```

- 出现"多手/融合手指"：`--negative-extra "extra arms, fused fingers, mutated hands"`
- 出现文字：`--negative-extra "text, kanji, logo"`
- 想要纯背景贴纸：`--style sticker`（自带 `complex background` 负面）

## 6. 排查「图不对」的固定动作

1. `--dry-run` 看实际提示词，确认关键 tag 没被裁。
2. 看 stderr 有没有「裁剪」「未收录」警告。
3. `--count 4 --grid` 一次出 4 张再挑，单张失败率比想象中高。
4. 脸部崩 → 换 `bust` 构图，或 `--hires 1.5`。
5. 还是不行 → 换 seed（同提示词不同 seed 差异很大）。

## 7. 实战配方：夜间打游戏（2026-11 实测）

目标画面：鲸鱼娘深夜坐在电脑前、双手握手柄、屏幕光打在脸和头发上。

**能直接跑的命令**（已逐 tag 验过 token）：

```powershell
& $py $gen --preset whale-chan --style gaming-night --composition half `
  --tags "holding controller, looking at viewer, smile, sitting, maid headdress" `
  --max-tokens 77 --aspect portrait --steps 32 --sampler dpmpp_2m_karras `
  --count 10 --grid --out anime-out\gaming-night
# 挑好后同一 seed 精修：
& $py $gen ... --seed 804199322 --hires 1.5 --hires-denoise 0.38 --hires-max-mp 2.3
```

这张图踩出来的六条规律，换任何「室内夜景 + 道具」场景都适用：

1. **`--style gaming-night` 解决打光，`--tags` 解决动作。** 夜景不是靠 `night` 一个词，
   而是「night + dark room + computer monitor + bloom + rim lighting」五件套一次给全；
   这套放进领域预设后不会被裁（style 层优先级高于场景/构图/细节层）。
2. **道具要点名，不能指望 `打游戏` 一个词。** 只说 `房间，打游戏` 时模型常给"坐在桌前笑"，
   桌面是空的。必须补 `computer monitor` / `keyboard` / `game controller`。
3. **分隔符也算 token。** CLIP 里每个 `", "` 约 1 token，所以 75 个内容 token ≈ 27 个 tag。
   预算紧张时"少一个 tag" 比"把 tag 写短"更省。
4. **`--tags` 是唯一能保住角色的地方。** detail 层（`whale tail / maid headdress / hair bow`）
   永远最先被裁——实测不加干预时**女仆头饰会整条消失**，看起来就不像那只女仆鲸。想保住就写进 `--tags`。
5. **`--composition half` 比 `sit` 稳。** `sit` 的 `sitting` 常被裁掉导致站着；把 `sitting`
   写进 `--tags`（高优先级）+ `half`（cowboy shot）更可靠。
6. **冷暖对撞最容易"精致"。** 桌面暖台灯 + 屏幕冷蓝 = 立刻有电影感；纯冷色会显得平。
   加 `desk lamp`（中文 `台灯`）就是这条。

已验证的入手点（同一 seed 可复现，1248×1824）：

| seed | 特点 |
|---|---|
| 804199322 | 正面、双鳍耳、双手握手柄、构图最稳（推荐作主图） |
| 873287625 | 回眸、鳍耳发光、键盘辉光，最有氛围 |
| 1666422308 | 暖台灯 + 冷屏幕，冷暖对撞最强 |
| 1851811044 | 城市夜景窗、发梢飘动，脸最好看 |

> 手部仍是概率问题：约 1/3 的种子会把手指和手柄糊在一起。用 `--count 8~10 --grid` 一次抽够，
> 挑"手柄握持关系清楚"的那张再精修；`--negative-extra "fused fingers, mutated hands"` 有帮助但救不回来。
