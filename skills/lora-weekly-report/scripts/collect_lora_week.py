#!/usr/bin/env python3
"""Disabled historical helper; importing this module does not read credentials or mutate files."""
from pathlib import Path
import sys

def main():
    guidance = Path(__file__).resolve().parents[2] / 'lora-weekly-report' / 'SKILL.md'
    print('DISABLED legacy helper: The old collector read a fixed credential at import, kept only the first100 search results and used overlapping window ends. Collect with a currently authorized DSH tool and use filter_merged_prs.py.', file=sys.stderr)
    print('Read the current DSH workflow: ' + str(guidance), file=sys.stderr)
    return 2

if __name__ == '__main__':
    sys.exit(main())
