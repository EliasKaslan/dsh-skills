#!/usr/bin/env python3
"""Normalize already-collected PR details with explicit half-open time bounds."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys

def instant(value):
    if not isinstance(value,str):raise ValueError('timestamp must be a string')
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:raise ValueError('timestamp needs explicit timezone')
    return parsed.astimezone(dt.timezone.utc)

def filter_records(data,start,end):
    start,end=instant(start),instant(end)
    if start>=end:raise ValueError('start must precede end')
    if not isinstance(data,dict) or not isinstance(data.get('items'),list):raise ValueError('input requires items list')
    warnings=[]
    if data.get('complete') is not True:warnings.append('collector did not declare completed coverage')
    if data.get('incomplete_results') is True:warnings.append('source search marked incomplete_results')
    total=data.get('total_count')
    if total is not None:
        if type(total) is not int or total<0:raise ValueError('total_count must be nonnegative integer')
        if total>len(data['items']):warnings.append('reported total exceeds supplied records; paging declaration cannot resolve the coverage contradiction')
    seen={}; kept=[]; unmerged=outside=duplicates=0
    for row in data['items']:
        if not isinstance(row,dict):raise ValueError('record must be an object')
        repo=row.get('repo');number=row.get('number')
        if not isinstance(repo,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('repo must be owner/name')
        if type(number) is not int or number<=0:raise ValueError('number must be positive integer')
        if 'merged_at' not in row:raise ValueError('record missing merged_at; fetch PR detail rather than assuming unmerged')
        if 'merged' in row and type(row['merged']) is not bool:raise ValueError('merged flag, when present, must be boolean')
        merged_at=row['merged_at']
        merged=instant(merged_at) if merged_at is not None else None
        if row.get('merged') is False and merged is not None:raise ValueError('contradictory merged flag and merged_at')
        if row.get('merged') is True and merged is None:raise ValueError('merged flag true without merge timestamp')
        key=(repo.lower(),number)
        if key in seen:
            if seen[key]!=merged:raise ValueError('duplicate PR has contradictory merge timestamps')
            duplicates+=1;continue
        seen[key]=merged
        if merged is None:unmerged+=1;continue
        if not start<=merged<end:outside+=1;continue
        item=dict(row);item['merged_at']=merged.isoformat().replace('+00:00','Z');kept.append(item)
    kept.sort(key=lambda item:(item['merged_at'],item['repo'].lower(),item['number']))
    return {'verdict':'PARTIAL' if warnings else 'FILTERED','coverage_warnings':warnings,
            'window_utc':{'start_inclusive':start.isoformat(),'end_exclusive':end.isoformat()},
            'merged_count':len(kept),'unmerged_count':unmerged,'outside_window_count':outside,
            'duplicates_removed':duplicates,'merged':kept,
            'scope':'filtering only; source completeness and deployment capability not independently verified'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_json');parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    args=parser.parse_args(argv)
    try:
        data=json.loads(Path(args.input_json).read_text(encoding='utf-8-sig'))
        result=filter_records(data,args.start,args.end)
    except (OSError,ValueError,TypeError) as exc:
        print(json.dumps({'verdict':'ERROR','error':str(exc)},ensure_ascii=False));return 2
    print(json.dumps(result,ensure_ascii=False,indent=2));return 1 if result['verdict']=='PARTIAL' else 0

if __name__=='__main__':sys.exit(main())
