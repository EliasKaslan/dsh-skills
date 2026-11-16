"""Retired legacy entry; no import-time side effects."""
import sys

if __name__ == "__main__":
    print('BLOCKED_LEGACY_ENTRY: 旧脚本会修改build-system外的TOML依赖，且无完整事务回滚；按SKILL进行精确局部diff。', file=sys.stderr)
    sys.exit(2)
