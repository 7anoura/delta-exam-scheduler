"""Read-only, necessary-but-not-sufficient scheduling feasibility checks."""
from collections import defaultdict
from datetime import datetime


def _min(time: str) -> int:
    h, m = map(int, time.split(':'))
    return h * 60 + m


def _active_at(d: str, minute: int, session: dict) -> bool:
    return session['date'] == d and _min(session['start']) <= minute < _min(session['end'])


def audit(data: dict) -> dict:
    people = data['staff']
    inv = [p for p in people if p['can_invigilate']]
    chairs = [p for p in people if p['can_chair'] and (
        data.get('head_of_control_staff_code') is None or
        p['staff_id'] != data.get('head_of_control_staff_code') or
        data['assumptions'].get('head_can_chair', False))]
    sittings = data['room_sittings']
    exams = data['exams']
    rules = data['assumptions']
    absences = rules.get('staff_unavailability') or []
    inv_per_room = rules['invigilators_per_room']

    points = sorted({(s['date'], s['start']) for s in sittings} |
                    {(session['date'], session['start'])
                     for exam in exams for session in exam['sessions']})
    slots = []
    chair_shortages = []
    inv_shortages = []
    for date, clock in points:
        now = _min(clock)
        occupied = [s for s in sittings if _active_at(date, now, s)]
        active_courses = sorted({e['code'] for e in exams if any(
            _active_at(date, now, session) for session in e['sessions'])})
        blocked_ids = {a['staff_id'] for a in absences if _active_at(date, now, a)}
        available_inv = sum(p['staff_id'] not in blocked_ids for p in inv)
        available_chairs = sum(p['staff_id'] not in blocked_ids for p in chairs)
        needed_inv = len(occupied) * inv_per_room
        needed_chairs = len(active_courses)
        row = {
            'date': date, 'time': clock,
            'occupied_rooms': len(occupied),
            'required_invigilators': needed_inv,
            'available_invigilators_at_start': available_inv,
            'simultaneous_courses': needed_chairs,
            'available_chairs_at_start': available_chairs,
        }
        slots.append(row)
        if needed_inv > available_inv:
            inv_shortages.append({**row, 'missing_invigilators_lower_bound': needed_inv - available_inv})
        if (not rules['allow_parallel_chair_assignments'] and needed_chairs > available_chairs):
            chair_shortages.append({**row, 'missing_chairs_lower_bound': needed_chairs - available_chairs,
                                    'course_codes': active_courses})

    by_room = defaultdict(list)
    for s in sittings:
        by_room[s['room_code']].append(s)
    double_bookings = []
    for code, events in by_room.items():
        events.sort(key=lambda r: (r['date'], r['start']))
        for i, event in enumerate(events):
            for later in events[i+1:]:
                if later['date'] != event['date']:
                    if later['date'] > event['date']:
                        break
                    continue
                if _min(later['start']) >= _min(event['end']):
                    break
                double_bookings.append({'room': code, 'date': event['date'],
                                        'first': event['sitting_id'], 'second': later['sitting_id']})
    issues = []
    if not data.get('head_of_control_selected'):
        issues.append('HEAD_OF_CONTROL_NOT_APPOINTED')
    if chair_shortages:
        issues.append('CHAIR_SHORTAGE')
    if inv_shortages:
        issues.append('INVIGILATOR_SHORTAGE')
    if double_bookings:
        issues.append('ROOM_DOUBLE_BOOKED')
    if rules['allow_parallel_chair_assignments']:
        issues.append('PARALLEL_CHAIR_POLICY_REQUIRES_MANUAL_VALIDATION')
    if rules['max_daily_invigilation_minutes'] is None:
        issues.append('DAILY_INVIGILATION_LIMIT_NOT_SET')
    issues.append('SOURCE_PDF_NOT_SIGNED_OFF')
    return {
        'status': 'BLOCKED_FOR_PUBLICATION',
        'counts': {
            'staff_total_active': len(people),
            'eligible_invigilators': len(inv),
            'eligible_chairs': len(chairs),
            'courses': len(exams),
            'exam_sessions': sum(len(e['sessions']) for e in exams),
            'physical_room_sittings': len(sittings),
            'required_invigilation_assignments': len(sittings) * inv_per_room,
            'time_points_evaluated': len(points),
        },
        'peak_required_invigilators': max((s['required_invigilators'] for s in slots), default=0),
        'chair_shortages': chair_shortages,
        'invigilator_shortages': inv_shortages,
        'double_booked_rooms': double_bookings[:30],
        'issues': issues,
        'note': 'This is only a lower-bound capacity/overlap screen, NOT a full scheduling solution. '
                'Break times, full duty intervals, fixed assignments and policies still require CP-SAT verification.'
    }
