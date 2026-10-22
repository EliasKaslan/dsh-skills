#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily runner for the DSH skill self-audit.

Sequence:
  1. take a lock (a stale lock older than LOCK_STALE_SEC is ignored)
  2. ask the gate whether we may run now (quiet / interval / fingerprint)
  3. if allowed, launch one headless DSH turn whose task is "follow the
     dsh-skill-self-audit skill", with stdout/stderr redirected to files
  4. record the outcome in the state file and bump a failure counter

Everything is logged; stdout stays ASCII-only (the console codepage is GBK and
a UnicodeEncodeError inside a scheduled task would kill the run silently).

Test hooks (NEVER set in the scheduled task, they bypass the user's quiet rule):
  SKILL_AUDIT_FORCE=1        -> pass --quiet-min 0 --min-interval-h 0 to the gate
  SKILL_AUDIT_STATE=<path>   -> use another state file
  SKILL_AUDIT_TASK=<text>    -> replace the audit task with this ASCII text
"""

import io
import os
import re
import subprocess
import sys
import time
from datetime import datetime

# This module imports its sibling, and the sibling lives INSIDE the audited
# skill tree. Without this line CPython writes scripts\__pycache__\*.pyc into
# that tree, i.e. the auditor pollutes the very tree it audits (verified: the
# file really appeared there). Must be set before the import below.
sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import skill_audit_gate as gate  # noqa: E402

AUDIT_HOME = r"D:\workspace\agent\skills-audit"
SKILLS_ROOT = r"C:\Users\admin\.dsh\skills"
DSH_HOME = r"C:\Users\admin\.dsh"
NODE = r"C:\Program Files\nodejs\node.exe"
DSH_LAUNCHER = (r"C:\Users\admin\AppData\Local\npm-cache\_npx\b86ed90107c62dab"
                r"\node_modules\@deepseek-ai\dsh\lib\bin.js")

LOGDIR = os.path.join(AUDIT_HOME, "logs")
STATEDIR = os.path.join(AUDIT_HOME, "state")
REPORTDIR = os.path.join(AUDIT_HOME, "reports")
DEFAULT_STATE = os.path.join(STATEDIR, "state.json")
LOCK = os.path.join(STATEDIR, "run.lock")
RUNNER_LOG = os.path.join(LOGDIR, "runner.log")
ALERT = os.path.join(AUDIT_HOME, "ALERT-needs-attention.txt")

HEADLESS_TIMEOUT_SEC = 1800
LOCK_STALE_SEC = 3 * 3600
VERDICT_RE = re.compile(r"^AUDIT-STATUS:.*$", re.M)

TASK_TEMPLATE = (
    "Load the skill named dsh-skill-self-audit and run today's skill-set audit "
    "exactly as its body prescribes. Report file: {report}. "
    "Your final output line must be exactly one line starting with "
    "'AUDIT-STATUS: ' followed by ok/warn/fail and the counts."
)


def ensure_dirs():
    for d in (LOGDIR, STATEDIR, REPORTDIR):
        os.makedirs(d, exist_ok=True)


def log(msg):
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    print("[daily] " + msg, flush=True)
    try:
        with io.open(RUNNER_LOG, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        print("[daily] cannot write runner.log: %s" % exc, flush=True)


def lock_age_sec():
    try:
        return time.time() - os.path.getmtime(LOCK)
    except OSError:
        return None


def take_lock():
    age = lock_age_sec()
    if age is not None:
        if age < LOCK_STALE_SEC:
            log("SKIP locked: another run started %d s ago" % int(age))
            return False
        log("stale lock age=%d s (> %d), taking over" % (int(age), LOCK_STALE_SEC))
    with io.open(LOCK, "w", encoding="ascii", newline="\n") as fh:
        fh.write("%d\n" % os.getpid())
    return True


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def read_text(path, limit=20000):
    try:
        with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def main():
    ensure_dirs()
    state_path = os.environ.get("SKILL_AUDIT_STATE") or DEFAULT_STATE
    forced = bool(os.environ.get("SKILL_AUDIT_FORCE"))

    log("start state=%s forced=%s" % (state_path, forced))
    if forced:
        log("WARNING: SKILL_AUDIT_FORCE is set - the quiet/interval gate is bypassed")

    if not take_lock():
        return 0
    try:
        gate_argv = ["--skills-root", SKILLS_ROOT, "--state", state_path]
        if forced:
            gate_argv += ["--quiet-min", "0", "--min-interval-h", "0"]
        code = gate.main(gate_argv)
        if code != gate.EXIT_PASS:
            log("gate blocked the run (exit %d); nothing to do" % code)
            return 0

        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        report_path = os.path.join(REPORTDIR, "audit-%s.md" % stamp)
        out_path = os.path.join(LOGDIR, "headless-%s.out.txt" % stamp)
        err_path = os.path.join(LOGDIR, "headless-%s.err.txt" % stamp)

        task = os.environ.get("SKILL_AUDIT_TASK") or TASK_TEMPLATE.format(report=report_path)
        cmd = [NODE, DSH_LAUNCHER, "--profile", "headless", task]
        env = dict(os.environ)
        env["DSH_HOME"] = DSH_HOME
        log("launching headless: report=%s" % report_path)

        t0 = time.time()
        rc = None
        with open(out_path, "wb") as fo, open(err_path, "wb") as fe:
            proc = subprocess.Popen(cmd, cwd=AUDIT_HOME, env=env, stdout=fo, stderr=fe)
            try:
                rc = proc.wait(timeout=HEADLESS_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                rc = 124
                log("headless timed out after %d s, killed" % HEADLESS_TIMEOUT_SEC)
        elapsed = int(time.time() - t0)

        stdout_text = read_text(out_path)
        verdict = ""
        m = VERDICT_RE.search(stdout_text)
        if m:
            verdict = m.group(0).strip()
        elif rc == 0:
            verdict = "AUDIT-STATUS: missing"

        if rc == 0 and verdict.startswith("AUDIT-STATUS:") and "missing" not in verdict:
            result = "ok"
        elif rc == 124:
            result = "timeout"
        else:
            result = "fail"

        log("headless exit=%s elapsed=%ds result=%s verdict=%r" % (rc, elapsed, result, verdict))
        log("stdout=%s" % out_path)
        log("stderr=%s" % err_path)

        gate.main(["--skills-root", SKILLS_ROOT, "--state", state_path, "--mark-run",
                   "--mark-result", result, "--report", report_path])

        # failure counter + a loud marker the human cannot miss
        state = gate.load_state(state_path)
        fails = int(state.get("consecutive_failures") or 0)
        if result == "ok":
            fails = 0
        else:
            fails += 1
        state["consecutive_failures"] = fails
        state["last_verdict"] = verdict
        state["last_stdout"] = out_path
        state["last_stderr"] = err_path
        state["last_elapsed_sec"] = elapsed
        gate.save_state(state_path, state)

        if fails >= 2:
            with io.open(ALERT, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("DSH skill self-audit failed %d times in a row.\n" % fails)
                fh.write("last result: %s\nlast verdict: %s\n" % (result, verdict))
                fh.write("stdout: %s\nstderr: %s\n" % (out_path, err_path))
                fh.write("log: %s\n" % RUNNER_LOG)
            log("ALERT written: %s" % ALERT)
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
