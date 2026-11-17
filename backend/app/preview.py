"""Read-only CP-SAT preview API implementation for Delta Exam Scheduler.

No Supabase writes, no approvals, no personal names/phones, no persistent cache.
The response is intended only for a loopback development dashboard.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from tools._phase5_solver import (
    chair_solver, feasibility_precheck, invig_solver, minute, validate_source,
)


def validate_roster(snapshot: dict, assignments: list[dict]) -> dict:
    """Independent checks of solver output before presenting it to an operator."""
    errors: list[str] = []
    sit_map = {s['sitting_id']: s for s in snapshot['room_sittings']}
    eligible = {s['staff_id'] for s in snapshot['staff'] if s['can_invigilate']}
    rules = snapshot['assumptions']
    k = int(rules['invigilators_per_room'])
    prep = int(rules.get('preparation_minutes') or 0)
    gap = int(rules.get('min_break_minutes') or 0)
    max_daily = rules.get('max_daily_invigilation_minutes')
    absences = rules.get('staff_unavailability') or []

    covered: dict[str, list[str]] = defaultdict(list)
    staff_duties: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
    daily_minutes: dict[tuple[str, str], int] = defaultdict(int)
    for a in assignments:
        sid, sitting = a['staff_id'], sit_map.get(a['sitting_id'])
        if sitting is None:
            errors.append('Assignment references unknown sitting')
            continue
        if sid not in eligible:
            errors.append('Assignment uses ineligible staff')
        covered[a['sitting_id']].append(sid)
        start = minute(sitting['start']) - prep
        end = minute(sitting['end'])
        day = sitting['date']
        staff_duties[sid].append((day, start, end))
        daily_minutes[(sid, day)] += end - start
        if any(b['staff_id'] == sid and b['date'] == day
               and start < minute(b['end']) and minute(b['start']) < end
               for b in absences):
            errors.append('Assignment intersects approved unavailability')

    for sitting_id in sit_map:
        assigned = covered[sitting_id]
        if len(assigned) != k or len(set(assigned)) != k:
            errors.append('Room sitting does not have the required distinct invigilators')
            break
    for sid, duties in staff_duties.items():
        by_day = defaultdict(list)
        for day, start, end in duties:
            by_day[day].append((start, end))
        for day, intervals in by_day.items():
            intervals.sort()
            for (start, end), (next_start, next_end) in zip(intervals, intervals[1:]):
                if next_start < end + gap:
                    errors.append('Staff time conflict / insufficient break')
                    break
            if max_daily is not None and daily_minutes[sid, day] > int(max_daily):
                errors.append('Daily time limit exceeded')
    return {
        'valid': not errors,
        'issues': sorted(set(errors)),
        'covered_sittings': sum(len(v) == k and len(set(v)) == k for v in covered.values()),
        'total_sittings': len(sit_map),
    }


def generate_preview(snapshot: dict, seconds: int = 25) -> dict:
    validate_source(snapshot)
    invig = invig_solver(snapshot, seconds=seconds)
    shortages = feasibility_precheck(snapshot)
    if snapshot['assumptions'].get('allow_parallel_chair_assignments'):
        chairs = {
            'status': 'MANUAL_POLICY_REQUIRED', 'shortages': shortages,
            'reason': 'Chair parallelism requires faculty policy approval and a different validated model.',
        }
    elif shortages:
        chairs = {
            'status': 'INFEASIBLE_PRECHECK', 'shortages': shortages,
            'reason': 'There are more concurrent course exams than eligible chairpersons.',
        }
    else:
        chairs = chair_solver(snapshot, seconds=min(seconds, 15))

    assignments = invig.get('assignments', [])
    roster_validation = validate_roster(snapshot, assignments) if assignments else {
        'valid': False, 'issues': [invig.get('reason', 'No invigilator solution produced')],
        'covered_sittings': 0, 'total_sittings': len(snapshot['room_sittings']),
    }
    eligible = [s['staff_id'] for s in snapshot['staff'] if s['can_invigilate']]
    loads: dict[str, dict] = {sid: {'staff_id': sid, 'minutes': 0, 'days': set(), 'duties': 0} for sid in eligible}
    for a in assignments:
        sid = a['staff_id']
        if sid not in loads:
            continue
        loads[sid]['minutes'] += int(a['minutes'])
        loads[sid]['days'].add(a['date'])
        loads[sid]['duties'] += 1
    staff_loads = sorted([
        {'staff_id': v['staff_id'], 'minutes': v['minutes'], 'days': len(v['days']), 'duties': v['duties']}
        for v in loads.values()
    ], key=lambda v: v['staff_id'])
    min_load = min((x['minutes'] for x in staff_loads), default=0)
    max_load = max((x['minutes'] for x in staff_loads), default=0)
    invig_metadata = {k: v for k, v in invig.items() if k != 'assignments'}
    chair_metadata = {k: v for k, v in chairs.items() if k not in {'assignments'}}
    return {
        'mode': 'preview_only', 'persisted': False, 'published': False,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'period_id': snapshot['exam_period_id'],
        'invigilator': invig_metadata,
        'chair': chair_metadata,
        'validation': roster_validation,
        'metrics': {
            'staff_used': sum(x['duties'] > 0 for x in staff_loads),
            'total_duties': len(assignments),
            'minimum_minutes': min_load,
            'maximum_minutes': max_load,
            'workload_gap_minutes': max_load - min_load,
            'total_days_min': min((x['days'] for x in staff_loads), default=0),
            'total_days_max': max((x['days'] for x in staff_loads), default=0),
        },
        'staff_loads': staff_loads,
        'assignments': assignments,
        'message': 'Draft only. Chair coverage, manual review, and sign-off remain required. No data was saved.',
    }
