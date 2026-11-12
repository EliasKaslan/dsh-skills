"""Build small review images so the agent never has to read a multi-MB PNG.

Usage:
  python review_sheet.py sheet <out.jpg> <img1> <img2> ...   # row-wise contact sheet
  python review_sheet.py crop  <in.png> <out.jpg> <x> <y> <w> <h>   # 100% crop, capped to 900px
"""
import io
import os
import sys

from PIL import Image

MAX_W = 1400   # sheet width cap
MAX_H = 1900   # sheet height cap


def sheet(out, paths, panel_w=440):
    imgs = [Image.open(p).convert("RGB") for p in paths]
    cols = 3 if len(paths) > 2 else len(paths)
    rows = (len(imgs) + cols - 1) // cols
    # panel height follows the aspect of the first image
    ar = imgs[0].size[1] / imgs[0].size[0]
    panel_h = int(panel_w * ar)
    W, H = cols * panel_w, rows * panel_h
    scale = min(1.0, MAX_W / W, MAX_H / H)
    W, H = int(W * scale), int(H * scale)
    pw, ph = W // cols, H // rows
    canvas = Image.new("RGB", (W, H), (24, 24, 28))
    for i, im in enumerate(imgs):
        im = im.resize((pw, ph), Image.LANCZOS)
        canvas.paste(im, ((i % cols) * pw, (i // cols) * ph))
    canvas.save(out, "JPEG", quality=86, optimize=True)
    print(f"{out} {canvas.size} {os.path.getsize(out)/1024:.0f}KB from {len(paths)} imgs")


def crop(src, out, x, y, w, h, maxw=900):
    im = Image.open(src).convert("RGB")
    print(f"src size={im.size}")
    box = (max(0, x), max(0, y), min(im.size[0], x + w), min(im.size[1], y + h))
    im = im.crop(box)
    if im.size[0] > maxw:
        im = im.resize((maxw, int(im.size[1] * maxw / im.size[0])), Image.LANCZOS)
    im.save(out, "JPEG", quality=90, optimize=True)
    print(f"{out} {im.size} {os.path.getsize(out)/1024:.0f}KB")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sheet":
        sheet(sys.argv[2], sys.argv[3:])
    elif cmd == "crop":
        crop(sys.argv[2], sys.argv[3], *[int(v) for v in sys.argv[4:8]])
