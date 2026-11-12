"""Horizontal montage of differently-sized images (scale to a fixed width).

Usage: python review_matrix.py <out.jpg> <col_w> <img1> <img2> ...
"""
import os
import sys

from PIL import Image


def main():
    out, cw = sys.argv[1], int(sys.argv[2])
    paths = sys.argv[3:]
    ims = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((cw, int(cw * im.size[1] / im.size[0])), Image.LANCZOS))
    H = max(i.size[1] for i in ims)
    cv = Image.new("RGB", (cw * len(ims), H), (20, 20, 24))
    for i, im in enumerate(ims):
        cv.paste(im, (i * cw, 0))
    cv.save(out, "JPEG", quality=88, optimize=True)
    print(f"{out} {cv.size} {os.path.getsize(out)/1024:.0f}KB")


if __name__ == "__main__":
    main()
