"""输出与元数据：PNG 内嵌提示词、JSON sidecar、拼图、图像体检。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, ImageFilter

CJK_FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def slugify(text: str, fallback: str = "image", limit: int = 48) -> str:
    t = re.sub(r"[\\/:*?\"<>|\s]+", "-", (text or "").strip())
    t = re.sub(r"-{2,}", "-", t).strip("-")
    if not t:
        return fallback
    return t[:limit]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in CJK_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def save_png(image: Image.Image, path: Path, meta: dict[str, Any]) -> Path:
    """保存 PNG，并把关键元数据写进 tEXt 块（可用 exiftool/PNG 查看器读取）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    for key, value in meta.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        info.add_text(str(key), str(value))
    image.convert("RGB").save(path, "PNG", pnginfo=info, optimize=True)
    return path


def save_sidecar(path: Path, meta: dict[str, Any]) -> Path:
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def read_png_text(path: Path) -> dict[str, str]:
    with Image.open(path) as im:
        return dict(getattr(im, "text", {}) or {})


# --------------------------------------------------------------------------
# 拼图
# --------------------------------------------------------------------------
def contact_sheet(
    entries: Iterable[tuple[Image.Image, str]],
    out_path: Path,
    *,
    cols: int = 2,
    tile_width: int = 640,
    pad: int = 16,
    bg: tuple[int, int, int] = (18, 20, 28),
    label_height: int = 34,
    tile_aspect: float = 0.75,
) -> Path:
    """把多张图拼成网格图。

    tile_aspect = 宽/高。默认 0.75（3:4）：所有格子统一裁成同比例再等比缩放，
    这样横图竖图混排也不会高低不齐。
    """
    items = [(im.convert("RGB"), label) for im, label in entries]
    if not items:
        raise ValueError("拼图为空：没有可用的图片")
    cols = max(1, min(cols, len(items)))
    rows = (len(items) + cols - 1) // cols

    cell_w = tile_width
    cell_h = max(1, int(round(tile_width / tile_aspect)))
    resized = []
    for im, label in items:
        resized.append((_crop_to_aspect(im, tile_aspect).resize((cell_w, cell_h), Image.LANCZOS), label))

    sheet = Image.new("RGB", (pad + cols * (cell_w + pad), pad + rows * (cell_h + label_height + pad)), bg)
    draw = ImageDraw.Draw(sheet)
    font = _font(20)
    for idx, (im, label) in enumerate(resized):
        r, c = divmod(idx, cols)
        x = pad + c * (cell_w + pad)
        y = pad + r * (cell_h + label_height + pad)
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + cell_h + 6), label[:64], fill=(226, 232, 240), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, "PNG", optimize=True)
    return out_path


def _crop_to_aspect(image: Image.Image, aspect: float) -> Image.Image:
    """居中裁剪到指定宽高比（多出来的部分裁掉，不拉伸）。"""
    w, h = image.size
    current = w / h
    if abs(current - aspect) < 0.01:
        return image
    if current > aspect:  # 太宽 → 裁两边
        new_w = int(round(h * aspect))
        left = (w - new_w) // 2
        return image.crop((left, 0, left + new_w, h))
    new_h = int(round(w / aspect))  # 太高 → 裁上下
    top = (h - new_h) // 2
    return image.crop((0, top, w, top + new_h))


# --------------------------------------------------------------------------
# 图像体检（自动化验收用）
# --------------------------------------------------------------------------
def image_stats(image: Image.Image) -> dict[str, Any]:
    """返回一组客观指标，用于判定「是否生成了有效图像」。"""
    rgb = image.convert("RGB")
    small = rgb.resize((256, 256), Image.LANCZOS)
    pixels = list(small.getdata())
    n = len(pixels)
    mean = [sum(p[i] for p in pixels) / n for i in range(3)]
    var = [sum((p[i] - mean[i]) ** 2 for p in pixels) / n for i in range(3)]
    std = [v ** 0.5 for v in var]

    uniq = len(set(pixels))
    # 边缘密度：越接近纯色，边缘越少
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_mean = sum(edges.getdata()) / n
    luma = small.convert("L")
    luma_vals = list(luma.getdata())
    dark_ratio = sum(1 for v in luma_vals if v < 8) / n
    bright_ratio = sum(1 for v in luma_vals if v > 247) / n

    return {
        "width": rgb.width,
        "height": rgb.height,
        "mean_rgb": [round(v, 1) for v in mean],
        "std_rgb": [round(v, 1) for v in std],
        "unique_colors_256": uniq,
        "edge_mean": round(edge_mean, 2),
        "dark_ratio": round(dark_ratio, 4),
        "bright_ratio": round(bright_ratio, 4),
    }


def looks_blank(stats: dict[str, Any]) -> tuple[bool, str]:
    """判定是否为无效图（纯色/全黑/全白/噪声极少/几乎无边缘）。"""
    if max(stats["std_rgb"]) < 3.0:
        return True, "画面几乎是纯色（std < 3）"
    if stats["dark_ratio"] > 0.97:
        return True, "画面几乎全黑"
    if stats["bright_ratio"] > 0.97:
        return True, "画面几乎全白"
    if stats["unique_colors_256"] < 96:
        return True, f"颜色数过少（{stats['unique_colors_256']}），疑似纯色图"
    if stats["edge_mean"] < 0.6:
        return True, "几乎没有细节（边缘密度过低），疑似噪声图"
    return False, ""


def build_meta(
    *,
    preset_id: str,
    preset_name: str,
    style_id: str,
    composition: str,
    plan: dict[str, Any],
    seed: int,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    sampler: str,
    model_path: str,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "generator": "dsh-skill anime-art",
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "preset": {"id": preset_id, "name": preset_name},
        "style": style_id,
        "composition": composition,
        "width": width,
        "height": height,
        "seed": seed,
        "steps": steps,
        "cfg": cfg,
        "sampler": sampler,
        "model": Path(model_path).name,
        "prompt": plan.get("prompt", ""),
        "negative_prompt": plan.get("negative_prompt", ""),
    }
    if extras:
        meta.update(extras)
    return meta
