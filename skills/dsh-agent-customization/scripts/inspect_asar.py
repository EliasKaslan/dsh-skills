"""Bounded, read-only inspection of packed regular files in standard Electron ASAR.

No extraction, module import, credential reading, or archive code execution.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

MAX_HEADER = 32 * 1024 * 1024
MAX_ENTRY = 2 * 1024 * 1024
MAX_ENTRIES = 100000


def open_header(path):
    path = Path(path)
    total = path.stat().st_size
    with path.open('rb') as stream:
        raw = stream.read(16)
        if len(raw) != 16:
            raise ValueError('short ASAR header')
        marker, header_size, pickle_size, json_size = struct.unpack('<4I', raw)
        if not (marker == 4 and 8 <= header_size <= MAX_HEADER
                and pickle_size + 4 == header_size
                and 0 < json_size <= pickle_size - 4
                and 8 + header_size <= total):
            raise ValueError('unsupported ASAR header/range')
        raw_json = stream.read(json_size)
        if len(raw_json) != json_size:
            raise ValueError('short ASAR JSON')
        header = json.loads(raw_json.decode('utf8'))
    if not isinstance(header, dict) or not isinstance(header.get('files'), dict):
        raise ValueError('invalid files tree')
    return header, 8 + header_size


def entries(header):
    pending = [('', header['files'], 0)]
    count = 0
    while pending:
        prefix, files, depth = pending.pop()
        if depth > 64:
            raise ValueError('excessive ASAR depth')
        for name, item in files.items():
            count += 1
            if count > MAX_ENTRIES:
                raise ValueError('excessive ASAR entries')
            if (not isinstance(name, str) or name in ('', '.', '..')
                    or '/' in name or '\\' in name or '\x00' in name
                    or not isinstance(item, dict)):
                raise ValueError('invalid ASAR entry')
            full = prefix + name
            if 'files' in item:
                if not isinstance(item['files'], dict):
                    raise ValueError('invalid directory')
                pending.append((full + '/', item['files'], depth + 1))
            else:
                yield full, item


def read_packed(path, base, entry, limit=MAX_ENTRY):
    if not isinstance(entry, dict) or entry.get('unpacked') or 'link' in entry:
        raise ValueError('not a packed regular file')
    try:
        size, relative = entry['size'], entry['offset']
        if isinstance(size, bool) or not isinstance(size, int):
            raise ValueError('invalid size')
        if not isinstance(relative, str) or not relative.isascii() or not relative.isdigit():
            raise ValueError('invalid offset')
        offset = int(relative)
    except (KeyError, TypeError) as exc:
        raise ValueError('missing size/offset') from exc
    path = Path(path)
    if (not isinstance(base, int) or base < 16 or limit < 0 or size < 0
            or size > limit or base + offset + size > path.stat().st_size):
        raise ValueError('unsafe file range')
    with path.open('rb') as stream:
        stream.seek(base + offset)
        result = stream.read(size)
    if len(result) != size:
        raise ValueError('short ASAR data')
    return result


def inspect(path, packages=False):
    header, base = open_header(path)
    with Path(path).open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = {'sha256': digest,
              'data_base': base, 'entry_count': 0, 'packages': []}
    for name, entry in entries(header):
        result['entry_count'] += 1
        if packages and (name == 'package.json' or name.endswith('/package.json')):
            if '/@deepseek-ai/' not in name and name not in ('package.json', 'dsh/package.json'):
                continue
            if entry.get('unpacked') or 'link' in entry:
                continue
            value = json.loads(read_packed(path, base, entry))
            if not isinstance(value, dict):
                raise ValueError('package JSON must be object')
            result['packages'].append({'entry': name, 'name': value.get('name'),
                                       'version': value.get('version')})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--packages', action='store_true')
    args = parser.parse_args()
    print(json.dumps(inspect(args.archive, args.packages), ensure_ascii=True, indent=2))
