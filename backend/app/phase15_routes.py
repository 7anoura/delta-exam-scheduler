"""Phase 15: server-authenticated, two-stage schedule release with fail-closed gates.

No role, staff id or source snapshot is accepted from the client. The server
recomputes Phase 13 readiness from saved rows and current timetable, while the
SQL transaction independently checks core scheduling and admin conditions.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .phase13_readiness import source_fingerprint
from .phase14_routes import _load_review_readiness
from .store import StoreError
from .supabase_reader import DatabaseReadError


class ReleaseDecision(BaseModel):
    action: Literal['approve', 'publish']
    official_reference: str = Field(min_length=12, max_length=800)
    confirms_authority: bool = False


def load_gate(period_id, version_id, *, reader, store):
    """Check current source and SAVED persisted assignments, not preview data."""
    raw = reader.period_data(str(period_id))
    report = _load_review_readiness(raw, store, str(period_id), str(version_id))
    if report['draft_status'] not in ('draft', 'approved'):
        return {'ready': False, 'status': report['draft_status'], 'issues': [
            {'code': 'INVALID_VERSION_STATE', 'message': 'Only saved draft/approved versions can be released.'}
        ], 'python': report, 'sql': {'ready': False}}
    # Phase 13 checks DRAFT only, but an APPROVED version may be published after
    # re-evaluating the very same scheduling constraints. Exclude only this
    # status-specific warning, never ignore any substantive scheduling blocker.
    phase13_issues = [i for i in report['issues'] if not (
        report['draft_status'] == 'approved' and i['code'] == 'NOT_DRAFT'
    )]
    fingerprint = source_fingerprint(raw)
    sql_report = store._request('POST', 'rpc/exam_release_blockers_v1', body={
        'p_period_id': str(period_id), 'p_version_id': str(version_id),
        'p_live_fingerprint': fingerprint,
    })
    sql_issues = [{'code': code, 'message': 'Database release validation blocked'}
                  for code in sql_report.get('issues', [])]
    # Deduplicate by code to avoid redundant UI warnings.
    merged = {i['code']: i for i in [*phase13_issues, *sql_issues]}
    return {'ready': not merged and sql_report.get('ready') is True,
            'status': report['draft_status'], 'issues': list(merged.values()),
            'python': report, 'sql': sql_report, '_fingerprint': fingerprint}


def mount_phase15_routes(app, *, require_admin, get_reader, get_store):
    def _gate(period_id, version_id):
        try:
            return load_gate(period_id, version_id, reader=get_reader(), store=get_store())
        except LookupError:
            raise HTTPException(404, 'Period or schedule version not found') from None
        except (StoreError, DatabaseReadError):
            raise HTTPException(502, 'Could not validate the current persisted schedule') from None

    @app.get('/api/v1/periods/{period_id}/release', tags=['Phase 15'], dependencies=[Depends(require_admin)])
    def release_overview(period_id: UUID):
        try:
            versions = get_store()._request('GET', 'schedule_versions', params={
                'select': 'id,version_number,status,generated_at,approved_at,published_at',
                'exam_period_id': 'eq.'+str(period_id), 'order': 'version_number.desc', 'limit': 100})
            events = get_store()._request('GET', 'schedule_release_events', params={
                'select': 'id,schedule_version_id,action,decision_reference,created_at',
                'exam_period_id': 'eq.'+str(period_id), 'order': 'created_at.desc', 'limit': 40})
        except StoreError:
            raise HTTPException(502, 'Release overview unavailable; check Phase 15 migration') from None
        return {'versions': versions, 'events': events,
                'current_published_version_id': next((v['id'] for v in versions if v['status']=='published'), None)}

    @app.get('/api/v1/periods/{period_id}/release/{version_id}/validation', tags=['Phase 15'], dependencies=[Depends(require_admin)])
    def release_validation(period_id: UUID, version_id: UUID):
        result = _gate(period_id, version_id)
        return {k: v for k, v in result.items() if not k.startswith('_')}

    @app.post('/api/v1/periods/{period_id}/release/{version_id}/transition', tags=['Phase 15'])
    def release_transition(period_id: UUID, version_id: UUID, decision: ReleaseDecision,
                           admin=Depends(require_admin)):
        if not decision.confirms_authority:
            raise HTTPException(422, 'Confirm you possess actual university authorization before attempting a release')
        result = _gate(period_id, version_id)
        expect = 'draft' if decision.action == 'approve' else 'approved'
        if result['status'] != expect:
            raise HTTPException(409, f'{decision.action} requires a saved {expect.upper()} version')
        if not result['ready']:
            raise HTTPException(409, {'message': 'Schedule release is BLOCKED',
                                      'blockers': [i['code'] for i in result['issues']]})
        try:
            # PostgreSQL transaction locks period/version and RECHECKS all core
            # conditions. Neither the actor identity nor fingerprint is taken
            # from the request body; identity was verified by require_admin.
            return get_store()._request('POST', 'rpc/transition_exam_schedule_v1', body={
                'p_period_id': str(period_id), 'p_version_id': str(version_id),
                'p_actor_auth_user_id': admin['user_id'], 'p_action': decision.action,
                'p_official_reference': decision.official_reference.strip(),
                'p_live_fingerprint': result['_fingerprint']})
        except StoreError:
            raise HTTPException(409, 'Database refused release; current source, rules or version may have changed') from None
