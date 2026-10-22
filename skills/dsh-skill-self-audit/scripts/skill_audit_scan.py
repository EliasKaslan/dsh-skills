#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only health scan of the DSH skill collection.

Produces a JSON + Markdown report for the daily skill self-audit flow.

HARD CONSTRAINT: this script NEVER writes inside the skills root. Every write
helper goes through guard_write(), which raises on any path under the skills
root, and the scanner re-fingerprints the tree afterwards and reports the
pre/post comparison as check item G. No repair action lives here: this is a
read-only physical, repairs belong to a later flow.

Stdout is a SINGLE ASCII line on purpose: the Windows console codepage is GBK
and Chinese text on stdout raises UnicodeEncodeError inside a scheduled task.
Chinese text only ever goes into the report files (UTF-8, no BOM).

Exit codes:
    0  scan completed and the report was written (look at the printed status)
    2  usage / IO error, no usable report

Checks:
    A  run the existing checker check-skill-frontmatter.ps1, keep its raw stdout
    B  per-skill description inventory (Python Unicode char counts)
    C  cross-reference matrix (dangling / asymmetric / orphan)
    D  duplicate body blocks between skill pairs
    E  volume inventory (counts, bytes, biggest SKILL.md, bundle subdirs)
    F  gate data: tree fingerprints (same algorithm as skill_audit_gate.py)
    G  read-only guard: skills-root fingerprint unchanged before vs after
"""

import argparse
import difflib
import glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from datetime import datetime

DEFAULT_SKILLS_ROOT = r"C:\Users\admin\.dsh\skills"
DEFAULT_OUT_DIR = r"D:\workspace\agent\skills-audit\reports"
DEFAULT_CHECKER = r"C:\Users\admin\.dsh\skills\dsh-skill-authoring\check-skill-frontmatter.ps1"


# --------------------------------------------------- yaml module discovery
def yaml_module_candidates():
    """Ordered candidate list of `yaml` PACKAGE dirs (not their parent).

    The checker's own default (~\\.dsh\\profiles\\node_modules\\yaml) does not exist
    on this box, so check A used to run with YAML_SKIP=31 and still report ok.
    The npx entry is globbed because the active dsh tree hash changes whenever
    the package is reinstalled. Last entry is the checker default, kept as a
    fallback only.
    """
    cands = [
        r"C:\Users\admin\.dsh\launcher\runtime\node_modules\yaml",
        os.path.expanduser(r"~\.dsh\launcher\runtime\node_modules\yaml"),
    ]
    newest, newest_ts = None, -1.0
    pattern = os.path.join(os.environ.get("LOCALAPPDATA", ""), "npm-cache", "_npx",
                           "*", "node_modules", "yaml")
    for hit in glob.glob(pattern):
        try:
            ts = os.path.getmtime(hit)
        except OSError:
            continue
        if ts > newest_ts:
            newest, newest_ts = hit, ts
    if newest:
        cands.append(newest)
    cands.append(os.path.expanduser(r"~\.dsh\profiles\node_modules\yaml"))
    return cands


DEFAULT_YAML_MODULES = yaml_module_candidates()


def find_yaml_module(explicit=None):
    """explicit wins verbatim (even if missing -- lets a fault be forced on
    purpose); otherwise the first candidate that exists; otherwise None."""
    if explicit:
        return explicit
    for cand in DEFAULT_YAML_MODULES:
        if os.path.exists(cand):
            return cand
    return None


CHECKER_TIMEOUT = 300
DESC_SOFT = 480
DESC_HARD = 500
RAW_LIMIT = 20000

SKIP_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}

LEGACY_CAMEL_KEYS = ("disableModelInvocation", "modelInvocable", "userInvocable")

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HYPHEN_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$")
BACKTICK_RE = re.compile(r"`([^`\n]{1,80})`")

# A cross-reference is only recognised from an explicit pointer phrase or from a
# backticked name that really is an existing sibling skill. A loose "any backtick
# near the word 用" rule was tried first and produced 52 bogus danglings out of
# commit hashes (`10d23bf5`), CI labels (`approved`), YAML keys (`null`) and
# tools (`grep`), so the context window is gone.
STRICT_REF_RES = [
    re.compile(u"(?:\u2192|->)\\s*\\u7528\\s*`([^`\\n]{1,80})`"),                    # -> 用 `x`
    re.compile(u"(?:\u89c1|\u53c2\u89c1|\u8be6\u89c1|\u53c2\u8003|\u8f6c\u4ea4|\u6539\\s*\u7528)\\s*`([^`\\n]{1,80})`"),
    re.compile(u"(?m)^[-*\\s]*(?:\u7528|\u89c1)\\s*`([^`\\n]{1,80})`"),              # bullet "- 用/见 `x`"
]


STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"
STATUS_NOT_TAKEN = "not_taken"

# filled in main(); lowercased absolute path of the skills root
_SKILLS_ROOT_GUARD = [None]


# ---------------------------------------------------------------- read helpers
def read_text(path):
    """Read a text file as UTF-8 (BOM tolerated), newlines normalised to \\n."""
    with io.open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        raw = fh.read()
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def iter_files(root, skip_dirs=SKIP_DIR_NAMES):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            yield os.path.join(dirpath, name)


def scan_tree(root, only_skill_md=False):
    """(files, fingerprint, latest_path, latest_ts) -- same algorithm as gate.py."""
    files = []
    for path in iter_files(root):
        if only_skill_md and os.path.basename(path).lower() != "skill.md":
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        files.append((path, st.st_mtime, st.st_size))
    files.sort()
    h = hashlib.sha256()
    for path, mtime, size in files:
        rel = os.path.relpath(path, root).replace("\\", "/")
        h.update(("%s|%.6f|%d\n" % (rel, mtime, size)).encode("utf-8"))
    latest_path, latest_ts = "", 0.0
    for path, mtime, size in files:
        if mtime > latest_ts:
            latest_path, latest_ts = path, mtime
    return files, h.hexdigest(), latest_path, latest_ts


def iso(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------- write  guard
def guard_write(path):
    """Refuse any write that would land inside the skills root."""
    root = _SKILLS_ROOT_GUARD[0]
    p = os.path.normcase(os.path.abspath(path))
    if root and (p == root or p.startswith(root + os.sep)):
        raise RuntimeError("READONLY VIOLATION: refusing to write under skills root: %s" % path)
    return p


def safe_makedirs(path):
    guard_write(path)
    os.makedirs(path, exist_ok=True)


def safe_write(path, text):
    guard_write(path)
    parent = os.path.dirname(path)
    if parent:
        safe_makedirs(parent)
    tmp = path + ".tmp"
    guard_write(tmp)
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


# --------------------------------------------------------------- frontmatter
def parse_frontmatter(text):
    """(keys_in_order, mapping, body_text, body_first_lineno). Best effort, no YAML.

    body_first_lineno is the 1-based line number of the first line after the
    closing '---'; 1 when there is no frontmatter block at all.
    """
    if not text.startswith("---"):
        return [], {}, text, 1
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return [], {}, text, 1
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return [], {}, text, 1
    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])

    def unquote(raw):
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
            return raw[1:-1]
        return raw

    order, mapping = [], {}
    i = 0
    while i < len(fm_lines):
        m = KEY_RE.match(fm_lines[i])
        if not m:
            i += 1
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw in ("|", ">", "|-", ">-", "|+", ">+"):
            block, j = [], i + 1
            while j < len(fm_lines) and (fm_lines[j].startswith(" ") or fm_lines[j].strip() == ""):
                block.append(fm_lines[j].strip())
                j += 1
            raw, i = " ".join(x for x in block if x), j
        else:
            raw, i = unquote(raw), i + 1
        order.append(key)
        mapping[key] = raw
    return order, mapping, body, end + 2


OPENERS = {u'"': u'"', u"\u201c": u"\u201d", u"\u300c": u"\u300d", u"'": u"'", u"\u300e": u"\u300f"}


def apply_segment(desc):
    """Return (segment, count, reason). Counts `/`-separated trigger phrases.

    The 适用于"..." block is the LAST occurrence: earlier occurrences may be part
    of a quoted template (e.g. inside dsh-skill-authoring's own description).
    """
    marker = u"\u9002\u7528\u4e8e"
    idx = desc.rfind(marker)
    if idx < 0:
        return "", 0, "marker not found"
    head = desc[idx + len(marker):]
    opener_pos, opener = None, None
    for k in range(min(5, len(head))):
        if head[k] in OPENERS:
            opener_pos, opener = k, head[k]
            break
    if opener is None:
        return "", 0, "opening quote not found after marker"
    closer = OPENERS[opener]
    start = idx + len(marker) + opener_pos + 1
    stop = desc.find(closer, start)
    if stop < 0:
        return desc[start:], desc[start:].count("/") + 1, "closing quote not found"
    seg = desc[start:stop]
    return seg, seg.count("/") + 1, ""


def mentions(text, name):
    return re.search(r"(?<![a-z0-9-])" + re.escape(name) + r"(?![a-z0-9-])", text, re.I) is not None


# ------------------------------------------------------------------ checker A
def decode_bytes(raw):
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def run_checker(checker, skills_root, cwd, yaml_module=None):
    item = {
        "checker_path": checker,
        "command": "",
        "exit_code": None,
        "timeout_s": CHECKER_TIMEOUT,
        "raw_chars": 0,
        "raw_truncated": False,
        "non_ascii_bytes": 0,
        "checker_raw": "",
        "counts": {},
        "checker_parse": STATUS_NOT_TAKEN,
        "status": STATUS_NOT_TAKEN,
        "reason": "",
        "yaml_module": yaml_module or "",
    }
    if not os.path.isfile(checker):
        item["status"] = STATUS_FAIL
        item["reason"] = "checker script not found: %s" % checker
        item["checker_parse"] = STATUS_FAIL
        return item
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", checker,
           "-SkillsRoot", skills_root]
    if yaml_module:
        cmd += ["-YamlModule", yaml_module]
    item["command"] = " ".join('"%s"' % c if " " in c else c for c in cmd)
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              cwd=cwd, timeout=CHECKER_TIMEOUT)
        raw = proc.stdout or b""
        item["exit_code"] = proc.returncode
    except subprocess.TimeoutExpired:
        item["status"] = STATUS_FAIL
        item["checker_parse"] = STATUS_FAIL
        item["reason"] = "checker timed out after %ds" % CHECKER_TIMEOUT
        return item
    except OSError as exc:
        item["status"] = STATUS_FAIL
        item["checker_parse"] = STATUS_FAIL
        item["reason"] = "checker could not be started: %s" % exc
        return item

    text = decode_bytes(raw)
    non_ascii = sum(1 for b in raw if b > 127)
    item["raw_chars"] = len(text)
    item["non_ascii_bytes"] = non_ascii
    if len(text) > RAW_LIMIT:
        item["raw_truncated"] = True
        item["checker_raw"] = text[:RAW_LIMIT]
    else:
        item["checker_raw"] = text

    counts = {}
    missing = []
    for key in ("TOTAL", "FAIL", "WARN", "YAML_FAIL", "YAML_SKIP"):
        m = re.search(r"(?<![A-Z_])%s=(\d+)" % key, text)
        if m:
            counts[key] = int(m.group(1))
        else:
            counts[key] = None
            missing.append(key)
    item["counts"] = counts
    if missing:
        item["checker_parse"] = STATUS_FAIL
        tail = "\n".join(text.strip().split("\n")[-6:])[:2000]
        item["reason"] = "cannot parse %s from checker output; tail=%r" % (",".join(missing), tail)
        item["status"] = STATUS_FAIL
        return item

    item["checker_parse"] = STATUS_OK
    if item["exit_code"] not in (0, 1):
        item["status"] = STATUS_FAIL
        item["reason"] = "checker exit code %s (>1) -- command failed, not a violation report" % item["exit_code"]
    elif counts["FAIL"]:
        item["status"] = STATUS_FAIL
        item["reason"] = "checker reports FAIL=%d (violations, exit=1 is expected)" % counts["FAIL"]
    elif counts["WARN"]:
        item["status"] = STATUS_WARN
        item["reason"] = "checker reports WARN=%d" % counts["WARN"]
    else:
        item["status"] = STATUS_OK
        item["reason"] = "checker exit=%s TOTAL=%s FAIL=0" % (item["exit_code"], counts["TOTAL"])

    # A clean FAIL/WARN count only proves the checker ran the shape checks. If it
    # could not load a yaml module it skips every round-trip and still prints
    # TOTAL=31 FAIL=0, which is exactly the false OK that hides an unparsable
    # skill, so YAML_SKIP has to gate the status too.
    yaml_skip = counts.get("YAML_SKIP")
    if yaml_skip is None or yaml_skip > 0:
        item["reason"] += (" | YAML round-trip NOT performed (YAML_SKIP=%s): "
                           "该项覆盖不全，结果不可信"
                           % ("missing" if yaml_skip is None else yaml_skip))
        if not item["yaml_module"]:
            item["reason"] += (" | no yaml module found among %d candidates"
                               % len(DEFAULT_YAML_MODULES))
        if item["status"] == STATUS_OK:
            item["status"] = STATUS_NOT_TAKEN
    return item


# ---------------------------------------------------------- inventory items B
def collect_skills(root):
    out = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        if not os.path.isdir(full) or name in SKIP_DIR_NAMES:
            continue
        out.append({"dir": name, "path": full, "md": os.path.join(full, "SKILL.md")})
    return out


def inventory_b(root, skills):
    rows, notes = [], []
    for s in skills:
        row = {
            "skill": s["dir"],
            "skill_md": s["md"],
            "status": STATUS_OK,
            "reason": "",
            "bytes": None,
            "last_write_time": "",
            "frontmatter_keys": [],
            "name": None,
            "name_matches_dir": None,
            "description_chars": None,
            "description_margin_to_480": None,
            "apply_segment_chars": None,
            "apply_trigger_phrases": None,
            "apply_segment_reason": "",
            "has_bu_shi_yong": None,
            "when_to_use_chars": None,
            "legacy_camel_keys": [],
            "unknown_camel_keys": [],
        }
        if not os.path.isfile(s["md"]):
            row["status"] = STATUS_NOT_TAKEN
            row["reason"] = "SKILL.md missing (bundle-only directory)"
            notes.append("%s: no SKILL.md" % s["dir"])
            rows.append(row)
            continue
        st = os.stat(s["md"])
        row["bytes"] = st.st_size
        row["last_write_time"] = iso(st.st_mtime)
        text = read_text(s["md"])
        keys, mapping, _body, _bl = parse_frontmatter(text)
        row["frontmatter_keys"] = keys
        row["legacy_camel_keys"] = [k for k in keys if k in LEGACY_CAMEL_KEYS]
        row["unknown_camel_keys"] = [k for k in keys
                                     if re.search(r"[a-z][A-Z]", k) and k not in LEGACY_CAMEL_KEYS
                                     and k != "whenToUse"]
        name = mapping.get("name")
        row["name"] = name
        row["name_matches_dir"] = (name == s["dir"]) if name is not None else None
        desc = mapping.get("description")
        if desc is None:
            row["status"] = STATUS_FAIL
            row["reason"] = "description key not found in frontmatter"
            rows.append(row)
            continue
        row["description_chars"] = len(desc)
        row["description_margin_to_480"] = DESC_SOFT - len(desc)
        seg, cnt, why = apply_segment(desc)
        row["apply_segment_chars"] = len(seg)
        row["apply_trigger_phrases"] = cnt
        row["apply_segment_reason"] = why
        if why and why != "closing quote not found":
            row["status"] = STATUS_WARN
            row["reason"] = "apply segment: %s" % why
        row["has_bu_shi_yong"] = (u"\u4e0d\u9002\u7528\uff1a" in desc) or (u"\u4e0d\u9002\u7528:" in desc)
        wtu = mapping.get("whenToUse")
        row["when_to_use_chars"] = len(wtu) if wtu is not None else None
        if len(desc) > DESC_HARD:
            row["status"] = STATUS_FAIL
            row["reason"] = "description %d chars > hard limit %d" % (len(desc), DESC_HARD)
        elif len(desc) > DESC_SOFT and row["status"] == STATUS_OK:
            row["status"] = STATUS_WARN
            row["reason"] = "description %d chars > %d" % (len(desc), DESC_SOFT)
        if row["legacy_camel_keys"]:
            row["status"] = STATUS_FAIL
            row["reason"] = ("legacy camelCase keys reject the whole skill: %s"
                             % ",".join(row["legacy_camel_keys"]))
        if name is not None and name != s["dir"] and row["status"] == STATUS_OK:
            row["status"] = STATUS_WARN
            row["reason"] = "frontmatter name != directory name"
        if not row["has_bu_shi_yong"] and row["status"] == STATUS_OK:
            row["status"] = STATUS_WARN
            row["reason"] = "no 不适用: disambiguation clause in description"
        rows.append(row)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    n_bad = counts.get(STATUS_FAIL, 0)
    n_not = counts.get(STATUS_NOT_TAKEN, 0)
    status = STATUS_FAIL if n_bad else (STATUS_WARN if counts.get(STATUS_WARN, 0) or n_not else STATUS_OK)
    item = {
        "status": status,
        "reason": "skills=%d with SKILL.md, %d rows fail, %d not_taken" % (
            len([r for r in rows if r["description_chars"] is not None]), n_bad, n_not),
        "counts_by_status": counts,
        "rows": rows,
        "notes": notes,
    }
    return item


# --------------------------------------------------------- cross refs item C
def extract_refs(skill_name, ref_text, known_dirs):
    """(refs, unresolved, selfs).

    refs      : name-shaped backticked tokens that exist as a skill dir, or that
                sit right behind an explicit pointer phrase (-> 用 `x`, 见 `x` ...)
    unresolved: name-shaped backticked tokens that are neither -- reported as an
                informational tier (renamed/decommissioned skills, CI labels, ...)
    """
    refs, unresolved, selfs = [], [], []
    seen_ref, seen_unres, seen_self = set(), set(), set()
    for m in BACKTICK_RE.finditer(ref_text):
        tok = m.group(1).strip()
        if len(tok) < 4 or not NAME_RE.match(tok):
            continue
        ctx = ref_text[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")
        if tok == skill_name:
            if tok not in seen_self:
                seen_self.add(tok)
                selfs.append(tok)
            continue
        if tok in known_dirs:
            if tok not in seen_ref:
                seen_ref.add(tok)
                refs.append({"to": tok, "self": False, "via": "backtick-known", "context": ctx})
            continue
        if tok not in seen_unres:
            seen_unres.add(tok)
            # informational tier only: a name has to look like a skill name
            # (lowercase, hyphen-separated, >=2 words). Otherwise ordinary prose
            # backticks (`grep`, `null`, `allow`, `10d23bf5`) flood the report
            # with 258 junk rows and bury the renamed-skill hits.
            if HYPHEN_NAME_RE.match(tok):
                unresolved.append({"to": tok, "known_dir": False, "context": ctx})

    for rx in STRICT_REF_RES:
        for m in rx.finditer(ref_text):
            tok = m.group(1).strip()
            if not NAME_RE.match(tok) or tok == skill_name:
                continue
            ctx = ref_text[max(0, m.start() - 40):m.end() + 20].replace("\n", " ")
            if tok in known_dirs:
                if tok not in seen_ref:
                    seen_ref.add(tok)
                    refs.append({"to": tok, "self": False, "via": "pointer-phrase", "context": ctx})
            else:
                if tok not in seen_unres:
                    seen_unres.add(tok)
                    unresolved.append({"to": tok, "known_dir": False, "context": ctx,
                                       "via": "pointer-phrase"})
    return refs, unresolved, selfs


def cross_refs(root, skills, inv_rows):
    by_name = {r["skill"]: r for r in inv_rows}
    texts = {}
    for s in skills:
        if not os.path.isfile(s["md"]):
            continue
        text = read_text(s["md"])
        _keys, mapping, body, _bl = parse_frontmatter(text)
        texts[s["dir"]] = (mapping.get("description") or "") + "\n" + body
    live = sorted(texts.keys())
    known_dirs = set(s["dir"] for s in skills)

    out_edges, dangling, self_refs, unresolved = {}, [], [], []
    for name in live:
        refs, unres, selfs = extract_refs(name, texts[name], known_dirs)
        outs = []
        for r in refs:
            if r["to"] not in known_dirs:
                dangling.append({"from": name, "to": r["to"], "via": r["via"], "context": r["context"]})
            elif r["to"] not in texts:
                dangling.append({"from": name, "to": r["to"], "via": r["via"],
                                 "context": r["context"],
                                 "note": "directory exists but has no SKILL.md, so it is not loadable"})
            else:
                outs.append(r)
        out_edges[name] = outs
        for u in unres:
            u = dict(u)
            u["from"] = name
            unresolved.append(u)
        if selfs:
            self_refs.append({"skill": name, "target": sorted(set(selfs))})

    weak_in = {}
    for name in live:
        weak_in[name] = sorted(other for other in live
                               if other != name and mentions(texts[other], name))

    in_edges = {}
    for name in live:
        in_edges[name] = sorted(set(r["to"] for other, rs in out_edges.items()
                                    if other != name for r in rs if r["to"] == name))

    asymmetric, cannot_verify = [], []
    for a in live:
        for r in out_edges[a]:
            b = r["to"]
            if b == a:
                continue
            if b not in texts:
                cannot_verify.append({"from": a, "to": b,
                                      "reason": "target has no SKILL.md, cannot check back-reference"})
                continue
            if not mentions(texts[b], a):
                asymmetric.append({"from": a, "to": b, "via": r["via"]})

    orphans = []
    for name in live:
        out_sibs = sorted(set(r["to"] for r in out_edges[name] if r["to"] != name and r["to"] in texts))
        if out_sibs or in_edges[name] or weak_in[name]:
            continue
        orphans.append({
            "skill": name,
            "refs_out": [],
            "refs_in": in_edges[name],
            "mentioned_by": weak_in[name],
        })

    matrix = []
    for name in live:
        matrix.append({
            "skill": name,
            "refs_out": sorted(set(r["to"] for r in out_edges[name] if r["to"] in texts)),
            "refs_in": in_edges[name],
            "mentioned_by": weak_in[name],
            "refs_in_or_mentioned": sorted(set(in_edges[name]) | set(weak_in[name])),
            "refs_out_missing_skill_md": sorted(set(r["to"] for r in out_edges[name]
                                                    if r["to"] not in texts)),
        })

    dedup = {}
    for d in dangling:
        dedup[(d["from"], d["to"])] = d
    dangling = sorted(dedup.values(), key=lambda d: (d["to"], d["from"]))
    asym_dedup = {}
    for d in asymmetric:
        asym_dedup[(d["from"], d["to"])] = d
    asymmetric = sorted(asym_dedup.values(), key=lambda d: (d["from"], d["to"]))
    unres_dedup = {}
    for d in unresolved:
        key = (d["from"], d["to"])
        if key not in unres_dedup:
            unres_dedup[key] = d
    unresolved = sorted(unres_dedup.values(), key=lambda d: (d["to"], d["from"]))

    n_dang = len(dangling)
    n_asym = len(asymmetric)
    status = STATUS_FAIL if (n_dang or n_asym) else (STATUS_WARN if orphans else STATUS_OK)
    item = {
        "status": status,
        "reason": "dangling=%d asymmetric=%d orphan=%d self_refs=%d unresolved_backtick_names=%d" % (
            n_dang, n_asym, len(orphans), len(self_refs), len(unresolved)),
        "nodes": live,
        "nodes_without_skill_md": sorted(known_dirs - set(live)),
        "dangling": dangling,
        "asymmetric": asymmetric,
        "orphan": orphans,
        "self_refs": self_refs,
        "cannot_verify": cannot_verify,
        "unresolved_backtick_names": unresolved,
        "matrix": matrix,
        "definition": ("reference = a backticked token that is an existing skill dir, or a backticked "
                       "token right behind an explicit pointer phrase (-> 用 `x` / 见 `x` / 转交 `x`) - "
                       "ordinary prose backticks are NOT references; "
                       "dangling = referenced name has no <root>\\<name> directory; "
                       "asymmetric = A references B but B's description+body never mention A "
                       "(plain-name match with [a-z0-9-] boundaries, so a backticked mention counts); "
                       "orphan = no outgoing sibling reference AND no incoming reference/mention at all; "
                       "unresolved_backtick_names = informational tier (NOT counted as dangling): "
                       "backticks shaped like a skill name (lowercase, hyphen-separated, >=2 words) "
                       "with no matching directory - renamed/decommissioned skills, CI labels"),
    }
    return item


# ------------------------------------------------------- duplicate blocks D
POINTER_LINES = [
    re.compile(r"^[-*\s]*(->|\u2192)\s*$"),
    re.compile(u"^[-*\\s]*(\\u2192|->)\\s*(\\u7528|\\u89c1|\\u8f6c\\u4ea4|\\u53c2\\u8003|\\u6539?\\u7528|\\u8d70)"),
    re.compile(u"^[-*\\s]*(\\u7528|\\u89c1|\\u8f6c\\u4ea4|\\u53c2\\u8003)\\s*`"),
    re.compile(u"^\\u4e0d\\u9002\\u7528"),
    re.compile(r"^#{1,6}\s"),
    re.compile(r"^```"),
    re.compile(r"^\|[\s\-:|]+\|$"),
    # boilerplate section headers shared by most skills: structural, not content
    re.compile(u"^\\*\\*\\u52a0\\u8f7d\\u672c skill \\u5f53\\uff1a\\*\\*$"),
    re.compile(u"^\\*\\*\\u4e0d\\u8981\\u7528\\u672c skill\\uff08\\u8f6c\\u4ea4\\uff09\\uff1a\\*\\*$"),
]


def is_pointer_line(line):
    for rx in POINTER_LINES:
        if rx.match(line):
            return True
    return False


def body_lines(path):
    """Non-empty body lines (frontmatter stripped) as {lineno, text, pointer}."""
    text = read_text(path)
    _keys, _mapping, body, body_first = parse_frontmatter(text)
    if body is text:  # no frontmatter block: treat the whole file as body
        body_first = 1
    out = []
    for i, raw in enumerate(text.split("\n"), start=1):
        if i < body_first:
            continue
        s = raw.strip()
        if not s:
            continue
        out.append({"lineno": i, "text": s, "pointer": is_pointer_line(s)})
    return out


def duplicate_blocks(skills, limit=10, max_blocks=3):
    """Pairs of skills sharing >=2 consecutive identical *content* body lines.

    A matched run qualifies only if at least 2 of its lines are real content:
    an unfiltered run of "## 何时调用" + "**加载本 skill 当：**" or a pair of ```
    fences is structural boilerplate shared by most skills, not duplicated
    experience, and would otherwise flag 216 of the 351 pairs.
    """
    bodies = {}
    for s in skills:
        if os.path.isfile(s["md"]):
            bodies[s["dir"]] = body_lines(s["md"])
    names = sorted(bodies.keys())
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            la, lb = bodies[a], bodies[b]
            if len(la) < 2 or len(lb) < 2:
                continue
            sa = [x["text"] for x in la]
            sb = [x["text"] for x in lb]
            sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
            blocks = []
            total = 0
            for blk in sm.get_matching_blocks():
                if blk.size < 2:
                    continue
                seg_a = la[blk.a:blk.a + blk.size]
                seg_b = lb[blk.b:blk.b + blk.size]
                content = [x for x in seg_a if not x["pointer"]]
                if len(content) < 2:
                    continue
                total += len(content)
                blocks.append({
                    "content_lines": len(content),
                    "block_lines": blk.size,
                    "a_line_range": [content[0]["lineno"], content[-1]["lineno"]],
                    "b_line_range": [seg_b[0]["lineno"], seg_b[-1]["lineno"]],
                    "a_lines": [x["lineno"] for x in content],
                    "b_lines": [seg_b[k]["lineno"] for k, x in enumerate(seg_a) if not x["pointer"]],
                    "snippet": " | ".join(x["text"] for x in content[:3])[:120],
                })
            if total >= 2:
                pairs.append({"a": a, "b": b, "shared_lines": total,
                              "blocks": blocks[:max_blocks], "block_count": len(blocks)})
    pairs.sort(key=lambda p: (-p["shared_lines"], p["a"], p["b"]))
    n_pairs = len(pairs)
    status = STATUS_FAIL if n_pairs else STATUS_OK
    return {
        "status": status,
        "reason": "%d skill pairs share >=2 consecutive identical body lines (top %d listed)" % (
            n_pairs, min(limit, n_pairs)),
        "pair_count": n_pairs,
        "pairs": pairs[:limit],
        "excluded_line_kinds": ["empty", "heading only", "pointer line (-> 用 `x` / 见 `x` / 不适用: ..)",
                                "code fence marker", "markdown table separator",
                                "何时调用 boilerplate header (**加载本 skill 当：**)",
                                "rule: a matched run counts only if >=2 of its lines are content"],
        "body_line_counts": {k: len(v) for k, v in bodies.items()},
    }


# -------------------------------------------------------------- volume E
def volume(root, skills):
    files = list(iter_files(root))
    total_bytes = 0
    for p in files:
        try:
            total_bytes += os.stat(p).st_size
        except OSError:
            pass
    with_md = [s for s in skills if os.path.isfile(s["md"])]
    sizes = []
    for s in with_md:
        try:
            sizes.append({"skill": s["dir"], "bytes": os.stat(s["md"]).st_size})
        except OSError:
            pass
    sizes.sort(key=lambda x: (-x["bytes"], x["skill"]))
    bundles = []
    for s in skills:
        subs = []
        for dirpath, dirnames, _f in os.walk(s["path"]):
            for d in dirnames:
                full = os.path.join(dirpath, d)
                subs.append(os.path.relpath(full, s["path"]).replace("\\", "/"))
        if subs:
            bundles.append({"skill": s["dir"], "subdirs": sorted(subs)})
    return {
        "status": STATUS_OK,
        "reason": "",
        "dir_count": len(skills),
        "skill_count_with_skill_md": len(with_md),
        "dirs_without_skill_md": sorted(s["dir"] for s in skills if not os.path.isfile(s["md"])),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "top10_skill_md_by_bytes": sizes[:10],
        "skills_with_bundle_subdirs": bundles,
    }


# ---------------------------------------------------------------- report
def status_word(checks):
    if any(c.get("status") == STATUS_FAIL for c in checks.values()):
        return STATUS_FAIL
    if any(c.get("status") in (STATUS_WARN, STATUS_NOT_TAKEN) for c in checks.values()):
        return STATUS_WARN
    return STATUS_OK


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return out


def build_markdown(rep):
    L = []
    add = L.append
    add("# DSH skill 只读体检报告")
    add("")
    add("- 生成时间: %s" % rep["generated_at"])
    add("- skills 根: `%s`" % rep["skills_root"])
    add("- 总体状态: **%s**" % rep["overall_status"])
    add("- 检查器: `%s`" % rep["checker_path"])
    add("- 本脚本: `%s` (只读，不修改 skills 根)" % rep["script_path"])
    add("")
    add("## 检查项状态")
    add("")
    add("| 项 | 名称 | status | 说明 |")
    add("|---|---|---|---|")
    names = {
        "A_checker": "A 现成校验器",
        "B_description_inventory": "B description 清单",
        "C_cross_reference": "C 交叉引用矩阵",
        "D_body_duplicates": "D 正文重复检测",
        "E_volume": "E 体量清单",
        "F_gate": "F 闸门数据",
        "G_readonly_guard": "G 只读护栏",
    }
    for k in ("A_checker", "B_description_inventory", "C_cross_reference",
              "D_body_duplicates", "E_volume", "F_gate", "G_readonly_guard"):
        c = rep["checks"][k]
        add("| %s | %s | %s | %s |" % (k[0], names[k], c.get("status"), (c.get("reason") or "").replace("|", "/")))
    add("")

    a = rep["checks"]["A_checker"]
    add("## A. 现成校验器原始输出")
    add("")
    add("- 命令: `%s`" % a.get("command"))
    add("- exit code: %s | checker_parse: %s | raw_chars=%s | truncated=%s" % (
        a.get("exit_code"), a.get("checker_parse"), a.get("raw_chars"), a.get("raw_truncated")))
    add("- 解析出的计数: `%s`" % json.dumps(a.get("counts"), ensure_ascii=False))
    add("- 判定: %s" % (a.get("reason") or ""))
    add("")
    add("```text")
    add((a.get("checker_raw") or "").rstrip("\n"))
    add("```")
    add("")

    b = rep["checks"]["B_description_inventory"]
    add("## B. description 清单（字符数按 Python Unicode 计，非 PS 的 .Length）")
    add("")
    add("- %s" % b["reason"])
    add("- 状态分布: `%s`" % json.dumps(b["counts_by_status"], ensure_ascii=False))
    add("")
    rows = []
    for r in b["rows"]:
        rows.append([r["skill"], r["bytes"], r["last_write_time"], ",".join(r["frontmatter_keys"]),
                     r["name"], r["description_chars"], r["description_margin_to_480"],
                     r["apply_trigger_phrases"], r["apply_segment_reason"] or "",
                     u"有" if r["has_bu_shi_yong"] else (u"无" if r["has_bu_shi_yong"] is not None else "-"),
                     r["when_to_use_chars"],
                     ",".join(r["legacy_camel_keys"]) or "-", r["status"]])
    L.extend(md_table(["skill", "bytes", "LastWriteTime", "fm keys", "name", "desc字符",
                       "余480", "触发句", "apply备注", u"不适用", "whenToUse", "旧键", "status"], rows))
    add("")

    c = rep["checks"]["C_cross_reference"]
    add("## C. 交叉引用矩阵")
    add("")
    add("- %s" % c["reason"])
    add("- 判定口径: %s" % c["definition"])
    add("- 无 SKILL.md 的目录（不可加载，故不参与对称性判定）: %s" % (
        ", ".join("`%s`" % x for x in c["nodes_without_skill_md"]) or "无"))
    add("")
    add("### C1 悬空引用 dangling（被引用但目录不存在）")
    add("")
    if c["dangling"]:
        L.extend(md_table(["from", "to", "via", "context"],
                          [[d["from"], "`%s`" % d["to"], d["via"], (d["context"] or "")[:90].replace("|", "/")]
                           for d in c["dangling"]]))
    else:
        add("无")
    add("")
    add("### C2 单向引用 asymmetric（A→B 但 B 不提 A）")
    add("")
    if c["asymmetric"]:
        L.extend(md_table(["from", "to", "via"], [[d["from"], "`%s`" % d["to"], d["via"]] for d in c["asymmetric"]]))
    else:
        add("无")
    add("")
    add("### C3 孤岛 orphan（不引用任何人，也没人引用/提及它）")
    add("")
    if c["orphan"]:
        add(", ".join("`%s`" % o["skill"] for o in c["orphan"]))
    else:
        add("无")
    add("")
    add("### C4 全部节点的入/出引用")
    add("")
    L.extend(md_table(["skill", "refs_out", "refs_in", "mentioned_by", "in∪mentioned"],
                      [[m["skill"], ", ".join(m["refs_out"]) or "-", ", ".join(m["refs_in"]) or "-",
                        ", ".join(m["mentioned_by"]) or "-", ", ".join(m["refs_in_or_mentioned"]) or "-"]
                       for m in c["matrix"]]))
    add("")
    add("### C5 信息层：形如 skill 名但无对应目录的反引号 token（不计入 dangling）")
    add("")
    add("口径：小写、连字符分词、≥2 段（`grep`/`null`/`10d23bf5` 这类散文反引号已被滤除）。")
    add("可能是改过名的 skill、CI 标签或外部项目名，供人工判断：")
    add("")
    if c["unresolved_backtick_names"]:
        L.extend(md_table(["from", "token", "via", "context"],
                          [[d["from"], "`%s`" % d["to"], d.get("via", "-"),
                            (d.get("context") or "")[:90].replace("|", "/")]
                           for d in c["unresolved_backtick_names"]]))
    else:
        add("无")
    add("")

    d = rep["checks"]["D_body_duplicates"]
    add("## D. 正文重复块（连续 ≥2 行非空且完全相同，排除纯指针行）")
    add("")
    add("- %s" % d["reason"])
    add("- 排除的行: %s" % "、".join(d["excluded_line_kinds"]))
    add("")
    if d["pairs"]:
        L.extend(md_table(["#", "pair", "共享内容行", "块数", "A 行号", "B 行号", "片段(≤120字符)"],
                          [[i + 1, "%s <-> %s" % (p["a"], p["b"]), p["shared_lines"], p["block_count"],
                            ",".join(",".join(str(n) for n in x["a_lines"]) for x in p["blocks"]),
                            ",".join(",".join(str(n) for n in x["b_lines"]) for x in p["blocks"]),
                            " // ".join(x["snippet"] for x in p["blocks"])]
                           for i, p in enumerate(d["pairs"])]))
    else:
        add("无")
    add("")

    e = rep["checks"]["E_volume"]
    add("## E. 体量清单")
    add("")
    add("- 一级目录数: %s；含 SKILL.md 的 skill 数: %s；无 SKILL.md 的目录: %s" % (
        e["dir_count"], e["skill_count_with_skill_md"], ", ".join(e["dirs_without_skill_md"]) or "无"))
    add("- 文件总数: %s；总字节: %s" % (e["file_count"], e["total_bytes"]))
    add("")
    add("SKILL.md 字节数前 10:")
    add("")
    L.extend(md_table(["#", "skill", "bytes"],
                      [[i + 1, x["skill"], x["bytes"]] for i, x in enumerate(e["top10_skill_md_by_bytes"])]))
    add("")
    add("带 bundle 子目录的 skill:")
    add("")
    if e["skills_with_bundle_subdirs"]:
        L.extend(md_table(["skill", "subdirs"],
                          [[x["skill"], ", ".join(x["subdirs"])] for x in e["skills_with_bundle_subdirs"]]))
    else:
        add("无")
    add("")

    f = rep["checks"]["F_gate"]
    add("## F. 闸门数据（算法与 skill_audit_gate.py 一致：`relpath|mtime|size` 逐行 sha256）")
    add("")
    L.extend(md_table(["口径", "文件数", "sha256", "最新改动时间", "最新改动文件"],
                      [["整树", f["all"]["file_count"], f["all"]["fingerprint"],
                        f["all"]["last_change_at"], "`%s`" % f["all"]["last_change_file"]],
                       ["仅 *\\SKILL.md", f["skill_md_only"]["file_count"],
                        f["skill_md_only"]["fingerprint"], f["skill_md_only"]["last_change_at"],
                        "`%s`" % f["skill_md_only"]["last_change_file"]]]))
    add("")

    g = rep["checks"]["G_readonly_guard"]
    add("## G. 只读护栏")
    add("")
    add("- 跑前指纹: `%s`" % g["fingerprint_before"])
    add("- 跑后指纹: `%s`" % g["fingerprint_after"])
    add("- 一致: **%s**；写护栏拦截次数: %s" % (g["unchanged"], g["blocked_writes"]))
    add("")

    add("## 未取到的项")
    add("")
    nt = rep["not_taken"]
    if nt:
        for x in nt:
            add("- %s: %s" % (x["check"], x["reason"]))
    else:
        add("无")
    add("")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="read-only DSH skill health scan")
    ap.add_argument("--skills-root", default=DEFAULT_SKILLS_ROOT)
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--checker", default=DEFAULT_CHECKER)
    ap.add_argument("--yaml-module", default=None,
                    help="path to the yaml PACKAGE dir passed to the checker as "
                         "-YamlModule (default: first existing candidate)")
    ap.add_argument("--no-checker", action="store_true")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.skills_root)
    out_dir = os.path.abspath(args.out_dir)
    if not os.path.isdir(root):
        sys.stderr.write("skills root not found: %s\n" % root)
        return 2
    _SKILLS_ROOT_GUARD[0] = os.path.normcase(root)
    # every write must land outside the skills root
    try:
        safe_makedirs(out_dir)
    except RuntimeError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

    started = datetime.now()
    stamp = started.strftime("%Y-%m-%d-%H%M")
    json_path = os.path.join(out_dir, "scan-%s.json" % stamp)
    md_path = os.path.join(out_dir, "scan-%s.md" % stamp)

    fp_before = scan_tree(root)[1]
    skills = collect_skills(root)

    checks = {}
    not_taken = []

    if args.no_checker:
        checks["A_checker"] = {
            "status": STATUS_NOT_TAKEN,
            "reason": "disabled by --no-checker",
            "checker_path": args.checker,
            "command": "",
            "exit_code": None,
            "timeout_s": CHECKER_TIMEOUT,
            "raw_chars": 0,
            "raw_truncated": False,
            "non_ascii_bytes": 0,
            "checker_raw": "",
            "counts": {},
            "checker_parse": STATUS_NOT_TAKEN,
            "yaml_module": "",
        }
        not_taken.append({"check": "A_checker", "reason": "--no-checker given"})
    else:
        checks["A_checker"] = run_checker(args.checker, root, out_dir,
                                          find_yaml_module(args.yaml_module))

    checks["B_description_inventory"] = inventory_b(root, skills)
    checks["C_cross_reference"] = cross_refs(root, skills, checks["B_description_inventory"]["rows"])
    checks["D_body_duplicates"] = duplicate_blocks(skills)
    checks["E_volume"] = volume(root, skills)

    files_all, fp_all, latest_path, latest_ts = scan_tree(root)
    files_md, fp_md, latest_path_md, latest_ts_md = scan_tree(root, only_skill_md=True)
    checks["F_gate"] = {
        "status": STATUS_OK,
        "reason": "algorithm identical to skill_audit_gate.py",
        "all": {"file_count": len(files_all), "fingerprint": fp_all,
                "last_change_at": iso(latest_ts), "last_change_file": latest_path},
        "skill_md_only": {"file_count": len(files_md), "fingerprint": fp_md,
                          "last_change_at": iso(latest_ts_md), "last_change_file": latest_path_md},
    }

    for name, c in checks.items():
        if c.get("status") == STATUS_NOT_TAKEN:
            not_taken.append({"check": name, "reason": c.get("reason") or "no data"})

    report = {
        "tool": "skill_audit_scan.py",
        "script_path": os.path.abspath(__file__),
        "generated_at": started.strftime("%Y-%m-%d %H:%M:%S"),
        "skills_root": root,
        "out_dir": out_dir,
        "checker_path": args.checker,
        "checker_enabled": not args.no_checker,
        "python": sys.executable,
        "python_version": sys.version.split()[0],
        "json_report": json_path,
        "md_report": "" if args.json_only else md_path,
        "checks": checks,
        "not_taken": not_taken,
        "read_only": True,
    }

    checks["G_readonly_guard"] = {
        "status": STATUS_OK,
        "reason": "skills root fingerprint identical before and after the scan",
        "fingerprint_before": fp_before,
        "fingerprint_after": fp_all,
        "unchanged": None,
        "blocked_writes": 0,
        "note": "any write helper raises on a path under the skills root; see guard_write()",
    }
    report["overall_status"] = status_word(checks)

    def write_all():
        safe_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        if not args.json_only:
            safe_write(md_path, build_markdown(report))
        safe_write(os.path.join(out_dir, "latest.txt"),
                   "json=%s\nmd=%s\ngenerated_at=%s\n" % (
                       json_path, "" if args.json_only else md_path,
                       started.strftime("%Y-%m-%d %H:%M:%S")))

    try:
        write_all()
    except (RuntimeError, OSError) as exc:
        sys.stderr.write("report write failed: %s\n" % exc)
        return 2

    fp_after = scan_tree(root)[1]
    checks["G_readonly_guard"]["unchanged"] = (fp_after == fp_before)
    if not checks["G_readonly_guard"]["unchanged"]:
        checks["G_readonly_guard"]["status"] = STATUS_FAIL
        checks["G_readonly_guard"]["reason"] = (
            "skills root CHANGED during the scan (other writers may be active)")
        report["overall_status"] = status_word(checks)
    # always rewrite: the post-scan fingerprint must land in the report on disk
    try:
        write_all()
    except (RuntimeError, OSError) as exc:
        sys.stderr.write("final report write failed: %s\n" % exc)
        return 2

    n_fail = sum(1 for c in checks.values() if c.get("status") == STATUS_FAIL)
    n_warn = sum(1 for c in checks.values() if c.get("status") in (STATUS_WARN, STATUS_NOT_TAKEN))
    n_dang = len(checks["C_cross_reference"]["dangling"])
    n_asym = len(checks["C_cross_reference"]["asymmetric"])
    n_dup = checks["D_body_duplicates"]["pair_count"]
    line = "SCAN %s files=%d fail=%d warn=%d dangling=%d asym=%d dup_pairs=%d report=%s" % (
        report["overall_status"], checks["E_volume"]["file_count"], n_fail, n_warn,
        n_dang, n_asym, n_dup, json_path)
    sys.stdout.write(line.encode("ascii", "backslashreplace").decode("ascii") + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
