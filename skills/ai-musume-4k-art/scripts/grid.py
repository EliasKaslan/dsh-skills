"""Grid montage: fixed column count, keeps aspect, rows auto.

Usage: python grid.py <out.jpg> <cols> <col_w> <img...>
"""
import os
import sys

from PIL import Image


def main():
    out, cols, cw = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    paths = sys.argv[4:]
    ims = [Image.open(p).convert("RGB") for p in paths]
    scaled = [im.resize((cw, int(cw * im.size[1] / im.size[0])), Image.LANCZOS) for im in ims]
    rows = (len(scaled) + cols - 1) // cols
    ch = max(im.size[1] for im in scaled)
    cv = Image.new("RGB", (cw * cols, ch * rows), (22, 22, 26))
    for i, im in enumerate(scaled):
        cv.paste(im, ((i % cols) * cw, (i // cols) * ch))
    cv.save(out, "JPEG", quality=86, optimize=True)
    print(f"{out} {cv.size} {os.path.getsize(out)/1024:.0f}KB")


if __name__ == "__main__":
    main()
