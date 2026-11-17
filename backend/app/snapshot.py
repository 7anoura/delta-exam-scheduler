"""Convert the live relational database to Phase-5-compatible, anonymous input.

No names, phone numbers, emails or Supabase keys are exported.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo('Africa/Cairo')


class DataIntegrityError(Exception):
    pass


def local(ts: str) -> tuple[str, str]:
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('Timestamp missing timezone')
        date_time = dt.astimezone(CAIRO)
    except (TypeError, AttributeError, ValueError) as exc:
        raise DataIntegrityError('Invalid timestamp in Supabase data') from exc
    return date_time.strftime('%Y-%m-%d'), date_time.strftime('%H:%M')


def normalized_session(row: dict) -> dict:
    sd, st = local(row['starts_at'])
    ed, en = local(row['ends_at'])
    if sd != ed or st >= en:
        raise DataIntegrityError('This prototype supports same-day, positive-duration exam sessions only')
    return {'date': sd, 'start': st, 'end': en,
            'source_ref': row['source_ref'] or row['id']}


def build_snapshot(raw: dict) -> dict:
    if len(raw['exam_periods']) != 1:
        raise DataIntegrityError('Expected exactly one matching examination period')
    period = raw['exam_periods'][0]
    rules = raw['scheduling_rules']
    if len(rules) != 1:
        raise DataIntegrityError('Scheduling rules are missing or duplicated for this period')
    rule = rules[0]
    people = [s for s in raw['staff'] if s['is_active']]
    staff_by_uuid = {}
    staff = []
    for s in people:
        sid = s.get('source_ref')
        if not sid:
            raise DataIntegrityError('Active staff without source_ref: review data before running optimizer')
        if sid in {p['staff_id'] for p in staff}:
            raise DataIntegrityError('Duplicate staff source_ref')
        staff_by_uuid[s['id']] = sid
        staff.append({'staff_id': sid, 'academic_rank': s['academic_rank'],
                      'can_invigilate': s['can_invigilate'], 'can_chair': s['can_chair']})

    courses = {r['id']: r for r in raw['courses']}
    rooms = {r['id']: r for r in raw['rooms']}
    exams = {r['id']: r for r in raw['exams']}
    room_sittings = {r['id']: r for r in raw['room_sittings']}
    exam_sessions = {r['id']: r for r in raw['exam_sessions']}
    grouped_sessions = defaultdict(list)
    for session in raw['exam_sessions']:
        exam_id = session['exam_id']
        if exam_id not in exams:
            raise DataIntegrityError('Exam session references a missing exam')
        grouped_sessions[exam_id].append(normalized_session(session))

    schedule_exams = []
    for eid, exam in exams.items():
        course = courses.get(exam['course_id'])
        if course is None:
            raise DataIntegrityError('Exam references a missing course')
        schedule_exams.append({
            'code': course['code'], 'title': course['title'],
            'sessions': sorted(grouped_sessions[eid], key=lambda s: (s['date'], s['start'], s['source_ref']))
        })

    sitting_links = defaultdict(list)
    linked_sessions = set()
    for link in raw['session_room_links']:
        session = exam_sessions.get(link['exam_session_id'])
        sitting = room_sittings.get(link['room_sitting_id'])
        if session is None or sitting is None:
            raise DataIntegrityError('A session-room link refers to a nonexistent entry')
        if (local(session['starts_at']) != local(sitting['starts_at']) or
                local(session['ends_at']) != local(sitting['ends_at'])):
            raise DataIntegrityError('Linked exam session and physical room have different time windows')
        course = courses.get(exams[session['exam_id']]['course_id'])
        sitting_links[sitting['id']].append((course['code'], session['source_ref'] or session['id']))
        linked_sessions.add(session['id'])

    unlinked = set(exam_sessions) - linked_sessions
    if unlinked:
        raise DataIntegrityError(f'{len(unlinked)} exam session(s) have no physical room assigned')

    sittings = []
    keys = set()
    for sitting in raw['room_sittings']:
        room = rooms.get(sitting['room_id'])
        if room is None:
            raise DataIntegrityError('Room sitting refers to missing room')
        if not sitting_links[sitting['id']]:
            raise DataIntegrityError('Room sitting has no course session link')
        date, start = local(sitting['starts_at'])
        end_date, end = local(sitting['ends_at'])
        if date != end_date or end <= start:
            raise DataIntegrityError('This prototype supports same-day, positive-duration room sittings only')
        key = f"{date}_{start}_{room['code']}"
        if key in keys:
            raise DataIntegrityError('Duplicate physical room and start time (possible overlap)')
        keys.add(key)
        links = sitting_links[sitting['id']]
        sittings.append({
            'sitting_id': key,
            'date': date, 'start': start, 'end': end,
            'room_code': room['code'],
            'course_codes': sorted({code for code, _ in links}),
            'session_refs': sorted({ref for _, ref in links}),
        })

    absence = []
    for interval in raw['staff_unavailability']:
        if interval['status'] != 'approved' or interval['staff_id'] not in staff_by_uuid:
            continue
        d1, t1 = local(interval['starts_at'])
        d2, t2 = local(interval['ends_at'])
        if d1 != d2:
            raise DataIntegrityError('Multi-day unavailability needs interval splitting before use by Phase 5 solver')
        absence.append({'staff_id': staff_by_uuid[interval['staff_id']], 'date': d1,
                        'start': t1, 'end': t2})

    return {
        'label': period['name'],
        'source': 'Live Supabase PostgREST (read-only; no names or phones)',
        'verified_against_live_database': True,
        'exam_period_id': period['id'],
        'head_of_control_selected': period['head_of_control_staff_id'] is not None,
        'head_of_control_staff_code': staff_by_uuid.get(period['head_of_control_staff_id']),
        'assumptions': {
            'invigilators_per_room': rule['invigilators_per_room'],
            'min_break_minutes': rule['min_break_minutes'],
            'preparation_minutes': rule['extra_preparation_minutes'],
            'max_daily_invigilation_minutes': rule['max_daily_invigilation_minutes'],
            'allow_parallel_chair_assignments': rule['allow_parallel_chair_assignments'],
            'head_can_chair': bool(rule.get('head_can_chair', False)),
            'staff_unavailability': absence,
        },
        'staff': sorted(staff, key=lambda s: s['staff_id']),
        'exams': sorted(schedule_exams, key=lambda e: e['code']),
        'room_sittings': sorted(sittings, key=lambda s: (s['date'], s['start'], s['room_code'])),
    }


def _fingerprints(data: dict) -> dict[str, set[tuple]]:
    return {
        'staff': {(s['staff_id'], s['academic_rank'], s['can_invigilate'], s['can_chair'])
                  for s in data['staff']},
        'exam_sessions': {
            (e['code'], s['date'], s['start'], s['end'], s['source_ref'])
            for e in data['exams'] for s in e['sessions']
        },
        'room_sittings': {
            (s['date'], s['start'], s['end'], s['room_code'],
             tuple(s['course_codes']), tuple(s['session_refs']))
            for s in data['room_sittings']
        },
    }


def compare_snapshot(live: dict, offline: dict) -> dict:
    current, original = _fingerprints(live), _fingerprints(offline)
    results = {}
    for key in original:
        removed = sorted(original[key] - current[key])
        added = sorted(current[key] - original[key])
        results[key] = {
            'matches': not removed and not added,
            'expected': len(original[key]), 'live': len(current[key]),
            'missing_from_live_count': len(removed), 'extra_in_live_count': len(added),
            'missing_from_live_sample': [str(i) for i in removed[:5]],
            'extra_in_live_sample': [str(i) for i in added[:5]],
        }
    rules_equal = {
        k: (offline['assumptions'].get(k) == live['assumptions'].get(k))
        for k in ('invigilators_per_room', 'min_break_minutes', 'preparation_minutes',
                  'max_daily_invigilation_minutes', 'allow_parallel_chair_assignments',
                  'staff_unavailability')
    }
    return {'matches': all(x['matches'] for x in results.values()) and all(rules_equal.values()),
            'sections': results, 'rule_matches': rules_equal,
            'note': 'Compares structure and assumptions with original draft; does not certify PDF transcription accuracy.'}
