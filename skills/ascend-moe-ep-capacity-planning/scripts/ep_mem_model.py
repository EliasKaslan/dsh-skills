"""Retired legacy entry; no import-time side effects."""
import sys

if __name__ == "__main__":
    print('BLOCKED_LEGACY_ENTRY: 旧不均匀专家估算会低估最大rank；使用同目录plan_capacity.py及references/planner.md的显式JSON输入。', file=sys.stderr)
    sys.exit(2)
