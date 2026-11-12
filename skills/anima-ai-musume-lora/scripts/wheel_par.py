#!/usr/bin/env python3
"""Resolve a wheel from the aliyun simple index and download it with N ranged connections."""
import concurrent.futures as cf
import hashlib
import os
import re
import sys
import urllib.parse
import urllib.request

IDX = "https://mirrors.aliyun.com/pypi/simple/%s/"
OUT = "/tmp/wheels"


def resolve(pkg, ver=None):
    idx = IDX % pkg
    html = urllib.request.urlopen(idx, timeout=60).read().decode("utf-8", "replace")
    from packaging.version import parse as vparse
    cands = []
    for href in re.findall(r'href="([^"]+)"', html):
        clean = href.split("#")[0]
        if not clean.endswith(".whl"):
            continue
        name = clean.rsplit("/", 1)[-1]
        if ver and ver not in name:
            continue
        score = 0
        if "py3-none-any" in name:
            score += 50
        if "cp312" in name:
            score += 40
        if "abi3" in name:
            score += 30
        if "manylinux" in name and "x86_64" in name:
            score += 40
        for bad in ("win", "macosx", "aarch64", "musllinux", "cp313", "cp314",
                    "ppc", "s390", "i686", "arm64"):
            if bad in name:
                score -= 100
        parts = name[:-4].split("-")
        try:
            verobj = vparse(parts[1])
        except Exception:
            continue
        cands.append((score, verobj, urllib.parse.urljoin(idx, clean), name))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[0], x[1]))
    return (cands[-1][2], cands[-1][3])


def head_size(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers.get("Content-Length", 0))


def fetch_range(url, s, e, dst):
    req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (s, e)})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def main():
    pkg, ver = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    got = resolve(pkg, ver)
    if not got:
        print("NO_WHEEL", pkg, ver)
        sys.exit(1)
    url, name = got
    size = head_size(url)
    os.makedirs(OUT, exist_ok=True)
    dst = os.path.join(OUT, name)
    print("URL", url, "SIZE", size, flush=True)
    chunk = (size + n - 1) // n
    parts = []
    jobs = []
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        for i in range(n):
            s = i * chunk
            e = min(s + chunk - 1, size - 1)
            p = dst + ".part%d" % i
            parts.append(p)
            jobs.append(ex.submit(fetch_range, url, s, e, p))
        for j in jobs:
            j.result()
    with open(dst, "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                out.write(f.read())
            os.remove(p)
    real = os.path.getsize(dst)
    sha = hashlib.sha256(open(dst, "rb").read()).hexdigest()
    print("DONE", dst, real, sha, flush=True)


if __name__ == "__main__":
    main()
