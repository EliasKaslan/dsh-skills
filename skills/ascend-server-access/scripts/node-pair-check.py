#!/usr/bin/env python3
"""Inter-node connectivity check for two Ascend hosts (L2/L3/MTU/L4/ssh/throughput).

usage:
    python node-pair-check.py 192.168.13.188 192.168.13.190
    python node-pair-check.py 192.168.13.188 192.168.13.190 --throughput

Why paramiko instead of OpenSSH: .188 sshd stalls at KEX under heavy load
(load ~460 observed 2026-11-03); paramiko key login still works.
Password fallback is read from ../credentials.txt next to this skill.
"""
import argparse
import os
import sys
import threading
import time

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY = os.path.normpath(os.path.join(HERE, "..", "credentials.txt"))
# 2026-11-13: 本目录的 credentials.txt 已移除（发布时会被剔除），凭据统一在 .dsh/.secrets
_SECRETS = os.path.join(os.path.expanduser("~"), ".dsh", ".secrets", "ascend-servers.txt")
CRED = _SECRETS if os.path.exists(_SECRETS) else _LEGACY
KEY = os.path.expanduser("~/.ssh/id_ed25519")
PORT = 39022
SIZE_MB = 1000


def password_for(host):
    if not os.path.exists(CRED):
        return None
    with open(CRED, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if len(parts) >= 3 and parts[0] == host:
                return parts[2]
    return None


def connect(host):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    errs = []
    try:
        cli.connect(host, username="root", key_filename=KEY, timeout=8,
                    banner_timeout=15, auth_timeout=15,
                    allow_agent=False, look_for_keys=False)
        return cli, "key"
    except Exception as exc:                     # noqa: BLE001
        errs.append("key: %r" % (exc,))
    pw = password_for(host)
    if pw:
        try:
            cli.connect(host, username="root", password=pw, timeout=8,
                        banner_timeout=15, auth_timeout=15,
                        allow_agent=False, look_for_keys=False)
            return cli, "password"
        except Exception as exc:                 # noqa: BLE001
            errs.append("password: %r" % (exc,))
    raise SystemExit("connect failed %s -> %s" % (host, "; ".join(errs)))


def run(cli, cmd, timeout=120):
    _, stdout, stderr = cli.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return out.strip(), err.strip()


def probe(cli, peer):
    """L2 / L3 / MTU / L4 / NIC / storage / ssh-to-peer for one host."""
    script = """
echo "@@neigh"; ip neigh show __PEER__
echo "@@addr"; ip -4 -o addr show | awk '$2!="lo"{print $2, $4}'
echo "@@ping"; ping -c 3 -W 2 __PEER__ | tail -2
echo "@@mtu"; ping -c 2 -W 2 -s 1472 -M do __PEER__ | tail -2
echo "@@tcp"; timeout 6 bash -c '</dev/tcp/__PEER__/22' && echo TCP22_OK || echo TCP22_FAIL
echo "@@nic"; dev=$(ip route get __PEER__ | sed -n 's/.* dev \\([^ ]*\\).*/\\1/p'); echo "ifc=$dev"
command -v ethtool >/dev/null && ethtool $dev 2>/dev/null | grep -E 'Speed|Duplex'
ip -s link show $dev | tail -4
echo "@@nfs"; mount | grep -c ' type nfs' || true
echo "@@sshpeer"; timeout 15 ssh -n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=6 root@__PEER__ hostname 2>&1 | tail -2
echo "@@hostname"; hostname; uptime | sed 's/.*load average/load/'
""".replace("__PEER__", peer)
    out, err = run(cli, script)
    blocks, cur = {}, None
    for line in out.splitlines():
        if line.startswith("@@"):
            cur = line[2:].strip()
            blocks[cur] = []
        elif cur:
            blocks[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in blocks.items()}, err


def throughput(sender, receiver, result, key_name):
    send_cli, _ = connect(sender)
    recv_cli, _ = connect(receiver)
    listen = ("ss -ltn 2>/dev/null | grep -q ':%d ' && { echo PORT_BUSY; exit 9; }; "
              "timeout 90 nc -l %d | dd of=/dev/null bs=1M 2>&1 | tail -1") % (PORT, PORT)
    send = ("s=$(date +%%s.%%N); dd if=/dev/zero bs=1M count=%d status=none | nc -w 5 %s %d; "
            "e=$(date +%%s.%%N); awk -v s=$s -v e=$e 'BEGIN{printf \"%%.1f MB/s\\n\", %d/(e-s)}'"
            % (SIZE_MB, receiver, PORT, SIZE_MB))

    def _recv():
        result[key_name + "_recv"] = run(recv_cli, listen, 150)[0]

    th = threading.Thread(target=_recv)
    th.start()
    time.sleep(2)
    result[key_name + "_send"] = run(send_cli, send, 150)[0]
    th.join()
    send_cli.close()
    recv_cli.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--throughput", action="store_true")
    args = ap.parse_args()

    results, clients = {}, {}
    for host in (args.a, args.b):
        cli, how = connect(host)
        clients[host] = (cli, how)
        peer = args.b if host == args.a else args.a
        blocks, err = probe(cli, peer)
        results[host] = blocks
        print("=" * 70)
        print("%s  (%s, login=%s)  peer=%s" % (host, blocks.get("hostname", "?"), how, peer))
        for key in ("addr", "neigh", "ping", "mtu", "tcp", "nic", "nfs", "sshpeer"):
            if key in blocks:
                print("-- %s --" % key)
                print(blocks[key])
        if err:
            print("-- stderr --")
            print(err[:600])

    if args.throughput:
        tp = {}
        throughput(args.a, args.b, tp, "ab")
        throughput(args.b, args.a, tp, "ba")
        print("=" * 70)
        print("throughput %s -> %s: send=%s recv=%s" % (args.a, args.b, tp.get("ab_send"), tp.get("ab_recv")))
        print("throughput %s -> %s: send=%s recv=%s" % (args.b, args.a, tp.get("ba_send"), tp.get("ba_recv")))

    for cli, _ in clients.values():
        cli.close()


if __name__ == "__main__":
    main()
