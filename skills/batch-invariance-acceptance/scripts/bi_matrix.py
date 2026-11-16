#!/usr/bin/env python3
"""Retired legacy entry: fail closed before imports, devices or writes."""
import json
import sys

if __name__ == "__main__":
    print(json.dumps({'verdict': 'BLOCKED_LEGACY_TOOL_RETIRED', 'tool': 'bi_matrix.py', 'reason': 'PASS日志可覆盖进程失败；NOT_RUN与未知枚举可被阶段汇总忽略，不能完整对账场景与rank。', 'next': 'Read ../SKILL.md and ../references/legacy-tool-status.md; build and validate the task-specific experiment.'}, ensure_ascii=False))
    sys.exit(2)
