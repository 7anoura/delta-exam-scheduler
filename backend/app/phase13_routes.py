"""Phase 13 authenticated admin-only decision records & read-only readiness checks.

No approvals, no publication, no mutation of schedule versions. SQL RPC performs
second admin-role check; the server secret is never passed to the browser.
"""
from __future__ import annotations
from uuid import UUID
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from .phase13_readiness import evaluate_readiness, source_fingerprint
from .store import StoreError
from .supabase_reader import DatabaseReadError

class AdminDecision(BaseModel):
    kind: Literal['chair_eligibility','daily_limit','source_signoff']
    staff_id: UUID | None = None
    can_chair: bool | None = None
    max_daily_minutes: int | None = Field(default=None,ge=45,le=720)
    source_name: str | None = Field(default=None,max_length=240)
    checked_original_document: bool = False
    reason: str = Field(min_length=12,max_length=800)


def mount_phase13_routes(app,*,require_admin,get_reader,get_store):
    def read(period_id):
        try:return get_reader().period_data(str(period_id))
        except LookupError:raise HTTPException(404,'Exam period not found') from None
        except DatabaseReadError:raise HTTPException(502,'Unable to read live Supabase timetable') from None

    @app.get('/api/v1/periods/{period_id}/administration',tags=['Phase 13'],dependencies=[Depends(require_admin)])
    def administration(period_id:UUID):
        data=read(period_id);store=get_store()
        try:
            people=store._request('GET','staff',params={'select':'id,source_ref,full_name,academic_rank,is_active,can_chair',
              'academic_rank':'eq.assistant_lecturer','order':'source_ref.asc','limit':25})
            reviews=store._request('GET','source_timetable_reviews',params={'select':'document_name,reviewed_at,source_fingerprint',
              'exam_period_id':'eq.'+str(period_id),'limit':1})
            log=store._request('GET','administrative_decisions',params={'select':'id,decision_type,target_staff_id,previous_value,new_value,justification,decided_at',
              'exam_period_id':'eq.'+str(period_id),'order':'decided_at.desc','limit':30})
        except StoreError:raise HTTPException(502,'Could not read Phase 13 tables; run 08_phase13 migration first') from None
        fingerprint=source_fingerprint(data)
        return {'period_id':str(period_id),'assistant_lecturers':people,
                'max_daily_minutes':data['scheduling_rules'][0].get('max_daily_invigilation_minutes'),
                'source_attestation':({'document_name':reviews[0]['document_name'],'reviewed_at':reviews[0]['reviewed_at'],
                  'matches_live_source':reviews[0]['source_fingerprint']==fingerprint} if reviews else None),
                'decisions':log,'approval_enabled':False,'publishing_enabled':False}

    @app.post('/api/v1/periods/{period_id}/administration/decision',tags=['Phase 13'])
    def record_decision(period_id:UUID,request:AdminDecision,admin=Depends(require_admin)):
        data=read(period_id)
        if request.kind=='chair_eligibility':
            if not request.staff_id or request.can_chair is None:
                raise HTTPException(422,'Select an Assistant Lecturer and their approved chair eligibility')
            who=next((s for s in data['staff'] if s['id']==str(request.staff_id)),None)
            if not who or not who['is_active'] or who['academic_rank']!='assistant_lecturer':
                raise HTTPException(422,'Only an active Assistant Lecturer can be changed here')
        if request.kind=='daily_limit' and request.max_daily_minutes is None:
            raise HTTPException(422,'Provide the faculty-approved daily maximum minutes')
        if request.kind=='source_signoff' and (not request.checked_original_document or not request.source_name):
            raise HTTPException(422,'You must check the original PDF and attest to a named document')
        try:
            result=get_store()._request('POST','rpc/record_exam_admin_decision_v1',body={
                'p_period_id':str(period_id),'p_actor_auth_user_id':admin['user_id'],
                'p_type':request.kind,'p_target_staff_id':str(request.staff_id) if request.staff_id else None,
                'p_can_chair':request.can_chair,'p_max_daily_minutes':request.max_daily_minutes,
                'p_source_name':request.source_name,'p_source_fingerprint':source_fingerprint(data) if request.kind=='source_signoff' else None,
                'p_justification':request.reason.strip(),
            })
            return result
        except StoreError:raise HTTPException(409,'Decision rejected; check admin permissions and the Phase 13 migration') from None

    @app.get('/api/v1/periods/{period_id}/drafts/{version_id}/readiness',tags=['Phase 13'],dependencies=[Depends(require_admin)])
    def draft_readiness(period_id:UUID,version_id:UUID):
        data=read(period_id);store=get_store()
        try:
            versions=store._request('GET','schedule_versions',params={'select':'id,version_number,status',
                'id':'eq.'+str(version_id),'exam_period_id':'eq.'+str(period_id),'limit':1})
            if not versions:raise HTTPException(404,'Schedule version not found')
            inv=store._all_rows('invigilator_assignments',{'select':'room_sitting_id,staff_id',
                'schedule_version_id':'eq.'+str(version_id),'order':'room_sitting_id.asc'})
            chairs=store._all_rows('chair_assignments',{'select':'exam_id,staff_id',
                'schedule_version_id':'eq.'+str(version_id),'order':'exam_id.asc'})
            reviews=store._request('GET','source_timetable_reviews',params={'select':'source_fingerprint',
                'exam_period_id':'eq.'+str(period_id),'limit':1})
            decisions=store._all_rows('administrative_decisions',{'select':'decision_type,target_staff_id,new_value',
                'exam_period_id':'eq.'+str(period_id),'order':'decided_at.asc'})
        except StoreError:raise HTTPException(502,'Unable to load saved assignments or administrative approvals') from None
        return evaluate_readiness(data,versions[0],inv,chairs,reviews[0] if reviews else None,decisions)
