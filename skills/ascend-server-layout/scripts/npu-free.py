#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""npu-free.py —— 一次问清「在册的这几台昇腾服务器，现在哪几台有空闲卡」。

只读：每台只跑一条 `npu-smi info`（.188 走 .190 跳板），不 kill、不 set/reset、不写远端。

用法（Windows 本机，隧道需先连好）：
    python npu-free.py                 # 采在册 6 台，打表
    python npu-free.py --json          # 给 agent 的结构化输出
    python npu-free.py --hosts 177.11.25.1,192.168.13.190
    python npu-free.py --raw D:\\tmp\\npudump   # 顺带落原始 npu-smi 文本，排障用

判空口径（与 ascend-server-layout「共享机占用铁律」一致，唯一判据出处在那里）：
  * 空闲 = 该 die 的 HBM used ≤ 驱动基线阈值，**且** Process 段没有该 die 的进程；
  * 阈值按卡型：65536MB → 3500；98304MB → 6000；其它按 total*6%；
  * **不要**用 NPU Util(%) 或 `-t usages` 的百分比判空（实测有负载时 Util 仍为 0、百分比与 MB 差约 2 倍）；
  * Health=Alarm 不算「占用」，但会单独标出来——UB/RAS 告警的卡别当正常卡长期跑。
"""
from __future__ import print_function

import argparse
import io
import json
import os
import re
import sys
import threading
import time

try:
    import paramiko
except ImportError:  # pragma: no cover
    sys.stderr.write("需要 paramiko：pip install paramiko\n")
    raise

# 在册清单（2026-11-13 用户口径）。增删机器改这里；jump 是跳板机。
HOSTS = [
    {"ip": "192.168.13.188", "label": "A3",   "jump": "192.168.13.190"},
    {"ip": "192.168.13.190", "label": "A3b",  "jump": None},
    {"ip": "177.8.21.1",     "label": "A5-1", "jump": None},
    {"ip": "177.11.25.1",    "label": "A5-2", "jump": None},
    {"ip": "177.11.26.1",    "label": "A5-3", "jump": None},
    {"ip": "177.11.27.1",    "label": "A5-4", "jump": None},
]

SECRETS = os.path.join(os.path.expanduser("~"), ".dsh", ".secrets", "ascend-servers.txt")


def password_for(ip):
    """从 .secrets/ascend-servers.txt 取 `<host> <user> <password>`；取不到返回 (None, None)。"""
    try:
        with io.open(SECRETS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) >= 3 and parts[0] == ip:
                    return parts[1], parts[2]
    except (IOError, OSError):
        pass
    return None, None


def connect(ip, timeout=15):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(ip, username="root", timeout=timeout, banner_timeout=timeout,
                    auth_timeout=timeout, look_for_keys=True, allow_agent=False)
        return cli
    except Exception:
        cli.close()
    user, pwd = password_for(ip)
    if not pwd:
        raise RuntimeError("免密失败且 .secrets 里没有 %s 的密码" % ip)
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(ip, username=user, password=pwd, timeout=timeout, banner_timeout=timeout,
                auth_timeout=timeout, look_for_keys=False, allow_agent=False)
    return cli


def run_npu_smi(ip, jump=None, timeout=35):
    cmd = "npu-smi info"
    if jump:
        jcli = connect(jump)
        try:
            remote = ("ssh -n -o BatchMode=yes -o StrictHostKeyChecking=no "
                      "-o ConnectTimeout=10 root@%s '%s'" % (ip, cmd))
            stdin, stdout, stderr = jcli.exec_command(remote)
            stdout.channel.settimeout(timeout)
            return stdout.read().decode("utf-8", "replace")
        finally:
            jcli.close()
    cli = connect(ip)
    try:
        stdin, stdout, stderr = cli.exec_command(cmd)
        stdout.channel.settimeout(timeout)
        return stdout.read().decode("utf-8", "replace")
    finally:
        cli.close()


def limit_for(total):
    """驱动基线上限：超过就当已占用。"""
    if total >= 90000:
        return 6000          # Ascend950DT / 98304MB，实测空卡 4791~4930
    if total >= 60000:
        return 3500          # 910 / 65536MB，实测空卡 2858~3175
    return int(total * 0.06)


PAIR = re.compile(r"(\d+)\s*/\s*(\d+)")
LEAD = re.compile(r"^(\d+)(?:\s+(\d+))?")


def _lead_ids(cell):
    """取行首的 NPU / Chip 号。
    只认开头两个数字：`0     Ascend910` -> (0, None)（910 是型号不是 chip！），
    `0     0` -> (0, 0)（A3 双 chip），`7` -> (7, None)（A5 单 die）。"""
    m = LEAD.match(cell.strip())
    if not m:
        return None, None
    return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)


def parse(text):
    """返回 (dies, procs, version)。dies: npu/chip/hbm_used/hbm_total/alarm。"""
    dies, procs = [], []
    version = ""
    m = re.search(r"npu-smi\s+([0-9][\w.\-]*)", text)
    if m:
        version = m.group(1)
    in_proc = False
    cur_npu, cur_chip = None, None
    pending_alarm = False
    for line in text.splitlines():
        if "Process id" in line:
            in_proc = True
            continue
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if in_proc:
            # | NPU [Chip] | Process id | name | mem | ...     或 No running processes found
            if len(cells) >= 3 and cells[1].isdigit():
                npu, chip = _lead_ids(cells[0])
                if npu is None:
                    continue
                procs.append({
                    "npu": npu,
                    "chip": chip,
                    "pid": int(cells[1]),
                    "name": cells[2],
                    "mem": int(cells[3]) if len(cells) > 3 and cells[3].isdigit() else 0,
                })
            continue
        # 卡信息段：A3 一个 die 两行（NPU 行 + Chip 行），A5 一个 die 两行但 Chip 行的首列是空的。
        # Health 永远在**首行**（HBM 在首行是 0/0，解析时被过滤掉），所以要跨行记住。
        joined = " ".join(cells)
        npu, chip = _lead_ids(cells[0])
        if npu is not None:
            cur_npu, cur_chip = npu, chip
            pending_alarm = bool(re.search(r"\b(Alarm|Warning|Critical)\b", joined))
        pairs = [(int(a), int(b)) for a, b in PAIR.findall(joined)]
        hbm = [(a, b) for a, b in pairs if b >= 8192]
        if not hbm or cur_npu is None:
            continue
        dies.append({
            "npu": cur_npu,
            "chip": cur_chip,
            "hbm_used": hbm[-1][0],
            "hbm_total": hbm[-1][1],
            "alarm": pending_alarm or bool(re.search(r"\b(Alarm|Warning|Critical)\b", joined)),
        })
        pending_alarm = False
    return dies, procs, version


def busy_dies(dies, procs):
    """把进程段的行映射到 die 序号（A3 双 chip、A5 单 die 都成立）。"""
    key2idx = {}
    for i, d in enumerate(dies):
        key2idx[(d["npu"], d["chip"])] = i
    busy = {}
    for p in procs:
        idx = key2idx.get((p["npu"], p["chip"]))
        if idx is None:
            idx = key2idx.get((p["npu"], None))
        if idx is None:
            continue
        busy.setdefault(idx, []).append(p)
    return busy


def scan_one(cfg, raw_dir=None):
    t0 = time.time()
    out = {"ip": cfg["ip"], "label": cfg.get("label", ""), "ok": False,
           "error": None, "chip": "", "version": "", "dies": 0, "free": 0,
           "hbm_used": [], "hbm_total": 0, "busy_by": [], "alarms": [], "secs": 0.0}
    try:
        text = run_npu_smi(cfg["ip"], cfg.get("jump"))
        if raw_dir:
            try:
                os.makedirs(raw_dir, exist_ok=True)
                path = os.path.join(raw_dir, cfg["ip"] + ".txt")
                with io.open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(text)
            except OSError:
                pass
        dies, procs, version = parse(text)
        if not dies:
            out["error"] = "npu-smi 输出里没有解析到 HBM 行（命令不存在或输出格式变了）"
            out["secs"] = round(time.time() - t0, 1)
            return out
        busy = busy_dies(dies, procs)
        limit = limit_for(dies[0]["hbm_total"])
        free = 0
        for i, d in enumerate(dies):
            if d["hbm_used"] <= limit and i not in busy:
                free += 1
        name = "Ascend" + "x"
        m = re.search(r"(Ascend\w+)", text)
        if m:
            name = m.group(1)
        out.update({
            "ok": True, "chip": name, "version": version, "dies": len(dies),
            "free": free, "hbm_total": dies[0]["hbm_total"],
            "hbm_used": [d["hbm_used"] for d in dies],
            "alarms": sorted({d["npu"] for d in dies if d["alarm"]}),
            "busy_by": [{"die": i, "pid": p["pid"], "name": p["name"], "mem": p["mem"]}
                        for i in sorted(busy) for p in busy[i]],
        })
    except Exception as exc:  # noqa: BLE001 - 单台失败不能拖垮整体
        out["error"] = "%s: %s" % (type(exc).__name__, str(exc).splitlines()[0][:160])
    out["secs"] = round(time.time() - t0, 1)
    return out


def scan(hosts, raw_dir=None, workers=6):
    results = [None] * len(hosts)
    lock = threading.Lock()

    def work(i, cfg):
        r = scan_one(cfg, raw_dir)
        with lock:
            results[i] = r

    threads = []
    for i, cfg in enumerate(hosts):
        t = threading.Thread(target=work, args=(i, cfg), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return [r for r in results if r]


def summarize(r):
    """一句话：这台能不能用。"""
    if not r["ok"]:
        return "UNREACHABLE"
    if r["free"] == 0:
        return "FULL"
    return "FREE"


def busy_text(r):
    if not r["ok"] or not r["busy_by"]:
        return "-"
    groups = {}
    for p in r["busy_by"]:
        g = groups.setdefault(p["name"], {"n": 0, "mem": 0})
        g["n"] += 1
        g["mem"] = max(g["mem"], p["mem"])
    parts = []
    for name, g in sorted(groups.items(), key=lambda kv: -kv[1]["mem"]):
        mem = "%.0fG" % (g["mem"] / 1024.0) if g["mem"] >= 1024 else "%dM" % g["mem"]
        parts.append("%s x%d %s" % (name, g["n"], mem))
    txt = ", ".join(parts) if len(parts) <= 3 else ", ".join(parts[:3]) + ", +%d" % (len(parts) - 3)
    return txt if len(txt) <= 52 else txt[:49] + "..."


def hbm_text(r):
    used = r["hbm_used"]
    if not used:
        return "-"
    if r["free"] == r["dies"]:
        return "base %d~%dMB" % (min(used), max(used))
    shown = ["%.1f" % (u / 1024.0) for u in used[:8]]
    txt = ",".join(shown)
    if len(used) > 8:
        txt += ",+%d" % (len(used) - 8)
    return txt + "G"


def print_table(rows):
    head = ("HOST", "TAG", "CHIP", "FREE", "HBM_USED", "BUSY_BY", "NOTE")
    table = [head]
    for r in rows:
        if not r["ok"]:
            table.append((r["ip"], r["label"], "-", "-", "-", "-", (r["error"] or "UNREACHABLE")[:56]))
            continue
        note = []
        if r["alarms"]:
            note.append("ALARM NPU%s" % "/".join(str(a) for a in r["alarms"]))
        table.append((r["ip"], r["label"], r["chip"], "%d/%d" % (r["free"], r["dies"]),
                      hbm_text(r), busy_text(r), " ".join(note) or "-"))
    widths = [max(len(str(row[i])) for row in table) for i in range(len(head))]
    for row in table:
        line = "  ".join(str(row[i]).ljust(widths[i]) for i in range(len(head)))
        print(line.rstrip())


def _tag(r):
    return "%s(%s)" % (r["ip"], r["label"]) if r["label"] else r["ip"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="快速判空：哪几台昇腾服务器现在有空闲 NPU 卡")
    ap.add_argument("--hosts", help="逗号分隔的 IP，覆盖默认在册清单")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 agent 用）")
    ap.add_argument("--raw", metavar="DIR", help="把每台的原始 npu-smi 文本落到该目录")
    args = ap.parse_args(argv)

    hosts = HOSTS
    if args.hosts:
        hosts = [{"ip": x.strip(), "label": "", "jump": None} for x in args.hosts.split(",") if x.strip()]

    t0 = time.time()
    rows = scan(hosts, raw_dir=args.raw)
    elapsed = time.time() - t0

    if args.json:
        print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                          "elapsed_s": round(elapsed, 1), "hosts": rows},
                         ensure_ascii=False, indent=2))
        return 0

    print("采集时间 %s（%.1fs，每台一条 npu-smi info）" %
          (time.strftime("%Y-%m-%d %H:%M:%S"), elapsed))
    print_table(rows)
    free_hosts = [r for r in rows if r["ok"] and r["free"] > 0]
    full = [r for r in rows if r["ok"] and r["free"] == 0]
    down = [r for r in rows if not r["ok"]]
    print("")
    print("有空卡：%s" % ("、".join("%s %d/%d" % (_tag(r), r["free"], r["dies"])
                                  for r in free_hosts) or "无"))
    if full:
        print("已占满：%s" % "、".join(_tag(r) for r in full))
    if down:
        print("连不上：%s" % "、".join(_tag(r) for r in down))
    print("提醒：卡状态是分钟级变量，动手前再跑一次本脚本；A3 是 2 die/NPU（16 die=8 张卡），A5 是 1 die/卡。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
