---
name: anima-ai-musume-lora
description: 用 Anima 底模 + AI 娘 LoRA 在昇腾 192.168.13.190 出图（ComfyUI on torch_npu，单 die 约 10 GB）——Aesthetic 1024×1536/32 步约 21 秒，Turbo 10 步约 4.5 秒；含模型与 LoRA 放置、gen_anima.py 调用、Danbooru 标签写法与半身构图铁律、Civitai 下载需登录、GLIBCXX 与 cast_weight 两个补丁。适用于「用 Anima 出 AI 娘」「跑 LoRA 生图」「Anima 在昇腾上怎么部署」「Anima 和 MiniMax H3 怎么选」「Civitai LoRA 下不下来」。不适用：MiniMax-H3 正片广播画风 → 用 minimax-ai-musume-4k-art。
disable-model-invocation: true
warm-triggers: Anima 底模 + LoRA 出 AI 娘 / Civitai 下载
warm-reason: 兴趣生图，低频
---

# anima-ai-musume-lora · Anima + AI 娘 LoRA（昇腾 190）

**做的是「二次元 AI 娘」的 LoRA 路线**：底模 `circlestone-labs/Anima`（2B DiT，Qwen3-0.6B 文本编码器 + Qwen-Image VAE），在 `192.168.13.190` 上以 **ComfyUI 0.45.0 + torch_npu 2.10.0.post7** 跑，单 die 约 10.3 GB HBM，HTTP API 在 `18188`。

**与 H3 的分工**：这套是「便宜、快、可挂角色 LoRA、单卡」；要正片广播画风 / 4K / 参考图锁身份，仍走 `minimax-ai-musume-4k-art`（MiniMax-H3-Image，4 die，8 秒/张）。同一角色两边都出过图，对照见 `D:\workspace\261108_recreation\anima\REPORT.md`。

## 何时调用

- 要「用 Anima 出一张」「跑一下 AI 娘 LoRA」「Anima 在 190 上怎么起」。
- 要低成本批量抽卡 / 单卡出图 / 训完 LoRA 验收。
- 手上只有 1 张卡、或 H3 的 4 die 被占满。
- 不适用：要正片画风、4K、参考图锁人 → `minimax-ai-musume-4k-art`；要装 CANN/torch → `ascend-env` 系。

## 1. 最快路径

```powershell
# 服务没起先起（约 30 秒就绪；已在跑会报 Port in use，属正常）
ssh root@192.168.13.190 "cd /home/vllm/x00886548/work/anima-comfy && setsid bash C:\Users\admin\.dsh\skills\anima-ai-musume-lora\scripts\start_comfy.sh > comfy.log 2>&1 < /dev/null &"

# 出一张 Aesthetic（1024×1536，32 步，约 21 秒）
python C:\Users\admin\.dsh\skills\anima-ai-musume-lora\scripts\gen_anima.py `
  --prompt "1girl, solo, blue hair, gradient hair, maid, smile, looking at viewer, (upper body:1.4), close-up, simple background" `
  --steps 32 --cfg 4.5 --width 1024 --height 1536 --seed 101 --prefix anima/test

# Turbo 抽卡（10 步 CFG 1，约 4.5 秒）
... --unet anima-turbo-v1.1.safetensors --steps 10 --cfg 1

# 挂 LoRA（触发词见第 3 节）
... --lora anima-deepseek-3.safetensors --lora-strength 1.0 --prompt "deepseek, 1girl, ..."
```

- `gen_anima.py` 默认 `--host http://127.0.0.1:18188`；**在 Windows 本机跑要加 `--host http://192.168.13.190:18188`**（端口已对本地开放）。
- 输出默认落在服务器 `/home/vllm/ai-musume/anima/out`，再用 `scp` 拉回；图约 1.1–1.6 MB/张。
- 脚本只依赖 `requests`；提交 workflow → 轮询 `/history` → `/view` 下载，超时 900 秒。

## 2. 模型与 LoRA 放哪

服务器目录（ComfyUI 里已做软链）：

```
/home/vllm/ai-musume/anima/
  diffusion_models/anima-aesthetic-v1.1.safetensors   4.18 GB，出图默认
  diffusion_models/anima-turbo-v1.1.safetensors       4.18 GB，抽卡用
  text_encoders/qwen_3_06b_base.safetensors           1.19 GB
  vae/qwen_image_vae.safetensors                      0.25 GB
  loras/anima-deepseek-3.safetensors                  91.9 MB，HF SAkizuki/anima-deepseek（MIT）
```

- 底模与 TE/VAE 从 `hf-mirror.com` 拉：`https://hf-mirror.com/circlestone-labs/Anima/resolve/main/split_files/...`；单连接 1–4 MB/s，**8 线程分段能到约 20 MB/s**（`scripts/wheel_par.py` 同款思路）。
- 下完必须校验 SHA256（LFS oid 从 `https://huggingface.co/api/models/circlestone-labs/Anima/tree/main?recursive=true&expand=true` 取）。
- 新 LoRA 丢进 `loras/` 后**重启 ComfyUI**（启动脚本只在启动时建软链），或直接软链到 `ComfyUI/models/loras/`。

## 3. 提示词：Danbooru 标签 + 半身铁律

Anima 吃 **Danbooru/Gelbooru 标签 + 自然语言** 的混合；aesthetic 版**不要加 `score_*` 或堆 quality 词**（官方说明，堆了会「过熟」）。

**半身/头像构图铁律**（本次实测）：只要提示词里写了 `shorts / skirt / thigh strap / socks / footwear / full body`，模型就会画全身，`upper body` 压不住。做法：

1. **删掉腿脚标签**（只保留腰以上）；
2. 正向加 `(upper body:1.4), close-up, portrait, centered`；
3. 负向加 `full body, wide shot, standing`。

同一 Claude 提示词，改这三处后从全身变成半身。

**八角色触发词与核心标签**（Civitai「AI娘 | ai girls」v1.0 描述，触发词原文）：

| 角色 | 触发词 | 核心标签（抄用） |
|---|---|---|
| DeepSeek 鲸鱼娘 | `aigirls, aigirls（deepseek）` | blue hair, gradient hair, ahoge, fins, cetacean tail, maid headdress, blue corset, white detached sleeves |
| DeepSeek Q 版冬装 | 同上 | chibi, flat chest, earmuffs, fur collar, long coat, whale hood |
| Qwen 千问娘 | `aigirls（qwen）` | blue purple gradient hair, single braid, mini hat, china dress, shawl, white long skirt |
| GLM 阔耳狐娘 | `aigirls（glm）` | black hair, fox ears, fox tail, sleep mask, Z hair ornament, black corset |
| Kimi 娘 | `aigirls（kimi）` | white light-blue gradient hair, crescent, K hair ornament, cape, star print |
| GPT 白龙娘 | `aigirls（gpt）` | white hair, purple eyes, dragon horns/wings/tail, white dress, side slit |
| Claude 娘 | `aigirls（claude）` | orange/red hair, orange eyes, flower hair ornament, ascot, capelet, black+orange overskirt |
| Gemini 猫耳娘 | `aigirls（gemini）` | blue purple hair, double bun, heterochromia red/yellow, cat ears, star ornament |
| Grok 吸血鬼 | `aigirls（grok）` | blonde twintails, slit pupils, pointy ears, fangs, **black crown**（原案是金冠嵌黑宝石，模型易画成黑冠） |

> 这 8 个触发词是 Civitai 描述里的原文；**本次没能下到该 8 合 1 LoRA**（见第 6 节），上表用于「拿到文件后」直接抄。单角色 LoRA 的触发词以各自模型卡为准（`SAkizuki/anima-deepseek` = `deepseek`，强度 1.0，建议追加 `(cetacean tail:1.5), maid, mary janes`）。

## 4. 参数与实测速度（190，单 die）

| 档 | 底模 | 步数 | CFG | 分辨率 | 实测 |
|---|---|---|---|---|---|
| 抽卡 | `anima-turbo-v1.1` | 10 | 1 | 1024×1536 | **4.5 s/张** |
| 成图 | `anima-aesthetic-v1.1` | 32 | 4.5 | 1024×1536 | **18–22.6 s/张** |
| LoRA | aesthetic + LoRA | 32 | 4.5 | 1024×1536 | **22.5 s/张** |

- 采样器 `euler` + `simple` 起步；换 `er_sde` 更稳，`dpmpp_2m_sde_gpu` 更多样。
- 原生分辨率 512²–1536²；要更大先出 1024×1536 再放大，别硬拉。
- 单 die 只占约 10.3 GB；`--highvram` 整载即可，**不要开 lowvram**（会触发 torch_npu 的 `cast_weight(device)` 兼容 bug）。

## 5. 验收红线

1. **身份四项**：发色/瞳色/头饰/主色板，逐项对角色卡；纯提示词只能做到「要素齐」，颜色漂是常态。
2. **构图**：是不是又出全身了（数到脚就是错）；脸是否在上三分之一。
3. **脸型**：LoRA（尤其 `anima-deepseek`）会把脸带幼；要成年脸就降强度到 0.8 或加负面 `loli, child`。
4. **画风**：aesthetic 是平涂亮调；要 H3 的正片哑光/细藏青线，别用这套硬凑。
5. 不满意换 seed 重抽，别把全身当半身交付。

## 6. 故障排查

| 现象 | 原因 / 修法 |
|---|---|
| `libhccl.so: cannot open shared object file` | 没 source CANN：`. /home/cann/921/ascend-toolkit/set_env.sh` |
| `GLIBCXX_3.4.29 not found`（`fla_npu/.../libcust_opapi.so`） | 系统 libstdc++ 旧；把 conda 的 `libstdc++.so.6.0.34` 放 `env/compat_lib/`，`export LD_LIBRARY_PATH=.../compat_lib:$LD_LIBRARY_PATH`（只放这一个 so） |
| `'torch.device' object has no attribute 'dtype'`（`comfy/ops.py:cast_bias_weight`） | torch_npu 的 `Module.to()` 位置传 device；跑 `scripts/patch_ops.py` 打守卫补丁，然后重启 |
| 打了补丁仍报同错 | 还在 lowvram；启动加 `--highvram` |
| `Port 18188 is already in use` | 已经有一份在跑；`pgrep -af 18188` 确认，别重复起 |
| Civitai 下载 307 → `/login?reason=download-auth` | 需要 Civitai 登录/API Token；`civitai.com` 在本机与 190 均不可达，元数据可走 `civitai.work/api/v1/...`，文件不行 |
| pip 装依赖卡在 frontend/kitchen | aliyun 单连接只有 50–300 KB/s；用 `scripts/wheel_par.py` 8 线程下 wheel，再 `pip install --no-index --no-deps` |
| `torchsde` 缺 `trampoline`、`kornia` 缺 `kornia_rs` | `pip install trampoline kornia_rs Mako` |
| 出图全身 / 构图不听话 | 见第 3 节：删腿脚标签 + `(upper body:1.4)` + 负面 `full body` |

## 7. 文件地图

```
scripts/gen_anima.py     ★唯一入口：拼 workflow + 调 ComfyUI API（文生图 / --lora）
scripts/start_comfy.sh   起服务（CANN、compat_lib、ASCEND_RT_VISIBLE_DEVICES、--highvram、软链模型）
scripts/patch_ops.py     给 comfy/ops.py 打 torch_npu 兼容补丁（幂等，已打过会跳过）
scripts/wheel_par.py     aliyun/PyPI wheel 8 线程分段下载器（下大依赖用）
scripts/prompts.json     八角色 Danbooru 提示词模板（可直接改）
```

## 8. 服务端一次性信息（日常不用改）

- 环境：`/home/vllm/x00886548/env/conda_envs/anima`（3.12.15，torch 2.10.0+cpu / torch_npu 2.10.0.post7）
- CANN：`/home/cann/921`；compat lib：`/home/vllm/x00886548/env/compat_lib`
- ComfyUI：`/home/vllm/x00886548/work/anima-comfy`（0.45.0）
- 启动：`ASCEND_RT_VISIBLE_DEVICES=4`（NPU 2 chip 0），`--listen 0.0.0.0 --port 18188 --highvram --bf16-unet --bf16-text-enc`
- 已打补丁：`comfy/ops.py` 的 `cast_bias_weight`（原文件备份 `ops.py.bak`）
- 依赖：comfyui-frontend-package 1.58.5 / comfy-kitchen 0.2.41 / comfy-aimdo 0.6.0 / torchsde 0.2.6 / kornia 0.9.0 / spandrel 0.4.2 / av 19.0.2；缺 workflow-templates 与 embedded-docs 只影响 Web UI 模板，不影响 API
