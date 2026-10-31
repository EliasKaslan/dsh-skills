#!/usr/bin/env python3
"""Fetch full PR bodies for every merged PR in a collected run, cleaned and capped."""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_lora_week as C  # reuse token + gh()


def clean(body):
    if not body:
        return ""
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    body = re.sub(r"<details>.*?</details>", " ", body, flags=re.S)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"^---+\s*$", "", body, flags=re.M)
    lines = []
    for ln in body.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if s.startswith("## "):
            lines.append("[%s] " % s[3:].strip())
        elif s.startswith("#"):
            lines.append("[%s] " % s.lstrip("#").strip())
        else:
            lines.append(s)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text)
    return text


def main():
    run = sys.argv[1]
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    data = json.load(io.open(os.path.join(run, "lora_prs.json"), encoding="utf-8"))
    merged = data["merged"]
    out = ["# PR 详情（按合入时间正序）", ""]
    for label in ("vLLM", "vLLM-Ascend", "SGLang"):
        rows = sorted([x for x in merged if x["repo"] == label], key=lambda x: x["merged_at"])
        out.append("## %s（%d）" % (label, len(rows)))
        for x in rows:
            p = C.gh("%s/repos/%s/pulls/%d" % (C.API, x["repo_full"], x["number"]))
            body = clean(p.get("body"))
            if len(body) > cap:
                body = body[:cap] + "…"
            out.append("### #%d  %s  +%d/-%d f%d  %s" % (
                x["number"], x["merged_cst"][5:16], x["additions"], x["deletions"],
                x["files"], x["title"]))
            out.append(body if body else "(no body)")
            out.append("")
    path = os.path.join(run, "details.md")
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print("written:", path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
