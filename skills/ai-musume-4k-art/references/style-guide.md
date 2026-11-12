# 画风对齐指南（对标《牢大百科》AI 娘立绘）

## 0. 目标画风口径（以用户确认的官方立绘为准）

**先记住结论：目标是「细而柔的线 + 平滑渐变上色 + 发丝渐变 + 大而精细的眼睛」，不是「粗描边 + 平涂」。**

| 维度 | 目标 | 反面（实测被否掉的） |
|---|---|---|
| 线 | 细、柔、有色（深蓝/棕），存在感低 | 粗黑描边、`bold lineart` |
| 上色 | 平滑渐变 + 柔和阴影，头发深→浅渐变到发梢 | 硬边平涂、`flat color, cel shading` |
| 眼睛 | 大、渐变虹膜、多个高光点、睫毛清晰 | 环形高光/玻璃球；也不要 `big eyes` 这种比例词 |
| 头发 | 整块 + 细发丝 + 纵向渐变 | 逐根发丝、`hair highlight band` 硬高光带 |
| 整体 | 暖、通透、完成度高 | 发灰、发闷、chibi |

正向（`refine` 预设）：`soft shading, gradient hair, detailed eyes, clean lineart, anime coloring, soft lighting`
负向：`flat color, bold lineart, thick outline, sketchy, rough lines, posterized, oversaturated, low detail`

### 0.1 血证：别拿压缩视频帧去"量化"画风

曾经对 960×540 的抽帧做像素统计（线宽、近黑线占比、平坦度、饱和度），得出「目标是粗线、少线、低平涂、高饱和」的结论，并按此重做了一版——**被用户直接否掉（"更差了"）**。

原因是测量口径有偏：视频压缩会把线糊粗、把细线糊没、把高光糊平、把饱和度拉低；抽帧分辨率又远低于立绘原生分辨率。**用这种素材统计出来的"风格数值"，测的是编码器，不是画风。**

做法上的修正：
- 判画风**只能用官方高清立绘**（封面单体裁切 / 官方设定图），并**以人眼确认为准**；
- 数值统计只能当辅助，且必须先确认素材分辨率与压缩比接近目标；差异超过 2 倍就不要拿它下结论；
- 用户给了一张参考图并说"严格按这个"时，**那张图就是唯一判据**，不要再用自己攒的素材去覆盖它。

## 0.6 2026-11-10 参考图实测（**现行口径，以本节为准**）

用户给的参考图：303×246，鲸鱼娘（DeepSeek 女仆），木质+金饰内景，胸像。量化结果：

| 维度 | 实测 | 落成的 tag |
|---|---|---|
| 发色 | `#476599` `#385589` `#5D81AC`——**中低饱和雾霾蓝** | `dark blue hair` + `gradient hair` |
| 深色 | `#423C3E` 暖炭黑 | `navy blue dress` |
| 白 | `#EDE0D6` `#FBF0E6` 暖米白 | `white ruffled blouse` |
| 金 | `#AB7F3B` `#E8B963` | `wooden wall`（背景） |
| 线 | 细、深蓝灰、有色 | `delicate lineart` |
| 眼 | 大、纵向渐变、3+ 高光 | `detailed eyes` |

**现行画风档 `keyvisual`**：`official art, key visual, soft shading, detailed eyes, delicate lineart`
负向：`flat color, bold lineart, thick outline, sketchy, posterized, oversaturated, neon colors, vivid colors, low detail`

在同一台机（.190 + illustrious-xl）上跑出来的对照结论：

| 尝试 | 结论 |
|---|---|
| 默认 `flat`（旧默认） | ❌ 挂历海报感，最差 |
| `clean lineart` | 线条偏硬 → 换 `delicate lineart` |
| `muted colors` | 能出雾霾蓝，但**把藏青裙一起洗成浅蓝**→ 单独成档 `keyvisual4`，默认不开 |
| `pastel colors` | ❌ 发灰、皮肤发白 |
| 画风词里再写一遍 `gradient hair` | ❌ 发色漂成紫/青；core 里已有就别重复 |
| `cel shading` / `bold lineart` / `flat color` | ❌ 一律进负向词 |
| IP-Adapter 拿参考图做风格锚 | ❌ 背景彩虹竖条纹，比旧记录更明显 |
| `--hires-denoise 0.40` | ❌ 颜色崩坏；`0.25~0.30` 才干净 |

**仍然对不上的**（别声称"完全一致"）：发色深浅、荷叶边的逐褶细节、脸/身材比例。这三项靠提示词到头了，要再进一步只能自训 LoRA 或换底模（见 SKILL.md §12.3）。


## 1. 目标画风长什么样（旧版直觉描述，已被 §0 / §0.6 修正，保留作对照）

> ⚠️ 本节写于还没有实测之前，**关于线条粗细与饱和度的判断是错的**（实测见 §0）。其余（眼睛、头发、整体的质感判断）仍然成立。

参考素材是 BV14C456WEXN 的**正片立绘**（不是封面海报）。两者不是一回事，别抄错：

| 维度 | 正片立绘（目标） | 封面海报（不要照抄） |
|---|---|---|
| 线条 | 粗、少、**有色**（棕/深蓝），收笔干净 | 细碎黑线、海报感 |
| 上色 | 扁平赛璐璐 + 两段阴影（可有网点质感） | 厚涂、强反光 |
| 眼睛 | 大眼、**平渐变**虹膜 + 深色虹膜环 + 2 高光 | 环形高光、"玻璃球" |
| 头发 | 整块 + **高光带**，不要逐根发丝 | 丝带感强反光 |
| 整体 | 暖、饱和、留白干净 | 拼贴感 |

## 2. 提示词公式（**已按 2026-11-10 重写**，见 SKILL.md §4）

```
质量词 → 身份核心(core) → 构图 → 画风 → 服装细节(detail)
```

- 质量词：Illustrious/NoobAI → `masterpiece, best quality, absurdres, safe, 1girl, solo`
- 身份核心：能认出是谁的那几条（发色/发长/瞳色/呆毛/头饰），**排在画风之前**
- 景别：`upper body` / `cowboy shot` / `full body`；神态：`gentle smile` / `smirk` / `expressionless`
- 画风：见 §0.6 的 `keyvisual`（**不要**再用 `colored lineart, bold lineart, flat color, cel shading` 这一串）
- 服装细节：荷叶边、领结、胸针这类，**排在最后**，预算不够先丢它们

**SDXL 文本编码器硬上限 77 token**。旧实现是「整块丢弃」，结果画风词被整条扔掉、几个预设渲染出同一张图。`gen.py` 现在用 `build_prompt()` **按词贪心装入**，并按上面的优先级排序；`skipped:` 里出现 `style:` 就是画风被挤掉了，要减词而不是加词。

**负向词也受同一个 77 墙**：旧实现拼了 147 token，CLIP 只吃前 77、尾部静默失效。现在 `NEG_CORE + STYLE_NEG` 实测 66 token，日志里紧跟一行 `negative tokens=`。

## 3. 反面清单（实拍踩过的坑，别重走）

| 写法 | 后果（实测） |
|---|---|
| `cel shading, flat colors, thick outlines, high saturation` | 被压成挂历式海报、色块断裂、眼睛失去渐层。**2026-11-10 在 Illustrious 上复测，`flat` 这一档仍然是最差的一档**（旧版此处写"换 Illustrious 后反而正确"，已证伪） |
| `vibrant colors, glossy hair, sharp focus` 三连 | 白毛/金毛角色出现霓虹紫粉"故障色"块（GPT、Grok、Qwen 三连中招），换 seed 不消失 |
| 负面词保留 `pastel, watercolor, soft focus` | 与目标画风冲突；这三个词已从默认负面词里删掉 |
| 只写 `horn` | 白毛角的 GPT 会被画成黑角恶魔 → 写 `white horn` |
| 场景写太长 | 77 token 挤掉画风词，风格立刻跑偏 |
| 用 IP-Adapter 补画风（.190 链路） | latent 被打崩，出竖条纹/拖影，换采样器也没用 → 只能靠提示词 |
| 不写脸型/年龄 | 六个角色统一变成「大眼圆脸」→ 显式写 `mature female` / `big eyes` / `cute` |

## 4. 采样参数

| 参数 | 值 | 说明 |
|---|---|---|
| sampler | `euler_a`（diffusers 默认 EulerAncestral） | 稳定，适合抽卡 |
| steps | 30（抽卡）/ 32（终稿） | 低于 24 细节明显掉 |
| cfg | 5.2 | 6.0 以上容易过饱和、出霓虹边 |
| 分辨率 | **1216×1024（横构图胸像，对齐参考图 1.23:1）**；竖图 896×1344 | Illustrious 在 1.2MP 附近最稳 |
| 种子 | 整数可复现 | 同一 seed + 同一 prompt + 同一尺寸 = 同图 |

## 5. 怎么判"像不像"

出图后**必须** `read_image` 亲眼看，并按下面四条打分（任一不过就重抽）：

1. **发色/发型**：色相与长度对不对（Claude 橙、DeepSeek 蓝渐变、GPT 银白、Grok 金、Gemini 紫、Qwen 黑）。
2. **瞳色**：Gemini 是否一粉一黄；GPT 是否紫瞳；DeepSeek 是否蓝瞳。
3. **头饰/服装锚点**：Claude 花饰 + 黑缎带；DeepSeek **女仆头饰 + 藏青裙 + 白荷叶边上衣 + 蓝宝石领结**（不是围裙）；GPT 白角 + 白礼服；Grok 蝙蝠翼 + 王冠；Gemini 星星 + 双马尾；Qwen 三七分波波头 + 黑上衣。
4. **画风**（2026-11-10 改口径）：线条**细而柔、有色但不抢眼**；上色是柔和渐变的软赛璐璐（不是硬边两段平涂）；虹膜有纵向渐变 + 多个高光点；整体低饱和偏暖；没有霓虹故障色、没有 3D/写实感、没有文字水印。
5. **主色板**（对参考图任务）：发色是不是 `#476599` 这一档的雾霾蓝、裙子是不是藏青、白是不是暖米白。

> 判「像不像」用**联系表看整体 + 100% 裁切看线**，不要逐张读大图（见 SKILL.md §8.1 的字节预算）。
