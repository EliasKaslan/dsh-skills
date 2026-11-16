#!/usr/bin/env python3
"""Disabled historical helper; importing this module does not read credentials or mutate files."""
from pathlib import Path
import sys

def main():
    guidance = Path(__file__).resolve().parents[2] / 'lora-weekly-report' / 'SKILL.md'
    print('DISABLED legacy helper: The old renderer lost links nested inside bold Markdown and used historical sender/recipient defaults. Use the currently authorized converter/mail tool and inspect the rendered message.', file=sys.stderr)
    print('Read the current DSH workflow: ' + str(guidance), file=sys.stderr)
    return 2

if __name__ == '__main__':
    sys.exit(main())
