"""Retired legacy entry; no import-time side effects."""
import sys

if __name__ == "__main__":
    print('BLOCKED_LEGACY_ENTRY: 旧主机根因、host-key绕过与吞吐负载流程已退役；按SKILL分层检查，仅显式目标可用probe_hosts.py。', file=sys.stderr)
    sys.exit(2)
