#!/usr/bin/env python3
"""Disabled historical helper; importing this module does not read credentials or mutate files."""
from pathlib import Path
import sys

def main():
    guidance = Path(__file__).resolve().parents[2] / 'anime-art' / 'SKILL.md'
    print('DISABLED legacy helper: Ignored Range responses were accepted as valid parts; fixed wheel tags did not validate compatibility. Use a verified package manager/downloader and hashes.', file=sys.stderr)
    print('Read the current DSH workflow: ' + str(guidance), file=sys.stderr)
    return 2

if __name__ == '__main__':
    sys.exit(main())
