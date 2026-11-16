#!/usr/bin/env python3
"""Retired legacy entry: fail closed before imports, devices or writes."""
import json
import sys

if __name__ == "__main__":
    print(json.dumps({'verdict': 'BLOCKED_LEGACY_TOOL_RETIRED', 'tool': 'bi_equivalence.py', 'reason': '空结果、zip截断、数值equal冒充逐位；float32重建与零轮次边界不满足验收证据契约。', 'next': 'Read ../SKILL.md and ../references/legacy-tool-status.md; build and validate the task-specific experiment.'}, ensure_ascii=False))
    sys.exit(2)
