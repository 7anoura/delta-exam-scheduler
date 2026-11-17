"""OPTIONAL: Run the original Phase-5 CP-SAT preview against LIVE, read-only Supabase data.

Outputs local CSV only. This does not write any assignments to the database.
Run: python -m tools.run_live_preview --seconds 25
"""
import argparse
import json
from pathlib import Path

from .live_snapshot import live_data, dump, ROOT
from ._phase5_solver import (
    validate_source, invig_solver, chair_solver, save_csv, feasibility_precheck,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--period-id')
    parser.add_argument('--seconds', type=int, default=25)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 180:
        parser.error('--seconds must be between 1 and 180')
    data = live_data(args.period_id)
    validate_source(data)
    out = ROOT/'output'
    out.mkdir(exist_ok=True)
    audit_chair = feasibility_precheck(data)
    # Do not produce a potentially false chair roster when availability or parallel
    # chair rules are unresolved. Chair solver from Phase 5 is an *early prototype*.
    if data['assumptions'].get('allow_parallel_chair_assignments'):
        chair = {'status': 'MANUAL_POLICY_REQUIRED', 'shortages': audit_chair,
                 'reason': 'Parallel chair assignments require an approved rule and a dedicated solver.'}
    else:
        chair = chair_solver(data, seconds=min(10, args.seconds))
    invig = invig_solver(data, seconds=args.seconds)
    if invig.get('assignments'):
        save_csv(out/'invigilator_LIVE_DRAFT.csv', invig['assignments'],
                 ['staff_id','date','start','end','room_code','sitting_id','minutes','course_codes'])
    if chair.get('assignments'):
        save_csv(out/'chair_LIVE_DRAFT.csv', chair['assignments'], ['course_code','staff_id'])
    if chair.get('shortages'):
        save_csv(out/'chair_shortages_LIVE.csv', chair['shortages'],
                 ['date','time','active_courses','eligible_chairs','minimum_missing_chairs','course_codes'])
    dump(out/'live_preview_report.json', {
        'draft_only': True, 'data_source': 'Live Supabase, read-only',
        'invigilator': {k:v for k,v in invig.items() if k != 'assignments'},
        'chair': {k:v for k,v in chair.items() if k != 'assignments'},
    })
    print('Invigilators:', invig['status'], 'Chairs:', chair['status'])
    print('Preview only: output/; nothing was saved or published in Supabase.')


if __name__ == '__main__':
    main()
