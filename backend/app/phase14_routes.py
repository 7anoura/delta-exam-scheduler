"""Phase 14: internal review requests and strictly published-only staff portal.

These routes do NOT approve or publish anything. Admin permissions are verified
using the existing Supabase Auth principal and an independent SQL RPC check.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from .phase13_readiness import evaluate_readiness
from .snapshot import local
from .store import StoreError
from .supabase_reader import DatabaseReadError


class InternalReviewRequest(BaseModel):
    note: str = Field(min_length=12, max_length=800)


class ReviewResponse(BaseModel):
    action: Literal['changes_requested', 'cancelled']
    note: str = Field(min_length=12, max_length=800)


class StaffAccountLink(BaseModel):
    staff_id: UUID
    auth_user_id: UUID
    justification: str = Field(min_length=12, max_length=800)


def _load_review_readiness(raw, store, period_id: str, version_id: str):
    """Run the Phase 13 independent checks on saved data, not a client preview."""
    versions = store._request('GET', 'schedule_versions', params={
        'select': 'id,version_number,status', 'id': 'eq.' + version_id,
        'exam_period_id': 'eq.' + period_id, 'limit': 1})
    if not versions:
        raise LookupError('Schedule version not found in this exam period')
    inv = store._all_rows('invigilator_assignments', {
        'select': 'room_sitting_id,staff_id',
        'schedule_version_id': 'eq.' + version_id, 'order': 'room_sitting_id.asc'})
    chairs = store._all_rows('chair_assignments', {
        'select': 'exam_id,staff_id',
        'schedule_version_id': 'eq.' + version_id, 'order': 'exam_id.asc'})
    reviews = store._request('GET', 'source_timetable_reviews', params={
        'select': 'source_fingerprint', 'exam_period_id': 'eq.' + period_id, 'limit': 1})
    decisions = store._all_rows('administrative_decisions', {
        'select': 'decision_type,target_staff_id,new_value',
        'exam_period_id': 'eq.' + period_id, 'order': 'decided_at.asc'})
    return evaluate_readiness(raw, versions[0], inv, chairs,
                              reviews[0] if reviews else None, decisions)


def _staff_published_schedule(store, reader, staff_id: str):
    """Published versions only, scoped to the VERIFIED principal's staff UUID.

    Do not accept a staff ID from client input; do not leak draft/approved rows.
    """
    published = store._all_rows('schedule_versions', {
        'select': 'id,exam_period_id,version_number,status',
        'status': 'eq.published', 'order': 'generated_at.desc'})
    duties = []
    for version in published:
        version_id = version['id']
        inv = store._all_rows('invigilator_assignments', {
            'select': 'room_sitting_id', 'schedule_version_id': 'eq.' + version_id,
            'staff_id': 'eq.' + staff_id})
        chairs = store._all_rows('chair_assignments', {
            'select': 'exam_id', 'schedule_version_id': 'eq.' + version_id,
            'staff_id': 'eq.' + staff_id})
        if not inv and not chairs:
            continue
        # READ all timetable metadata on the server, but return only THIS member's duties.
        raw = reader.period_data(version['exam_period_id'])
        if not raw['exam_periods']:
            continue
        period_name = raw['exam_periods'][0]['name']
        rooms = {r['id']: r for r in raw['rooms']}
        sittings = {r['id']: r for r in raw['room_sittings']}
        sessions = {r['id']: r for r in raw['exam_sessions']}
        exams = {r['id']: r for r in raw['exams']}
        courses = {r['id']: r for r in raw['courses']}
        links = defaultdict(list)
        for link in raw['session_room_links']:
            row = sessions.get(link['exam_session_id'])
            if row:
                exam = exams.get(row['exam_id'])
                course = courses.get(exam['course_id']) if exam else None
                if course:
                    links[link['room_sitting_id']].append(course['code'])
        for a in inv:
            sitting = sittings.get(a['room_sitting_id'])
            if not sitting:
                raise StoreError('Published duty references an unavailable room sitting')
            room = rooms.get(sitting['room_id'], {})
            date, start = local(sitting['starts_at'])
            _, end = local(sitting['ends_at'])
            duties.append({
                'type': 'invigilation', 'date': date, 'start': start, 'end': end,
                'room_code': room.get('code', 'Unknown'),
                'room_number': room.get('room_number'),
                'course_codes': sorted(set(links[a['room_sitting_id']])),
                'period': period_name, 'version_number': version['version_number'],
                'duration_minutes': round((datetime.fromisoformat(sitting['ends_at'].replace('Z','+00:00'))
                    - datetime.fromisoformat(sitting['starts_at'].replace('Z','+00:00'))).total_seconds()/60),
            })
        for a in chairs:
            exam = exams.get(a['exam_id'])
            if not exam:
                raise StoreError('Published chair duty references an unavailable exam')
            course = courses.get(exam['course_id'], {})
            for session in raw['exam_sessions']:
                if session['exam_id'] != a['exam_id']:
                    continue
                date, start = local(session['starts_at'])
                _, end = local(session['ends_at'])
                duties.append({
                    'type': 'committee_chair', 'date': date, 'start': start, 'end': end,
                    'room_code': None, 'room_number': None,
                    'course_codes': [course.get('code', '')],
                    'period': period_name, 'version_number': version['version_number'],
                    'duration_minutes': round((datetime.fromisoformat(session['ends_at'].replace('Z','+00:00'))
                        - datetime.fromisoformat(session['starts_at'].replace('Z','+00:00'))).total_seconds()/60),
                })
    duties.sort(key=lambda d: (d['date'], d['start'], d['type'], d['room_code'] or ''))
    return {'published_only': True, 'duties': duties,
            'total_duties': len(duties), 'total_minutes': sum(d['duration_minutes'] for d in duties),
            'total_days': len({d['date'] for d in duties}),
            'message': 'Only duties from PUBLISHED versions are shown. Drafts and internal reviews are not visible.'}


def mount_phase14_routes(app, *, principal, require_admin, get_reader, get_store):
    def read(period_id):
        try:
            return get_reader().period_data(str(period_id))
        except LookupError:
            raise HTTPException(404, 'Exam period not found') from None
        except DatabaseReadError:
            raise HTTPException(502, 'Unable to read live examination records') from None

    @app.get('/api/v1/periods/{period_id}/internal-reviews', tags=['Phase 14'], dependencies=[Depends(require_admin)])
    def review_list(period_id: UUID):
        try:
            return get_store()._all_rows('schedule_review_requests', {
                'select': 'id,schedule_version_id,state,request_note,observed_blockers,requested_at,response_note,resolved_at',
                'exam_period_id': 'eq.' + str(period_id), 'order': 'requested_at.desc'})
        except StoreError:
            raise HTTPException(502, 'Review records unavailable. Check Phase 14 SQL migration.') from None

    @app.post('/api/v1/periods/{period_id}/drafts/{version_id}/request-internal-review', tags=['Phase 14'])
    def request_review(period_id: UUID, version_id: UUID, request: InternalReviewRequest,
                       admin=Depends(require_admin)):
        store = get_store()
        try:
            report = _load_review_readiness(read(period_id), store, str(period_id), str(version_id))
            if report['draft_status'] != 'draft':
                raise HTTPException(409, 'Only saved drafts can be reviewed')
            result = store._request('POST', 'rpc/request_exam_internal_review_v1', body={
                'p_period_id': str(period_id), 'p_version_id': str(version_id),
                'p_actor': admin['user_id'], 'p_note': request.note.strip(),
                'p_blockers': report['issues'],
            })
            return {**result, 'readiness_at_request': report,
                    'warning': 'Review requested, not approved or published. Existing blockers still apply.'}
        except LookupError:
            raise HTTPException(404, 'Draft not found') from None
        except (StoreError, DatabaseReadError):
            raise HTTPException(409, 'Review request rejected; verify draft state, role and migration') from None

    @app.post('/api/v1/internal-reviews/{review_id}/respond', tags=['Phase 14'])
    def respond_review(review_id: UUID, request: ReviewResponse, admin=Depends(require_admin)):
        try:
            return get_store()._request('POST', 'rpc/respond_exam_internal_review_v1', body={
                'p_review_id': str(review_id), 'p_actor': admin['user_id'],
                'p_action': request.action, 'p_note': request.note.strip(),
            })
        except StoreError:
            raise HTTPException(409, 'Review response rejected; it may already be closed') from None

    @app.get('/api/v1/staff-access', tags=['Phase 14'], dependencies=[Depends(require_admin)])
    def staff_access_list():
        try:
            return get_store()._all_rows('staff', {
                'select': 'id,source_ref,full_name,academic_rank,is_active,auth_user_id',
                'order': 'source_ref.asc'})
        except StoreError:
            raise HTTPException(502, 'Staff access records unavailable') from None

    @app.post('/api/v1/staff-access/link', tags=['Phase 14'])
    def link_staff(request: StaffAccountLink, admin=Depends(require_admin)):
        try:
            return get_store()._request('POST', 'rpc/link_exam_staff_account_v1', body={
                'p_staff_id': str(request.staff_id),
                'p_auth_user_id': str(request.auth_user_id),
                'p_actor': admin['user_id'],
                'p_justification': request.justification.strip(),
            })
        except StoreError:
            raise HTTPException(409, 'Account linking rejected. Check staff status, user UUID and existing links.') from None

    @app.get('/api/v1/staff/me/published-schedule', tags=['Staff'])
    def staff_published_schedule(user=Depends(principal)):
        if user['role'] != 'staff' or not user.get('staff_id'):
            raise HTTPException(403, 'Only a linked, active staff account can view this page')
        try:
            return _staff_published_schedule(get_store(), get_reader(), user['staff_id'])
        except (StoreError, DatabaseReadError, LookupError):
            raise HTTPException(502, 'Could not retrieve personal published duties') from None
