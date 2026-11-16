#!/usr/bin/env python3
"""Retired legacy entry: fail closed before imports, devices or writes."""
import json
import sys

if __name__ == "__main__":
    print(json.dumps({'verdict': 'BLOCKED_LEGACY_TOOL_RETIRED', 'tool': 'bi_ops_triage.py', 'reason': '空CSV集合仍PASS；旧白名单/比例/芯片默认及排序规范化不能证明模型数值一致。', 'next': 'Read ../SKILL.md and ../references/legacy-tool-status.md; build and validate the task-specific experiment.'}, ensure_ascii=False))
    sys.exit(2)
