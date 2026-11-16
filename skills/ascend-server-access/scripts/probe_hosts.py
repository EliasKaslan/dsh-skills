#!/usr/bin/env python3
"""Read-only explicit-target TCP/SSH probe; existing keys and verified host keys only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import re
import socket
import subprocess
import sys

TARGET = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*$")
INVENTORY = "hostname; uname -m; nproc; df -h / /home /mnt/share /mnt/weight 2>/dev/null; npu-smi info"

def probe(target, timeout=6, inventory=False):
    if not TARGET.fullmatch(target):
        raise ValueError("use explicit user@IPv4-or-hostname; options and shell metacharacters are not accepted")
    host = target.rsplit("@",1)[-1]
    result = {"target":target,"observed_at":dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        with socket.create_connection((host,22),timeout=min(timeout,4)):
            result["tcp22"] = True
    except OSError as exc:
        result.update(tcp22=False,tcp_error=type(exc).__name__)
    # SSH may resolve a configured alias/proxy even if raw TCP did not.
    try:
        p = subprocess.run(["ssh","-n","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                            "-o",f"ConnectTimeout={timeout}","-o","ConnectionAttempts=1",target,
                            INVENTORY if inventory else "hostname"],capture_output=True,timeout=timeout+10)
        result.update(ssh_rc=p.returncode,stdout=p.stdout.decode("utf-8","replace"),stderr=p.stderr.decode("utf-8","replace"))
    except subprocess.TimeoutExpired:
        result.update(ssh_rc=None,ssh_error="bounded SSH timeout")
    except OSError as exc:
        result.update(ssh_rc=None,ssh_error=str(exc))
    return result

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets",nargs="+")
    ap.add_argument("--timeout",type=int,default=6)
    ap.add_argument("--inventory",action="store_true",help="also collect disk and raw npu-smi telemetry; no NPU context initialized")
    args=ap.parse_args(argv)
    if not 1<=args.timeout<=30 or any(not TARGET.fullmatch(x) for x in args.targets):
        ap.error("timeout must be 1..30 and targets must be explicit safe host names")
    with ThreadPoolExecutor(max_workers=min(4,len(args.targets))) as pool:
        results=list(pool.map(lambda x:probe(x,args.timeout,args.inventory),args.targets))
    print(json.dumps({"hosts":results,"scope":"observations only; no free-card classification or remote mutations"},ensure_ascii=False,indent=2))
    return 0 if all(r.get("ssh_rc")==0 for r in results) else 1

if __name__=="__main__":
    sys.exit(main())
