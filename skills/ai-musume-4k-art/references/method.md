# 方法论：把一个 B 站动画角色"锁死"并批量出图

> 这份是 `ai-musume-4k-art` 的**可复用方法**，不是本次会话的流水账。
> 适用：手上有参考视频/图，要产出"同一个人 + 同一种画风 + 任意神态"的立绘。
> 工具：`.190` 的 `MiniMax-H3-Image`（vllm-omni）+ 本 skill 的 5 个脚本。

## 一、总纲：六道锁

单靠文字 prompt 只能"像这一类角色"。要"一模一样"，必须六道锁同时上，缺一道就会漂：

| 锁 | 手段 | 不加会怎样 |
|---|---|---|
| ① 身份锁 | 同一角色 **2~3 张不同帧** 做 `--ref`（`/v1/images/edits`，上限 9 张） | 服装/道具细节随机漂移，单张参考尤其不稳 |
| ② 构图锁 | prompt 明确"保持 `<Picture 1>` 的机位/姿势"，或反过来"**彻底去掉背景**，只要角色" | 模型自由重排构图；想保留场景时不写这句必丢场景 |
| ③ 表演锁 | 明确的**收敛**措辞：闭口、不张嘴大笑、不夸张 | 出"张大嘴吼叫/夸张颜艺"，与这批角色人设不符 |
| ④ 形体锁 | 显式写脸型，**默认用已验收的「半档」**：`soft but defined jawline, chin gently rounded at the tip, light cheek fullness` | 不写会出圆脸幼态；写过头（`longer chin`）会出尖 V 下巴 |
| ⑤ 影调锁 | 生成侧写柔和平光；后处理用 **gamma** 提亮 + 可选 Lab 调色 | 偏暗；或反过来过曝冲白 |
| ⑥ 画风锁 | 默认 `--style show`；严格一致用 2~3 张 `--ref`（内置 style-lock）+ `match_style --strength 0.5~0.7` | 出"海报立绘"：大片白发高光、黑粗线、高饱和、强对比，与 480p 正片截图不是一套 |

## 二、可直接复制的模板（无背景版）

```
<Picture 1> is a frame of an anime character from a TV animation; the other pictures are other
frames of the SAME character. Reproduce her exactly as in the references: identical face shape,
identical hair style and hair colour, identical eye colour, identical headwear and hair ornaments,
identical outfit, accessories and props, identical lineart weight and flat cel shading, same pose
as <Picture 1>. Balanced adult face: oval face with a soft but defined jawline, chin gently rounded at the tip
(not pointed, not a sharp V), light cheek fullness, same face length as the reference, mature,
not childlike. Dial this ONE clause to taste: more "rounded chin / cheek fullness" = softer and
younger; more "defined jawline / longer chin" = sharper and more mature.
Restrained expression acting: mouth closed, no wide-open mouth, no shouting, no exaggerated
comedic face. Bright but not washed out: luminous even skin tone, soft warm fill light, gentle
contrast, no clipped whites, no heavy shadows. Remove the background completely: flat uniform
light neutral grey (#EDEDED) studio background only, absolutely no scenery, no courtroom, no
curtains, no railings, no furniture, no props, no floor line, no text, no watermark, no UI overlays.
The facial expression is __EXPR__.
```

要保留原场景时，把 "Remove the background…" 整段换成
`Keep <Picture 1>'s exact camera angle, pose, framing and background.`

## 三、标准流程（每张图的完整命令链）

```powershell
$py='<python>'; $S='<skill>\scripts'
# 1) 生成（4K，落 3840x2176，32 网格）
& $py $S\gen_h3.py --char claude --expr smile --size 4k --seed 901 --prompt-raw $tmpl `
   --ref ...\references\frames\claude\t00784.png `
   --ref ...\references\frames\claude\t01438.png `
   --ref ...\references\frames\claude\t01568.png --outdir out
# 2) 只提亮 + 裁 UHD（strength 0 = 不转色，避免把场景暖色带进无背景图）
& $py $S\match_style.py out\raw.png ref.png out\char_smile_4k.png --strength 0 --gamma 0.85 --crop 3840x2160
# 3) 透明底（只抠「与画面边缘连通」的底色，白衬衫不会被抠穿）
& $py $S\key_out.py out\char_smile_4k.png out\char_smile_alpha.png --tol 26 --feather 1.5
```

成本（实测）：4K 生成 **26~27 s/张**，提亮+裁剪 ~2 s，抠图 ~3 s；批量 25 张约 13 分钟。

## 四、量化闸门（别靠肉眼判断"像不像"）

| 指标 | 脚本 | 通过判据 | 实测（本系列） |
|---|---|---|---|
| 调色板距离 | `eval_match.py` | `dE_mean ≤ 8` | 1.9~3.8 ✅ |
| 对比度距离 | `eval_match.py` | `dE_std` 与参考同量级 | 1.5~2.4 ✅ |
| 亮度 | `eval_match.py` / 自写 stat | `clipped%` ≈ 0 且 `meanL` ≥ 参考 | 参考 55.5→成图 62.1，截断 0% ✅ |
| 锐度 | 拉普拉斯方差 | 成图/参考 ≈ 1（**不是**用 edge_ratio） | 漂移时 4.9×，`--soft 2.2~2.5` 可收到 0.87~0.97 |

## 五、踩过的坑（照着避）

1. **`--target-l` 把图冲白**：把 Lab 的 L 均值硬拉到目标值，L 上限 100，等于削平高光。**提亮一律用 `--gamma`**（sRGB 幂函数，提中间调、不削高光）。
2. **`edge_ratio` 是错指标**：它测的是"画面内容复杂度"（道具/刺绣/帷幕越多越高），不是锐度。软化解扫 1.0→3.5 它纹丝不动（1.78→1.80）。**锐度用原分辨率拉普拉斯方差**。
3. **单张参考不稳**：同一角色 1 张 vs 3 张，服装细节与道具稳定性差别明显，**统一用 3 张**。
4. **"保留背景"和"去掉背景"是互斥指令**，模板里必须二选一，否则模型两边各做一半。
5. **按颜色距离抠图会抠穿白衣服**：必须用"从画面边缘做连通域 BFS"的版本（`key_out.py` 已实现）；底色用中性灰比暖白好，因为白衬衫与暖白贴色。
6. **弹幕峰值不能用来定位角色**：五个角色被同时讨论，峰值全挤在同样时间点（实测五个角色的 top 时间几乎重合）。
7. **发色 HSV 分类器不可靠**：正面锚点自测 1/12。别用它自动打标，**用人眼在总览图上逐格标注**。
8. **4K 必须落 32 网格**：3840×2160 的 2160 不是 32 的倍数 → 生成 `3840×2176`，收图后 `--crop 3840x2160`。
9. **UI 会进图**：参考帧左下角有角色名标签、底部有对话气泡，模板里必须写 `no text, no name plates, no UI overlays`。

## 六、参考帧的获取与核验（"别认错人"的唯一可靠办法）

1. `bili_frames.py` 拉正片（playurl → imageio-ffmpeg 抽帧，1 fps）。
2. **每 30 秒取一帧拼总览图**，人眼把角色的出镜区间标出来（这一步不能自动化）。
3. 按标注时间裁切（固定机位：`x 0.30~0.68, y 0.02~0.87`），2× LANCZOS 放大。
4. **再拼一张"逐格校验图"人工复核**——本轮就靠它剔掉了 16 张错标（把牢大/别的角色混进来）。
5. 存档目录 `references/frames/<char>/tNNNNN.png`，**文件名数字 = 视频秒数**，永远可回原片对帧。

## 七、服务运维（共享机必须知道）

- 看护：`supervise_h3.sh`，进程被杀后 10 s 重启、60~70 s 就绪（实测 04:19、07:16 各被杀一次，均自愈）。
- 批量前先探活：`curl -s -o /dev/null -w "%{http_code}" http://192.168.13.190:18080/v1/models`。
- 单次前台工具调用有 10 分钟上限，**批量务必分段**（每段 ≤20 张）或让脚本转后台任务。

## 八、决策记录（已定稿，别反复推翻）

2026-11-11 与用户逐轮比对后定稿，后续直接沿用；要改先看这张表，别从零再试一遍。

| 维度 | 定稿 | 被否决的做法 | 否决原因 |
|---|---|---|---|
| **脸型** | **半档**：`soft but defined jawline, chin gently rounded at the tip, light cheek fullness` | ① `defined jawline + slightly longer chin` ② `gently rounded chin + natural cheek fullness` | ①下巴过尖成 V，脸被拉长；②一直圆到尖部，少女化、与原片成熟感不符。半档经用户确认「刚刚好」 |
| 表情 | 12 档**闭口收敛**（`soft_laugh` 取代 `laugh`） | 张嘴大笑 / 夸张颜艺 | 这批角色人设不会张嘴大笑 |
| 提亮 | `match_style --gamma 0.85~0.9` | `--target-l` 硬拉 L 均值 | L 上限 100，硬拉等于削平高光，实测把图冲成惨白 |
| 锐度 | 拉普拉斯方差比 ≈1，`--soft 2.2~2.5` | `eval_match.py` 的 `edge_ratio` | 它测的是画面内容复杂度，软化解扫 1.0→3.5 纹丝不动（1.78→1.80） |
| 背景 | 立绘默认**彻底去背景**（`#EDEDED` 平涂 + `key_out.py` 透明底） | 保留原片法庭场景 | 用户明确要求只要角色 |
| 抠图 | 边缘连通域 BFS + 颜色容差 | 单纯按颜色距离抠 | 会把她/他的白衬衫一起抠穿 |
| **画风** | **正片广播截图风**：`--style show` + 参考帧 style-lock | `anime` 默认档（key visual：玻璃高光/强对比/黑粗线） | 与用户指定的正片画风不一致（2026-11-11 用户指出） |
| 角色范围 | 五位（Claude/DeepSeek/GPT/Grok/Gemini） | 豆姐（千问） | 她是 3D 主持、无正片立绘，用户要求从 skill 删除 |
