#!/usr/bin/env python3
"""Collect merged PRs for the LoRA weekly report.

Outputs (into --out):
  lora_prs.json   full record of every merged PR in the window
  worksheet.md    compact worksheet the agent reads to write the report

Usage:
  python collect_lora_week.py --out "D:\\workspace\\LoRA特性跟踪\\runs\\2026-10-30"
  python collect_lora_week.py --days 7                # last 7 days, ends now
  python collect_lora_week.py --start 2026-10-23 --end 2026-10-30
  python collect_lora_week.py --keyword lora --days 14
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
TOKEN_PATH = os.path.expanduser(os.path.join("~", ".dsh", ".secrets", "github-pr-flow.token"))
CST = dt.timezone(dt.timedelta(hours=8))
REPOS = [
    ("vLLM", "vllm-project/vllm"),
    ("vLLM-Ascend", "vllm-project/vllm-ascend"),
    ("SGLang", "sgl-project/sglang"),
]


def read_token():
    if not os.path.exists(TOKEN_PATH):
        sys.exit("missing GitHub token: %s" % TOKEN_PATH)
    tok = open(TOKEN_PATH, encoding="utf-8").read().strip()
    if not tok:
        sys.exit("empty token file: %s" % TOKEN_PATH)
    return tok


TOKEN = read_token()
HEADERS = {
    "User-Agent": "dsh-lora-weekly",
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
}


def gh(url, params=None, tries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            last = "HTTP %s %s" % (e.code, body)
            if e.code in (403, 429, 502):
                time.sleep(3 * (attempt + 1))
                continue
            break
        except Exception as e:  # noqa: BLE001
            last = repr(e)
            time.sleep(2)
    raise RuntimeError("%s -> %s" % (url, last))


def search(repo, qualifiers, sort="updated", per_page=100):
    q = "repo:%s %s" % (repo, qualifiers)
    data = gh(API + "/search/issues", {
        "q": q, "sort": sort, "order": "desc", "per_page": per_page,
    })
    return data.get("items", []), data.get("total_count", 0)


def parse_utc(s):
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def fmt_cst(d):
    return d.astimezone(CST).strftime("%Y-%m-%d %H:%M")


def one_line(text, limit=220):
    if not text:
        return ""
    text = " ".join(text.split())
    return text[:limit] + ("…" if len(text) > limit else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start", help="YYYY-MM-DD (CST, inclusive)")
    ap.add_argument("--end", help="YYYY-MM-DD (CST, inclusive) or 'now'")
    ap.add_argument("--keyword", default="lora")
    ap.add_argument("--any", action="store_true",
                    help="match keyword anywhere (title+body), not just title")
    ap.add_argument("--out", default=".")
    ap.add_argument("--open-candidates", type=int, default=5)
    args = ap.parse_args()

    if args.start or args.end:
        start = dt.datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=CST) if args.start \
            else dt.datetime.now(CST) - dt.timedelta(days=args.days)
        if args.end in (None, "now"):
            end = dt.datetime.now(CST)
        else:
            end = dt.datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=CST) + dt.timedelta(days=1)
    else:
        end = dt.datetime.now(CST)
        start = end - dt.timedelta(days=args.days)

    start_utc, end_utc = start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)
    since = start_utc.strftime("%Y-%m-%d")
    os.makedirs(args.out, exist_ok=True)

    merged_all, open_all = [], []
    scope = "" if args.any else " in:title"
    for label, repo in REPOS:
        items, total = search(
            repo, "is:pr is:merged %s%s merged:>=%s" % (args.keyword, scope, since))
        kept = []
        for it in items:
            m = it.get("pull_request", {}).get("merged_at")
            if not m:
                continue
            when = parse_utc(m)
            if not (start_utc <= when <= end_utc):
                continue
            num = it["number"]
            det = gh("%s/repos/%s/pulls/%d" % (API, repo, num))
            kept.append({
                "repo": label,
                "repo_full": repo,
                "number": num,
                "title": it["title"],
                "url": it["html_url"],
                "merged_at": m,
                "merged_cst": fmt_cst(when),
                "additions": det.get("additions", 0),
                "deletions": det.get("deletions", 0),
                "files": det.get("changed_files", 0),
                "author": (it.get("user") or {}).get("login", ""),
                "body": det.get("body") or "",
            })
        kept.sort(key=lambda x: x["merged_at"], reverse=True)
        merged_all.extend(kept)
        print("%-12s merged=%2d  (search total=%d)" % (label, len(kept), total))

        if args.open_candidates > 0:
            oitems, _ = search(repo, "is:pr is:open %s in:title" % args.keyword, per_page=50)
            cand = [{
                "repo": label,
                "number": it["number"],
                "title": it["title"],
                "url": it["html_url"],
                "updated_cst": fmt_cst(parse_utc(it["updated_at"])),
                "created_cst": fmt_cst(parse_utc(it["created_at"])),
                "draft": bool(it.get("draft")),
            } for it in oitems if parse_utc(it["updated_at"]) >= start_utc]
            open_all.extend(cand[:args.open_candidates])

    json_path = os.path.join(args.out, "lora_prs.json")
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({
            "window": {"start_cst": start.strftime("%Y-%m-%d %H:%M"),
                       "end_cst": end.strftime("%Y-%m-%d %H:%M"),
                       "keyword": args.keyword},
            "merged": merged_all,
            "open_candidates": open_all,
        }, f, ensure_ascii=False, indent=1)

    lines = ["# 采集工作表", "",
             "窗口：%s ~ %s（北京时间）　主题：%s" % (
                 start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M"), args.keyword),
             "", "合入合计：%d（%s）" % (
                 len(merged_all),
                 "、".join("%s %d" % (l, sum(1 for x in merged_all if x["repo"] == l)) for l, _ in REPOS)),
             ""]
    for label, repo in REPOS:
        rows = [x for x in merged_all if x["repo"] == label]
        lines.append("## %s（%d 个合入）" % (label, len(rows)))
        if not rows:
            lines.append("（本周无）")
        for x in rows:
            lines.append("- #%d  %s  +%d/-%d  f%d  %s" % (
                x["number"], x["merged_cst"][5:16], x["additions"], x["deletions"],
                x["files"], x["url"]))
            lines.append("  %s" % x["title"])
            if x["body"]:
                lines.append("  body: %s" % one_line(x["body"], 240))
        lines.append("")
    if open_all:
        lines.append("## 未合入候选（仅在很值得关注时写 1-2 条，需要规模就单独查 /pulls/{n}）")
        for x in open_all:
            lines.append("- [%s] #%d %s  updated=%s%s" % (
                x["repo"], x["number"], x["title"], x["updated_cst"][:10],
                "  (draft)" if x["draft"] else ""))
        lines.append("")

    ws_path = os.path.join(args.out, "worksheet.md")
    with open(ws_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print("json     :", json_path)
    print("worksheet:", ws_path)
    print("window   : %s ~ %s CST" % (
        start.strftime("%Y-%m-%d %H:%M"), end.strftime("%Y-%m-%d %H:%M")))


if __name__ == "__main__":
    main()
