"""Phase 9: verified Supabase login and server-side draft persistence.

Only authenticated admins can view bulk data or save schedules. Staff can see
only their own PUBLISHED duties. Approval and publication are intentionally absent.
No X-Admin-Token endpoints remain; v0.8's development bypass is removed.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .audit import audit
from .authentication import AuthVerifier, LoginError, AuthUnavailable
from .config import Settings
from .preview import generate_preview
from .snapshot import DataIntegrityError, build_snapshot, compare_snapshot, local
from .store import Phase9Store, StoreError
from .replacement import suggest
from .control_routes import mount_control_routes
from .phase13_routes import mount_phase13_routes
from .phase14_routes import mount_phase14_routes
from .phase15_routes import mount_phase15_routes
from .supabase_reader import DatabaseReadError, SupabaseReader

bearer_scheme = HTTPBearer(auto_error=False)
REFERENCE = Path(__file__).resolve().parents[1] / 'data' / 'draft_snapshot.json'


class ReplaceDraftRequest(BaseModel):
    room_sitting_id: UUID
    old_staff_code: str = Field(min_length=4, max_length=40)
    new_staff_code: str = Field(min_length=4, max_length=40)
    reason: str = Field(min_length=3, max_length=300)


class SaveDraftRequest(BaseModel):
    seconds: int = Field(default=25, ge=5, le=60)
    note: str = Field(default='', max_length=500)


def create_app(settings: Settings | None = None, reader: SupabaseReader | None = None,
               verifier: AuthVerifier | None = None, store: Phase9Store | None = None) -> FastAPI:
    app = FastAPI(
        title='Delta Exam Scheduler — Phase 13 (Administrative Review)', version='0.15.0',
        description='Supabase Auth + server verified roles + draft saving. Publishing DISABLED.',
    )
    app.state.settings = settings
    app.state.reader = reader
    app.state.verifier = verifier
    app.state.store = store
    app.state.preview_lock = threading.Lock()

    def get_settings():
        if app.state.settings is None:
            try:
                app.state.settings = Settings.from_env()
            except ValueError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
        return app.state.settings

    def get_reader():
        if app.state.reader is None:
            cfg = get_settings()
            app.state.reader = SupabaseReader(cfg.supabase_url, cfg.supabase_secret_key)
        return app.state.reader

    def get_store():
        if app.state.store is None:
            cfg = get_settings()
            app.state.store = Phase9Store(cfg.supabase_url, cfg.supabase_secret_key)
        return app.state.store

    def get_verifier():
        if app.state.verifier is None:
            cfg = get_settings()
            app.state.verifier = AuthVerifier(cfg.supabase_url, cfg.supabase_publishable_key)
        return app.state.verifier

    def principal(auth: HTTPAuthorizationCredentials | None = Security(bearer_scheme)):
        if not auth or auth.scheme.lower() != 'bearer':
            raise HTTPException(status_code=401, detail='Please sign in with Supabase Auth')
        try:
            identity = get_verifier().verify(auth.credentials)
            role = get_store().role(identity.user_id)
        except LoginError:
            raise HTTPException(status_code=401, detail='Invalid or expired Supabase session') from None
        except AuthUnavailable:
            raise HTTPException(status_code=503, detail='Authentication service unavailable') from None
        except StoreError:
            raise HTTPException(status_code=502, detail='Could not check application permissions') from None
        if not role:
            raise HTTPException(status_code=403, detail='Account has no university role. Ask the system administrator to link it.')
        return {'user_id': identity.user_id, 'email': identity.email, **role}

    def require_admin(user=Depends(principal)):
        if user['role'] != 'admin':
            raise HTTPException(status_code=403, detail='Administrator access required')
        return user

    def get_data(period_id: UUID):
        try:
            raw = get_reader().period_data(str(period_id))
            return build_snapshot(raw)
        except LookupError:
            raise HTTPException(status_code=404, detail='Exam period not found') from None
        except DatabaseReadError:
            raise HTTPException(status_code=502, detail='Supabase read failed') from None
        except DataIntegrityError as exc:
            raise HTTPException(status_code=409, detail=f'Import needs review: {exc}') from None

    @app.get('/health', tags=['Public'])
    def health():
        return {'status': 'ok', 'version': '0.11.0', 'mode': 'authenticated_drafts', 'publishing': False}

    @app.get('/api/v1/auth/me', tags=['Auth'])
    def whoami(user=Depends(principal)):
        return user

    @app.get('/api/v1/periods', tags=['Admin'], dependencies=[Depends(require_admin)])
    def periods():
        try:
            return get_reader().list_periods()
        except DatabaseReadError:
            raise HTTPException(status_code=502, detail='Supabase read failed') from None

    @app.get('/api/v1/periods/{period_id}/audit', tags=['Admin'], dependencies=[Depends(require_admin)])
    def audit_period(period_id: UUID):
        return audit(get_data(period_id))

    @app.get('/api/v1/periods/{period_id}/comparison', tags=['Admin'], dependencies=[Depends(require_admin)])
    def compare_period(period_id: UUID):
        baseline = json.loads(REFERENCE.read_text(encoding='utf-8'))
        return compare_snapshot(get_data(period_id), baseline)

    @app.get('/api/v1/periods/{period_id}/snapshot', tags=['Admin'], dependencies=[Depends(require_admin)])
    def period_snapshot(period_id: UUID):
        return get_data(period_id)

    @app.post('/api/v1/periods/{period_id}/preview', tags=['Admin'], dependencies=[Depends(require_admin)])
    def preview_period(period_id: UUID, seconds: int = Query(25, ge=5, le=60)):
        if not app.state.preview_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail='Optimization already running')
        try:
            return generate_preview(get_data(period_id), seconds=seconds)
        finally:
            app.state.preview_lock.release()

    @app.post('/api/v1/periods/{period_id}/drafts', tags=['Admin'], dependencies=[Depends(require_admin)])
    def generate_and_save_draft(period_id: UUID, request: SaveDraftRequest):
        """Re-solve against LIVE records before an atomic, server-authorized draft write.

        The frontend cannot provide assignments or a staff_id to this route.
        """
        if not app.state.preview_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail='Optimization already running')
        try:
            raw = get_reader().period_data(str(period_id))
            snapshot = build_snapshot(raw)
            result = generate_preview(snapshot, seconds=request.seconds)
            if not result['validation']['valid']:
                raise HTTPException(status_code=409, detail='Solver result failed independent validation')
            if result['invigilator']['status'] not in ('OPTIMAL', 'FEASIBLE'):
                raise HTTPException(status_code=409, detail='No valid invigilator solution to save')
            sid_map = {s['source_ref']: s['id'] for s in raw['staff']}
            room_codes = {r['id']: r['code'] for r in raw['rooms']}
            sitting_map = {}
            for s in raw['room_sittings']:
                day, clock = local(s['starts_at'])
                sitting_map[f"{day}_{clock}_{room_codes[s['room_id']]}"] = s['id']
            # Strict key mapping: refuse saving if the snapshot cannot map to real UUIDs.
            invigilators = [{'staff_id': sid_map[a['staff_id']],
                             'room_sitting_id': sitting_map[a['sitting_id']]}
                            for a in result['assignments']]
            chairs = []
            # Current imported data has a known chair shortage. Even on future feasible
            # datasets, keep Phase 9 chair coverage out of saved drafts until the
            # chair-coverage validator is implemented and separately tested.
            note = (request.note.strip() + ' | ' if request.note.strip() else '') + \
                f"Invigilation draft; chairs: {result['chair']['status']}; publishing disabled"
            record = get_store().save_draft(
                str(period_id), result['invigilator']['status'], invigilators, chairs,
                len(snapshot['room_sittings']), note)
            return {'version': record, 'saved_assignments': len(invigilators),
                    'chairs_saved': 0, 'publication_blocked': True,
                    'warning': 'DRAFT ONLY. Chair assignments have not been stored or approved.'}
        except LookupError:
            raise HTTPException(status_code=404, detail='Exam period not found') from None
        except (DataIntegrityError, KeyError, ValueError, StopIteration):
            raise HTTPException(status_code=409, detail='Live source could not be mapped consistently') from None
        except DatabaseReadError:
            raise HTTPException(status_code=502, detail='Supabase read failed') from None
        except StoreError:
            raise HTTPException(status_code=502, detail='Draft not saved. Check Phase 9 SQL migration and database rules.') from None
        finally:
            app.state.preview_lock.release()

    @app.get('/api/v1/periods/{period_id}/drafts', tags=['Admin'], dependencies=[Depends(require_admin)])
    def list_period_drafts(period_id: UUID):
        try:
            return get_store().list_drafts(str(period_id))
        except StoreError:
            raise HTTPException(status_code=502, detail='Unable to load saved drafts') from None

    @app.get('/api/v1/periods/{period_id}/drafts/{version_id}', tags=['Admin'], dependencies=[Depends(require_admin)])
    def get_period_draft(period_id: UUID, version_id: UUID):
        try:
            raw = get_reader().period_data(str(period_id))
            return get_store().draft_assignments(str(period_id), str(version_id), raw)
        except LookupError:
            raise HTTPException(status_code=404, detail='Draft not found') from None
        except (StoreError, DatabaseReadError):
            raise HTTPException(status_code=502, detail='Unable to read saved draft') from None

    @app.get('/api/v1/periods/{period_id}/drafts/{version_id}/replacement-options',
             tags=['Admin'], dependencies=[Depends(require_admin)])
    def replacement_options(period_id: UUID, version_id: UUID, room_sitting_id: UUID,
                            old_staff_code: str = Query(min_length=4, max_length=40)):
        try:
            raw = get_reader().period_data(str(period_id))
            saved = get_store().draft_assignments(str(period_id), str(version_id), raw)
            recommended = suggest(raw, saved, str(room_sitting_id), old_staff_code)
            return {'source_version_id': str(version_id), 'candidates': recommended,
                    'note': 'Recommendations only. SQL revalidates the whole draft before saving.'}
        except LookupError:
            raise HTTPException(status_code=404, detail='Saved draft not found') from None
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (StoreError, DatabaseReadError):
            raise HTTPException(status_code=502, detail='Unable to evaluate replacement options') from None

    @app.post('/api/v1/periods/{period_id}/drafts/{version_id}/replace', tags=['Admin'])
    def replace_invigilator(period_id: UUID, version_id: UUID, request: ReplaceDraftRequest,
                           admin=Depends(require_admin)):
        if request.old_staff_code == request.new_staff_code:
            raise HTTPException(status_code=400, detail='Choose a different staff member')
        try:
            raw = get_reader().period_data(str(period_id))
            saved = get_store().draft_assignments(str(period_id), str(version_id), raw)
            if saved['version']['status'] != 'draft':
                raise HTTPException(status_code=409, detail='Only DRAFT versions may be edited')
            if not any(a['sitting_id'] == str(request.room_sitting_id) and
                       a['staff_id'] == request.old_staff_code for a in saved['assignments']):
                raise HTTPException(status_code=409, detail='Source assignment not found')
            code_ids = {s['source_ref']: s['id'] for s in raw['staff']}
            old_id = code_ids.get(request.old_staff_code)
            new_id = code_ids.get(request.new_staff_code)
            if not old_id or not new_id:
                raise HTTPException(status_code=400, detail='Invalid staff code')
            # Authoritative checking happens in the atomic SQL function. Verify
            # admin UID again in the SQL function; no browser-supplied UID used.
            result = get_store().replace_invigilator(
                version_id=str(version_id), sitting_id=str(request.room_sitting_id),
                old_id=old_id, new_id=new_id, actor_uid=admin['user_id'],
                reason=request.reason.strip())
            return {'version': result, 'publication_blocked': True,
                    'warning': 'New draft saved. Original unchanged. Never automatically published.'}
        except LookupError:
            raise HTTPException(status_code=404, detail='Saved draft not found') from None
        except (DatabaseReadError, StoreError):
            raise HTTPException(status_code=409, detail='Replacement rejected or database unavailable. Confirm constraints and Phase 10 SQL migration.') from None

    @app.get('/api/v1/my-assignments', tags=['Staff'])
    def my_assignments(user=Depends(principal)):
        if user['role'] != 'staff':
            raise HTTPException(status_code=403, detail='This endpoint is for linked staff accounts')
        try:
            return get_store().my_published_duties(user['staff_id'])
        except StoreError:
            raise HTTPException(status_code=502, detail='Unable to load assigned duties') from None

    mount_control_routes(app, require_admin=require_admin, get_reader=get_reader, get_store=get_store)
    mount_phase13_routes(app, require_admin=require_admin, get_reader=get_reader, get_store=get_store)
    mount_phase14_routes(app, principal=principal, require_admin=require_admin, get_reader=get_reader, get_store=get_store)
    mount_phase15_routes(app, require_admin=require_admin, get_reader=get_reader, get_store=get_store)
    return app

app = create_app()
