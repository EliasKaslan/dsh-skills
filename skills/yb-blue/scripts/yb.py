#!/usr/bin/env python3
"""yb.py - YB-Bridge client (blue zone / orchestrator side).

Pure standard library. Uses the GitHub Contents API for small files and the
Git Data API for large ones. Message format is shared with tools/yb.ps1.

Env overrides: YB_HOME, YB_TOKEN, YB_REPO, YB_BRANCH, YB_API
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HOME = Path(os.environ.get("YB_HOME") or (Path.home() / ".yb"))
CONFIG_PATH = HOME / "config"


def load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        for raw in CONFIG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip().lower()] = v.strip()
    return cfg


CFG = load_config()
REPO = os.environ.get("YB_REPO") or CFG.get("repo") or "EliasKaslan/yb-bridge"
BRANCH = os.environ.get("YB_BRANCH") or CFG.get("branch") or "main"
API = (os.environ.get("YB_API") or CFG.get("api") or "https://api.github.com").rstrip("/")
MAX_REQUEST_BYTES = int(CFG.get("max_request_bytes") or 98304)
MAX_FILE_BYTES = int(CFG.get("max_file_bytes") or 70000)
PROXY = CFG.get("proxy") or None
STATE_PATH = HOME / "blue-state.json"
VERSION = "6"


def token() -> str:
    t = os.environ.get("YB_TOKEN", "").strip()
    if t:
        return t
    tf = CFG.get("token_file")
    candidate = Path(os.path.expandvars(tf)) if tf else (HOME / "token")
    if candidate.exists():
        return candidate.read_text(encoding="utf-8").strip()
    alt = Path.home() / ".dsh" / ".secrets" / "yb-bridge.token"
    if alt.exists():
        return alt.read_text(encoding="utf-8").strip()
    raise SystemExit("YB:ERROR NO_TOKEN set YB_TOKEN or create " + str(HOME / "token"))


TOKEN = ""


def _token() -> str:
    global TOKEN
    if not TOKEN:
        TOKEN = token()
    return TOKEN


def request(method: str, url: str, payload=None, raw: bool = False):
    data = None
    headers = {
        "Authorization": "Bearer " + _token(),
        "User-Agent": "yb-blue/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    handlers = []
    if PROXY:
        handlers.append(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(req, timeout=90) as resp:
            body = resp.read()
            if raw:
                return body
            if not body:
                return {}
            return json.loads(body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except Exception:
            pass
        raise YbHttpError(e.code, detail) from None
    except urllib.error.URLError as e:
        raise YbHttpError(0, str(e.reason)) from None


class YbHttpError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__("HTTP %s %s" % (code, message[:400]))
        self.code = code
        self.message = message


def qpath(path: str) -> str:
    path = path.replace("\\", "/")
    return "/".join(urllib.parse.quote(seg) for seg in path.split("/"))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_file(path: str) -> bytes:
    url = f"{API}/repos/{REPO}/contents/{qpath(path)}?ref={BRANCH}"
    r = request("GET", url)
    if r.get("encoding") == "base64" and r.get("content"):
        return base64.b64decode(re.sub(r"\s", "", r["content"]))
    dl = r.get("download_url")
    if dl:
        return request("GET", dl, raw=True)
    raise SystemExit("YB:ERROR NO_CONTENT " + path)


def get_sha(path: str) -> str:
    r = request("GET", f"{API}/repos/{REPO}/contents/{qpath(path)}?ref={BRANCH}")
    return r["sha"]


def put_file(path: str, data: bytes, message: str):
    if len(data) > 900_000:
        return put_large(path, data, message)
    try:
        resp = _put_contents(path, data, message)
        if get_file(path) == data:
            return resp
        print("YB:WARN contents put not verified, retry via blobs: " + path)
    except YbHttpError as e:
        if e.code not in (409, 422, 500, 502, 503, 504):
            raise
        print("YB:WARN contents put failed (HTTP %s), retry via blobs: %s" % (e.code, path))
    return put_large(path, data, message)


def _put_contents(path: str, data: bytes, message: str):
    url = f"{API}/repos/{REPO}/contents/{qpath(path)}"
    payload = {
        "message": message,
        "content": base64.b64encode(data).decode("ascii"),
        "branch": BRANCH,
    }
    for attempt in range(3):
        try:
            return request("PUT", url, payload)
        except YbHttpError as e:
            if e.code != 422:
                raise
            try:
                if get_file(path) == data:
                    return {"sha": "unchanged"}
            except Exception:
                pass
            payload["sha"] = get_sha(path)
            if attempt == 2:
                raise
    return {"sha": "unchanged"}


def head_commit():
    try:
        ref = request("GET", f"{API}/repos/{REPO}/git/ref/heads/{BRANCH}")
        return ref["object"]["sha"]
    except YbHttpError as e:
        if e.code in (404, 409):
            return None
        raise


def put_large(path: str, data: bytes, message: str):
    blob = request(
        "POST",
        f"{API}/repos/{REPO}/git/blobs",
        {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"},
    )
    last = ""
    for attempt in range(5):
        head = head_commit()
        tree_payload = {
            "tree": [{"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]}]
        }
        if head:
            commit = request("GET", f"{API}/repos/{REPO}/git/commits/{head}")
            tree_payload["base_tree"] = commit["tree"]["sha"]
        tree = request("POST", f"{API}/repos/{REPO}/git/trees", tree_payload)
        cpayload = {"message": message, "tree": tree["sha"], "parents": [head] if head else []}
        new_commit = request("POST", f"{API}/repos/{REPO}/git/commits", cpayload)
        try:
            update_ref(new_commit["sha"], head is not None)
            return {"sha": new_commit["sha"]}
        except YbHttpError as e:
            if e.code != 422:
                raise
            last = str(e)
            time.sleep(1 + attempt)
    raise SystemExit("YB:ERROR branch moved repeatedly (concurrent writer): " + last)


def update_ref(sha: str, exists: bool):
    try:
        if exists:
            request(
                "PATCH",
                f"{API}/repos/{REPO}/git/refs/heads/{BRANCH}",
                {"sha": sha, "force": False},
            )
        else:
            request(
                "POST",
                f"{API}/repos/{REPO}/git/refs",
                {"ref": f"refs/heads/{BRANCH}", "sha": sha},
            )
    except YbHttpError as e:
        if e.code == 422:
            raise YbHttpError(422, "REF_CONFLICT branch moved") from None
        raise


def tree():
    try:
        return request("GET", f"{API}/repos/{REPO}/git/trees/{BRANCH}?recursive=1")
    except YbHttpError as e:
        if e.code in (404, 409):
            return None
        raise


# ------------------------------------------------------------------ message --
def new_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(3).hex()


def front_matter(fields: dict) -> str:
    order = [
        "id", "from", "to", "type", "task", "subject", "created", "reply_to",
        "parts", "part", "whole_sha256", "whole_bytes", "artifacts",
    ]
    lines = ["---"]
    for k in order:
        v = fields.get(k)
        if v is not None and str(v) != "":
            lines.append("%s: %s" % (k, str(v).replace("\n", " ").replace("\r", " ")))
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_message(data: bytes):
    off = 3 if data.startswith(b"\xef\xbb\xbf") else 0
    text = data[off:].decode("utf-8", "replace")
    m = re.match(r"^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n", text)
    if not m:
        raise ValueError("BAD_FRONTMATTER")
    meta = {}
    for line in re.split(r"\r?\n", m.group(1)):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    start = off + len(m.group(0).encode("utf-8"))
    return meta, data[start:]


def split_bytes(data: bytes, limit: int):
    parts = []
    pos = 0
    n = len(data)
    while pos < n:
        ln = min(limit, n - pos)
        if pos + ln < n:
            floor = pos + int(ln * 0.7)
            cut = data.rfind(b"\n", floor, pos + ln)
            if cut >= 0:
                ln = cut - pos + 1
            while ln > 1 and pos + ln < n and 0x80 <= data[pos + ln] <= 0xBF:
                ln -= 1
        parts.append(data[pos:pos + ln])
        pos += ln
    return parts


SECRET_PATTERNS = (
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"github_pat_[A-Za-z0-9_]{20,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
)


def assert_no_secret(body: bytes) -> None:
    """Blue side must not push credentials into the repo either."""
    if os.environ.get("YB_ALLOW_SECRET") == "1":
        return
    text = body.decode("utf-8", "replace")
    for pat in SECRET_PATTERNS:
        if re.search(pat, text):
            raise SystemExit("YB:ERROR SECRET_BLOCKED pattern=%s (remove it; YB_ALLOW_SECRET=1 to override)" % pat)


def send_message(msg_type: str, task: str, subject: str, body: bytes,
                 reply_to: str = "", artifacts: str = "", extra_subject_prefix: str = ""):
    assert_no_secret(body)
    mid = new_id()
    created = now_utc()
    day = created[:10].replace("-", "/")
    base = f"bus/b2y/{day}/{mid}"
    subject = (subject or "").replace("\n", " ").strip()[:120]
    fields = {
        "id": mid, "from": "blue", "to": "yellow", "type": msg_type,
        "task": task, "subject": subject, "created": created,
    }
    if reply_to:
        fields["reply_to"] = reply_to
    if artifacts:
        fields["artifacts"] = artifacts

    if len(body) <= MAX_FILE_BYTES - 2000:
        data = front_matter(fields).encode("utf-8") + body
        path = f"{base}.{msg_type}.md"
        put_file(path, data, f"yb: {msg_type} {mid} {task}")
        print(f"YB:SENT id={mid} type={msg_type} bytes={len(data)} path={path}")
        print(f"YB:URL https://github.com/{REPO}/blob/{BRANCH}/{path}")
        return mid

    part_limit = MAX_FILE_BYTES - 1600
    chunks = split_bytes(body, part_limit)
    whole = sha256(body)
    fields["parts"] = str(len(chunks))
    fields["whole_sha256"] = whole
    fields["whole_bytes"] = str(len(body))
    for i, chunk in enumerate(chunks, 1):
        pf = {
            "id": mid, "part": str(i), "parts": str(len(chunks)),
            "whole_sha256": whole, "created": created,
        }
        pdata = front_matter(pf).encode("utf-8") + chunk
        ppath = f"{base}.p{i:03d}.md"
        put_file(ppath, pdata, f"yb: part {i}/{len(chunks)} {mid}")
        print(f"YB:PART {i}/{len(chunks)} bytes={len(pdata)} path={ppath}")
    edata = front_matter(fields).encode("utf-8")
    epath = f"{base}.{msg_type}.md"
    put_file(epath, edata, f"yb: {msg_type} {mid} {task}")
    print(f"YB:SENT id={mid} type={msg_type} parts={len(chunks)} bytes={len(body)} sha256={whole} path={epath}")
    print(f"YB:URL https://github.com/{REPO}/blob/{BRANCH}/{epath}")
    return mid


# -------------------------------------------------------------------- state --
LOCK_PATH = HOME / "state.lock"


@contextmanager
def state_lock(timeout=180):
    """Serialize state read-modify-write across parallel blue agents."""
    HOME.mkdir(parents=True, exist_ok=True)
    start = time.time()
    while True:
        try:
            fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - LOCK_PATH.stat().st_mtime
            except OSError:
                age = 0
            if age > 600:
                try:
                    LOCK_PATH.unlink()
                except OSError:
                    pass
                continue
            if time.time() - start > timeout:
                raise SystemExit("YB:ERROR state lock timeout " + str(LOCK_PATH))
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"seen": [], "task_seq": {}}


def save_state(st: dict):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(STATE_PATH))


# ------------------------------------------------------------------ commands --
def _probe():
    """Read server Date / scopes / rate-limit remaining from a cheap endpoint."""
    headers = {
        "Authorization": "Bearer " + _token(),
        "User-Agent": "yb-relay/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    req = urllib.request.Request(API + "/rate_limit", headers=headers)
    if PROXY:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))
        resp = opener.open(req, timeout=30)
    else:
        resp = urllib.request.urlopen(req, timeout=30)
    with resp:
        h = resp.headers
        return h.get("Date", ""), h.get("X-OAuth-Scopes", ""), h.get("X-RateLimit-Remaining", "")


def cmd_doctor(_args):
    print("YB:VERSION", VERSION)
    print("YB:HOME", HOME)
    print("YB:REPO", REPO, "BRANCH", BRANCH, "API", API)
    print("YB:LIMITS request=%d file=%d" % (MAX_REQUEST_BYTES, MAX_FILE_BYTES))
    t = _token()
    print("OK token len=%d" % len(t))
    r = request("GET", f"{API}/repos/{REPO}")
    print("OK repo private=%s default_branch=%s" % (r.get("private"), r.get("default_branch")))
    perms = r.get("permissions") or {}
    print("OK permission push=%s" % perms.get("push"))
    if not r.get("private"):
        print("WARN repo is PUBLIC - do not put internal data here")
    tr = tree()
    if tr:
        n = len([x for x in tr.get("tree", []) if x["path"].startswith("bus/y2b/") and x["path"].endswith(".md")])
        print("OK tree yellow_messages=%d truncated=%s" % (n, tr.get("truncated")))
    else:
        print("OK tree empty repo")
    try:
        date_h, scopes, remain = _probe()
        print("YB:SCOPES", scopes or "(none)")
        broad = [s.strip() for s in (scopes or "").split(",")
                 if s.strip() in ("admin:org", "admin:enterprise", "delete_repo",
                                  "admin:public_key", "admin:ssh_signing_key")]
        if broad:
            print("WARN token scopes too broad: %s (a repo-only token is enough)" % ",".join(broad))
        print("YB:RATE remaining=%s" % remain)
        if date_h:
            srv = parsedate_to_datetime(date_h)
            skew = int((datetime.now(timezone.utc) - srv).total_seconds())
            print("YB:CLOCK skew=%+ds" % skew)
            if abs(skew) > 300:
                print("WARN clock skew > 5min; message ids are time-ordered")
    except Exception as e:
        print("WARN probe failed: %s" % e)
    lock = HOME / "state.lock"
    print("YB:LOCK state=%s" % (("pid=" + lock.read_text().strip()) if lock.exists() else "none"))
    print("INFO python=%s" % sys.version.split()[0])
    print("YB:DOCTOR OK")


def cmd_task(args):
    body = read_body(args)
    with state_lock():
        st = load_state()
        day = datetime.now().strftime("%Y%m%d")
        seq = int(st.get("task_seq", {}).get(day, 0)) + 1
        st.setdefault("task_seq", {})[day] = seq
        task = "T-%s-%02d" % (day, seq)
        subject = args.title or task
        artifacts = upload_attachments(task, args.attach or [])
        mid = send_message("task", task, subject, body, artifacts=",".join(artifacts))
        st.setdefault("tasks", {})[task] = {"spec_message": mid, "created": now_utc(), "title": subject}
        save_state(st)
    print("YB:TASK", task)


def upload_attachments(task: str, paths: list) -> list:
    out = []
    for p in paths:
        src = Path(p)
        if not src.is_file():
            raise SystemExit("YB:ERROR attachment not found " + str(src))
        data = src.read_bytes()
        repo_path = "artifacts/%s/%s" % (task, src.name)
        put_file(repo_path, data, "yb: artifact " + repo_path)
        out.append(repo_path)
        print("YB:ARTIFACT %s bytes=%d" % (repo_path, len(data)))
    return out


def cmd_send(args):
    body = read_body(args)
    artifacts = upload_attachments(args.task, args.attach or [])
    mid = send_message(args.type, args.task, args.subject or args.type, body,
                       reply_to=args.reply_to or "", artifacts=",".join(artifacts))
    print("YB:MESSAGE", mid)


def _poll_collect(limit: int, quiet: bool = False):
    tr = tree()
    if not tr:
        if not quiet:
            print("YB:NO_MESSAGES empty repository")
        return [], 0
    blobs = [x for x in tr.get("tree", []) if x.get("type") == "blob"
             and x["path"].startswith("bus/y2b/") and x["path"].endswith(".md")]
    groups = {}
    for b in blobs:
        name = b["path"].rsplit("/", 1)[-1]
        mid = name.split(".", 1)[0]
        groups.setdefault(mid, []).append(b["path"])
    metas = []
    with state_lock():
        st = load_state()
        seen = set(st.get("seen", []))
        ids = sorted((i for i in groups if i not in seen), reverse=True)[:limit]
        ids = sorted(ids)
        if not ids:
            if not quiet:
                print("YB:NO_MESSAGES no new yellow messages")
            return [], 0
        for mid in ids:
            try:
                meta, body = fetch_message(mid, groups[mid])
            except Exception as e:
                print("YB:ERROR id=%s %s" % (mid, e))
                continue
            d = HOME / "inbox" / mid
            d.mkdir(parents=True, exist_ok=True)
            (d / "body.md").write_bytes(body)
            st.setdefault("seen", []).append(mid)
            save_state(st)
            meta = dict(meta)
            meta["id"] = mid
            metas.append(meta)
            print()
            print("YB:MSG id=%s type=%s task=%s subject=%s" % (
                mid, meta.get("type"), meta.get("task"), meta.get("subject", "")))
            print("YB:BODY", d / "body.md")
            text = body.decode("utf-8", "replace")
            if len(text) > 4000:
                text = text[:4000] + "\n... [truncated, read the file]"
            print(text)
    return metas, len(ids)


def cmd_poll(args):
    metas, scanned = _poll_collect(args.limit)
    print()
    print("YB:POLL_DONE new=%d scanned=%d" % (len(metas), scanned))


def cmd_follow(args):
    until = set(t.strip() for t in args.until.split(",") if t.strip())
    deadline = time.time() + args.timeout
    print("YB:FOLLOW start task=%s until=%s timeout=%d interval=%d" % (
        args.task or "*", ",".join(sorted(until)), args.timeout, args.interval))
    while True:
        metas, _ = _poll_collect(args.limit, quiet=True)
        hit = [m for m in metas
               if (m.get("type") in until)
               and (not args.task or args.task in str(m.get("task") or "").split(","))]
        if hit:
            print("YB:FOLLOW_HIT id=%s type=%s task=%s" % (
                hit[0].get("id"), hit[0].get("type"), hit[0].get("task")))
            return 0
        if time.time() >= deadline:
            print("YB:FOLLOW_TIMEOUT seconds=%d" % args.timeout)
            return 3
        time.sleep(args.interval)


def fetch_message(mid: str, paths: list):
    env_path = None
    part_paths = []
    for p in paths:
        name = p.rsplit("/", 1)[-1]
        if re.match(r"^" + re.escape(mid) + r"\.p\d+\.md$", name):
            part_paths.append(p)
        elif re.match(r"^" + re.escape(mid) + r"\.[a-z]+\.md$", name):
            env_path = p
    if not env_path:
        raise ValueError("NO_ENVELOPE")
    meta, body = parse_message(get_file(env_path))
    n = int(meta.get("parts") or 0)
    if n:
        if len(part_paths) < n:
            raise ValueError("INCOMPLETE %d/%d" % (len(part_paths), n))
        chunks = []
        for i in range(1, n + 1):
            hit = [p for p in part_paths if re.search(r"\.p0*%d\.md$" % i, p)]
            if not hit:
                raise ValueError("MISSING_PART %d" % i)
            pm, pb = parse_message(get_file(hit[0]))
            chunks.append(pb)
        body = b"".join(chunks)
    if meta.get("whole_sha256") and meta["whole_sha256"] != sha256(body):
        raise ValueError("SHA_MISMATCH")
    if meta.get("whole_bytes") and int(meta["whole_bytes"]) != len(body):
        raise ValueError("SIZE_MISMATCH")
    return meta, body


def cmd_done(args):
    if args.all:
        task = "ALL"
        subject = "本次协同结束"
        body = "全部任务已验收通过，请停止监听并收工。\n"
    else:
        if not args.task:
            raise SystemExit("YB:ERROR need --task or --all")
        task = args.task
        subject = "任务验收通过"
        body = "任务 %s 已验收通过，可以收工。\n" % task
    mid = send_message("done", task, subject, body.encode("utf-8"))
    print("YB:DONE", mid, "task=" + task)


def cmd_show(args):
    tr = tree()
    if not tr:
        raise SystemExit("YB:ERROR empty repo")
    paths = [x["path"] for x in tr.get("tree", [])
             if x["path"].startswith("bus/") and x["path"].rsplit("/", 1)[-1].startswith(args.id)]
    if not paths:
        raise SystemExit("YB:ERROR not found " + args.id)
    meta, body = fetch_message(args.id, paths)
    print("YB:META", json.dumps(meta, ensure_ascii=False))
    print(body.decode("utf-8", "replace"))


def cmd_fetch(args):
    data = get_file(args.path)
    out = Path(args.out) if args.out else (HOME / "files" / Path(args.path).name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print("YB:FETCHED path=%s bytes=%d out=%s" % (args.path, len(data), out))


MESSAGE_TYPES = ("task", "report", "progress", "question", "answer", "error", "note", "ack")


def cmd_inbox(args):
    tr = tree()
    if not tr:
        print("YB:INBOX 0")
        return
    rows = []
    for e in tr.get("tree", []):
        if e.get("type") != "blob":
            continue
        p = e["path"]
        if not p.startswith("bus/y2b/") or not p.endswith(".md"):
            continue
        name = p.rsplit("/", 1)[-1]
        m = re.match(r"^(?P<id>[^.]+)\.(?P<type>[a-z]+)\.md$", name)
        if not m or m.group("type") not in MESSAGE_TYPES:
            continue
        rows.append((m.group("id"), m.group("type")))
    rows.sort(reverse=True)
    rows = rows[: args.limit]
    seen = set(load_state().get("seen", []))
    unseen = sum(1 for mid, _t in rows if mid not in seen)
    print("YB:INBOX %d shown (unseen=%d)" % (len(rows), unseen))
    for mid, t in rows:
        mark = " " if mid in seen else "*"
        print("  [%s] %s  %-8s  %s" % (mark, mid, t, "seen" if mid in seen else "UNSEEN"))
    if rows and unseen:
        print("YB:HINT show <id> ; poll 会消费未读并打印正文")


def cmd_status(_args):
    st = load_state()
    print("YB:HOME", HOME)
    print("YB:REPO", REPO)
    print("YB:SEEN", len(st.get("seen", [])))
    print("YB:TASKS", len(st.get("tasks", {})))
    for t, info in list(st.get("tasks", {}).items())[-5:]:
        print("  %s  %s" % (t, info.get("title", "")))


def read_body(args) -> bytes:
    if getattr(args, "file", None):
        data = Path(args.file).read_bytes()
    elif getattr(args, "text", None):
        data = args.text.encode("utf-8")
    else:
        raise SystemExit("YB:ERROR need --file or --text")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data


def cmd_publish(args):
    root = Path(args.dir)
    prefix = args.prefix.strip("/")
    head = head_commit()
    entries = []
    base_tree = None
    if head:
        base_tree = request("GET", f"{API}/repos/{REPO}/git/commits/{head}")["tree"]["sha"]
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for p in files:
        rel = p.relative_to(root).as_posix()
        if any(seg.startswith(".") or seg == "__pycache__" for seg in rel.split("/")):
            continue
        data = p.read_bytes()
        blob = request("POST", f"{API}/repos/{REPO}/git/blobs",
                       {"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        entries.append({"path": (prefix + "/" + rel) if prefix else rel,
                        "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("BLOB %-60s %7d" % (rel, len(data)))
    payload = {"tree": entries}
    if base_tree:
        payload["base_tree"] = base_tree
    new_tree = request("POST", f"{API}/repos/{REPO}/git/trees", payload)
    cp = {"message": args.message, "tree": new_tree["sha"], "parents": [head] if head else []}
    commit = request("POST", f"{API}/repos/{REPO}/git/commits", cp)
    update_ref(commit["sha"], head is not None)
    print("YB:PUBLISHED files=%d commit=%s" % (len(entries), commit["sha"]))


def main():
    ap = argparse.ArgumentParser(prog="yb.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)

    p = sub.add_parser("task")
    p.add_argument("--title", required=True)
    p.add_argument("--file")
    p.add_argument("--text")
    p.add_argument("--attach", nargs="*", default=[])
    p.set_defaults(func=cmd_task)

    p = sub.add_parser("send")
    p.add_argument("--type", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--subject", default="")
    p.add_argument("--file")
    p.add_argument("--text")
    p.add_argument("--reply-to", default="")
    p.add_argument("--attach", nargs="*", default=[])
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("poll")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_poll)

    p = sub.add_parser("follow")
    p.add_argument("--task", default="")
    p.add_argument("--until", default="report,error")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_follow)

    p = sub.add_parser("done")
    p.add_argument("--task", default="")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("show")
    p.add_argument("id")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("fetch")
    p.add_argument("--path", required=True)
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_fetch)

    sub.add_parser("status").set_defaults(func=cmd_status)

    p = sub.add_parser("inbox")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_inbox)

    p = sub.add_parser("publish")
    p.add_argument("--dir", required=True)
    p.add_argument("--prefix", default="")
    p.add_argument("--message", default="yb: publish")
    p.set_defaults(func=cmd_publish)

    args = ap.parse_args()
    try:
        rc = args.func(args)
    except YbHttpError as e:
        print("YB:ERROR", e)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    if isinstance(rc, int) and rc:
        raise SystemExit(rc)


if __name__ == "__main__":
    main()
