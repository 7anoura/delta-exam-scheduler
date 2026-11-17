"""Phase 12 routes; mounted into the existing authenticated FastAPI app.

Routes never expose Supabase server keys, and are disabled for non-admin users.
Preview is not an approved or published university schedule.
"""
from __future__ import annotations
from uuid import UUID
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .chair_planner import build_chair_context, generate_chair_plan
from .resolution import simulate_shortage_resolution
from .store import StoreError
from .supabase_reader import DatabaseReadError


class AppointHead(BaseModel):
    staff_id: UUID | None


class SimulateResolution(BaseModel):
    include_assistant_lecturers: bool = False
    simulate_head_appointment: bool = False
    head_staff_id: UUID | None = None
    head_can_chair: bool | None = None
    seconds: int = Field(default=12, ge=2, le=25)


class SaveChairPlan(BaseModel):
    chairs: list[dict[str, UUID]] = Field(max_length=500)
    note: str = Field(default='', max_length=450)


def mount_control_routes(app, *, require_admin, get_reader, get_store):
    def read(period_id: UUID):
        try:
            return get_reader().period_data(str(period_id))
        except LookupError:
            raise HTTPException(404, detail='Exam period not found') from None
        except DatabaseReadError:
            raise HTTPException(502, detail='Supabase read failed') from None

    @app.get('/api/v1/periods/{period_id}/control', tags=['Control'], dependencies=[Depends(require_admin)])
    def control_dashboard(period_id: UUID):
        raw = read(period_id)
        ctx = build_chair_context(raw)
        staff_rows = get_reader().list_rows('staff',
           'id,source_ref,full_name,academic_rank,is_active,can_chair', order='source_ref.asc')
        eligible_ids = {x['id'] for x in ctx['eligible']}
        head_id = ctx['head_id']
        return {
            'exam_period_id': str(period_id),
            'head_staff_id': head_id,
            'head_can_chair': ctx['head_can_chair'],
            'parallel_chair_assignments_allowed': ctx['parallel_allowed'],
            'staff': [{**{k: s[k] for k in ('id','source_ref','full_name','academic_rank','is_active','can_chair')},
                       'eligible_for_this_plan': s['id'] in eligible_ids}
                      for s in staff_rows if s['is_active'] and (s['can_chair'] or s['academic_rank'] == 'assistant_lecturer')],
            'course_count': len(ctx['exams']),
            'note': 'The Head of Control is not assigned to course committees unless head_can_chair is explicitly enabled.'
        }

    @app.post('/api/v1/periods/{period_id}/control/head', tags=['Control'])
    def appoint_head(period_id: UUID, request: AppointHead, admin=Depends(require_admin)):
        try:
            return get_store().appoint_head(str(period_id),
                     str(request.staff_id) if request.staff_id else None, admin['user_id'])
        except StoreError:
            raise HTTPException(409, detail='Control appointment rejected. Verify the member is active and no version is approved.') from None

    @app.post('/api/v1/periods/{period_id}/chairs/preview', tags=['Control'], dependencies=[Depends(require_admin)])
    def preview_chairs(period_id: UUID, seconds: int = Query(15, ge=2, le=45)):
        try:
            return generate_chair_plan(read(period_id), seconds)
        except ValueError:
            raise HTTPException(409, detail='Exam data needs review before chair planning') from None

    @app.post('/api/v1/periods/{period_id}/control/resolution-preview', tags=['Control'])
    def preview_resolution(period_id: UUID, req: SimulateResolution, admin=Depends(require_admin)):
        # Advisory-only, no changes to staff ranks, rules, schedule versions, or head appointment.
        if not app.state.preview_lock.acquire(blocking=False):
            raise HTTPException(409, detail='Another optimization is already running')
        try:
            return simulate_shortage_resolution(
                read(period_id),
                include_assistant_lecturers=req.include_assistant_lecturers,
                simulate_head_appointment=req.simulate_head_appointment,
                head_staff_id=str(req.head_staff_id) if req.head_staff_id else None,
                head_can_chair=req.head_can_chair,
                seconds=req.seconds,
            )
        except ValueError as exc:
            raise HTTPException(409, detail=str(exc)) from None
        finally:
            app.state.preview_lock.release()

    @app.get('/api/v1/periods/{period_id}/drafts/{version_id}/chairs', tags=['Control'], dependencies=[Depends(require_admin)])
    def saved_chairs(period_id: UUID, version_id: UUID):
        try:
            raw = read(period_id)
            return get_store().saved_chair_plan(str(period_id), str(version_id), raw)
        except LookupError:
            raise HTTPException(404, detail='Draft version not found') from None
        except StoreError:
            raise HTTPException(502, detail='Unable to read chair assignments') from None

    @app.post('/api/v1/periods/{period_id}/drafts/{version_id}/chairs', tags=['Control'])
    def save_chairs(period_id: UUID, version_id: UUID, request: SaveChairPlan,
                   admin=Depends(require_admin)):
        # Reject ambiguous payloads early; trusted database transaction performs
        # authoritative checks for exam memberships, interval conflicts and role.
        if len(request.chairs) != len({p.get('exam_id') for p in request.chairs}):
            raise HTTPException(400, detail='Only one chair per exam')
        try:
            record = get_store().save_chair_plan(
                str(period_id), str(version_id),
                [{k: str(v) for k, v in row.items()} for row in request.chairs],
                admin['user_id'], request.note)
            return {'version': record, 'publication_blocked': True,
                    'warning': ('Saved as a NEW DRAFT, not approved or published. '
                                'Partial plans still contain unassigned courses.')}
        except LookupError:
            raise HTTPException(404, detail='Draft version not found') from None
        except StoreError:
            raise HTTPException(409, detail='Chair plan rejected or database unavailable. Check conflicts, source draft and Phase 11 SQL migration.') from None
