#!/usr/bin/env python3
"""Skill catalog budget checker (read-only unless --write-index).

The DSH skill catalog is injected as one user message and re-sent with every
request, so hot entries are a fixed cost. This script measures that cost and
regenerates the warm-tier index.

Usage:
    python skill_budget.py                 # report hot/warm + catalog chars
    python skill_budget.py --json          # machine-readable
    python skill_budget.py --write-index   # rewrite skills-archive/INDEX.json, then report

Exit codes: 0 = within budget, 1 = over budget (hot count / chars / description),
2 = usage error.
"""

import argparse
import io
import json
import os
import re
import sys

HOT_LIMIT = 40
CHAR_LIMIT = 7000
DESC_LIMIT = 120


def dsh_home() -> str:
    env = os.environ.get("DSH_HOME", "").strip()
    return os.path.abspath(env) if env else os.path.join(os.path.expanduser("~"), ".dsh")


def field(frontmatter: str, key: str) -> str:
    match = re.search(r"^" + re.escape(key) + r":[ \t]*(.*)$", frontmatter, re.M)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.startswith('"'):
        try:
            return json.loads(value)
        except Exception:
            return value.strip('"')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def scan(home: str):
    roots = [
        os.path.join(home, "skills"),
        os.path.join(os.path.expanduser("~"), ".agents", "skills"),
    ]
    hot, warm, problems = [], [], []
    seen = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            directory = os.path.join(root, name)
            path = os.path.join(directory, "SKILL.md") if os.path.isdir(directory) else directory
            if not os.path.isfile(path) or not name.endswith(".md") and not os.path.isdir(directory):
                continue
            skill_name = name if os.path.isdir(directory) else name[:-3]
            if skill_name in seen:
                continue
            with io.open(path, "r", encoding="utf-8", newline="") as handle:
                text = handle.read()
            if text.startswith("\ufeff"):
                text = text[1:]
            match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
            if not match:
                problems.append(f"{skill_name}: 无合法 YAML frontmatter（不会被加载）")
                continue
            frontmatter = match.group(1)
            description = field(frontmatter, "description")
            declared = field(frontmatter, "name")
            if not description:
                problems.append(f"{skill_name}: frontmatter 缺 description")
                continue
            if declared and declared != skill_name:
                problems.append(f'{skill_name}: frontmatter name "{declared}" 与目录名不一致')
            seen.add(skill_name)
            entry = {
                "name": skill_name,
                "path": path,
                "description": description,
                "descLen": len(description),
            }
            if field(frontmatter, "disable-model-invocation").lower() == "true":
                entry["triggers"] = field(frontmatter, "warm-triggers") or description
                entry["reason"] = field(frontmatter, "warm-reason")
                warm.append(entry)
            else:
                hot.append(entry)
    chars = sum(len(item["name"]) + item["descLen"] + 4 for item in hot)
    return hot, warm, chars, problems


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="DSH skill catalog budget checker")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-index", action="store_true")
    parser.add_argument("--home", default=None)
    args = parser.parse_args(argv)

    home = os.path.abspath(args.home) if args.home else dsh_home()
    hot, warm, chars, problems = scan(home)
    over = [item for item in hot if item["descLen"] > DESC_LIMIT]

    if args.write_index:
        archive = os.path.join(home, "skills-archive")
        os.makedirs(archive, exist_ok=True)
        index = {
            "generatedAt": "auto",
            "note": "冷备 skill 索引：前台目录不包含这些 skill；任务相关时先读本文件，再按 path 读取 SKILL.md。",
            "hotCount": len(hot),
            "warmCount": len(warm),
            "catalogChars": chars,
            "entries": [
                {
                    "name": item["name"],
                    "triggers": item["triggers"],
                    "reason": item.get("reason", ""),
                    "path": item["path"],
                    "scope": "user",
                }
                for item in warm
            ],
        }
        with io.open(os.path.join(archive, "INDEX.json"), "w", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")

    ok = len(hot) <= HOT_LIMIT and chars <= CHAR_LIMIT and not over
    report = {
        "ok": ok,
        "home": home,
        "hot": len(hot),
        "warm": len(warm),
        "hotLimit": HOT_LIMIT,
        "catalogChars": chars,
        "catalogCharLimit": CHAR_LIMIT,
        "descLimit": DESC_LIMIT,
        "overDescLimit": [{"name": item["name"], "descLen": item["descLen"]} for item in over],
        "problems": problems,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"hot {len(hot)}/{HOT_LIMIT}  warm {len(warm)}  catalog {chars}/{CHAR_LIMIT} chars")
        if over:
            print("description 超预算:")
            for item in over:
                print(f"  - {item['name']}: {item['descLen']} > {DESC_LIMIT}")
        if problems:
            print("其它问题:")
            for item in problems:
                print("  - " + item)
        if ok:
            print("预算内 ✓")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
