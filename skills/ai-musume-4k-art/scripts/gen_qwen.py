"""Qwen-Image-2.1 / 2.1-Turbo runner (Ascend NPU).

Why a separate entry point instead of reusing gen.py: this family is not an
SDXL tag model. It reads *natural language*, has no 77-token wall, and the Turbo
checkpoint carries its own 8-step sigmas. Squeezing it into the tag pipeline
would lose exactly the thing that makes it better.

Usage (inside the container, with venv-qwen):
    python gen_qwen.py --model /home/vllm/ai-musume/models/qwen-image-2.1-turbo \\
        --preset deepseek --size 1216x1024 --seed 7777 --tag q1
"""
import argparse
import io
import json
import os
import time

import torch
import torch_npu  # noqa: F401
from PIL import Image
from PIL.PngImagePlugin import PngInfo

STYLE = ("Modern anime key visual illustration: thin delicate lineart, smooth soft shading "
         "with gentle gradients, muted slightly desaturated colours, highly detailed, "
         "clean and polished, bright high-key lighting, warm cream tones, no harsh shadows")

CHARS = {
    "deepseek": ("a young woman with very long wavy blue hair that fades to a lighter blue "
                 "at the tips, an ahoge, large expressive blue eyes with bright highlights, "
                 "wearing a white lace maid headdress, a navy blue dress over a white frilled "
                 "blouse, and a blue ribbon bow with a gem brooch at the collar"),
    "generic": ("a young woman with long flowing hair and large expressive eyes, "
                "wearing a simple elegant dress"),
}

NEG = ("photorealistic, 3d render, cgi, lowres, blurry, jpeg artifacts, text, watermark, "
       "signature, bad anatomy, extra fingers, deformed hands, oversaturated neon colours")


def patch_npu_ops():
    """Route `Tensor.nonzero` through CPU.

    QwenImage21Transformer2DModel.build_token_metadata() calls
    `image_pad_mask.nonzero(as_tuple=True)`; CANN has no aclnnIndex kernel for it
    and the whole run dies with "current working operator name is aclnnIndex".
    The call only produces indices for a small mask, so doing it on CPU and
    copying back is cheap and exact.
    """
    orig = torch.Tensor.nonzero

    def nonzero(self, *a, **k):
        if self.device.type == "npu":
            out = orig(self.cpu(), *a, **k)
            if isinstance(out, tuple):
                return tuple(o.to(self.device) for o in out)
            return out.to(self.device)
        return orig(self, *a, **k)

    torch.Tensor.nonzero = nonzero


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def build_prompt(char, scene, style):
    return "%s. %s. %s." % (CHARS.get(char, CHARS["generic"]), scene, style or STYLE)


def load(model_dir, offload=False):
    from diffusers import QwenImage21Pipeline
    t0 = time.time()
    pipe = QwenImage21Pipeline.from_pretrained(model_dir, torch_dtype=torch.bfloat16)
    pipe.set_progress_bar_config(disable=True)
    if offload:
        # 64GB die minus 33GB of weights leaves little room for activations at
        # 1216x1024; this trades speed for headroom instead of failing outright.
        pipe.enable_model_cpu_offload()
        log("cpu offload enabled")
    else:
        # N.B. `pipe.to("npu")` on this pipeline dies with "9.36 MiB free" even
        # though the die has 65GB free; moving each component on its own works
        # (measured: 65.4 -> 49.9 -> 31.8 GB free). Do not "simplify" this back.
        for name in ("vae", "transformer", "text_encoder"):
            comp = getattr(pipe, name, None)
            if comp is not None:
                comp.to("npu")
                log("%s on npu" % name)
    log("pipeline ready in %.1fs (dtype=bfloat16, offload=%s)" % (time.time() - t0, offload))
    return pipe


def call_kwargs(pipe, args, prompt, neg):
    """Pass only the kwargs this pipeline version actually accepts."""
    import inspect
    params = set(inspect.signature(pipe.__call__).parameters)
    kw = dict(prompt=prompt, num_inference_steps=args.steps,
              width=args.width, height=args.height,
              generator=torch.Generator(device="npu").manual_seed(int(args.seed)))
    if neg and "negative_prompt" in params:
        kw["negative_prompt"] = neg
    for key in ("true_cfg_scale", "guidance_scale", "cfg_scale"):
        if key in params:
            kw[key] = args.cfg
            break
    unsupported = [k for k in kw if k not in params and k not in ("prompt",)]
    for k in unsupported:
        kw.pop(k)
    return kw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--preset", default="deepseek")
    ap.add_argument("--scene", default="upper body portrait, looking at viewer, gentle smile, "
                                      "standing in a warm wooden interior with gold trim")
    ap.add_argument("--style", default="")
    ap.add_argument("--neg", default=NEG)
    ap.add_argument("--size", default="1216x1024")
    ap.add_argument("--steps", type=int, default=0, help="0 = auto (turbo 8 / base 40)")
    ap.add_argument("--cfg", type=float, default=-1.0, help="<0 = auto (turbo 1.0 / base 4.0)")
    ap.add_argument("--seed", type=int, default=7777)
    ap.add_argument("--out", default="/home/vllm/ai-musume/out")
    ap.add_argument("--tag", default="q")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offload", action="store_true",
                    help="CPU offload 权重（慢，但 64GB die 上更不容易 OOM）")
    ap.add_argument("--lora", default="",
                    help="角色 LoRA 的目录或 safetensors 路径；加载后可保证同一角色")
    ap.add_argument("--lora-scale", type=float, default=1.0)
    ap.add_argument("--trigger", default="whale_chan",
                    help="LoRA 触发词；只在 --lora 时拼到提示词最前面")
    args = ap.parse_args()

    is_turbo = "turbo" in os.path.basename(args.model.rstrip("/")).lower()
    args.steps = args.steps or (8 if is_turbo else 40)
    args.cfg = args.cfg if args.cfg >= 0 else (1.0 if is_turbo else 4.0)
    w, h = [int(v) for v in args.size.split("x")]
    args.width, args.height = w // 16 * 16, h // 16 * 16

    prompt = build_prompt(args.preset, args.scene, args.style)
    if args.lora and args.trigger:
        prompt = "%s, %s" % (args.trigger, prompt)
    patch_npu_ops()
    log("prompt=%s" % prompt)
    log("steps=%d cfg=%.2f size=%dx%d turbo=%s" % (args.steps, args.cfg, args.width,
                                                   args.height, is_turbo))
    if args.dry_run:
        return

    pipe = load(args.model, offload=args.offload)
    if args.lora:
        # 角色 LoRA：训练时用的 instance prompt 里带了触发词 whale_chan，
        # 推理时把它写进 --scene 或 --preset 才能稳定触发。
        pipe.load_lora_weights(args.lora)
        if args.lora_scale != 1.0:
            pipe.set_adapters(["default_0"], adapter_weights=[args.lora_scale])
        log("lora loaded: %s (scale=%.2f)" % (args.lora, args.lora_scale))
    t0 = time.time()
    img = pipe(**call_kwargs(pipe, args, prompt, args.neg)).images[0]
    log("gen %dx%d steps=%d in %.1fs" % (img.width, img.height, args.steps, time.time() - t0))

    os.makedirs(args.out, exist_ok=True)
    name = "qwen_%s_%s_%d" % (os.path.basename(args.model.rstrip("/")), args.tag, args.seed)
    path = os.path.join(args.out, name + ".png")
    info = PngInfo()
    meta = dict(prompt=prompt, negative=args.neg, seed=args.seed, steps=args.steps,
                cfg=args.cfg, size="%dx%d" % img.size, model=os.path.basename(args.model.rstrip("/")))
    for k, v in meta.items():
        info.add_text(k, str(v))
    img.save(path, pnginfo=info)
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    log("saved %s" % path)


if __name__ == "__main__":
    main()
