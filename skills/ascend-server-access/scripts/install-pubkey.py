"""Retired legacy entry; no import-time side effects."""
import sys

if __name__ == "__main__":
    print('BLOCKED_LEGACY_ENTRY: 旧自动信任主机与authorized_keys整文件覆盖路径已停用；按SKILL验证指纹并在授权内并发安全追加。', file=sys.stderr)
    sys.exit(2)
