#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Key out a flat studio background -> transparent PNG.

Why border-connected: anime characters often wear white/light clothes. A plain
"colour distance" key would punch holes in a white blouse; only the region that
is connected to the image border is background.

Usage: python key_out.py IN.png OUT.png [--tol 26] [--feather 1.5] [--scale 4]
"""
import argparse
from collections import deque

import numpy as np
from PIL import Image, ImageFilter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--tol", type=float, default=26.0, help="colour distance to the background colour")
    ap.add_argument("--feather", type=float, default=1.5, help="alpha feather radius in px")
    ap.add_argument("--scale", type=int, default=4, help="BFS runs at 1/scale resolution")
    a = ap.parse_args()

    im = Image.open(a.src).convert("RGB")
    W, H = im.size
    arr = np.asarray(im).astype(np.float32)

    # background colour = median of the border strip
    b = max(4, min(W, H) // 50)
    strip = np.concatenate([arr[:b].reshape(-1, 3), arr[-b:].reshape(-1, 3),
                            arr[:, :b].reshape(-1, 3), arr[:, -b:].reshape(-1, 3)])
    bg = np.median(strip, axis=0)
    dist = np.sqrt(((arr - bg) ** 2).sum(-1))

    s = max(1, a.scale)
    small = dist[::s, ::s]
    mask = small < a.tol
    h, w = mask.shape

    # BFS from every border pixel that is already background-coloured
    seen = np.zeros_like(mask, dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))

    alpha_small = Image.fromarray(np.where(seen, 0, 255).astype(np.uint8))
    alpha = alpha_small.resize((W, H), Image.NEAREST)
    if a.feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(a.feather))

    out = im.convert("RGBA")
    out.putalpha(alpha)
    out.save(a.dst)

    a_np = np.asarray(alpha)
    print("keyed %s -> %s  bg=#%02X%02X%02X  transparent=%.1f%%  feather=%.1f"
          % (a.src.split("\\")[-1], a.dst.split("\\")[-1],
             int(bg[0]), int(bg[1]), int(bg[2]),
             100.0 * (a_np < 8).mean(), a.feather))


if __name__ == "__main__":
    main()
