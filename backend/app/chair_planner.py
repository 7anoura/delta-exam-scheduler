"""Partial-safe committee-chair planning from live Supabase data.

One doctor is assigned to one course exam (covering ALL its sessions), not
one per lab. A chair cannot be booked across overlapping course sessions.
Head of Control is an administrative appointment and is excluded by default.
Never claims completeness for a partial result; never publishes anything.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo('Africa/Cairo')


def dt(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timezone missing in exam data')
    return parsed


def intersects(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def build_chair_context(raw: dict) -> dict:
    period = raw['exam_periods'][0]
    rule = raw['scheduling_rules'][0]
    head_id = period.get('head_of_control_staff_id')
    head_can_chair = bool(rule.get('head_can_chair', False))
    people = {s['id']: s for s in raw['staff']}
    eligible = [s for s in people.values()
                if s['is_active'] and s['can_chair'] and (s['id'] != head_id or head_can_chair)]
    course_by_id = {c['id']: c for c in raw['courses']}
    intervals = defaultdict(list)
    for s in raw['exam_sessions']:
        intervals[s['exam_id']].append((dt(s['starts_at']), dt(s['ends_at'])))
    exams = []
    for exam in raw['exams']:
        course = course_by_id.get(exam['course_id'])
        if not course or not intervals.get(exam['id']):
            raise ValueError('Exam has missing course or sessions')
        sessions = sorted(intervals[exam['id']])
        minutes = sum(int((stop - start).total_seconds() // 60) for start, stop in sessions)
        if minutes < 1 or any(stop <= start for start,stop in sessions):
            raise ValueError('Invalid exam session duration')
        exams.append({'exam_id': exam['id'], 'code': course['code'], 'title': course['title'],
                      'sessions': sessions, 'minutes': minutes})
    exams.sort(key=lambda e: e['code'])
    blocks = defaultdict(list)
    for s in raw['staff_unavailability']:
        if s['status'] == 'approved':
            blocks[s['staff_id']].append((dt(s['starts_at']), dt(s['ends_at'])))
    return {'period_id': period['id'], 'head_id': head_id, 'head_can_chair': head_can_chair,
            'eligible': sorted(eligible, key=lambda s: s['source_ref']),
            'exams': exams, 'blocks': blocks, 'people': people,
            'parallel_allowed': rule['allow_parallel_chair_assignments']}


def generate_chair_plan(raw: dict, seconds: int = 15) -> dict:
    from ortools.sat.python import cp_model
    ctx = build_chair_context(raw)
    if ctx['parallel_allowed']:
        return {'status': 'POLICY_REVIEW_REQUIRED', 'coverage': 'not_generated',
                'assignments': [], 'unassigned_exams': [],
                'reason': 'Parallel chair assignments require an approved scheduling policy and separate solver.'}
    exams = ctx['exams']; chairs = ctx['eligible']
    if not exams:
        return {'status': 'NO_EXAMS', 'assignments': [], 'unassigned_exams': [], 'total_exams': 0,
                'assigned_exams': 0, 'eligible_chairs': len(chairs)}
    model = cp_model.CpModel()
    x = {}; unassigned = []
    for i, exam in enumerate(exams):
        picks = []
        for j, chair in enumerate(chairs):
            if any(intersects(session, absence)
                   for session in exam['sessions'] for absence in ctx['blocks'][chair['id']]):
                continue
            v = model.new_bool_var(f'chair_{i}_{j}')
            x[(i, j)] = v
            picks.append(v)
        missing = model.new_bool_var(f'unfilled_{i}')
        unassigned.append(missing)
        model.add(sum(picks) + missing == 1)
    for i in range(len(exams)):
        for k in range(i+1, len(exams)):
            if any(intersects(a, b) for a in exams[i]['sessions'] for b in exams[k]['sessions']):
                for j in range(len(chairs)):
                    if (i,j) in x and (k,j) in x:
                        model.add(x[(i,j)] + x[(k,j)] <= 1)
    total_minutes = sum(exam['minutes'] for exam in exams)
    max_load = model.new_int_var(0, total_minutes, 'max_minutes')
    min_load = model.new_int_var(0, total_minutes, 'min_minutes')
    for j in range(len(chairs)):
        load = sum(exams[i]['minutes'] * v for (i, cj), v in x.items() if cj == j)
        model.add(load <= max_load)
        model.add(load >= min_load)
    # Filling one more course always outweighs any possible minutes imbalance.
    model.minimize((total_minutes+1) * sum(unassigned) + (max_load-min_load))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    state = solver.solve(model)
    if state not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {'status': solver.status_name(state), 'coverage': 'not_generated',
                'assigned_exams': 0, 'total_exams': len(exams), 'eligible_chairs': len(chairs),
                'assignments': [], 'unassigned_exams': [],
                'reason': 'No solution was returned within the solver time limit. Do not save.'}
    assignments = []
    unfilled = []
    for i, exam in enumerate(exams):
        if solver.value(unassigned[i]):
            unfilled.append({'exam_id': exam['exam_id'], 'code': exam['code'], 'title': exam['title']})
        else:
            chosen = [j for j in range(len(chairs)) if (i,j) in x and solver.value(x[(i,j)])]
            if len(chosen) != 1:
                raise ValueError('Solver returned an invalid chair assignment')
            person = chairs[chosen[0]]
            assignments.append({'exam_id': exam['exam_id'], 'code': exam['code'], 'title': exam['title'],
                                'staff_id': person['id'], 'staff_code': person['source_ref']})
    assignments.sort(key=lambda a:a['code'])
    return {'status': solver.status_name(state),
            'coverage': 'complete' if not unfilled else 'partial',
            'assigned_exams': len(assignments), 'total_exams': len(exams),
            'missing_count': len(unfilled), 'eligible_chairs': len(chairs),
            'head_of_control_id': ctx['head_id'],
            'head_can_chair': ctx['head_can_chair'],
            'assignments': assignments, 'unassigned_exams': unfilled,
            'reason': ('All courses assigned, subject to administrator review.' if not unfilled
                       else 'A partial chair plan was generated. Publication remains blocked.')}
