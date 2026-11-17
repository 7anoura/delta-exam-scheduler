"""Export a non-PII local snapshot, audit and comparison (GET-only).

Usage: python -m tools.live_snapshot
       python -m tools.live_snapshot --period-id <uuid>
"""
import argparse
import json
from pathlib import Path

from app.audit import audit
from app.config import Settings
from app.snapshot import build_snapshot, compare_snapshot
from app.supabase_reader import SupabaseReader

ROOT = Path(__file__).resolve().parents[1]


def live_data(period_id: str | None = None):
    cfg = Settings.from_env()
    reader = SupabaseReader(cfg.supabase_url, cfg.supabase_secret_key)
    periods = reader.list_periods()
    if period_id is None:
        if len(periods) != 1:
            raise ValueError('Multiple (or zero) exam periods found; pass --period-id from /api/v1/periods')
        period_id = periods[0]['id']
    return build_snapshot(reader.period_data(period_id))


def dump(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Read live Supabase and compare it with the offline draft')
    parser.add_argument('--period-id', help='UUID of the exam period (optional when only one exists)')
    args = parser.parse_args()
    snapshot = live_data(args.period_id)
    output = ROOT / 'output'
    output.mkdir(exist_ok=True)
    baseline = json.loads((ROOT/'data'/'draft_snapshot.json').read_text(encoding='utf-8'))
    report = audit(snapshot)
    comparison = compare_snapshot(snapshot, baseline)
    dump(output/'live_snapshot.json', snapshot)
    dump(output/'live_audit.json', report)
    dump(output/'live_comparison.json', comparison)
    print('Live database read OK. (No Supabase records were edited.)')
    print('Active staff:', report['counts']['staff_total_active'])
    print('Course exams:', report['counts']['courses'])
    print('Exam sessions:', report['counts']['exam_sessions'])
    print('Room sittings:', report['counts']['physical_room_sittings'])
    print('Chair shortage time points:', len(report['chair_shortages']))
    print('Live matches offline draft:', comparison['matches'])
    print('Files: output/live_snapshot.json, output/live_audit.json, output/live_comparison.json')


if __name__ == '__main__':
    main()
