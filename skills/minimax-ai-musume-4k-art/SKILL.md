---
name: minimax-ai-musume-4k-art
description: 用 MiniMax-H3-Image 在昇腾 192.168.13.190 出 AI 娘插画（1696×2528 六步约 8 秒，4 die）——五位 AI 娘（Claude／DeepSeek／GPT／Grok／Gemini）的形象已按 B站 BV14C456WEXN 原分辨率逐项核对固化（含 DeepSeek 的鲸鱼鳍耳），画风默认正片广播 show 档，支持 12 种神态、5 档画风、参考图锁人、批量抽卡与一致性验收。适用于「用 MiniMax 生图」「画一张AI娘」「画鲸鱼娘」「画Grok娘」「出AI娘表情包或头像」「按参考图对齐画风」「要正片那种画风」。不适用：要用 Anima 底模 + AI 娘 LoRA → 用 anima-ai-musume-lora；只改 skill 的 frontmatter → 用 dsh-skill-authoring；装 CANN 或 vLLM → 用 ascend-env。
disable-model-invocation: true
warm-triggers: MiniMax-H3 出 AI 娘 / 五位 AI 娘形象 / 画风档位
warm-reason: 兴趣生图，低频
---

# minimax-ai-musume-4k-art · AI 娘插画（MiniMax-H3-Image on Ascend）

**与 Anima 的分工**：要 LoRA 定制 / 单卡 / 低成本批量抽卡 → 用 `anima-ai-musume-lora`（Anima + ComfyUI，单 die，Turbo 4.5 秒）；要正片广播画风 / 4K / 参考图锁人 → 留在这里。

**唯一模型**：`MiniMax-H3-Image`（33.1B DiT + Qwen3-VL 文本编码 + 图像 VAE），跑在 `192.168.13.190` 的 vllm-omni 服务上，OpenAI 兼容 `POST /v1/images/generations`。

**不要再用** Qwen-Image / SDXL / diffusers 本地管线——那几条链路已从本 skill 移除。

## 1. 最快路径

```powershell
# 出一张（默认 show 正片画风、胸像、1696x2528、约 5.4 秒）
python C:\Users\admin\.dsh\skills\minimax-ai-musume-4k-art\scripts\gen_h3.py --char deepseek --expr smile --seed 101

# 换神态 / 换画风 / 换构图
... --expr laugh --style cel --framing half
... --expr shy --scene "standing under a streetlight at night, warm rim light"

# 批量抽卡（同 prompt 多 seed，一次出 4 张）
... --seeds 11,22,33,44 --tag pick

# 把结果拼成联系表（验收用，别直接读大图）
python ...\scripts\sheet.py out.jpg 3 500 "glob:D:\...\*.png"
```

- 输出目录默认 `D:\workspace\261108_recreation\out\musume`，可用 `--outdir` 或环境变量 `H3_OUTDIR` 改。
- 服务地址用 `H3_ENDPOINT` 覆盖（默认 `http://192.168.13.190:18080`）。
- `--dry-run` 只打印最终 prompt，不出图——改提示词时先用它。

## 2. 提示词怎么写（和 SDXL/Qwen 完全不同）

H3-Image 吃**自然语言整段描述**，不吃 danbooru tag 串；`gen_h3.py` 已按四段拼接：

```
画风档（必须显式声明二维动画，否则出真人）
+ 动画比例（大眼/圆脸/细颈，不加会出写实成人脸）
+ 角色卡（发色/瞳色/头饰/服装，见 references/character-cards.md）
+ 神态 + 构图 + 背景 + 单人不串味
```

三条硬规则：

1. **不能写负面提示词**。服务端对 `negative_prompt` 直接返回 HTTP 400；`guidance_scale` 只能是 1、`num_inference_steps` 只能是 6（其它值 400）。要"排除"什么，就用正向措辞（`Not a photograph, no photorealistic skin, no 3D render`）。
2. **画风档不能省**。H3 摄影倾向很强，只写角色会出真人写真；**本系列默认 `show`**（正片广播截图风：细藏青线 + 平涂哑光，见第 3 节）。`anime` 是海报立绘风（高光成片、对比更强），只在做二创海报时用；`cel` 更硬朗、`soft` 偏轻小说封面、`retro` 是 90 年代赛璐璐。
3. **一图一人**。橙发与蓝发同框必串色；要多人同框就分开出图再拼。

## 2.5 参考图模式（要"和正片一模一样"就走这条，默认推荐）

纯文字 prompt 只能"像这一类角色"；**要把人锁死，必须给参考图**。`references/frames/<char>/` 里是正片真帧
（文件名数字 = 视频秒数），`--ref` 走 `/v1/images/edits`（最多 9 张）。

**三道锁**（缺一味就会跑偏）：

1. **身份锁**：同一角色给 **2~3 张不同帧**做参考，比单张稳得多。
2. **构图锁**：prompt 里明确"保持 `<Picture 1>` 的机位/姿势/构图/背景"，只改表情——否则模型会重排画面。
3. **色调锁**：H3 一定会比 480p 动画帧更"干净油亮"，出图后用 `match_style.py` 把调色板拉回参考帧（Reinhard Lab 匹配）。

> `--ref` 的**内置模板已带 style-lock**（细藏青线 / 平涂哑光 / 禁玻璃高光 / 小高光单点），日常直接 `--ref` 三张 + `--expr` 即可；下面这段是想要更强控制时的 `--prompt-raw` 写法。

```powershell
$p = @'
<Picture 1> is a frame of an anime character from a TV animation; the other pictures are other frames
of the SAME character. Reproduce her exactly as in the references: identical face shape, identical
hair style and hair colour, identical eye colour, identical headwear and hair ornaments, identical
outfit, accessories and props, identical lineart weight and flat cel shading. Keep <Picture 1>'s exact
camera angle, pose, framing and background. Change ONLY the facial expression to __EXPR__.
No extra decorations, no text, no watermark, no UI overlays.
'@
python ...\scripts\gen_h3.py --char claude --expr laugh --size 2752x1568 --seed 777 `
  --ref ...\references\frames\claude\t00784.png `
  --ref ...\references\frames\claude\t01438.png `
  --ref ...\references\frames\claude\t01568.png --prompt-raw $p --outdir out
python ...\scripts\match_style.py out\xx.png ...\references\frames\claude\t00784.png out\xx_styled.png
```

- 走参考图时耗时约 **15~28 秒/张**（多一遍 VAE 编码），纯文生图是 5.4 秒。
- 背景里有名字标签/气泡的帧也能用，但要在 prompt 里写 `no text, no name plates`。
- `--prompt-raw` 会**完全替换**内置模板（想手写整段时用）；`--dry-run` 先看最终 prompt。



## 3. 画风档（`--style`，默认 `show`）

| 档 | 观感 | 适用 |
|---|---|---|
| `show`（默认） | **正片广播截图风**：细藏青线、平涂哑光、低饱和、单点小高光 | 这五位 AI 娘的标准交付；要"和 BV14C456WEXN 一模一样"就用它 |
| `anime` | 现代 TV 动画 key visual、黑线条 + 三色赛璐璐、发丝高光成片 | 二创海报/头像（**不是正片画风**，会被判"画风不一致"） |
| `cel` | 更硬的墨线、平涂 | 想要"动画截图感"但更硬朗 |
| `soft` | 细线、渐变、偏亮偏白 | 轻小说封面、柔光 |
| `retro` | 90 年代手绘赛璐璐、颗粒感 | 复古风、做旧 |

**正片画风的六条硬指标**（对照 `references/frames/*/` 看，别凭印象）：

1. 线：**细、均匀、深藏青**（不是纯黑粗线），转角圆润。
2. 发：深蓝到青蓝的**发梢渐变**；高光只有几根**细浅线**，绝不出现大片白色镜面高光。
3. 色：**低饱和哑光**，皮肤是奶白不是橘黄，没有 HDR/塑料感。
4. 眼：大而圆，虹膜径向渐变（外深内亮），**通常一个小高光**。
5. 光：**平光**，无镜头光斑、无强轮廓光、无景深散景。
6. 质感：广播截图有轻微柔化，**不要锐化到 4K 商业插画**；需要时 `match_style.py --soft 1.1~1.3`。

> 只用文字 prompt 时 `show` 档能贴近到"像是这一部动画"，但发丝高光仍可能偏亮；**要严格一致必须走 2.5 的参考图模式**（`--ref` 会带上 style-lock 模板）。

## 4. 神态（12 档，`--expr`）

`neutral` 平静 / `smile` 微笑 / `soft_laugh` 轻微笑出声 / `shy` 害羞 / `pout` 微嘟嘴 / `surprised` 微惊讶 /
`sleepy` 困倦 / `wink` 眨眼 / `sad` 委屈 / `tease` 挑逗坏笑 / `serious` 认真 / `awe` 惊叹

> 全部神态都是**收敛表演**：闭口、不张嘴大笑、不夸张。角色设定上不会出现张大嘴的表情。

## 5. 尺寸（必须 32 的倍数，且 ≥4 MP，否则服务端会先放大画布再缩回）

| `--size` | 像素 | 场景 |
|---|---|---|
| `portrait`（默认） | 1696×2528 | 立绘/半身 |
| `square` | 2048×2048 | 方图、头像 |
| `landscape` | 2528×1696 | 横构图 |
| `wide` | 2688×1536 | 16:9 |
| `big` | 3072×3072 | 4K 级细节 |
| `4k` | 3840×2176 → 裁 3840×2160 | **交付默认：4K UHD** |

## 6. 验收红线（每次交付前逐条过）

1. **身份四项**：发色、瞳色、头饰、主色板——四项必须同时对上 `references/character-cards.md`。
2. **易错点专查**：
   - **DeepSeek 的鲸鱼鳍耳**：两侧太阳穴各一只**藏青蓝鳍状大耳**，向外横展并耷拉到下颌旁，下缘有**窄白荷叶边**，鳍根各一个小浅蓝蝴蝶结。画成"蓝色发带/蝴蝶结"、只有白色羽片没有蓝鳍、或两只鳍竖成兔耳 = 错。
   - Grok 的冠必须是**金冠嵌黑宝石**（出黑冠 = 错）；有没有**长尖精灵耳**。
   - GPT 的角必须是**大号象牙白羊角**（出小圆环 = 错）；瞳是**紫**不是蓝。
   - Gemini 是**蓝紫**发不是纯紫；异色瞳 **viewer 左粉、右金**，出镜像要重抽。
   - Claude 的雏菊在 **viewer 右侧**；豆姐必须是**深棕波波头**，不能画成紫发或长发。
3. **画风**：有没有退回写真/3D 渲染；**有没有变成海报立绘**（大片白色发丝高光、黑粗线、高饱和、强对比）；对照 `references/frames/<char>/` 的线宽与哑光感逐项比。
4. **构图**：脸在上三分之一、胸像不被裁掉五官。
5. 不满意就换 seed 重抽（`--seeds` 一次多抽），**不要把坏图当交付**。

## 7. 故障排查

| 现象 | 原因 / 修法 |
|---|---|
| `cannot reach http://192.168.13.190:18080` | 服务被杀了（共享机上会被别人 pkill）。**先确认容器没停在 `Exited`**，再起看护进程，见 §11；约 1 分钟就绪 |
| `HTTP 400` 且提到 `negative_prompt` / `num_inference_steps` / `guidance_scale` | 传了不支持的参数，删掉即可 |
| `HTTP 400` 且提到 `size` | 边不是 32 的倍数，或面积 <4 MP 且没传 `min_generation_area` |
| 出图是真人照片 | 画风档被截断或没写 `Not a photograph`，用 `--dry-run` 看最终 prompt |
| 出图变成"海报立绘"（大片白发高光/黑粗线/高饱和） | 用错档：改 `--style show`；严格一致就走 `--ref` 三张参考帧（内置 style-lock） |
| DeepSeek 的鳍耳画成兔耳/蓝发带/纯白羽片 | 角色卡被旧版本覆盖或描述被截断；`--dry-run` 确认有 `navy-blue whale-flipper ear` + `narrow white ruffled trim` + `at each temple` |
| 参考图模式仍出玻璃高光 | `--prompt-raw` 把内置 style-lock 覆盖了；去掉 raw，或把 style-lock 那段抄进自定义模板 |
| 全企业务慢成分钟级 | 4 个 die 被别人占了，`npu-smi info` 看 Process 段；本服务用 NPU 0–3 |
| 连接超时但端口通 | VPN 掉了，见 `ascend-server-access` |

## 8. 文件地图

```
scripts/gen_h3.py            ★唯一入口：拼 prompt + 调 HTTP（文生图 / --ref / --prompt-raw）+ 存 PNG/JSON
scripts/match_style.py       后处理：Lab 调色匹配、--gamma 提亮、--soft 柔化、--crop 裁 UHD
scripts/key_out.py           透明底：只抠与画面边缘连通的底色（白衣服不会被抠穿）
scripts/eval_match.py        量化验收：dE_mean / dE_std / 饱和度 / 亮度 / 锐度
scripts/sheet.py             联系表 + 每张图 sha256（验收必用，别直接读 12MB 大图）
scripts/bili_frames.py       可选：从 B 站视频抽真帧（需 numpy/PIL/imageio-ffmpeg）
references/character-cards.md ★五位 AI 娘的唯一设定源（身份速查 + 逐项细节 + 错法）
references/method.md         ★方法论：六道锁、可复制模板、量化闸门、九个坑、参考帧核验流程
references/frames/<char>/    ★正片存档帧，文件名数字=视频秒数
```

`gen_h3.py` 里的 `CHARS` / `EXPRS` / `STYLES` / `FRAMING` 是**唯一真相**；本文件只做说明，不要在别处再抄一份角色描述（历史上 `presets/characters.json` 就是这样漂移掉的）。

> `scripts/` 下还留着 Qwen/SDXL 时代的旧脚本（`gen_qwen.py`、`gen.py`、`run_qwen.sh`、`setup_qwen_runtime.sh`、`patch_qwen_rotary.py` 等）。它们已被 `DSH-Guard` 的 `skills` 哨兵保护，删掉会被自动还原（设计如此，别去硬删）。**一律不要调用**——新流程只认 `gen_h3.py` 与 `sheet.py`。

## 8.5 方法论（完整版见 `references/method.md`）

要"和参考图一模一样"，靠**六道锁**，缺一道就漂：身份（同角色 2~3 张 `--ref`）+ 构图（保住机位/姿势，或改成"彻底去背景"）+
表演（闭口收敛，不张嘴大笑）+ 形体（**默认半档脸型**：`soft but defined jawline, chin gently rounded at the tip, light cheek fullness`，别写成尖 V 也别写成少女圆）+
**画风（默认 `show` 正片广播截图风：细藏青线、平涂哑光、单点小高光；禁止玻璃高光/海报对比）** + 影调（生成侧柔和平光，后处理 `--gamma` 提亮）。

标准三步链：

```powershell
gen_h3.py --size 4k --prompt-raw $tmpl --ref 帧1 --ref 帧2 --ref 帧3   # 3840x2176
match_style.py raw.png ref.png out_4k.png --strength 0 --gamma 0.85 --crop 3840x2160
key_out.py out_4k.png out_alpha.png --tol 26 --feather 1.5               # 只抠边缘连通底色
```

**量化验收**（别靠肉眼）：`dE_mean ≤ 8`（调色板）、`clipped% ≈ 0`（亮度）、拉普拉斯方差比 ≈1（锐度，不要用 edge_ratio）。

三个已经踩出结论的坑：`--target-l` 会把图冲白（提亮只用 `--gamma`）；`edge_ratio` 测的是画面复杂度不是锐度；
按颜色距离抠图会抠穿白衣服（必须走边缘连通域）。其余坑与"参考帧获取 + 逐格复核"流程见 `references/method.md`。

## 9. 服务端（一次性了解，日常不用改）

- 模型权重 `/home/vllm/h3img/MiniMax-H3-Image` + `MiniMax-H3/text_encoder`（126 GB）
- 容器 `h3`，镜像 `quay.io/ascend/vllm-omni:nightly-20261111-2869e5c-a3`（vLLM 0.33.0 / torch_npu 2.10.0.post7 / CANN 9.2.1）
- 启动 `bash /home/vllm/h3img/run_h3img.sh`（TP4 + text-encoder TP4，4 die）
- 看护 `bash /home/vllm/h3img/supervise_h3.sh`（被杀后 10 秒自愈）
- 细节与三处坑见服务器 `/home/vllm/h3img/RUNBOOK.md`

## 10. 非模板场景（室内 / 坐姿 / 夜景）→ 必须 `--prompt-raw`

内置模板只服务「立绘 / 半身 / 站立 + 平涂背景」，`--scene` 是**追加在** `simple flat painted background` 之后，`FRAMING` 也没有坐姿档——画「坐在房间地垫上打游戏」这类场景会被模板拉回半身/平涂背景。实测可行的写法：

- 走 `--prompt-raw`，四段自己拼（顺序与 `build_prompt()` 一致）：画风档 → 二维比例 → **完整角色卡** → 场景。
- 夜景别用 `show` 档：它的 `no glossy rim light` / `flat simple painted background` 会把房间压成平光。用 `anime` 档的措辞（key-visual、细藏青线、平涂哑光）+ 补 `cool cyan monitor glow` 与 `warm amber desk lamp`。
- 构图必须显式写 `full-body seated ..., her whole figure including her bare feet stays inside the frame`；只写 `sitting` 会裁到大腿以上。
- 手柄写 `game controller with two thumbsticks and a cross-shaped D-pad`，否则是一块黑长条。
- 尺寸：`wide` = 2688×1536 = **4.13 MP < 4 MP**，会命中「先放大再缩回」。16:9 用 `2752x1568` 或 `3840x2176`；4K 出图 3840×2176 裁上下各 8 px 即 3840×2160。

prompt 别走命令行：把整段落到 `.txt`，用 `out/musume/gen_scene.py <prompt.txt> <WxH> <seeds> <outdir> <tag>` 调 `gen_h3.post()`，规避 PowerShell 传长中文/引号的开销。

```powershell
python out\musume\gen_scene.py out\musume\prompts\scene.txt 3840x2176 77 . final
```

## 11. 端点不通：先看容器，不是先看进程

`docker exec -d h3 ...` 前必须先确认容器在跑。共享机上 `h3` 会处于 `Exited (137)`（进程被 pkill 后容器没起来），此时 `docker exec` 直接失败，看起来却像「服务被杀」。

```powershell
ssh root@192.168.13.190 "docker ps -a --format '{{.Names}}|{{.Status}}' | grep -i h3"
ssh root@192.168.13.190 "docker start h3; docker exec -d h3 bash -lc 'setsid bash /home/vllm/h3img/supervise_h3.sh >/dev/null 2>&1'"
# 之后约 1 分钟 GET /v1/models 返回；4K（8.3 MP）单张约 12 s
```

共享机上别默认 NPU 0–3 空着：先看 `npu-smi info` 的 Process 段，某 die 被别人几十 GB 占着就等它退出（`ps -p <pid> -o etime,cmd`）再起。**未验证**：把 `run_h3img.sh` 的 `ASCEND_RT_VISIBLE_DEVICES` 改成别的 die 来绕开占用。
