#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Contact sheet + hash for AI-musume acceptance (keeps context small).

Usage:
  python sheet.py OUT.jpg COLS TILE_PX file1.png file2.png ...
  python sheet.py OUT.jpg 4 448 "glob:C:\\path\\*.png"
"""
import glob
import hashlib
import os
import sys

from PIL import Image, ImageDraw


def collect(args):
    files = []
    for a in args:
        if a.startswith("glob:"):
            files.extend(sorted(glob.glob(a[5:])))
        else:
            files.append(a)
    return [f for f in files if os.path.isfile(f)]


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 1
    out, cols, tile = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    files = collect(sys.argv[4:])
    if not files:
        print("no input files")
        return 1
    thumbs = []
    for f in files:
        im = Image.open(f).convert("RGB")
        im.thumbnail((tile, tile), Image.LANCZOS)
        thumbs.append((f, im))
        h = hashlib.sha256(open(f, "rb").read()).hexdigest()[:16]
        print("%s  %dx%d  %s" % (h, im.size[0], im.size[1], os.path.basename(f)))
    cw = max(t[1].size[0] for t in thumbs)
    ch = max(t[1].size[1] for t in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cw * cols, ch * rows), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, (f, im) in enumerate(thumbs):
        x = (i % cols) * cw + (cw - im.size[0]) // 2
        y = (i // cols) * ch
        sheet.paste(im, (x, y))
        d.text((x + 4, y + ch - 14), os.path.basename(f)[: 40], fill=(255, 235, 120))
    sheet.save(out, quality=85)
    print("sheet=%s  %dx%d  %.0f KB" % (out, sheet.size[0], sheet.size[1], os.path.getsize(out) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
