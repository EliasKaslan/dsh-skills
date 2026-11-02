#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_gate.py - deterministic checks for the DSH skill sedimentation gate.

Why this exists: the "is it worth keeping / merge or new / is this stale"
judgement is semantic, but the numbers behind it are not. Eyeballing a
400+ char Chinese description is off by ~25% (measured), so every budget
gate must come from a command, not from reading.

ASCII-only stdout on purpose: Windows PowerShell 5.1 decodes native
process output with the OEM code page (GBK here), so Chinese would be
mangled. Names, counts and line numbers are enough to act on.

Usage:
  python skill_gate.py catalog
      name / desc length / per-entry tax / total vs budget / YAML health.

  python skill_gate.py anchor TEAM_NOT_MEMBER "No matching distribution"
      substring search over every SKILL.md; prints name:line, never echoes
      the anchor (it may be non-ASCII).

  python skill_gate.py stale
      dead section refs (AGENTS.md §..), dangling `skill` pointers,
      description over 480/500, invalid frontmatter YAML, 未验证 markers.

  python skill_gate.py check-desc <draft.txt>
      measure a draft description after the same flattening the catalog
      applies (folded YAML -> one line), plus the two mandatory shapes.

  python skill_gate.py delta <name> <draft.txt>
      tax delta and the post-add total, with ok/over verdict.

Options:
  --root <dir>     skills root (default: %USERPROFILE%\\.dsh\\skills)
  --budget <n>     catalog character budget (default: 20000)

Exit code is always 0: this is a report tool. The verdict is in the text.
"""
import sys

sys.dont_write_bytecode = True  # never create __pycache__ inside the skill tree

import io
import os
import re

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DEAD_SECTION_RE = re.compile(r"(?:AGENTS\.md|\u5baa\u6cd5)\s*\u00a7\s*\d+(?:\.\d+)?")
K_REF_RE = re.compile(r"(?:AGENTS\.md|\u786c\u89c4\u5219)\s*[`*\s]*K(\d+)")
POINTER_RE = re.compile(
    r"(?:\u7528|\u89c1|\u8f6c\u4ea4|\u2192\s*\u7528)\s*`([a-z0-9][a-z0-9-]{2,})`"
)
DATE_RE = re.compile(r"20\d\d-\d\d-\d\d")


def die(msg):
    sys.stdout.write("ERROR %s\n" % msg)
    raise SystemExit(0)


def read_text(path):
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        return fh.read()


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def flatten(value):
    return " ".join(str(value).split())


def parse_frontmatter(raw):
    """Return (data, err). data has flattened name/description."""
    try:
        import yaml  # set dont_write_bytecode before this import (module top)
    except Exception:
        return None, "no-yaml-module"
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:
        return None, "yaml:" + type(exc).__name__
    if not isinstance(data, dict):
        return None, "yaml:not-a-mapping"
    out = {}
    for key in ("name", "description", "whenToUse"):
        if key in data and data[key] is not None:
            out[key] = flatten(data[key])
    return out, None


def skills_root(argv):
    root = os.path.join(os.path.expanduser("~"), ".dsh", "skills")
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            die("--root needs a value")
        root = argv[i + 1]
        del argv[i:i + 2]
    return os.path.abspath(root)


def budget(argv):
    value = 20000
    if "--budget" in argv:
        i = argv.index("--budget")
        if i + 1 >= len(argv):
            die("--budget needs a value")
        try:
            value = int(argv[i + 1])
        except ValueError:
            die("--budget must be an integer")
        del argv[i:i + 2]
    return value


def collect(root):
    entries = []
    if not os.path.isdir(root):
        die("root not found")
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        path = None
        dir_name = None
        if os.path.isdir(full):
            candidate = os.path.join(full, "SKILL.md")
            if os.path.isfile(candidate):
                path, dir_name = candidate, entry
        elif entry.endswith(".md") and os.path.isfile(full):
            path, dir_name = full, entry[:-3]
        if not path:
            continue
        text = read_text(path)
        raw, _body = split_frontmatter(text)
        item = {
            "dir": dir_name,
            "path": path,
            "text": text,
            "raw": raw,
            "name": dir_name,
            "desc": "",
            "err": None,
        }
        if raw is None:
            item["err"] = "no-frontmatter"
        else:
            data, err = parse_frontmatter(raw)
            item["err"] = err
            if data:
                item["name"] = data.get("name", dir_name)
                item["desc"] = data.get("description", "")
        if item["err"] is None and not NAME_RE.match(item["name"]):
            item["err"] = "bad-name"
        if item["err"] is None and item["name"] != dir_name:
            item["err"] = "name-dir-mismatch"
        item["cost"] = len(item["name"]) + len(item["desc"]) + 7
        entries.append(item)
    return entries


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def cmd_catalog(root, limit):
    entries = collect(root)
    total = sum(e["cost"] for e in entries)
    over_480 = [e for e in entries if len(e["desc"]) > 480]
    over_500 = [e for e in entries if len(e["desc"]) > 500]
    bad = [e for e in entries if e["err"]]
    headroom = limit - total
    sys.stdout.write(
        "SKILLS %d TAX %d BUDGET %d HEADROOM %d VERDICT %s\n"
        % (len(entries), total, limit, headroom, "ok" if headroom >= 0 else "over")
    )
    sys.stdout.write(
        "DESC_OVER_480 %d DESC_OVER_500 %d FRONTMATTER_BAD %d\n"
        % (len(over_480), len(over_500), len(bad))
    )
    descs = sorted((len(e["desc"]) for e in entries), reverse=True)
    if descs:
        mid = descs[len(descs) // 2]
        near = sum(1 for d in descs if 480 - 16 < d <= 480)
        sys.stdout.write("DESC_MEDIAN %d NEAR_LIMIT_16 %d\n" % (mid, near))
    for e in entries:
        flag = ""
        if len(e["desc"]) > 480:
            flag += " DESC_OVER"
        if e["err"]:
            flag += " ERR:" + e["err"]
        sys.stdout.write(
            "%-46s desc=%3d cost=%3d%s\n" % (e["name"], len(e["desc"]), e["cost"], flag)
        )
    for e in bad:
        sys.stdout.write("FRONTMATTER_ERR %s %s\n" % (e["name"], e["err"]))


def cmd_anchor(root, anchors):
    entries = collect(root)
    total = 0
    files = 0
    for anchor in anchors:
        low = anchor.lower()
        hits = []
        for e in entries:
            for m in re.finditer(re.escape(low), e["text"].lower()):
                hits.append((e["name"], line_of(e["text"], m.start())))
        if hits:
            files += 1
        total += len(hits)
        sys.stdout.write("ANCHOR %d hits in %d files\n" % (len(hits), len({h[0] for h in hits})))
        for name, line in hits[:40]:
            sys.stdout.write("  %s:%d\n" % (name, line))
        if len(hits) > 40:
            sys.stdout.write("  ... %d more\n" % (len(hits) - 40))
    sys.stdout.write("ANCHOR_TOTAL %d\n" % total)


def cmd_stale(root):
    entries = collect(root)
    names = {e["dir"] for e in entries}
    agents_path = os.path.join(os.path.dirname(root), "AGENTS.md")
    k_sections = set()
    if os.path.isfile(agents_path):
        for m in re.finditer(r"(?m)^##\s*K(\d+)", read_text(agents_path)):
            k_sections.add(m.group(1))
    dead = dangling = desc_over = yaml_bad = unverified = 0
    for e in entries:
        lines = e["text"].split("\n")
        in_fence = False
        for idx, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if DEAD_SECTION_RE.search(line):
                dead += 1
                sys.stdout.write("DEAD_SECTION_REF %s:%d\n" % (e["name"], idx))
            for m in K_REF_RE.finditer(line):
                if k_sections and m.group(1) not in k_sections:
                    dead += 1
                    sys.stdout.write("DEAD_K_REF %s:%d K%s\n" % (e["name"], idx, m.group(1)))
            for m in POINTER_RE.finditer(line):
                token = m.group(1)
                # Skill names are kebab-case; a bare backticked word is a
                # command or a tool name ("用 `curl`"), not a sibling skill.
                if "-" not in token:
                    continue
                if token not in names and not os.path.isfile(os.path.join(root, token + ".md")):
                    dangling += 1
                    sys.stdout.write("DANGLING_POINTER %s:%d %s\n" % (e["name"], idx, token))
        if len(e["desc"]) > 480:
            desc_over += 1
            sys.stdout.write("DESC_OVER %s %d\n" % (e["name"], len(e["desc"])))
        if e["err"]:
            yaml_bad += 1
            sys.stdout.write("FRONTMATTER_ERR %s %s\n" % (e["name"], e["err"]))
        count = e["text"].count("\u672a\u9a8c\u8bc1")
        if count:
            unverified += 1
            sys.stdout.write("UNVERIFIED %s %d\n" % (e["name"], count))
    total = sum(e["cost"] for e in entries)
    sys.stdout.write(
        "STALE dead=%d dangling=%d desc_over=%d frontmatter_bad=%d unverified=%d tax=%d\n"
        % (dead, dangling, desc_over, yaml_bad, unverified, total)
    )


def cmd_check_desc(path):
    text = read_text(path)
    flat = flatten(text)
    verdict = "ok" if len(flat) <= 480 else "over"
    has_suitable = "\u9002\u7528\u4e8e\u201c" in flat or "\u9002\u7528\u4e8e\"" in flat
    has_boundary = "\u4e0d\u9002\u7528" in flat
    triggers = flat.count(" / ")
    sys.stdout.write(
        "DESC_LEN %d LIMIT 480 VERDICT %s\n" % (len(flat), verdict)
    )
    sys.stdout.write(
        "HAS_SUITABLE %s HAS_DISAMBIG %s TRIGGER_SEP %d\n"
        % ("yes" if has_suitable else "no", "yes" if has_boundary else "no", triggers)
    )


def cmd_delta(root, name, path):
    if not NAME_RE.match(name):
        die("name must be kebab-case")
    entries = collect(root)
    total = sum(e["cost"] for e in entries)
    desc = flatten(read_text(path))
    cost = len(name) + len(desc) + 7
    new_total = total + cost
    sys.stdout.write(
        "DELTA name=%s desc=%d cost=%d tax=%d new_tax=%d budget=20000 verdict=%s\n"
        % (name, len(desc), cost, total, new_total, "ok" if new_total <= 20000 else "over")
    )
    if any(e["dir"] == name for e in entries):
        sys.stdout.write("NOTE skill already exists: merge edits cost=0\n")


def main(argv):
    if not argv:
        die("usage: catalog | anchor <text>... | stale | check-desc <file> | delta <name> <file>")
    try:
        sys.stdout.reconfigure(encoding="ascii", errors="replace")
    except Exception:
        pass
    root = skills_root(argv)
    limit = budget(argv)
    cmd = argv.pop(0) if argv else ""
    if cmd == "catalog":
        cmd_catalog(root, limit)
    elif cmd == "anchor":
        if not argv:
            die("anchor needs at least one substring")
        cmd_anchor(root, argv)
    elif cmd == "stale":
        cmd_stale(root)
    elif cmd == "check-desc":
        if len(argv) != 1:
            die("check-desc needs exactly one file")
        cmd_check_desc(argv[0])
    elif cmd == "delta":
        if len(argv) != 2:
            die("delta needs <name> <draft-file>")
        cmd_delta(root, argv[0], argv[1])
    else:
        die("unknown command: " + cmd)


if __name__ == "__main__":
    main(sys.argv[1:])
