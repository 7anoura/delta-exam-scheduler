"""Phase 5: experimental, OFFLINE CP-SAT proof-of-concept.

Usage: python run_solver.py
Requires: pip install -r requirements.txt
Reads data/draft_snapshot.json; writes output/*.csv and report.json.
Never accesses, changes or publishes the live Supabase database.
"""
from __future__ import annotations
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'draft_snapshot.json'
OUT = ROOT / 'output'


def minute(time_value: str) -> int:
    h, m = map(int, time_value.split(':'))
    return 60 * h + m


def overlaps(a: dict, b: dict, gap: int = 0) -> bool:
    return (a['date'] == b['date']
            and minute(a['start']) < minute(b['end']) + gap
            and minute(b['start']) < minute(a['end']) + gap)


def save_csv(path: Path, records: list[dict], columns: list[str]) -> None:
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)


def validate_source(data: dict) -> None:
    ids = [x['sitting_id'] for x in data['room_sittings']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate sitting_id in source data')
    for s in data['room_sittings']:
        if minute(s['end']) <= minute(s['start']):
            raise ValueError('Invalid sitting interval: '+s['sitting_id'])
    for i, s in enumerate(data['room_sittings']):
        for other in data['room_sittings'][i + 1:]:
            if s['room_code'] == other['room_code'] and overlaps(s, other):
                raise ValueError('Physical room double-booked: '+s['sitting_id']+' and '+other['sitting_id'])


def feasibility_precheck(data: dict) -> list[dict]:
    """Detect obvious chair shortages before claiming a complete schedule."""
    chairs = [s for s in data['staff'] if s['can_chair']]
    unavailability = data['assumptions'].get('staff_unavailability') or []
    timestamps = sorted(
        {(slot['date'], slot['start']) for exam in data['exams'] for slot in exam['sessions']}
        | {(a['date'], a['start']) for a in unavailability}
    )
    shortages=[]
    for date, time in timestamps:
        point = minute(time)
        active=[e['code'] for e in data['exams'] if any(
            x['date']==date and minute(x['start']) <= point < minute(x['end']) for x in e['sessions'])]
        available = [c for c in chairs if not any(
            a['staff_id'] == c['staff_id'] and a['date'] == date and
            minute(a['start']) <= point < minute(a['end']) for a in unavailability)]
        if len(active)>len(available):
            shortages.append({'date':date,'time':time,'active_courses':len(active),
                              'eligible_chairs':len(available),'minimum_missing_chairs':len(active)-len(available),
                              'course_codes':';'.join(sorted(active))})
    return shortages


def invig_solver(data: dict, seconds: int = 25) -> dict:
    staff = [s for s in data['staff'] if s['can_invigilate']]
    sittings = data['room_sittings']
    rules = data['assumptions']
    k = int(rules['invigilators_per_room'])
    gap = int(rules.get('min_break_minutes') or 0)
    prep = int(rules.get('preparation_minutes') or 0)
    unavailability = rules.get('staff_unavailability') or []

    model = cp_model.CpModel()
    x={}
    sitting_candidates=defaultdict(list)
    staff_candidates=defaultdict(list)
    staff_day=defaultdict(list)
    for staff_member in staff:
        person=staff_member['staff_id']
        blocked=[b for b in unavailability if b['staff_id']==person]
        for i,s in enumerate(sittings):
            duty_start=minute(s['start'])-prep
            duty_end=minute(s['end'])
            if any(b['date']==s['date'] and duty_start < minute(b['end'])
                   and minute(b['start']) < duty_end for b in blocked):
                continue
            var=model.new_bool_var(f'i_{person}_{i}')
            x[person,i]=var
            sitting_candidates[i].append(var)
            duration=duty_end-duty_start
            staff_candidates[person].append((i,var,duration))
            staff_day[person,s['date']].append((i,var,duration))

    for i,s in enumerate(sittings):
        if len(sitting_candidates[i])<k:
            return {'status':'INFEASIBLE_PRECHECK', 'reason':f'Not enough staff for {s["sitting_id"]}'}
        model.add(sum(sitting_candidates[i]) == k)

    # A member cannot cover overlapping sittings or sittings closer than required break.
    # Group same windows into one at-most-one constraint; use pairs for differing intervals.
    for member in staff:
        sid=member['staff_id']
        daily=defaultdict(list)
        for i,var,duration in staff_candidates[sid]:
            daily[sittings[i]['date']].append((i,var))
        for day, items in daily.items():
            buckets=defaultdict(list)
            for i,var in items:
                buckets[sittings[i]['start'],sittings[i]['end']].append(var)
            for vars_ in buckets.values():
                if len(vars_)>1:
                    model.add_at_most_one(vars_)
            starts=sorted(buckets)
            for ai, a in enumerate(starts):
                for b in starts[ai+1:]:
                    a_interval={'date':day,'start':a[0],'end':a[1]}
                    b_interval={'date':day,'start':b[0],'end':b[1]}
                    if (minute(a[0])-prep < minute(b[1])+gap
                            and minute(b[0])-prep < minute(a[1])+gap):
                        for xvar in buckets[a]:
                            for yvar in buckets[b]:
                                model.add(xvar + yvar <= 1)

    max_daily=rules.get('max_daily_invigilation_minutes')
    if max_daily:
        for (sid,day),vars_ in staff_day.items():
            model.add(sum(minutes*v for _,v,minutes in vars_) <= int(max_daily))

    total_minutes=sum((minute(s['end']) - minute(s['start']) + prep)*k for s in sittings)
    max_load=model.new_int_var(0,total_minutes,'max_load')
    min_load=model.new_int_var(0,total_minutes,'min_load')
    for member in staff:
        sid=member['staff_id']
        load=sum(minutes*v for _,v,minutes in staff_candidates[sid])
        model.add(load <= max_load)
        model.add(load >= min_load)
    model.minimize(max_load-min_load)

    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.num_search_workers=8
    solver.parameters.random_seed=42
    status=solver.solve(model)
    status_name=solver.status_name(status)
    if status not in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        return {'status':status_name,'reason':'No invigilator solution returned within the configured limits.'}

    result=[]
    loads=defaultdict(int)
    for (sid,i),v in x.items():
        if solver.value(v):
            s=sittings[i]
            minutes=minute(s['end']) - minute(s['start'])+prep
            loads[sid]+=minutes
            result.append({'staff_id':sid, 'sitting_id':s['sitting_id'],'date':s['date'],
                           'start':s['start'],'end':s['end'],'room_code':s['room_code'],
                           'minutes':minutes,'course_codes':';'.join(sorted(s['course_codes']))})
    result.sort(key=lambda z:(z['date'],z['start'],z['room_code'],z['staff_id']))
    for member in staff:
        loads.setdefault(member['staff_id'],0)
    return {'status':status_name,'assignments':result,'counts':{'occupied_rooms':len(sittings),
        'invigilator_assignments':len(result),'eligible_invigilators':len(staff),
        'min_minutes':min(loads.values()),'max_minutes':max(loads.values()),
        'average_minutes':round(sum(loads.values())/len(loads),2)}}


def chair_solver(data: dict, seconds: int = 10) -> dict:
    shortages=feasibility_precheck(data)
    if shortages:
        return {'status':'INFEASIBLE_PRECHECK','shortages':shortages,
                'reason':'Simultaneous courses exceed eligible and available chairs under current policy.'}
    chairs=[s for s in data['staff'] if s['can_chair']]
    blocked=data['assumptions'].get('staff_unavailability') or []
    exams=data['exams']
    model=cp_model.CpModel()
    z={}
    for e, exam in enumerate(exams):
        vars_=[]
        for c,person in enumerate(chairs):
            var=model.new_bool_var(f'chair_{e}_{c}')
            z[e,c]=var
            vars_.append(var)
            # Chair is responsible for all the exam's sessions; never assign
            # if an approved absence intersects any session.
            if any(b['staff_id'] == person['staff_id'] and overlaps(slot, b)
                   for b in blocked for slot in exam['sessions']):
                model.add(var == 0)
        model.add_exactly_one(vars_)
    conflicting=[]
    for e in range(len(exams)):
        for other in range(e+1,len(exams)):
            if any(overlaps(a,b) for a in exams[e]['sessions'] for b in exams[other]['sessions']):
                conflicting.append((e,other))
    for e,o in conflicting:
        for c in range(len(chairs)):
            model.add(z[e,c]+z[o,c]<=1)
    max_courses=model.new_int_var(0,len(exams),'max_courses')
    min_courses=model.new_int_var(0,len(exams),'min_courses')
    for c in range(len(chairs)):
        load=sum(z[e,c] for e in range(len(exams)))
        model.add(load<=max_courses)
        model.add(load>=min_courses)
    model.minimize(max_courses-min_courses)
    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=seconds
    solver.parameters.num_search_workers=8
    stat=solver.solve(model)
    if stat not in (cp_model.FEASIBLE,cp_model.OPTIMAL):
        return {'status':solver.status_name(stat),'reason':'No chair schedule was found.'}
    result=[{'course_code':exams[e]['code'],'staff_id':chairs[c]['staff_id']}
        for e in range(len(exams)) for c in range(len(chairs)) if solver.value(z[e,c])]
    return {'status':solver.status_name(stat),'assignments':result}


def main():
    OUT.mkdir(exist_ok=True)
    data=json.loads(DATA.read_text(encoding='utf-8'))
    validate_source(data)
    chair=chair_solver(data)
    invig=invig_solver(data)
    if invig.get('assignments'):
        save_csv(OUT/'invigilator_DRAFT.csv',invig['assignments'],
            ['staff_id','date','start','end','room_code','sitting_id','minutes','course_codes'])
    if chair.get('assignments'):
        save_csv(OUT/'chair_DRAFT.csv',chair['assignments'],['course_code','staff_id'])
    if chair.get('shortages'):
        save_csv(OUT/'chair_shortages.csv',chair['shortages'],
            ['date','time','active_courses','eligible_chairs','minimum_missing_chairs','course_codes'])
    summary={'input_is_draft':True,'live_database_untouched':True,
        'invigilators':{k:v for k,v in invig.items() if k!='assignments'},
        'chairs':{k:v for k,v in chair.items() if k!='assignments'}}
    (OUT/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if chair.get('status')=='INFEASIBLE_PRECHECK':
        print('WARNING: Chairman schedule is IMPOSSIBLE under the current 1 doctor per concurrent course rule.')
        print('No results from this draft should be published or inserted into Supabase.')


if __name__=='__main__':
    main()
