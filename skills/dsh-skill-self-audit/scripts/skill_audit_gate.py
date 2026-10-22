#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate for the daily DSH skill self-audit.

Decides whether it is allowed to run the audit RIGHT NOW.

Three gates (all must pass):
  QUIET   : no file under the skills root changed within the last --quiet-min minutes
  INTERVAL: at least --min-interval-h hours since the last successful audit
  CONFLICT: (optional) the tree fingerprint must equal the fingerprint taken by
            the caller before it started editing, so we never audit a moving target

Stdout is ASCII-only on purpose: the Windows console codepage is GBK and Chinese
text on stdout would raise UnicodeEncodeError inside a scheduled task.
Chinese text goes into the JSON state / report files (UTF-8, no BOM).

Exit codes:
   0  PASS       -> caller may run the audit
  10  SKIP_QUIET -> skills tree changed too recently
  11  SKIP_INTERVAL -> an audit already ran recently
  12  SKIP_CONFLICT -> tree fingerprint mismatch
  2  usage / IO error
"""

import argparse
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

SKILLS_ROOT = r"C:\Users\admin\.dsh\skills"
AUDIT_HOME = r"D:\workspace\agent\skills-audit"
STATE_PATH = os.path.join(AUDIT_HOME, "state", "state.json")

EXIT_PASS = 0
EXIT_QUIET = 10
EXIT_INTERVAL = 11
EXIT_CONFLICT = 12
EXIT_ERROR = 2

SKIP_DIR_NAMES = {".git", "__pycache__", ".pytest_cache", ".mypy_cache"}


def log(msg):
    print("[gate] " + msg, flush=True)


def iter_files(root, skip_dirs=SKIP_DIR_NAMES):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            yield os.path.join(dirpath, name)


def scan_tree(root, only_skill_md=False):
    """Return (files, fingerprint, latest_path, latest_ts)."""
    files = []
    for path in iter_files(root):
        if only_skill_md and os.path.basename(path).lower() != "skill.md":
            continue
        try:
            st = os.stat(path)
        except OSError as exc:
            log("stat failed (skipped): %s : %s" % (path, exc))
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


def fingerprint_of(root):
    return scan_tree(root)[1]


def load_state(state_path):
    if not os.path.exists(state_path):
        return {}
    try:
        with io.open(state_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # corrupted state must not block the audit forever
        log("state unreadable, treated as empty: %s" % exc)
        return {}


def save_state(state_path, state):
    parent = os.path.dirname(state_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = state_path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True))
    os.replace(tmp, state_path)


def iso(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def parse_now(value):
    if not value:
        return datetime.now()
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills-root", default=SKILLS_ROOT)
    ap.add_argument("--state", default=STATE_PATH)
    ap.add_argument("--quiet-min", type=float, default=60.0)
    ap.add_argument("--min-interval-h", type=float, default=20.0)
    ap.add_argument("--now", default="", help="override current time, format 'YYYY-MM-DD HH:MM:SS'")
    ap.add_argument("--expect-fingerprint", default="", help="fail if the tree does not match")
    ap.add_argument("--mark-run", action="store_true", help="record a successful audit")
    ap.add_argument("--mark-result", default="ok", help="value stored as last_result with --mark-run")
    ap.add_argument("--report", default="", help="report path stored with --mark-run")
    ap.add_argument("--print-fingerprint", action="store_true")
    args = ap.parse_args(argv)

    if args.print_fingerprint:
        log("fingerprint=%s" % fingerprint_of(args.skills_root))
        return EXIT_PASS

    now = parse_now(args.now)
    now_ts = now.timestamp()
    state = load_state(args.state)

    if args.mark_run:
        files, fp, latest_path, latest_ts = scan_tree(args.skills_root)
        state["last_audit_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
        state["last_audit_epoch"] = now_ts
        state["last_result"] = args.mark_result
        state["last_report"] = args.report
        state["last_fingerprint"] = fp
        state["last_file_count"] = len(files)
        state["last_change_at"] = iso(latest_ts)
        state["last_change_file"] = latest_path
        save_state(args.state, state)
        log("marked audit run at %s result=%s" % (state["last_audit_at"], args.mark_result))
        return EXIT_PASS

    files, fp, latest_path, latest_ts = scan_tree(args.skills_root)
    _, fp_skillmd, latest_path_md, latest_ts_md = scan_tree(args.skills_root, only_skill_md=True)

    quiet_min = (now_ts - latest_ts) / 60.0 if latest_ts else 99999.0
    quiet_min_md = (now_ts - latest_ts_md) / 60.0 if latest_ts_md else 99999.0

    last_audit_epoch = float(state.get("last_audit_epoch") or 0.0)
    since_audit_h = (now_ts - last_audit_epoch) / 3600.0 if last_audit_epoch else 99999.0

    result = {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "skills_root": args.skills_root,
        "file_count": len(files),
        "fingerprint": fp,
        "fingerprint_skillmd_only": fp_skillmd,
        "last_change_at": iso(latest_ts),
        "last_change_file": latest_path,
        "quiet_minutes": round(quiet_min, 2),
        "last_change_at_skillmd_only": iso(latest_ts_md),
        "last_change_file_skillmd_only": latest_path_md,
        "quiet_minutes_skillmd_only": round(quiet_min_md, 2),
        "last_audit_at": state.get("last_audit_at", ""),
        "hours_since_audit": round(since_audit_h, 2),
        "thresholds": {"quiet_min": args.quiet_min, "min_interval_h": args.min_interval_h},
        "gate": "PASS",
        "reason": "",
    }

    if args.expect_fingerprint and args.expect_fingerprint != fp:
        result["gate"] = "SKIP_CONFLICT"
        result["reason"] = "tree fingerprint changed since the caller sampled it"
        code = EXIT_CONFLICT
    elif quiet_min < args.quiet_min:
        result["gate"] = "SKIP_QUIET"
        result["reason"] = "skills tree changed %.1f min ago (< %.0f min)" % (quiet_min, args.quiet_min)
        code = EXIT_QUIET
    elif since_audit_h < args.min_interval_h:
        result["gate"] = "SKIP_INTERVAL"
        result["reason"] = "last audit %.1f h ago (< %.0f h)" % (since_audit_h, args.min_interval_h)
        code = EXIT_INTERVAL
    else:
        code = EXIT_PASS

    log("gate=%s %s" % (result["gate"], result["reason"]))
    log("quiet=%.1f min  since_audit=%.1f h  files=%d  last_change=%s" % (
        quiet_min, since_audit_h, len(files), result["last_change_at"]))
    log("last_change_file=%s" % result["last_change_file"])
    log("JSON=" + json.dumps(result, ensure_ascii=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
