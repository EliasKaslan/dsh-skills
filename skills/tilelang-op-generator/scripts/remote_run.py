#!/usr/bin/env python3
"""Retired legacy remote runner: no shell, SSH, deletion or device work."""
import json
import sys

if __name__ == "__main__":
    print(json.dumps({'verdict': 'BLOCKED_LEGACY_TOOL_RETIRED', 'tool': 'remote_run.py', 'reason': 'Superseded unsafe shell interpolation and whole-target remote replacement.', 'next': 'Read tilelang-op-generator/SKILL.md: use a task-specific unique directory, explicit deployment, file hashes and admitted devices. No automatic fallback to the legacy runner.'}, ensure_ascii=False))
    sys.exit(2)
