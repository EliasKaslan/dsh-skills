#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Match a generated image's palette/contrast to a reference frame (Reinhard in Lab).

Why: MiniMax-H3-Image always renders "cleaner and glossier" than a 480p animation
frame, so even a perfect character match reads as a different art style. This
pulls the generated image back onto the reference's colour statistics.

Usage:
  python match_style.py GEN.png REF.png OUT.png [--strength 0.85] [--resize]
"""
import argparse
import os

import numpy as np
from PIL import Image, ImageFilter


def srgb_to_lab(a):
    # a: HxWx3 float in [0,1]
    m = a.reshape(-1, 3)
    m = np.where(m <= 0.04045, m / 12.92, ((m + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = m @ M.T
    white = np.array([0.95047, 1.0, 1.08883])
    xyz = xyz / white
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    L = 116 * f[:, 1] - 16
    A = 500 * (f[:, 0] - f[:, 1])
    B = 200 * (f[:, 1] - f[:, 2])
    return np.stack([L, A, B], 1).reshape(a.shape)


def lab_to_srgb(lab):
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16) / 116.0
    fx = fy + A / 500.0
    fz = fy - B / 200.0
    d = 6.0 / 29.0
    def inv(t):
        return np.where(t > d, t ** 3, 3 * d * d * (t - 4.0 / 29.0))
    xyz = np.stack([inv(fx), inv(fy), inv(fz)], -1)
    white = np.array([0.95047, 1.0, 1.08883])
    xyz = xyz * white
    Minv = np.linalg.inv(np.array([[0.4124, 0.3576, 0.1805],
                                   [0.2126, 0.7152, 0.0722],
                                   [0.0193, 0.1192, 0.9505]]))
    lin = xyz.reshape(-1, 3) @ Minv.T
    lin = np.clip(lin, 0, 1)
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return srgb.reshape(lab.shape)


def stats(lab):
    m = lab.reshape(-1, 3)
    return m.mean(0), m.std(0) + 1e-6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gen")
    ap.add_argument("ref")
    ap.add_argument("out")
    ap.add_argument("--strength", type=float, default=0.85)
    ap.add_argument("--soft", type=float, default=1.0,
                    help="downscale/upscale factor to shed edge energy (>1 = softer, like a 480p frame)")
    ap.add_argument("--blur", type=float, default=0.0, help="gaussian radius after softening")
    ap.add_argument("--gamma", type=float, default=1.0,
                    help="sRGB gamma lift after matching: 0.85 brightens midtones without clipping")
    ap.add_argument("--crop", default="", help="center-crop to WxH after everything (e.g. 3840x2160)")
    ap.add_argument("--resize", action="store_true", help="resize output to the reference's size")
    a = ap.parse_args()

    gen = Image.open(a.gen).convert("RGB")
    ref = Image.open(a.ref).convert("RGB")
    if a.soft and a.soft > 1.0:
        w, h = gen.size
        gen = gen.resize((max(1, int(w / a.soft)), max(1, int(h / a.soft))), Image.LANCZOS)
        gen = gen.resize((w, h), Image.LANCZOS)
    if a.blur and a.blur > 0:
        gen = gen.filter(ImageFilter.GaussianBlur(a.blur))
    if a.resize:
        gen = gen.resize(ref.size, Image.LANCZOS)

    g = np.asarray(gen).astype(np.float32) / 255.0
    r = np.asarray(ref).astype(np.float32) / 255.0
    gl, rl = srgb_to_lab(g), srgb_to_lab(r)
    gm, gs = stats(gl)
    rm, rs = stats(rl)
    sm = (1 - a.strength) * gm + a.strength * rm
    ss = (1 - a.strength) * gs + a.strength * rs
    out_lab = (gl - gm) / gs * ss + sm
    out = np.clip(lab_to_srgb(out_lab), 0, 1)
    if a.gamma and a.gamma != 1.0:
        # gamma on sRGB lifts midtones; highlights keep their roll-off instead of hard-clipping
        out = np.clip(out, 0, 1) ** a.gamma
    img = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    if a.crop:
        cw, ch = [int(v) for v in a.crop.lower().split("x")]
        w, h = img.size
        left, top = (w - cw) // 2, (h - ch) // 2
        img = img.crop((left, top, left + cw, top + ch))
    img.save(a.out)
    print("matched %s -> %s  (%dx%d, %.0f KB)" % (os.path.basename(a.gen), a.out,
                                                  img.size[0], img.size[1], os.path.getsize(a.out) / 1024))


if __name__ == "__main__":
    main()
