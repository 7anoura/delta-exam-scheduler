"""Independent READ ONLY pre-approval checks for a SAVED version against CURRENT records.
No API in Phase 13 approves or publishes a schedule.
"""
from __future__ import annotations
import hashlib, json
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
CAIRO = ZoneInfo('Africa/Cairo')
SOURCE_TABLES=('exam_periods','courses','exams','exam_sessions','rooms','room_sittings','session_room_links')

def source_fingerprint(raw:dict)->str:
    groups={name:sorted(([{k:v for k,v in r.items() if k not in ('head_of_control_staff_id','status')} for r in raw.get(name,[])] if name=='exam_periods' else raw.get(name,[])),key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False)) for name in SOURCE_TABLES}
    b=json.dumps(groups,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode('utf-8')
    return hashlib.sha256(b).hexdigest()

def dt(s):return datetime.fromisoformat(s.replace('Z','+00:00'))

def clash(a,b,break_mins=0):
    a,b=sorted((a,b),key=lambda t:t[0]);return a[1]+timedelta(minutes=break_mins)>b[0]

def evaluate_readiness(raw:dict,version:dict,invigilators:list,chairs:list,review:dict|None,decisions:list)->dict:
    issues=[]
    def issue(code,message):
        if code not in {x['code'] for x in issues}:issues.append({'code':code,'message':message})
    period=raw['exam_periods'][0];rules=raw['scheduling_rules'][0]
    staff={s['id']:s for s in raw['staff']};exams={e['id']:e for e in raw['exams']}
    sittings={s['id']:s for s in raw['room_sittings']}
    sessions=defaultdict(list);unavailable=defaultdict(list)
    for s in raw['exam_sessions']:sessions[s['exam_id']].append((dt(s['starts_at']),dt(s['ends_at'])))
    for r in raw['staff_unavailability']:
        if r['status']=='approved':unavailable[r['staff_id']].append((dt(r['starts_at']),dt(r['ends_at'])))
    if version['status']!='draft':issue('NOT_DRAFT','Only DRAFT versions may undergo the Phase 13 review.')
    if period['status']=='closed':issue('PERIOD_CLOSED','Exam period is closed.')
    head_id=period.get('head_of_control_staff_id');head=staff.get(head_id)
    if not head or not head['is_active'] or not head['can_chair']:
        issue('HEAD_NOT_APPOINTED','Choose an active chair-eligible Head of Examination Control.')
    if rules.get('allow_parallel_chair_assignments'):
        issue('UNSUPPORTED_PARALLEL_CHAIRS','Parallel course-chair assignments are not supported by current validator.')
    if rules['invigilators_per_room']!=2:issue('INVIGILATION_POLICY','University default requires two invigilators per occupied room.')
    if rules['chairs_per_exam']!=1:issue('CHAIR_POLICY','University default requires one chair per course exam.')
    max_minutes=rules.get('max_daily_invigilation_minutes')
    if max_minutes is None:issue('DAILY_LIMIT_UNSET','The daily workload ceiling must be set based on university rules.')
    if not review:issue('SOURCE_NOT_SIGNED_OFF','A faculty representative must manually verify the original exam PDF.')
    elif review['source_fingerprint']!=source_fingerprint(raw):
        issue('SOURCE_CHANGED_SINCE_REVIEW','Live timetable has changed since the PDF was signed off; re-review the source.')
    approval_ids={d['target_staff_id'] for d in decisions if d['decision_type']=='chair_eligibility' and d['new_value']=='true'}
    duty_by_room=defaultdict(list);duty_by_staff=defaultdict(list);day_minutes=defaultdict(int)
    for a in invigilators:
        sid,person_id=a['room_sitting_id'],a['staff_id'];duty_by_room[sid].append(person_id)
        r=sittings.get(sid);p=staff.get(person_id)
        if not r:issue('UNKNOWN_ROOM_SITTING','An invigilation duty refers to a non-period sitting.');continue
        if not p or not p['is_active'] or not p['can_invigilate']:
            issue('INELIGIBLE_INVIGILATOR','An invigilator is inactive or no longer eligible.')
        t0,t1=dt(r['starts_at']),dt(r['ends_at']);duty_by_staff[person_id].append((t0,t1))
        if any(clash((t0,t1),x) for x in unavailable[person_id]):
            issue('INVIGILATOR_ABSENCE','A duty overlaps an approved invigilator absence.')
        local0=t0.astimezone(CAIRO);local1=t1.astimezone(CAIRO)
        while local0<local1:
            midnight=datetime.combine(local0.date()+timedelta(days=1),datetime.min.time(),CAIRO)
            boundary=min(local1,midnight)
            day_minutes[(person_id,local0.date().isoformat())]+=(boundary-local0).total_seconds()/60
            local0=boundary
    for sid in sittings:
        values=duty_by_room[sid]
        if len(values)!=2 or len(set(values))!=2:
            issue('ROOM_COVERAGE_INCOMPLETE','Every room sitting needs two DIFFERENT invigilators.')
    break_mins=int(rules.get('min_break_minutes') or 0)+int(rules.get('extra_preparation_minutes') or 0)
    for arr in duty_by_staff.values():
        arr.sort()
        for a,b in zip(arr,arr[1:]):
            if clash(a,b,break_mins):issue('INVIGILATOR_TIME_CONFLICT','Invigilator has conflicting shifts or insufficient time between them.')
    if max_minutes is not None and any(t>max_minutes for t in day_minutes.values()):
        issue('DAILY_LIMIT_EXCEEDED','At least one invigilator exceeds the agreed daily limit.')
    chairs_by_exam=defaultdict(list);chair_by_staff=defaultdict(list)
    for a in chairs:
        eid,sid=a['exam_id'],a['staff_id'];chairs_by_exam[eid].append(sid);p=staff.get(sid)
        if eid not in exams:issue('UNKNOWN_COURSE_EXAM','A chair is allocated to an exam outside this period.')
        if not p or not p['is_active'] or not p['can_chair']:
            issue('INELIGIBLE_CHAIR','A chair is inactive or lacks faculty chair eligibility.')
        if p and p['academic_rank']=='assistant_lecturer' and sid not in approval_ids:
            issue('ASSISTANT_CHAIR_NOT_APPROVED','Assistant Lecturer course-chair eligibility has no recorded administrative authorization.')
        if head_id==sid and not rules.get('head_can_chair'):
            issue('HEAD_CHAIR_CONFLICT','Head of Control is chairing a course despite separate-role rule.')
        for span in sessions.get(eid,[]):
            chair_by_staff[sid].append((eid,span))
            if any(clash(span,x) for x in unavailable[sid]):
                issue('CHAIR_ABSENCE','Course chair has an approved overlapping absence.')
    for eid in exams:
        if len(chairs_by_exam[eid])!=1:issue('CHAIR_COVERAGE_INCOMPLETE','All course exams must have exactly one chair across sessions.')
    # People who are eligible for both roles may not supervise a course and
    # invigilate another room at the same time.
    for person_id, spans in chair_by_staff.items():
        if person_id in duty_by_staff and any(clash(cspan, duty) for _, cspan in spans for duty in duty_by_staff[person_id]):
            issue('CROSS_ROLE_TIME_CONFLICT', 'A person is scheduled as chair and invigilator simultaneously.')
    # A sitting must refer to a physical, active room and a matching exam-session.
    rooms = {r['id']:r for r in raw['rooms']}
    session_rows={s['id']:s for s in raw['exam_sessions']}
    linked=set()
    for link in raw['session_room_links']:
        exam_session=session_rows.get(link['exam_session_id'])
        room_sitting=sittings.get(link['room_sitting_id'])
        if not room_sitting or not exam_session or (exam_session['starts_at'],exam_session['ends_at']) != (room_sitting['starts_at'],room_sitting['ends_at']):
            issue('EXAM_ROOM_LINK_INVALID','A course session and its linked physical room do not match.')
        linked.add(link['room_sitting_id'])
    if set(sittings)-linked:issue('UNLINKED_ROOM_SITTING','An occupied room has no associated course exam-session.')
    if any(not rooms.get(r['room_id'],{}).get('is_active',False) for r in sittings.values()):
        issue('INACTIVE_OR_UNKNOWN_ROOM','A sitting uses an inactive or missing room.')
    for arr in chair_by_staff.values():
        arr.sort(key=lambda a:a[1][0])
        for a,b in zip(arr,arr[1:]):
            if a[0]!=b[0] and clash(a[1],b[1]):
                issue('CHAIR_TIME_CONFLICT','Chair assigned to overlapping course exams.')
    rooms_by_id=defaultdict(list)
    for r in sittings.values():rooms_by_id[r['room_id']].append((dt(r['starts_at']),dt(r['ends_at'])))
    for arr in rooms_by_id.values():
        arr.sort()
        for a,b in zip(arr,arr[1:]):
            if clash(a,b):issue('ROOM_COLLISION','Physical room occupied by overlapping exam sittings.')
    return {'version_id':version['id'],'version_number':version['version_number'],
            'draft_status':version['status'],'ready_for_formal_review':not issues,
            'approval_enabled':False,'publishing_enabled':False,
            'checks':{'room_sittings':len(sittings),'invigilator_duties':len(invigilators),
                      'course_exams':len(exams),'chair_assignments':len(chairs)},
            'issues':issues,'note':'Pre-approval validation ONLY. Formal university authorization is required. This phase cannot approve or publish.'}
