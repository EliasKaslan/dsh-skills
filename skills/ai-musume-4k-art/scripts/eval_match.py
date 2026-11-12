#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quantify "does the generated image match the reference frame's art style?"

Metrics vs the reference frame (all cheap, no model needed):
  dE_mean   mean Lab distance of the image's mean colour   (lower = closer palette)
  dE_std    Lab distance of the per-channel std            (lower = closer contrast)
  sat_diff  saturation mean difference                      (lower = closer vividness)
  val_diff  brightness (L) mean difference
  edge_ratio  edge energy of generated / reference          (>1 = crisper than source)

Verdict: dE_mean<=8 and abs(edge_ratio-1)<=0.35 -> "style-closed".

Usage: python eval_match.py GEN.png REF.png [GEN2.png REF2.png ...]
"""
import itertools
import sys

import numpy as np
from PIL import Image, ImageFilter


def srgb_to_lab(a):
    m = a.reshape(-1, 3)
    m = np.where(m <= 0.04045, m / 12.92, ((m + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (m @ M.T) / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])],
                    1).reshape(a.shape)


def sat_val(a):
    mx = a.max(-1)
    mn = a.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return float(sat.mean()), float(mx.mean())


def edge_energy(im, size=512):
    g = im.convert("L").resize((size, size), Image.LANCZOS)
    e = g.filter(ImageFilter.FIND_EDGES)
    return float(np.asarray(e, dtype=np.float32).mean())


def compare(gen_path, ref_path):
    g = Image.open(gen_path).convert("RGB")
    r = Image.open(ref_path).convert("RGB")
    ga = np.asarray(g).astype(np.float32) / 255.0
    ra = np.asarray(r).astype(np.float32) / 255.0
    gl, rl = srgb_to_lab(ga), srgb_to_lab(ra)
    dm = float(np.linalg.norm(gl.reshape(-1, 3).mean(0) - rl.reshape(-1, 3).mean(0)))
    ds = float(np.linalg.norm(gl.reshape(-1, 3).std(0) - rl.reshape(-1, 3).std(0)))
    gs, gv = sat_val(ga)
    rs, rv = sat_val(ra)
    er = edge_energy(g) / max(edge_energy(r), 1e-6)
    ok = dm <= 8.0 and abs(er - 1.0) <= 0.35
    return dict(dE_mean=round(dm, 2), dE_std=round(ds, 2), sat_diff=round(gs - rs, 3),
                val_diff=round(gv - rv, 3), edge_ratio=round(er, 2), ok=ok)


def main():
    pairs = list(itertools.zip_longest(sys.argv[1::2], sys.argv[2::2]))
    pairs = [(g, r) for g, r in pairs if g and r]
    if not pairs:
        print(__doc__)
        return 1
    print("%-46s %7s %7s %8s %8s %10s %s" % ("generated", "dE_mean", "dE_std", "sat_d", "val_d", "edge_ratio", "verdict"))
    n_ok = 0
    for g, r in pairs:
        m = compare(g, r)
        n_ok += m["ok"]
        name = g.split("\\")[-1][:46]
        print("%-46s %7.2f %7.2f %8.3f %8.3f %10.2f %s" % (name, m["dE_mean"], m["dE_std"], m["sat_diff"],
                                                           m["val_diff"], m["edge_ratio"],
                                                           "OK" if m["ok"] else "off"))
    print("\nstyle-closed %d/%d" % (n_ok, len(pairs)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
