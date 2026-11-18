#!/usr/bin/env python3
"""Skill budget checker (read-only unless --write-index).

Two budgets, because two different costs:

* catalog: every hot skill contributes one `name: description` line to a user
  message that is re-sent with every request.
* body: the whole SKILL.md text enters the context whenever the skill is
  loaded, so the body must stay a router plus the facts that matter. Long
  detail belongs in references/.

Usage:
    python skill_budget.py                 # report
    python skill_budget.py --json          # machine-readable
    python skill_budget.py --top 10        # list this many largest bodies
    python skill_budget.py --write-index   # rewrite skills-archive/INDEX.json

Exit codes: 0 = within budget, 1 = over budget, 2 = usage error.
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
BODY_LIMIT = 8000
WARM_BODY_LIMIT = 16000
SECTION_LIMIT = 8


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
            is_dir = os.path.isdir(directory)
            if is_dir:
                path = os.path.join(directory, "SKILL.md")
            elif name.endswith(".md"):
                path = directory
            else:
                continue
            if not os.path.isfile(path):
                continue
            skill_name = name if is_dir else name[:-3]
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
            body = text[match.end():]
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
                "bodyBytes": len(body.encode("utf-8")),
                "sections": len(re.findall(r"^## ", body, re.M)),
            }
            if field(frontmatter, "disable-model-invocation").lower() == "true":
                entry["triggers"] = field(frontmatter, "warm-triggers") or description
                entry["reason"] = field(frontmatter, "warm-reason")
                warm.append(entry)
            else:
                hot.append(entry)
    chars = sum(len(item["name"]) + item["descLen"] + 4 for item in hot)
    return hot, warm, chars, problems


def over_body(entries, limit):
    return [
        item
        for item in entries
        if item["bodyBytes"] > limit or item["sections"] > SECTION_LIMIT
    ]


def main(argv) -> int:
    parser = argparse.ArgumentParser(description="DSH skill budget checker")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-index", action="store_true")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--home", default=None)
    args = parser.parse_args(argv)

    home = os.path.abspath(args.home) if args.home else dsh_home()
    hot, warm, chars, problems = scan(home)
    over_desc = [item for item in hot if item["descLen"] > DESC_LIMIT]
    over_hot_body = over_body(hot, BODY_LIMIT)
    over_warm_body = over_body(warm, WARM_BODY_LIMIT)
    ok = (
        len(hot) <= HOT_LIMIT
        and chars <= CHAR_LIMIT
        and not over_desc
        and not over_hot_body
        and not over_warm_body
    )

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

    report = {
        "ok": ok,
        "home": home,
        "hot": len(hot),
        "warm": len(warm),
        "hotLimit": HOT_LIMIT,
        "catalogChars": chars,
        "catalogCharLimit": CHAR_LIMIT,
        "descLimit": DESC_LIMIT,
        "overDescLimit": [{"name": item["name"], "descLen": item["descLen"]} for item in over_desc],
        "bodyLimit": BODY_LIMIT,
        "warmBodyLimit": WARM_BODY_LIMIT,
        "sectionLimit": SECTION_LIMIT,
        "overBody": [
            {"name": item["name"], "bodyBytes": item["bodyBytes"], "sections": item["sections"], "warm": False}
            for item in over_hot_body
        ]
        + [
            {"name": item["name"], "bodyBytes": item["bodyBytes"], "sections": item["sections"], "warm": True}
            for item in over_warm_body
        ],
        "largest": [
            {"name": item["name"], "bodyBytes": item["bodyBytes"], "sections": item["sections"], "warm": False}
            for item in sorted(hot, key=lambda x: -x["bodyBytes"])[: args.top]
        ],
        "problems": problems,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"catalog: hot {len(hot)}/{HOT_LIMIT}  warm {len(warm)}  chars {chars}/{CHAR_LIMIT}")
        print(f"body:    hot <= {BODY_LIMIT} B / {SECTION_LIMIT} 段   warm <= {WARM_BODY_LIMIT} B")
        if over_desc:
            print("description 超预算:")
            for item in over_desc:
                print(f"  - {item['name']}: {item['descLen']} > {DESC_LIMIT}")
        if over_hot_body or over_warm_body:
            print("正文超预算（先精简再用 distill_skill 写）:")
            for item in over_hot_body:
                print(f"  - {item['name']}: {item['bodyBytes']} B / {item['sections']} 段（热上限 {BODY_LIMIT} B / {SECTION_LIMIT} 段）")
            for item in over_warm_body:
                print(f"  - {item['name']}（冷备）: {item['bodyBytes']} B / {item['sections']} 段（上限 {WARM_BODY_LIMIT} B）")
        if args.top > 0:
            print(f"最大正文 top{args.top}:")
            for item in sorted(hot, key=lambda x: -x["bodyBytes"])[: args.top]:
                print(f"  - {item['name']}: {item['bodyBytes']} B / {item['sections']} 段")
        if problems:
            print("其它问题:")
            for item in problems:
                print("  - " + item)
        print("预算内 ✓" if ok else "超预算 ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
