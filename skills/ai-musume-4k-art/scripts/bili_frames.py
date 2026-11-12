"""Grab character stills from a bilibili video, for LoRA datasets.

Why this shape:
  - the video page is 412-blocked from a datacenter IP, so yt-dlp's HTML scrape
    fails; the JSON APIs still answer, so we go view -> playurl -> stream;
  - the playurl CDN list includes hosts that are unroutable here, so ALL of
    baseUrl + backupUrl are tried in order;
  - no system ffmpeg on the box, so imageio-ffmpeg supplies a static binary;
  - raw frames are 480p and full of UI, so we screen on the character's blue hair
    and crop a fixed box (the show's layout is constant) before anything else.

Usage (inside the container with venv-qwen):
    python bili_frames.py BV14C456WEXN --out /home/vllm/ai-musume/lora_data
    python bili_frames.py BV14C456WEXN --picks 01482,01308 --no-download

Outputs: <out>/video/src.mp4, <out>/frames/*.jpg, <out>/real/*.png, <out>/sheets_real/
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REF = "https://www.bilibili.com/"


def http(url, headers=None, timeout=40, method="GET"):
    h = {"User-Agent": UA, "Referer": REF}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read() if method == "GET" else b""


def cookie_header(jar):
    if not os.path.exists(jar):
        return ""
    kv = []
    for line in open(jar, encoding="utf-8", errors="replace"):
        if line.startswith("#") or "\t" not in line:
            continue
        f = line.strip().split("\t")
        if len(f) >= 7:
            kv.append("%s=%s" % (f[5], f[6]))
    return "; ".join(kv)


def warm_cookies(out_dir):
    """bilibili answers 412 without a browser cookie; the homepage hands out buvid."""
    jar = os.path.join(out_dir, "bili_cookies.txt")
    if os.path.exists(jar) and os.path.getsize(jar) > 100:
        return cookie_header(jar)
    subprocess.run(["curl", "-s", "-o", os.devnull, "-c", jar, "--max-time", "25",
                    "-H", "User-Agent: " + UA, REF], check=False)
    return cookie_header(jar)


def api(url, ck):
    return json.loads(http(url, {"Accept": "application/json", "Cookie": ck})
                      .decode("utf-8", "replace"))


def download(bv, out_dir):
    ck = warm_cookies(out_dir)
    v = api("https://api.bilibili.com/x/web-interface/view?bvid=%s" % bv, ck)
    if v.get("code") != 0:
        raise SystemExit("view api: %s %s" % (v.get("code"), v.get("message")))
    d = v["data"]
    cid = (d.get("pages") or [{}])[0].get("cid") or d["cid"]
    print("title=%s  duration=%ss  cid=%s" % (d["title"], d["duration"], cid))

    cands = []
    for fnval, qn in ((16, 80), (16, 64), (1, 64), (1, 32)):
        try:
            p = api("https://api.bilibili.com/x/player/playurl?bvid=%s&cid=%s&qn=%d"
                    "&fnval=%d&fnver=0&fourk=1" % (bv, cid, qn, fnval), ck)
        except Exception:                               # noqa: BLE001
            continue
        if p.get("code") != 0:
            continue
        data = p.get("data") or {}
        if data.get("dash"):
            vids = sorted(data["dash"].get("video") or [],
                          key=lambda x: -(x.get("height") or 0))
            if vids:
                print("  dash %dx%d" % (vids[0].get("width", 0), vids[0].get("height", 0)))
                cands += [vids[0].get("baseUrl") or vids[0].get("base_url")]
                cands += vids[0].get("backupUrl") or vids[0].get("backup_url") or []
                break
        if data.get("durl"):
            cands += [x.get("url") for x in data["durl"] if x.get("url")]
            break

    dst = os.path.join(out_dir, "video", "src.mp4")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    for url in [c for c in cands if c]:
        host = urllib.parse.urlparse(url).netloc
        print("  try", host)
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REF}),
                    timeout=40) as r, open(dst, "wb") as fh:
                while True:
                    buf = r.read(1 << 20)
                    if not buf:
                        break
                    fh.write(buf)
            if os.path.getsize(dst) > 1 << 20:
                print("  ok %.1f MB" % (os.path.getsize(dst) / 1e6))
                return dst
        except Exception as exc:                        # noqa: BLE001
            print("    fail", repr(exc)[:70])
    raise SystemExit("all CDN hosts failed")


def extract(video, frames_dir, fps):
    os.makedirs(frames_dir, exist_ok=True)
    if os.listdir(frames_dir):
        print("frames already there:", len(os.listdir(frames_dir)))
        return
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", video,
                    "-vf", "fps=%g" % fps, "-q:v", "2",
                    os.path.join(frames_dir, "%05d.jpg")], check=True)
    print("extracted", len(os.listdir(frames_dir)))


def screen(frames_dir, top=60):
    """Rank frames by how much of the frame is saturated blue (the character's hair)."""
    rows = []
    for name in sorted(os.listdir(frames_dir)):
        p = os.path.join(frames_dir, name)
        try:
            im = Image.open(p).convert("RGB")
        except Exception:                               # noqa: BLE001
            continue
        small = im.resize((320, int(320 * im.height / im.width)), Image.LANCZOS)
        a = np.asarray(small, dtype=np.float32) / 255.0
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        mx, mn = a.max(2), a.min(2)
        sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
        blue = float(((b > r + 0.08) & (sat > 0.22) & (mx > 0.25)).mean())
        rows.append((blue, name))
    rows.sort(reverse=True)
    return [n for _, n in rows[:top]]


def crop(frames_dir, names, out_dir, box, scale):
    for d in (out_dir, os.path.join(out_dir, "..", "sheets_real")):
        pass
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for name in names:
        p = os.path.join(frames_dir, name)
        im = Image.open(p).convert("RGB")
        W, H = im.size
        c = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
        if scale != 1:
            c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
        dst = os.path.join(out_dir, os.path.splitext(name)[0] + ".png")
        c.save(dst)
        made.append((dst, c.size))
    return made


def sheet(made, path, cols=6, cell=240):
    rows = max(1, (len(made) + cols - 1) // cols)
    im0 = Image.new("RGB", (cols * (cell + 6), rows * (cell + 24)), (22, 22, 26))
    dr = ImageDraw.Draw(im0)
    for j, (p, size) in enumerate(made):
        im = Image.open(p)
        im.thumbnail((cell, cell), Image.LANCZOS)
        x = (j % cols) * (cell + 6) + 3
        y = (j // cols) * (cell + 24) + 18
        dr.text((x, y - 14), "%s %dx%d" % (os.path.basename(p)[:5], size[0], size[1]),
                fill=(235, 235, 235))
        im0.paste(im, (x, y))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im0.save(path, quality=90)
    print("sheet ->", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bv")
    ap.add_argument("--out", default="/home/vllm/ai-musume/lora_data")
    ap.add_argument("--fps", type=float, default=1.0)
    ap.add_argument("--picks", default="", help="逗号分隔的帧号，如 01482,01308")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--box", default="0.29,0.09,0.73,0.76",
                    help="归一化裁剪框 x0,y0,x1,y1；要避开字幕条")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()

    video = os.path.join(a.out, "video", "src.mp4")
    if not a.no_download and not os.path.exists(video):
        video = download(a.bv, a.out)
    frames = os.path.join(a.out, "frames")
    extract(video, frames, a.fps)

    picks = [p.strip() for p in a.picks.split(",") if p.strip()]
    if not picks:
        picks = screen(frames, a.top)
        print("auto-picked top %d by blue ratio: %s" % (len(picks), ", ".join(picks[:10])))
    box = [float(x) for x in a.box.split(",")]
    made = crop(frames, picks, os.path.join(a.out, "real"), box, a.scale)
    sheet(made, os.path.join(a.out, "sheets_real", "real.jpg"))
    print("crops: %d -> %s" % (len(made), os.path.join(a.out, "real")))


if __name__ == "__main__":
    sys.exit(main())
