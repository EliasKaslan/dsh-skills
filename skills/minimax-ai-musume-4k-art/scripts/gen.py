"""anime-gen-npu: offline SDXL anime image generation on Ascend NPU.

Usage (inside the vllm-ascend container):
    python gen.py smoke
    python gen.py gen --char claude --scene "..." --seed 42
"""
import argparse
import json
import os
import random
import time

import numpy as np
import torch
import torch_npu  # noqa: F401  (registers the npu device)
from PIL import Image
from PIL import ImageDraw, ImageFilter
from PIL.PngImagePlugin import PngInfo

MODEL_DIR = os.environ.get("SDXL_MODEL_DIR", "/work/models/animagine-xl-4.0")
IP_DIR = os.environ.get("IP_ADAPTER_DIR", "/work/models/ip-adapter-sdxl")
OUT_DIR = os.environ.get("OUT_DIR", "/work/out")
REF_DIR = os.environ.get("REF_DIR", "/work/refs")
VAE_DIR = os.environ.get("SDXL_VAE_DIR", "")   # 可选：外部 fp16-fix VAE 目录
BASE_DIR = os.environ.get("SDXL_BASE_DIR",
                          "/mnt/weight/f00913055/LLM/mindSpeed_mm/sdxl/stable-diffusion-xl-base-1.0")

QUALITY_PRESETS = {
    # Animagine XL 4.0 的口径（"high score / great score" 是它特有的质量词）
    "animagine": "masterpiece, high score, great score, absurdres, safe, 1girl, solo",
    # Illustrious / NoobAI 的口径（2025 主流二次元底模的通用质量词）
    "illustrious": "masterpiece, best quality, absurdres, safe, 1girl, solo",
}


def detect_profile():
    d = os.path.basename(MODEL_DIR.rstrip("/")).lower()
    if "noobai" in d or "illustrious" in d or "wai" in d:
        return "illustrious"
    return "animagine"


PROFILE = None  # 懒加载，见 get_profile()


def get_profile():
    global PROFILE
    if PROFILE is None:
        PROFILE = os.environ.get("MODEL_PROFILE") or detect_profile()
    return PROFILE


def quality_for(profile):
    return QUALITY_PRESETS.get(profile, QUALITY_PRESETS["illustrious"])

# 画风预设（2026-11 按参考素材实测重写）。
# 定量结论来自对 980 帧的统计：目标画风 = 线更粗更少但**有颜色**（近黑线仅 3%，
# 产出是 13.9%）+ 有中间层次（平坦度 32%，产出 73%）+ 饱和度更高（0.34 vs 0.28）。
# 所以正向词只留最关键几条，把"去黑线/去玻璃眼/去灰"全部放进负向词——
# 负向词有独立的 77 token 预算，不会挤掉正向风格词。
STYLE_PRESETS = {
    # 旧口径，仅作对照（会出细碎黑线 + 玻璃眼，已证伪）
    "video": "anime style, detailed eyes, clean lineart, soft colors",
    "soft": ("anime coloring, vibrant colors, detailed eyes, shiny hair, "
             "official art, illustration, depth of field"),
    # 目标口径：扁平赛璐璐 + 有色粗线 + 中间层次 + 高饱和
    "flat": ("flat color, cel shading, two-tone shading, colored lineart, "
             "clean lineart, vivid colors, blush, thick eyelashes"),
    # 番剧截图感
    "vn": ("anime screencap, flat color, cel shading, colored lineart, "
           "clean lineart, vivid colors, blush"),
    # 官方立绘感（最"正"的一档）
    "official": ("official art, anime coloring, cel shading, colored lineart, "
                 "clean lineart, vivid colors, detailed hair shading, blush"),
    # 针对《牢大百科》立绘实测调的一档：强调有色的粗线 + 两段上色 + 暖饱和
    # （2026-11-09 复盘：这一档是**错的**方向，出图发糙；保留仅作对照）
    "musume": ("colored lineart, bold lineart, flat color, cel shading, "
               "vivid colors, blush"),
    # 真正对齐参考图的档位：细线 + 柔和平滑上色 + 发丝渐变 + 精细眼睛
    "refine": ("soft shading, gradient hair, detailed eyes, clean lineart, "
               "anime coloring, soft lighting"),
    "refine2": ("anime style, soft shading, gradient hair, detailed eyes, glossy hair, "
                "clean lineart, depth of field, highres"),
    # 2026-11-10 按用户新参考图（深蓝渐变发 + 白蕾丝女仆装 + 木质内景，低饱和）
    # 重排的档位，配 illustrious-xl 实测。要点：
    # - `delicate lineart` 取代 `clean lineart`（后者在 Illustrious 上线条偏硬）
    # - `muted colors` 压饱和：参考图的蓝是雾霾蓝 #476599，不是高饱和电子蓝
    # - 这里**不写 gradient hair**：角色 core 里已经有了，重复占预算还会把发色
    #   漂成紫/青（实测 6 张里 6 张发色都不对，多半是这里双写的锅）
    "keyvisual": ("official art, key visual, soft shading, detailed eyes, "
                  "delicate lineart"),
    # 同上 + 压饱和；`muted colors` 会连藏青裙一起洗淡，只在需要"雾霾感"时开
    "keyvisual4": ("official art, key visual, soft shading, detailed eyes, "
                   "delicate lineart, muted colors"),
    # 对照档：去掉 muted，改压"细节层次"，用来判断到底是"低饱和"对还是"高细节"对
    "keyvisual3": ("official art, key visual, soft shading, detailed eyes, "
                   "delicate lineart, detailed shading"),
    "keyvisual2": ("official art, soft shading, detailed eyes, "
                   "delicate lineart, muted colors, warm lighting"),
    "none": "",
}
STYLE = STYLE_PRESETS["flat"]

# 负向词和正向一样受 77 token 硬墙约束。旧写法 NEG_SAFE + NEG_REAL + NEG_AI 拼起来
# 实测 147 token，CLIP 只吃前 77 个——尾部整段静默失效，日志里只留一行
# `Token indices sequence length is longer than ... (147 > 77)`。
# 2026-11-10 改成"紧凑核心 + 该画风增量"，每档都压在 75 以内；
# build_negative() 会打印 token 数，超了就是又写长了。
NEG_SAFE = ("lowres, bad anatomy, bad hands, extra digits, cropped, worst quality, "
            "low quality, signature, watermark, text, blurry")
NEG_REAL = "3d, realistic, photorealistic"
# 压"AI 味"的一档（黑碎线、玻璃眼、吹风式渐变）。
# 注意别往这里加 desaturated / pale colors —— 那一组会和 keyvisual 的
# `muted colors` 互相打架，出图会灰掉。
NEG_AI = ("pure black lineart, sketchy, wispy hair lines, glossy eyes, ring highlight, "
          "glassy eyes, 3d eyeball, heavy shading, painterly")
NEG_CORE = ", ".join([NEG_SAFE, NEG_REAL])
STYLE_NEG = {
    "video": "",
    "soft": "",
    "flat": NEG_AI,
    "vn": NEG_AI,
    "official": NEG_AI,
    "musume": NEG_AI,
    # 软上色档：反过来要压"平涂/粗描边"，别再压光泽
    "refine": ("flat color, bold lineart, thick outline, sketchy, rough lines, "
               "posterized, oversaturated, low detail"), 
    "refine2": ("flat color, bold lineart, thick outline, sketchy, rough lines, "
                "posterized, oversaturated, low detail"),
    # 新档：只压"海报感/霓虹感"，不再压光泽（参考图的眼是有高光的）
    "keyvisual": ("flat color, bold lineart, thick outline, sketchy, posterized, "
                  "oversaturated, neon colors, vivid colors, low detail"),
    "keyvisual2": ("flat color, bold lineart, thick outline, sketchy, posterized, "
                   "oversaturated, neon colors, vivid colors, low detail"),
    "none": "",
}
NEGATIVE = ", ".join([NEG_SAFE, NEG_REAL])  # 兼容旧调用；实际由 build_negative(style) 拼

CHARS = {
    "claude": {
        "tags": ("orange hair, long hair, orange eyes, flower hair ornament, "
                 "black ribbon, white blouse, brooch, gentle smile"),
        "ref": "claude.png",
    },
    "deepseek": {
        # 2026-11-10 按用户参考图重写。身份核心只留"不看这五条就认不出"的，
        # 它们排在画风词之前，保证换画风不会把发色/发长一起换掉
        # （实测：丢掉 very long hair 立刻变短发，丢掉 blue 只剩 gradient hair 会漂成青绿）。
        "core": ["dark blue hair", "gradient hair", "very long hair", "blue eyes",
                 "ahoge", "maid headdress"],
        # 服装细节排在画风之后：预算不够时先丢这里，丢的是荷叶边而不是画的质感。
        # `white apron` 被去掉——参考图是藏青胸衣 + 白色荷叶边衬衫，不是围裙；
        # `whale tail` 在胸像构图里根本进不了画面，留着只会干扰构图。
        "detail": ["navy blue dress", "white ruffled blouse", "blue bowtie",
                   "gem brooch", "smile"],
        "tags": ("blue hair, gradient hair, very long hair, blue eyes, ahoge, "
                 "maid, maid headdress, white frilled blouse, blue hair ribbon, "
                 "blue gem brooch, smile"),
        "ref": "deepseek.png",
    },
    "gpt": {
        "tags": ("white hair, very long hair, purple eyes, white horn, white dress, "
                 "bare shoulders, expressionless"),
        "ref": "gpt.png",
    },
    "grok": {
        "tags": ("blonde hair, long hair, blue eyes, bat wings, black crown, "
                 "gold trim, red gem, black gothic dress, fang, smirk"),
        "ref": "grok.png",
    },
    "gemini": {
        "tags": ("purple hair, long twintails, drill hair, heterochromia, pink eyes, "
                 "yellow eyes, star hair ornament, purple dress, open mouth, smile"),
        "ref": "gemini.png",
    },
    "qwen": {
        "tags": ("black hair, bob cut, side part, brown eyes, black shirt, "
                 "black top, blush, gentle smile"),
        "ref": "qwen.png",
    },
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def char_parts(ch):
    """把角色预设拆成 (身份核心, 服装细节)。

    没写 core/detail 的角色按老规矩自动拆：前 3 条算身份核心，其余算细节。
    """
    core = [t.strip() for t in (ch.get("core") or []) if t.strip()]
    detail = [t.strip() for t in (ch.get("detail") or []) if t.strip()]
    if not core:
        tags = [t.strip() for t in (ch.get("tags") or "").split(",") if t.strip()]
        core, detail = tags[:3], tags[3:]
    return core, detail


def build_negative(style="flat", extra="", override=""):
    """负面词 = 安全/解剖 + 去写实 + 该画风的去海报段 + 临时追加。

    注意追加词排在最后，有被 77 token 硬墙切掉的风险：要"必须生效"的负面词
    请写进 STYLE_NEG，不要用 --neg-extra。
    """
    if override:
        return override
    parts = [NEG_CORE, STYLE_NEG.get(style, ""), extra]
    return ", ".join([p for p in parts if p])


def patch_vae_fp32(pipe):
    """Run the VAE in fp32 and auto-cast inputs; avoids fp16 VAE artifacts on NPU."""
    import types

    pipe.vae.to(torch.float32)
    for name in ("decode", "encode"):
        orig = getattr(pipe.vae, name)

        def wrapper(self, x, *a, __orig=orig, **k):
            return __orig(x.to(self.dtype), *a, **k)

        setattr(pipe.vae, name, types.MethodType(wrapper, pipe.vae))
    log(f"vae dtype={pipe.vae.dtype} (fp32 decode patch)")

def load_single_file_manual(ckpt, base_dir, torch_dtype):
    """diffusers 0.37 的 from_single_file 在 Illustrious/NoobAI 上报
    `AttributeError: 'CLIPTextModel' object has no attribute 'text_model'`。

    这里用 SDXL base 的配置做骨架，再用 diffusers 自己的 LDM 转换器把权重灌进去：
    LDM 的 UNet 键（input_blocks.* / middle_block.*）与 diffusers 键（down_blocks.*）
    不是改个前缀就能对上的，必须走 convert_ldm_unet_checkpoint。
    """
    import gc

    from diffusers import StableDiffusionXLPipeline
    from diffusers.loaders.single_file_utils import (
        convert_ldm_unet_checkpoint, convert_ldm_vae_checkpoint,
        convert_open_clip_checkpoint)
    from safetensors.torch import load_file

    log(f"manual assemble: base={base_dir} ckpt={os.path.basename(ckpt)}")
    pipe = StableDiffusionXLPipeline.from_pretrained(
        base_dir, torch_dtype=torch_dtype, use_safetensors=True)
    sd = load_file(ckpt)
    rep = []

    # --- UNet：LDM -> diffusers 键名转换
    try:
        unet_sd = convert_ldm_unet_checkpoint(sd, dict(pipe.unet.config),
                                              extract_ema=False)
        m, un = pipe.unet.load_state_dict(unet_sd, strict=False)
        rep.append(f"unet ok missing={len(m)} unexpected={len(un)}")
    except Exception as e:  # noqa: BLE001
        rep.append(f"unet SKIPPED {type(e).__name__}: {e}")
    gc.collect()

    # --- VAE：同样需要转换
    try:
        vae_sd = convert_ldm_vae_checkpoint(sd, dict(pipe.vae.config))
        m, un = pipe.vae.load_state_dict(vae_sd, strict=False)
        rep.append(f"vae ok missing={len(m)} unexpected={len(un)}")
    except Exception as e:  # noqa: BLE001
        rep.append(f"vae SKIPPED {type(e).__name__}: {e}")
    gc.collect()

    # --- TE1：本版本的 pipe.text_encoder.state_dict() 键不带 `text_model.` 前缀，
    # 所以剥离时要多剥一层（这也是 diffusers 自身报 'CLIPTextModel' has no attribute
    # 'text_model' 的根因）。
    pfx = "conditioner.embedders.0.transformer.text_model."
    t1 = {k[len(pfx):]: v for k, v in sd.items() if k.startswith(pfx)}
    if t1:
        m, un = pipe.text_encoder.load_state_dict(t1, strict=False)
        rep.append(f"te1 missing={len(m)} unexpected={len(un)}")
    else:
        rep.append("te1 NOT FOUND in ckpt")
    del t1; gc.collect()

    # --- TE2：OpenCLIP -> transformers，走 diffusers 的转换器
    try:
        t2 = convert_open_clip_checkpoint(pipe.text_encoder_2, sd,
                                          prefix="conditioner.embedders.1.model.")
        m, un = pipe.text_encoder_2.load_state_dict(t2, strict=False)
        rep.append(f"te2 missing={len(m)} unexpected={len(un)}")
        del t2
    except Exception as e:  # noqa: BLE001
        rep.append(f"te2 SKIPPED {type(e).__name__}: {e}")
    del sd; gc.collect()
    log("manual load -> " + " | ".join(rep))
    return pipe


def load_pipe(use_ip=True):
    from diffusers import StableDiffusionXLPipeline
    t0 = time.time()
    if os.path.exists(os.path.join(MODEL_DIR, "model_index.json")):
        log(f"loading diffusers folder {MODEL_DIR}")
        pipe = StableDiffusionXLPipeline.from_pretrained(
            MODEL_DIR, torch_dtype=torch.float16, use_safetensors=True)
    else:
        ckpt = None
        for f in os.listdir(MODEL_DIR):
            if f.endswith(".safetensors") and os.path.getsize(os.path.join(MODEL_DIR, f)) > 1e9:
                ckpt = os.path.join(MODEL_DIR, f)
                break
        if ckpt is None:
            raise SystemExit(f"no big safetensors in {MODEL_DIR}: {os.listdir(MODEL_DIR)}")
        log(f"loading single file {ckpt}")
        if os.environ.get("SINGLE_FILE_LOADER", "auto") == "manual":
            pipe = load_single_file_manual(ckpt, BASE_DIR, torch.float16)
        else:
            try:
                pipe = StableDiffusionXLPipeline.from_single_file(
                    ckpt, torch_dtype=torch.float16, local_files_only=True)
            except Exception as e:  # noqa: BLE001
                log(f"from_single_file failed ({type(e).__name__}: {e})"
                    f" -> manual assemble")
                pipe = load_single_file_manual(ckpt, BASE_DIR, torch.float16)
    if VAE_DIR and os.path.isdir(VAE_DIR):
        # 有些 SDXL 社区权重自带 fp16 不安全的 VAE，会出全黑/NaN 图
        from diffusers import AutoencoderKL
        log(f"swapping external VAE {VAE_DIR}")
        pipe.vae = AutoencoderKL.from_pretrained(VAE_DIR, torch_dtype=torch.float32)
    pipe.to("npu:0")
    if os.environ.get("VAE_FP32", "1") == "1":
        patch_vae_fp32(pipe)
    pipe.set_progress_bar_config(disable=True)
    if use_ip:
        pipe.load_ip_adapter(
            IP_DIR,
            subfolder="sdxl_models",
            weight_name="ip-adapter-plus_sdxl_vit-h.safetensors",
            image_encoder_folder="models/image_encoder",
        )
        pipe.set_ip_adapter_scale(0.55)
    log(f"pipeline ready in {time.time() - t0:.1f}s")
    return pipe


SCHEDULERS = ("default", "euler_a", "dpmpp_2m", "unipc")


def apply_scheduler(pipe, name):
    """换采样器。Illustrious/NoobAI 社区常用 Euler a，比 SDXL 默认 Euler 更"软"。"""
    if not name or name == "default":
        return
    if name == "euler_a":
        from diffusers import EulerAncestralDiscreteScheduler as S
        pipe.scheduler = S.from_config(pipe.scheduler.config)
    elif name == "dpmpp_2m":
        from diffusers import DPMSolverMultistepScheduler as S
        pipe.scheduler = S.from_config(pipe.scheduler.config, use_karras_sigmas=True)
    elif name == "unipc":
        from diffusers import UniPCMultistepScheduler as S
        pipe.scheduler = S.from_config(pipe.scheduler.config)
    else:
        raise SystemExit(f"unknown scheduler {name}")
    log(f"scheduler={name}")


def count_tokens(pipe, text):
    try:
        return len(pipe.tokenizer(text, truncation=False).input_ids)
    except Exception:
        return 0


def progressive(pipe, image, prompt, negative, sizes, denoise, steps, cfg, seed, ip_image=None):
    """Progressive full-image img2img upscale (1.5x -> 2x -> target)."""
    from diffusers import StableDiffusionXLImg2ImgPipeline
    p2 = StableDiffusionXLImg2ImgPipeline(**pipe.components)
    p2.set_progress_bar_config(disable=True)
    w, h = image.size
    cur = image
    for i, (tw, th) in enumerate(sizes):
        cur = cur.resize((tw, th), Image.LANCZOS)
        g = torch.Generator(device="npu").manual_seed(int(seed) + 10 + i)
        t0 = time.time()
        kw = {}
        if ip_image is not None:
            kw["ip_adapter_image"] = ip_image
        cur = p2(prompt=prompt, negative_prompt=negative, image=cur,
                 strength=denoise, num_inference_steps=steps,
                 guidance_scale=cfg, generator=g, **kw).images[0]
        log(f"progressive {tw}x{th} in {time.time() - t0:.1f}s")
    return cur

def fit_prompt(pipe, parts, limit=77):
    """兼容旧签名：把 parts 当块，超限时从尾部整块丢弃。"""
    parts = [p for p in parts if p]
    while len(parts) > 1 and count_tokens(pipe, ", ".join(parts)) > limit:
        dropped = parts.pop()
        log(f"prompt over {limit} tokens, dropped: {dropped[:40]}...")
    text = ", ".join(parts)
    log(f"prompt tokens={count_tokens(pipe, text)}")
    return text


def build_prompt(pipe, quality, core, detail, scene, style, limit=75):
    """按「质量 → 身份核心 → 构图 → 画风 → 服装细节」的优先级逐词贪心装入。

    旧顺序是 质量 → 全部角色词 → 构图 → 画风，角色词先把预算吃光，画风词
    于是被整批跳过（2026-11-10 实测：flat 丢 4 个、refine2 丢 4 个，出图千篇
    一律）。现在把"认出是谁"的几条顶到画风之前，服装细节挪到最后——丢也只
    丢尾巴，画风不再被牺牲。
    """
    must = [x.strip() for x in (quality or "").split(",") if x.strip()]
    core = [x.strip() for x in core if x.strip()]
    while count_tokens(pipe, ", ".join(must + core)) > limit and core:
        log("char core over budget, dropped: %s" % core.pop())

    picked, skipped = [], []

    def try_add(group, label):
        for item in [x.strip() for x in (group or "").split(",") if x.strip()]:
            if count_tokens(pipe, ", ".join(must + core + picked + [item])) <= limit:
                picked.append(item)
            else:
                skipped.append("%s:%s" % (label, item))

    try_add(scene, "scene")
    try_add(style, "style")
    try_add(", ".join(detail or []), "detail")

    text = ", ".join(must + core + picked)
    log("prompt tokens=%d (scene+style+detail kept=%d, skipped=%d)"
        % (count_tokens(pipe, text), len(picked), len(skipped)))
    if skipped:
        log("skipped: " + ", ".join(skipped))
    return text


def gen(pipe, prompt, negative, width, height, steps, cfg, seed, ip_image=None, ip_scale=None):
    if ip_scale is not None:
        pipe.set_ip_adapter_scale(ip_scale)
    g = torch.Generator(device="npu").manual_seed(int(seed))
    kwargs = {}
    if ip_image is not None:
        kwargs["ip_adapter_image"] = ip_image
    t0 = time.time()
    out = pipe(
        prompt=prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        num_inference_steps=steps,
        guidance_scale=cfg,
        generator=g,
        **kwargs,
    ).images[0]
    log(f"gen {width}x{height} steps={steps} in {time.time() - t0:.1f}s")
    return out


def hires(pipe, image, prompt, negative, scale, denoise, steps, cfg, seed, ip_image=None):
    from diffusers import StableDiffusionXLImg2ImgPipeline
    p2 = StableDiffusionXLImg2ImgPipeline(**pipe.components)
    p2.set_progress_bar_config(disable=True)
    w, h = image.size
    nw, nh = int(w * scale) // 8 * 8, int(h * scale) // 8 * 8
    img = image.resize((nw, nh), Image.LANCZOS)
    g = torch.Generator(device="npu").manual_seed(int(seed) + 1)
    t0 = time.time()
    kw = {}
    if ip_image is not None:
        kw["ip_adapter_image"] = ip_image
    out = p2(
        prompt=prompt, negative_prompt=negative, image=img,
        strength=denoise, num_inference_steps=steps, guidance_scale=cfg,
        generator=g, **kw
    ).images[0]
    log(f"hires {nw}x{nh} strength={denoise} in {time.time() - t0:.1f}s")
    return out


def tiles(img, target_w, target_h, prompt, negative, pipe, steps, cfg, seed,
          tile=1024, overlap=96, denoise=0.30, ip_image=None):
    """USDU-style tiled img2img upscale."""
    from diffusers import StableDiffusionXLImg2ImgPipeline
    p2 = StableDiffusionXLImg2ImgPipeline(**pipe.components)
    p2.set_progress_bar_config(disable=True)
    base = img.resize((target_w, target_h), Image.LANCZOS)
    arr = np.asarray(base).astype(np.float32)
    acc = np.zeros_like(arr)
    wsum = np.zeros((target_h, target_w, 1), dtype=np.float32)
    xs = list(range(0, max(target_w - tile, 0) + 1, tile - overlap))
    ys = list(range(0, max(target_h - tile, 0) + 1, tile - overlap))
    if xs[-1] != target_w - tile:
        xs.append(max(target_w - tile, 0))
    if ys[-1] != target_h - tile:
        ys.append(max(target_h - tile, 0))
    total = len(xs) * len(ys)
    n = 0
    t0 = time.time()
    for y in ys:
        for x in xs:
            crop = base.crop((x, y, min(x + tile, target_w), min(y + tile, target_h)))
            g = torch.Generator(device="npu").manual_seed(int(seed) + 100 + n)
            kw = {}
            if ip_image is not None:
                kw["ip_adapter_image"] = ip_image
            out = p2(prompt=prompt, negative_prompt=negative, image=crop,
                     strength=denoise, num_inference_steps=steps,
                     guidance_scale=cfg, generator=g, **kw).images[0]
            o = np.asarray(out).astype(np.float32)
            h, w = o.shape[:2]
            yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
            xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
            mask = (np.minimum(yy, 1 - yy) * 24 + 1) * (np.minimum(xx, 1 - xx) * 24 + 1)
            mask = np.clip(mask, 0, 1)[..., None]
            acc[y:y + h, x:x + w] += o * mask
            wsum[y:y + h, x:x + w] += mask
            n += 1
            log(f"tile {n}/{total} ({x},{y}) in {time.time() - t0:.0f}s total")
    out = (acc / np.maximum(wsum, 1e-6)).clip(0, 255).astype(np.uint8)
    return Image.fromarray(out)


def save(img, path, meta):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    info = PngInfo()
    for k, v in meta.items():
        info.add_text(k, str(v))
    img.save(path, pnginfo=info)
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log(f"saved {path}")


def cmd_smoke(args):
    pipe = load_pipe(use_ip=False)
    img = gen(pipe, quality_for(get_profile()) + ", " + CHARS["claude"]["tags"], build_negative("flat"),
              512, 512, 4, 5.0, 42)
    img.save(os.path.join(OUT_DIR, "smoke.png"))
    log("smoke ok")


def refine_face(pipe, img, prompt, neg, args):
    """脸部局部重绘：裁出脸区 → 放大 2 倍 → 低强度 img2img → 羽化贴回。

    为什么有效：整图放大（hires）会连背景一起重画、还容易把颜色弄坏；
    而"精致度"的观感 80% 来自眼睛/皮肤/发丝这几处局部细节。只重画脸，
    构图和服装一个像素都不动，也不碰背景，风险最低。
    """
    from diffusers import StableDiffusionXLImg2ImgPipeline

    W, H = img.size
    box = [float(v) for v in (getattr(args, "face_box", "") or "0.30,0.08,0.70,0.44").split(",")]
    x0, y0 = int(box[0] * W), int(box[1] * H)
    x1, y1 = int(box[2] * W), int(box[3] * H)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 64 or y1 - y0 < 64:
        log("face refine skipped: region too small")
        return img

    crop = img.crop((x0, y0, x1, y1))
    big = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    p2 = StableDiffusionXLImg2ImgPipeline(**pipe.components)
    p2.set_progress_bar_config(disable=True)
    g = torch.Generator(device="npu").manual_seed(int(args.seed) + 11)
    t0 = time.time()
    out = p2(prompt=prompt + ", detailed face, detailed eyes",
             negative_prompt=neg, image=big,
             strength=float(args.face_refine),
             num_inference_steps=max(16, int(args.steps * 0.8)),
             guidance_scale=args.cfg, generator=g).images[0]
    out = out.resize(crop.size, Image.LANCZOS)

    # 羽化蒙版：边缘一圈 12% 渐变，避免贴回后出现方形接缝
    mask = Image.new("L", crop.size, 0)
    dx, dy = max(2, int(crop.width * 0.12)), max(2, int(crop.height * 0.12))
    ImageDraw.Draw(mask).rectangle([dx, dy, crop.width - dx, crop.height - dy], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(3, crop.width // 20)))
    img.paste(out, (x0, y0), mask)
    log("face refine denoise=%.2f region=%s in %.1fs"
        % (float(args.face_refine), (x0, y0, x1, y1), time.time() - t0))
    return img


def cmd_gen(args):
    ch = CHARS[args.char]
    pipe = load_pipe(use_ip=not args.no_ip)
    apply_scheduler(pipe, getattr(args, "scheduler", "default"))
    ref = None
    if ch["ref"] and not args.no_ip:
        p = os.path.join(REF_DIR, ch["ref"])
        if os.path.exists(p):
            ref = Image.open(p).convert("RGB")
    style_text = args.style_tags or STYLE_PRESETS[args.style]
    core, detail = char_parts(ch)
    if args.tags:
        core, detail = [t.strip() for t in args.tags.split(",") if t.strip()], []
    prompt = build_prompt(pipe, quality_for(get_profile()), core, detail,
                          args.scene, style_text)
    neg = build_negative(args.style, args.neg_extra, args.negative)
    log("negative tokens=%d" % count_tokens(pipe, neg))
    w, h = [int(v) for v in args.base.split("x")]
    # 超采样：先按倍数渲染，出图后再用 LANCZOS 降回目标尺寸。
    # 等价于 1.25 倍抗锯齿 + 细节超集，线条比直接渲染更实、没有 hires 的调色风险。
    ss = max(1.0, float(getattr(args, "supersample", 1.0) or 1.0))
    gw, gh = w, h
    if ss > 1.0 and not args.target:
        gw, gh = int(w * ss) // 8 * 8, int(h * ss) // 8 * 8
        log("supersample %.2fx: render %dx%d -> %dx%d" % (ss, gw, gh, w, h))
    if args.init:
        img = Image.open(args.init).convert("RGB")
        log(f"init from {args.init} {img.size}")
        if args.init_denoise > 0:
            from diffusers import StableDiffusionXLImg2ImgPipeline
            p2 = StableDiffusionXLImg2ImgPipeline(**pipe.components)
            p2.set_progress_bar_config(disable=True)
            g = torch.Generator(device="npu").manual_seed(int(args.seed) + 7)
            t0 = time.time()
            img = p2(prompt=prompt, negative_prompt=neg, image=img,
                     strength=args.init_denoise, num_inference_steps=args.steps,
                     guidance_scale=args.cfg, generator=g).images[0]
            log(f"init img2img strength={args.init_denoise} in {time.time() - t0:.1f}s")
    else:
        img = gen(pipe, prompt, neg, gw, gh, args.steps, args.cfg, args.seed,
                  ip_image=ref, ip_scale=args.ip_scale)
    if args.hires > 1:
        img = hires(pipe, img, prompt, neg, args.hires, args.hires_denoise,
                    args.hires_steps, args.cfg, args.seed, ip_image=ref)
    if args.target:
        tw, th = [int(v) for v in args.target.split("x")]
        if args.upscale == "tiles":
            img = tiles(img, tw, th, prompt, neg, pipe, args.tile_steps, args.cfg,
                        args.seed, tile=args.tile, denoise=args.tile_denoise,
                        ip_image=ref)
        else:
            w, h = img.size
            sizes = []
            for frac in (0.55, 0.75):
                nw, nh = int(tw * frac) // 8 * 8, int(th * frac) // 8 * 8
                if nw >= w * 1.02 and nh >= h * 1.02:
                    sizes.append((nw, nh))
            sizes.append((tw, th))
            pipe.vae.enable_tiling()
            img = progressive(pipe, img, prompt, neg, sizes, args.tile_denoise,
                              args.tile_steps, args.cfg, args.seed, ip_image=ref)
    if ss > 1.0 and not args.target and img.size != (w, h):
        img = img.resize((w, h), Image.LANCZOS)
        log("supersample downscale -> %dx%d" % (w, h))
    if getattr(args, "face_refine", 0) > 0:
        img = refine_face(pipe, img, prompt, neg, args)
    meta = dict(prompt=prompt, negative=neg, seed=args.seed, steps=args.steps,
                cfg=args.cfg, size=img.size, char=args.char, model=os.path.basename(MODEL_DIR),
                ip_scale=args.ip_scale, scene=args.scene,
                supersample=ss, face_refine=getattr(args, "face_refine", 0),
                face_box=getattr(args, "face_box", ""))
    save(img, os.path.join(args.out, f"{args.char}_{args.tag or 'v'}_{args.seed}.png"), meta)


def cmd_sweep(args):
    """Draw N candidates in ONE process: the 20GB pipeline is loaded only once.

    Repeated `run_gen.sh gen` calls each pay a fresh container + weight load,
    so a 6-seed sweep costs ~6x the load time. This keeps it to one.
    """
    ch = CHARS[args.char]
    seeds = [int(s) for s in str(args.seeds).replace(" ", "").split(",") if s != ""]
    if not seeds:
        raise SystemExit("--seeds is empty")
    styles = [s for s in str(getattr(args, "styles", "") or "").split(",") if s] or [args.style]
    pipe = load_pipe(use_ip=bool(getattr(args, "ip_scale", None)))
    apply_scheduler(pipe, getattr(args, "scheduler", "default"))
    w, h = [int(v) for v in args.base.split("x")]
    ss = max(1.0, float(getattr(args, "supersample", 1.0) or 1.0))
    gw, gh = (int(w * ss) // 8 * 8, int(h * ss) // 8 * 8) if ss > 1.0 else (w, h)
    ref = None
    if getattr(args, "ip_scale", None):
        p = os.path.join(REF_DIR, ch["ref"])
        if os.path.exists(p):
            ref = Image.open(p).convert("RGB")
            log(f"ip ref {p} {ref.size} scale={args.ip_scale}")
        else:
            log(f"WARNING ip ref missing: {p} -> running without IP")
    for st in styles:
        style_text = args.style_tags or STYLE_PRESETS[st]
        core, detail = char_parts(ch)
        if args.tags:
            core, detail = [t.strip() for t in args.tags.split(",") if t.strip()], []
        prompt = build_prompt(pipe, quality_for(get_profile()), core, detail,
                              args.scene, style_text)
        neg = build_negative(st, args.neg_extra, args.negative)
        log("negative tokens=%d" % count_tokens(pipe, neg))
        for s in seeds:
            img = gen(pipe, prompt, neg, gw, gh, args.steps, args.cfg, s,
                      ip_image=ref, ip_scale=getattr(args, "ip_scale", None))
            if ss > 1.0 and img.size != (w, h):
                img = img.resize((w, h), Image.LANCZOS)
            meta = dict(prompt=prompt, negative=neg, seed=s, steps=args.steps,
                        cfg=args.cfg, size=img.size, char=args.char, style=st,
                        model=os.path.basename(MODEL_DIR), scene=args.scene,
                        ip_scale=getattr(args, "ip_scale", None),
                        supersample=ss,
                        tags=args.tags or ch["tags"])
            save(img, os.path.join(args.out, f"{args.char}_{args.tag or 'sw'}_{st}_{s}.png"), meta)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("smoke")
    s.set_defaults(func=cmd_smoke)
    g = sub.add_parser("gen")
    g.add_argument("--char", required=True, choices=sorted(CHARS))
    g.add_argument("--scene", default="upper body, looking at viewer, simple background")
    g.add_argument("--seed", type=int, default=-1)
    g.add_argument("--base", default="1216x1024")
    g.add_argument("--steps", type=int, default=30)
    g.add_argument("--cfg", type=float, default=5.2)
    g.add_argument("--hires", type=float, default=1.5)
    g.add_argument("--hires-denoise", type=float, default=0.38)
    g.add_argument("--hires-steps", type=int, default=20)
    g.add_argument("--ip-scale", type=float, default=0.55)
    g.add_argument("--no-ip", action="store_true")
    g.add_argument("--style", default="keyvisual", choices=sorted(STYLE_PRESETS))
    g.add_argument("--neg-extra", default="", help="追加负面词")
    g.add_argument("--negative", default="", help="整体覆盖负面词")
    g.add_argument("--scheduler", default="default", choices=list(SCHEDULERS))
    g.add_argument("--style-tags", default="")
    g.add_argument("--target", default="")
    g.add_argument("--tile", type=int, default=1024)
    g.add_argument("--tile-denoise", type=float, default=0.30)
    g.add_argument("--tile-steps", type=int, default=20)
    g.add_argument("--supersample", type=float, default=1.0,
                   help=">1 时按倍数渲染再 LANCZOS 降回 --base（1.25 常用），线条更实；"
                        "与 --target 同时给时不生效")
    g.add_argument("--face-refine", type=float, default=0.0,
                   help=">0 时对脸部做一次局部 img2img（建议 0.25~0.35），只动脸不动构图")
    g.add_argument("--face-box", default="0.30,0.08,0.70,0.44",
                   help="脸区归一化坐标 x0,y0,x1,y1，按景别调")
    g.add_argument("--upscale", default="progressive", choices=["progressive", "tiles"])
    g.add_argument("--init", default="")
    g.add_argument("--init-denoise", type=float, default=0.0,
                   help=">0 时先对 --init 图做一次 img2img（风格锚定），如 0.5")
    g.add_argument("--tags", default="", help="override character tags")
    g.add_argument("--out", default=OUT_DIR)
    g.add_argument("--tag", default="")
    g.set_defaults(func=cmd_gen)
    sw = sub.add_parser("sweep")
    sw.add_argument("--char", required=True, choices=sorted(CHARS))
    sw.add_argument("--seeds", required=True, help="comma list, e.g. 11,22,33,44")
    sw.add_argument("--scene", default="upper body, looking at viewer, simple background")
    sw.add_argument("--base", default="1216x1024")
    sw.add_argument("--steps", type=int, default=30)
    sw.add_argument("--cfg", type=float, default=5.2)
    sw.add_argument("--style", default="keyvisual", choices=sorted(STYLE_PRESETS))
    sw.add_argument("--neg-extra", default="", help="追加负面词")
    sw.add_argument("--negative", default="", help="整体覆盖负面词")
    sw.add_argument("--scheduler", default="default", choices=list(SCHEDULERS))
    sw.add_argument("--styles", default="", help="逗号分隔多个画风预设，一次装模型全跑")
    sw.add_argument("--ip-scale", type=float, default=None, help="启用 IP-Adapter 并设强度")
    sw.add_argument("--style-tags", default="")
    sw.add_argument("--tags", default="", help="override character tags")
    sw.add_argument("--supersample", type=float, default=1.0,
                    help=">1 时按倍数渲染再降回 --base，抽卡阶段就能看出线条锐度")
    sw.add_argument("--out", default=OUT_DIR)
    sw.add_argument("--tag", default="")
    sw.set_defaults(func=cmd_sweep)
    args = ap.parse_args()
    if getattr(args, "seed", 1) < 0:
        args.seed = random.randint(0, 2**31 - 1)
    args.func(args)


if __name__ == "__main__":
    main()
