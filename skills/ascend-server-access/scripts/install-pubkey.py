#!/usr/bin/env python3
"""Install this machine's SSH public key on one or more remote hosts (idempotent).

Usage:
  python install-pubkey.py 192.168.13.190
  python install-pubkey.py 177.8.21.1 --key C:\\Users\\admin\\.ssh\\id_ed25519
  python install-pubkey.py host1 host2 --user root --password '***'

Password resolution: --password, else credentials.txt line "<host> <user> <pwd>",
else environment SSH_PASSWORD.  Never overwrites authorized_keys: appends only
when the key is missing, then verifies a key-only login.
"""
import argparse
import io
import os
import sys

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
_LEGACY = os.path.normpath(os.path.join(HERE, "..", "credentials.txt"))
# 2026-11-13: 本目录的 credentials.txt 已移除（发布时会被剔除），凭据统一在 .dsh/.secrets
_SECRETS = os.path.join(os.path.expanduser("~"), ".dsh", ".secrets", "ascend-servers.txt")
CREDS = _SECRETS if os.path.exists(_SECRETS) else _LEGACY


def read_creds(host):
    if not os.path.exists(CREDS):
        return None
    for raw in io.open(CREDS, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[0] == host:
            return parts[1], parts[2]
    return None


def run(c, cmd):
    chan = c.exec_command(cmd)[1].channel
    return chan.recv_exit_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hosts", nargs="+")
    ap.add_argument("--user", default="root")
    ap.add_argument("--password", default=os.environ.get("SSH_PASSWORD"))
    ap.add_argument("--key", default=os.path.expanduser("~/.ssh/id_ed25519"))
    ap.add_argument("--port", type=int, default=22)
    args = ap.parse_args()

    if not os.path.exists(args.key):
        sys.exit("key not found: %s (generate with ssh-keygen -t ed25519)" % args.key)
    pub = io.open(args.key + ".pub", encoding="utf-8").read().strip()
    if not pub.startswith("ssh-"):
        sys.exit("bad public key: %s.pub" % args.key)

    rc = 0
    for host in args.hosts:
        user, pwd = args.user, args.password
        if not pwd:
            hit = read_creds(host)
            if hit:
                user, pwd = hit
        if not pwd:
            print("SKIP", host, "no password (use --password or add to credentials.txt)")
            rc = 1
            continue

        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            c.connect(host, port=args.port, username=user, password=pwd,
                      timeout=30, banner_timeout=120, auth_timeout=90,
                      look_for_keys=False, allow_agent=False)
            sftp = c.open_sftp()
            home = sftp.normalize(".")
            d = home.rstrip("/") + "/.ssh"
            f = d + "/authorized_keys"
            run(c, "mkdir -p %s && chmod 700 %s" % (d, d))
            try:
                old = sftp.open(f, "r").read().decode("utf-8", "replace")
            except IOError:
                old = ""
            lines = [x.strip() for x in old.splitlines() if x.strip()]
            if pub in lines:
                action = "already-present"
            else:
                new = old
                if new and not new.endswith("\n"):
                    new += "\n"
                new += pub + "\n"
                with sftp.open(f, "w") as fh:
                    fh.write(new.encode("utf-8"))
                action = "appended"
            sftp.chmod(f, 0o600)
            sftp.chmod(d, 0o700)
            run(c, "chown -R %s %s" % (user, d))
            now = sftp.open(f, "r").read().decode("utf-8", "replace")
            sftp.close()
            print("KEY", host, action, "lines=%d" % len(now.splitlines()))
        except Exception as ex:
            print("FAIL", host, type(ex).__name__, str(ex)[:160])
            rc = 1
            c.close()
            continue
        finally:
            c.close()

        v = paramiko.SSHClient()
        v.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            v.connect(host, port=args.port, username=user, key_filename=args.key,
                      timeout=30, banner_timeout=120, auth_timeout=60,
                      look_for_keys=False, allow_agent=False)
            _, out, _ = v.exec_command("hostname; whoami")
            print("VERIFY", host, "OK", out.read().decode().strip().replace("\n", "/"))
        except Exception as ex:
            print("VERIFY", host, "FAIL", type(ex).__name__, str(ex)[:120])
            rc = 1
        finally:
            v.close()

    sys.exit(rc)


if __name__ == "__main__":
    main()
