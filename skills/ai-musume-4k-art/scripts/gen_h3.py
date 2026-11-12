#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai-musume H3 client — MiniMax-H3-Image via vllm-omni on 192.168.13.190:18080.

Only stdlib. H3-Image contract: 6 CFG-distilled steps, guidance fixed at 1,
NO negative_prompt (server returns HTTP 400), size must be on a 32px grid and
>= 4 MP unless min_generation_area is lowered.
"""
import argparse
import base64
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

ENDPOINT = os.environ.get("H3_ENDPOINT", "http://192.168.13.190:18080")
MODEL = os.environ.get("H3_MODEL", "/home/vllm/h3img/MiniMax-H3-Image")
OUTDIR = os.environ.get("H3_OUTDIR", r"D:\workspace\261108_recreation\out\musume")

SIZES = {
    "portrait": "1696x2528",   # 4.29 MP, 立绘/半身
    "square": "2048x2048",     # 原生画布
    "landscape": "2528x1696",
    "wide": "2688x1536",
    "big": "3072x3072",
    "4k": "3840x2176",         # 4K UHD 画幅（32 网格），接收后裁到 3840x2160
}

# ---- 画风档：H3 摄影倾向强，必须显式声明"二维动画"，否则出真人 ----
STYLES = {
    "anime": (
        "A 2D Japanese anime illustration in a modern TV-anime style, crisp dark lineart, "
        "two-tone cel shading, saturated poster colors, glossy hair highlights with sharp specular bands, "
        "official character key visual quality. Not a photograph, no photorealistic skin, no 3D render."
    ),
    "show": (
        "A faithful 2D TV-anime screencap from a 2020s broadcast series: thin delicate lineart in "
        "desaturated dark navy, flat two-tone cel shading with soft gradients, matte muted colors, "
        "no glossy white shine, hair drawn as fine strands with a cyan-blue gradient at the tips and "
        "only thin pale line highlights instead of broad specular bands, large eyes with a soft radial "
        "iris gradient and one small catchlight, small nose with a soft shadow, flat simple painted "
        "background, slight broadcast softness, no poster-key-visual contrast. "
        "Not a photograph, no photorealistic skin, no 3D render."
    ),
    "cel": (
        "A 2D Japanese anime illustration, hand-drawn digital anime art, "
        "clean confident lineart with visible ink outlines, flat cel shading with two-tone shadows, "
        "vivid saturated color palette, official character key visual quality. "
        "Not a photograph, no photorealistic skin, no 3D render."
    ),
    "soft": (
        "A soft-shaded anime illustration in the style of a modern Japanese light-novel cover, "
        "delicate thin lineart, gradient cel shading, pastel-leaning palette with warm rim light, "
        "painterly hair strands. Not a photograph, no 3D render."
    ),
    "retro": (
        "A 1990s hand-painted anime cel illustration, thick dark outlines, flat poster colors, "
        "grainy film texture, nostalgic retro anime aesthetic, bold highlights in the hair. "
        "Not a photograph, not 3D."
    ),
}

# ---- 动画比例：不写这段，H3 会给出写实成人脸 ----
ANATOMY = (
    "Anime proportions: large expressive eyes with thick upper eyelashes and crisp catchlights, "
    "small nose and mouth, rounded youthful face, slender neck, stylized simplified anatomy."
)

# ---- 角色卡：以 B站 BV14C456WEXN（牢大百科16）封面原分辨率逐项核对过 ----
CHARS = {
    "claude": (
        "an anime girl with long orange hair swept to one side, warm amber-orange eyes, "
        "a large orange daisy flower on the viewer-right side of her head (her left), "
        "a gold dangling flower earring, wearing a white blouse with cream daisy embroidery on the shoulder, "
        "a white lace high collar tied with a black ribbon, and an orange daisy brooch at her chest, "
        "gentle sultry smile with light blush"
    ),
    "deepseek": (
        "an anime girl with very long deep-blue hair fading to cyan-blue at the wavy tips, one thin ahoge "
        "curling above her head, large soft sapphire-blue eyes, a narrow white frilled maid headband across "
        "the top of her head, and at each temple a relatively small navy-blue whale-flipper ear that flares "
        "out sideways and droops down beside her cheek, lying flat against the side of her head rather than "
        "standing upright, the fin is dark navy blue with a narrow white ruffled trim only along its lower "
        "edge, a small light-blue ribbon bow at the root of each fin, a round blue gem brooch on a black "
        "ribbon bow at her collar, a navy-blue short-sleeve dress with a white ruffled bib and apron collar, "
        "white frilled cuffs"
    ),
    "gpt": (
        "an anime girl with very long wavy silver-white hair and a large two-loop cowlick on top, "
        "light purple half-lidded eyes, calm expressionless face, "
        "two big ivory-white ram horns curling outward from her temples, each horn as wide as her head, "
        "a thick white braided rope headdress on the viewer-right side, "
        "a white lace dress with bare shoulders"
    ),
    "grok": (
        "an anime girl with long blonde hair, a high side ponytail tied with a large black ribbon bow with gold piping, "
        "a long blonde drill curl, bright blue eyes with sharp eyeliner, long pointed elf ears, "
        "an ornate gold crown set with large black gemstones and a small cross finial on top, "
        "a black gothic dress with dark maroon velvet collar, a gold star brooch at the chest, smug smirk"
    ),
    "gemini": (
        "an anime girl with long blue-violet hair fading to lavender at the curled tips, one ahoge, "
        "heterochromatic eyes: the viewer-left eye pink-magenta and the viewer-right eye golden-yellow, "
        "iridescent pastel star hair ornaments, a blue ribbon bow, "
        "a deep purple off-shoulder dress with gold trim and a gold star brooch, open-mouth laughing smile"
    ),
}

EXPRS = {
    "neutral": "calm neutral expression, mouth closed, looking at viewer",
    "smile": "gentle closed-mouth smile, looking at viewer",
    "soft_laugh": "soft closed-mouth laugh, eyes slightly narrowed, quietly amused",
    "shy": "shy blush, eyes glancing away, small closed-mouth smile",
    "pout": "slight pout with faintly knitted brows, mouth closed",
    "surprised": "mildly surprised, eyes slightly widened, mouth closed",
    "sleepy": "sleepy half-lidded eyes, small suppressed yawn",
    "wink": "playful single wink, closed-mouth smile",
    "sad": "quietly sad eyes, faint frown, mouth closed",
    "tease": "teasing smirk with one raised eyebrow",
    "serious": "composed serious expression, straight face, mouth closed",
    "awe": "quiet amazement, wide sparkling eyes, mouth closed",
}

# 角色几乎不会张嘴大笑——统一收紧表演幅度
RESTRAINT = (
    "Restrained expression acting: mouth closed, no wide-open mouth, no shouting, "
    "no exaggerated comedic face, subtle Japanese TV-anime acting."
)

# 脸型纠偏：不写这段会出偏圆偏幼的脸
FACE = (
    "Balanced adult face: oval face with a soft but defined jawline, chin gently rounded at the tip (not pointed, not a sharp V), light cheek fullness, same face length as the reference, mature, not childlike."
)

# 亮度纠偏：H3 默认偏暗，给一个明亮的高调打光
LIGHT = (
    "Bright high-key lighting, luminous even skin tone, soft warm fill light, "
    "no heavy shadows, no underexposure, overall bright and airy image."
)

# 正片（show）档的光：广播底色是柔和平光，压掉海报立绘那种玻璃高光
LIGHT_SHOW = (
    "Soft even broadcast lighting, gentle contrast, bright but not blown out, "
    "light warm skin tone, no heavy shadows, no glossy rim light, no lens flare."
)

FRAMING = {
    "bust": "close-up bust portrait, head and shoulders, face centered in the upper third, cropped at the chest",
    "half": "half-body shot from the waist up, centered composition",
    "full": "full body standing, centered composition, entire figure visible",
}


def build_prompt(char, expr, style, framing, scene, extra):
    light = LIGHT_SHOW if style == "show" else LIGHT
    parts = [
        STYLES[style],
        CHARS[char] + ".",
        EXPRS[expr] + ".",
        FRAMING[framing] + ".",
        FACE,
        RESTRAINT,
        light,
    ]
    if scene:
        parts.append(scene.rstrip(".") + ".")
    if style == "show":
        parts.append("Single character, simple flat painted background, no text, no watermark, no logo.")
    else:
        parts.append("Single character, clean background with soft bokeh, no text, no watermark, no logo.")
    if extra:
        parts.append(extra.rstrip(".") + ".")
    return " ".join(parts)


def post(prompt, size, seed, timeout=900, min_area=None):
    body = {
        "model": MODEL,
        "prompt": prompt,
        "size": size,
        "seed": int(seed),
        "response_format": "b64_json",
    }
    if min_area:
        body["min_generation_area"] = int(min_area)
    req = urllib.request.Request(
        ENDPOINT.rstrip("/") + "/v1/images/generations",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit("HTTP %s from %s\n%s" % (e.code, ENDPOINT, detail))
    except urllib.error.URLError as e:
        raise SystemExit(
            "cannot reach %s (%s)\n"
            "  -> 服务可能被杀了。到服务器上执行：\n"
            "     ssh root@192.168.13.190 \"docker exec -d h3 bash -lc "
            "'setsid bash /home/vllm/h3img/supervise_h3.sh >/dev/null 2>&1'\"\n"
            "     然后 curl -s %s/v1/models | head -c 200 确认" % (ENDPOINT, e.reason, ENDPOINT)
        )
    dt = time.time() - t0
    return base64.b64decode(payload["data"][0]["b64_json"]), dt


def png_size(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    w = int.from_bytes(raw[16:20], "big")
    h = int.from_bytes(raw[20:24], "big")
    return (w, h)


def _multipart(fields, files):
    b = "----h3img" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode("utf-8")
    for k, fn, data, ct in files:
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n" % (b, k, fn, ct)).encode("utf-8")
        out += data + b"\r\n"
    out += ("--%s--\r\n" % b).encode("utf-8")
    return bytes(out), "multipart/form-data; boundary=" + b


def post_edit(prompt, size, seed, refs, timeout=900):
    """Reference-image mode: /v1/images/edits, 1..9 reference images."""
    files = []
    for i, p in enumerate(refs):
        data = open(p, "rb").read()
        ct = "image/png" if p.lower().endswith(".png") else "image/jpeg"
        files.append(("image", os.path.basename(p), data, ct))
    body, ctype = _multipart(
        {"model": MODEL, "prompt": prompt, "size": size, "seed": int(seed),
         "response_format": "b64_json"}, files)
    req = urllib.request.Request(ENDPOINT.rstrip("/") + "/v1/images/edits",
                                 data=body, headers={"Content-Type": ctype}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s from /v1/images/edits\n%s" % (e.code, e.read().decode("utf-8", "replace")[:400]))
    except urllib.error.URLError as e:
        raise SystemExit("cannot reach %s (%s)" % (ENDPOINT, e.reason))
    return base64.b64decode(payload["data"][0]["b64_json"]), time.time() - t0


def build_ref_prompt(expr, framing, extra, style="show"):
    light = LIGHT_SHOW if style == "show" else LIGHT
    bg = ("Plain flat light neutral grey background." if style == "show"
          else "Clean background with soft bokeh.")
    return (
        "<Picture 1> is a frame of the character from a 2D TV anime; the other pictures are other frames "
        "of the SAME character. Copy the reference art style exactly: thin desaturated navy lineart, flat "
        "matte cel colours, compact face proportions, small nose shadow, a soft single catchlight in each "
        "eye, slight broadcast softness. Do not add glossy white hair shine, do not raise saturation, do not "
        "repaint her as a poster key visual. "
        "Keep the SAME character: identical face shape, hairstyle, hair colour and gradient, eye colour, "
        "headwear, hair ornaments, outfit, accessories and props, identical lineart weight and cel-shading "
        "technique as <Picture 1>. "
        "Redraw her with " + EXPRS[expr] + ", " + FRAMING[framing] + ". "
        + FACE + " " + RESTRAINT + " " + light + " "
        "Keep the original colour palette unchanged. " + bg +
        " No text, no watermark, no UI overlays, no name plates."
        + ((" " + extra.rstrip(".") + ".") if extra else "")
    )


def main():
    ap = argparse.ArgumentParser(description="Generate AI-musume art with MiniMax-H3-Image")
    ap.add_argument("--char", required=True, choices=sorted(CHARS))
    ap.add_argument("--expr", default="smile", choices=sorted(EXPRS))
    ap.add_argument("--style", default="show", choices=sorted(STYLES))
    ap.add_argument("--framing", default="bust", choices=sorted(FRAMING))
    ap.add_argument("--size", default="portrait", help="preset name or WxH (32px grid)")
    ap.add_argument("--scene", default="", help="extra scene / background clause (English)")
    ap.add_argument("--extra", default="", help="extra clause appended last")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--seeds", default="", help="comma list for batch")
    ap.add_argument("--tag", default="")
    ap.add_argument("--outdir", default=OUTDIR)
    ap.add_argument("--ref", action="append", default=[],
                    help="reference image (repeatable, 1..9); switches to /v1/images/edits")
    ap.add_argument("--prompt-raw", default="",
                    help="use this prompt verbatim (skips the built-in templates)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    size = SIZES.get(args.size, args.size)
    w, h = [int(x) for x in size.lower().split("x")]
    if w % 32 or h % 32:
        sys.exit("size must be on a 32px grid: %s" % size)
    if w * h < 4194304:
        print("warn: %.2f MP < 4 MP, server will upscale the canvas to reach 4 MP" % (w * h / 1e6))

    if args.prompt_raw:
        prompt = args.prompt_raw
        mode = "raw"
    elif args.ref:
        prompt = build_ref_prompt(args.expr, args.framing, args.scene or args.extra, args.style)
        mode = "ref"
    else:
        prompt = build_prompt(args.char, args.expr, args.style, args.framing, args.scene, args.extra)
        mode = "txt"
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()] or [args.seed]
    os.makedirs(args.outdir, exist_ok=True)

    if args.dry_run:
        print(json.dumps({"prompt": prompt, "size": size, "seeds": seeds}, ensure_ascii=False, indent=2))
        return

    for seed in seeds:
        if seed < 0:
            seed = int.from_bytes(os.urandom(4), "big") % 2_000_000_000
        raw, dt = (post_edit(prompt, size, seed, args.ref) if args.ref else post(prompt, size, seed))
        gw, gh = png_size(raw)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = "%s_%s_%s_%s%s_%s_%s" % (args.char, mode, args.expr, args.style, size,
                                        ("_" + args.tag) if args.tag else "", stamp)
        png = os.path.join(args.outdir, name + ".png")
        with open(png, "wb") as f:
            f.write(raw)
        with open(png[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump({"char": args.char, "expr": args.expr, "style": args.style,
                       "framing": args.framing, "size": size, "seed": seed,
                       "elapsed_s": round(dt, 3), "prompt": prompt,
                       "png": os.path.basename(png)}, f, ensure_ascii=False, indent=2)
        print("OK %5.2fs %dx%d %7.2f MB  %s" % (dt, gw, gh, len(raw) / 1048576, png))


if __name__ == "__main__":
    main()
