#!/usr/bin/env python3
"""Disabled historical helper; importing this module does not read credentials, fetch or mutate files."""
from pathlib import Path
import sys

def main():
    guidance = Path(__file__).resolve().parents[2] / 'lora-weekly-report' / 'SKILL.md'
    print('DISABLED legacy helper: it reused token + gh() from the disabled collect_lora_week module, so every call died with AttributeError (C.API / C.gh absent) before fetching anything. Collect PR details with a currently authorized DSH tool and pass the records to filter_merged_prs.py.', file=sys.stderr)
    print('Read the current DSH workflow: ' + str(guidance), file=sys.stderr)
    return 2

if __name__ == '__main__':
    sys.exit(main())
