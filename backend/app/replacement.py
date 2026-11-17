"""Phase 10 replacement candidate recommendations (advisory only).

The Postgres RPC is the authoritative validator for writes. The API never trusts
browser-provided UUIDs for staff and never edits an existing draft in place.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any


def time_value(s: str) -> datetime:
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def suggest(raw: dict, saved: dict, sitting_id: str, old_staff_code: str) -> list[dict[str, Any]]:
    entries = saved['assignments']
    if saved['version']['status'] != 'draft':
        raise ValueError('Only saved DRAFT versions support replacement')
    selected = [x for x in entries if x['sitting_id'] == sitting_id and x['staff_id'] == old_staff_code]
    if len(selected) != 1:
        raise ValueError('Target assignment is not present in this draft')
    sittings = {s['id']: s for s in raw['room_sittings']}
    target = sittings.get(sitting_id)
    if not target:
        raise ValueError('Selected room sitting was not found in current records')
    rules = raw['scheduling_rules'][0]
    prep = int(rules['extra_preparation_minutes'])
    rest = int(rules['min_break_minutes'])
    limit = rules['max_daily_invigilation_minutes']
    start = time_value(target['starts_at'])
    end = time_value(target['ends_at'])
    # Same date convention as the DB: Cairo calendar day.
    from zoneinfo import ZoneInfo
    cairo = ZoneInfo('Africa/Cairo')
    day = start.astimezone(cairo).date()
    unavailable = defaultdict(list)
    for item in raw['staff_unavailability']:
        if item['status'] == 'approved':
            unavailable[item['staff_id']].append((time_value(item['starts_at']), time_value(item['ends_at'])))
    bystaff = defaultdict(list)
    assigned_codes = set()
    for row in entries:
        s = sittings.get(row['sitting_id'])
        if not s:
            raise ValueError('Saved assignments refer to a deleted sitting')
        if row['sitting_id'] == sitting_id:
            assigned_codes.add(row['staff_id'])
        bystaff[row['staff_id']].append((time_value(s['starts_at']), time_value(s['ends_at'])))
    options = []
    for person in raw['staff']:
        code, uid = person['source_ref'], person['id']
        if not person['is_active'] or not person['can_invigilate'] or code in assigned_codes:
            continue
        if any(start - timedelta(minutes=prep) < u_end and end > u_start for u_start,u_end in unavailable[uid]):
            continue
        duties = bystaff[code]
        overlap = any((start - timedelta(minutes=prep) < e + timedelta(minutes=rest)
                       and s - timedelta(minutes=prep) < end + timedelta(minutes=rest)) for s,e in duties)
        if overlap:
            continue
        today = sum(((e-s).total_seconds()/60 + prep) for s,e in duties if s.astimezone(cairo).date() == day)
        if limit is not None and today + (end-start).total_seconds()/60 + prep > int(limit):
            continue
        minutes = round(sum((e-s).total_seconds()/60 + prep for s,e in duties))
        days = len({s.astimezone(cairo).date() for s,_ in duties})
        options.append({'staff_code': code, 'existing_minutes': minutes, 'existing_days': days,
                        'existing_duties': len(duties), 'new_daily_minutes': round(today + (end-start).total_seconds()/60 + prep)})
    options.sort(key=lambda x: (x['existing_minutes'], x['existing_days'], x['existing_duties'], x['staff_code']))
    return options[:30]
