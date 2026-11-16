#!/usr/bin/env python3
"""Retired legacy entry: fail closed before imports, devices or writes."""
import json
import sys

if __name__ == "__main__":
    print(json.dumps({'verdict': 'BLOCKED_LEGACY_TOOL_RETIRED', 'tool': 'bi_preflight.py', 'reason': '仅元数据与名称/首个动态库探测不能完成当前框架/硬件语义准入，旧固定映射不作当前能力判据。', 'next': 'Read ../SKILL.md and ../references/legacy-tool-status.md; build and validate the task-specific experiment.'}, ensure_ascii=False))
    sys.exit(2)
