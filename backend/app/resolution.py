"""Advisory-only what-if analysis for committee chair shortages.

Makes *copies* of live records. No Supabase writes, policy updates, or chair-plan
saving. Every suggestion is conditional on university approval. The solver
is the same Phase 11 CP-SAT chair planner used by the actual preview.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from .chair_planner import build_chair_context, generate_chair_plan, dt, intersects, CAIRO


def hypothetical_data(raw: dict, *, include_assistant_lecturers: bool = False,
                      simulate_head_appointment: bool = False,
                      head_staff_id: str | None = None,
                      head_can_chair: bool | None = None) -> tuple[dict, dict]:
    data = deepcopy(raw)
    period = data['exam_periods'][0]
    staff = {row['id']: row for row in data['staff']}
    if simulate_head_appointment:
        if head_staff_id is not None:
            selected = staff.get(head_staff_id)
            # Policy changes are not allowed to appoint ineligible staff as head.
            if not selected or not selected['is_active'] or not selected['can_chair']:
                raise ValueError('Select an active current chair-eligible doctor as the simulated Head of Control.')
        period['head_of_control_staff_id'] = head_staff_id
    enabled = []
    if include_assistant_lecturers:
        for person in data['staff']:
            if person['is_active'] and person['academic_rank'] == 'assistant_lecturer' and not person['can_chair']:
                person['can_chair'] = True
                enabled.append(person['source_ref'])
    if head_can_chair is not None:
        data['scheduling_rules'][0]['head_can_chair'] = head_can_chair
    if data['scheduling_rules'][0]['allow_parallel_chair_assignments']:
        raise ValueError('Parallel chair assignments require a separately approved university policy.')
    return data, {
        'assistant_lecturer_ids_simulated': enabled,
        'selected_head_id': period.get('head_of_control_staff_id'),
        'head_can_chair_simulated': data['scheduling_rules'][0].get('head_can_chair', False),
        'head_appointment_simulated': simulate_head_appointment,
    }


def overlapping_bottlenecks(raw: dict, max_rows: int = 12) -> list[dict]:
    """Lower bound on simultaneous chair demand at each distinct start instant.

    Note: sufficient pointwise capacity doesn't prove an entire-course solution
    exists. CP-SAT still checks eligibility, absences and all course intervals.
    """
    ctx = build_chair_context(raw)
    starts = sorted({a for exam in ctx['exams'] for a, _ in exam['sessions']})
    rows = []
    for t in starts:
        active = [e for e in ctx['exams'] if any(a <= t < b for a, b in e['sessions'])]
        if not active:
            continue
        free = [p for p in ctx['eligible'] if not any(a <= t < b for a, b in ctx['blocks'][p['id']])]
        missing = max(0, len(active) - len(free))
        if missing:
            local_time = t.astimezone(CAIRO)
            rows.append({
                'date': local_time.strftime('%Y-%m-%d'),
                'time': local_time.strftime('%H:%M'),
                'simultaneous_courses': len(active),
                'eligible_present_chairs': len(free),
                'minimum_missing_chairs': missing,
                'course_codes': sorted([e['code'] for e in active]),
                'occupied_chair_codes': sorted([p['source_ref'] for p in free]),
            })
    return sorted(rows, key=lambda r: (-r['minimum_missing_chairs'], r['date'], r['time']))[:max_rows]


def _summarize(plan: dict, raw: dict) -> dict:
    return {
        'solver_status': plan['status'],
        'coverage': plan.get('coverage', 'not_generated'),
        'assigned_exams': plan.get('assigned_exams', 0),
        'total_exams': plan.get('total_exams', 0),
        'missing_count': plan.get('missing_count'),
        'eligible_chairs': plan.get('eligible_chairs', 0),
        'unassigned_exams': plan.get('unassigned_exams', []),
        'bottlenecks': overlapping_bottlenecks(raw),
        'reason': plan.get('reason', ''),
    }


def simulate_shortage_resolution(raw: dict, *, include_assistant_lecturers: bool = False,
                                  simulate_head_appointment: bool = False,
                                  head_staff_id: str | None = None,
                                  head_can_chair: bool | None = None,
                                  seconds: int = 12) -> dict:
    if not 2 <= seconds <= 25:
        raise ValueError('Solver time must be 2–25 seconds per scenario.')
    if raw['exam_periods'][0].get('status') == 'closed':
        raise ValueError('Examination period is closed.')
    if raw['scheduling_rules'][0].get('allow_parallel_chair_assignments'):
        raise ValueError('Parallel chair policy needs separate modelling; simulation declined.')
    alternative, changes = hypothetical_data(
        raw, include_assistant_lecturers=include_assistant_lecturers,
        simulate_head_appointment=simulate_head_appointment,
        head_staff_id=head_staff_id, head_can_chair=head_can_chair,
    )
    base_plan = generate_chair_plan(raw, seconds=seconds)
    alternative_plan = generate_chair_plan(alternative, seconds=seconds)
    base = _summarize(base_plan, raw)
    sim = _summarize(alternative_plan, alternative)
    verified = {'OPTIMAL', 'FEASIBLE'}
    both_valid = base['solver_status'] in verified and sim['solver_status'] in verified
    delta = (base['missing_count'] - sim['missing_count']) if both_valid else None
    return {
        'mode': 'ADVISORY_ONLY',
        'saved': False,
        'policy_changed': False,
        'schedule_changed': False,
        'publication_enabled': False,
        'baseline': base,
        'hypothetical': sim,
        'comparison': {
            'missing_courses_reduced_by': delta,
            'full_coverage_in_simulation': sim['coverage'] == 'complete' if both_valid else False,
            'requires_formal_approval': bool(include_assistant_lecturers or head_can_chair is True),
            'conclusive': both_valid,
        },
        'scenario': changes,
        'advisory': ('This is a counterfactual planning preview only. It does NOT appoint a Head, '
                     'promote Assistant Lecturers, authorize dual roles, alter drafts, or publish a schedule. '
                     'A zero missing count is not final academic or administrative approval.'),
    }
