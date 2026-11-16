"""Retired legacy entry; no import-time side effects."""
import sys

if __name__ == "__main__":
    print('BLOCKED_LEGACY_ENTRY: 旧静态阈值/进程映射可能误判空卡。用 ascend-server-access/scripts/probe_hosts.py 显式指定主机采原始遥测，再按SKILL判据核实。', file=sys.stderr)
    sys.exit(2)
