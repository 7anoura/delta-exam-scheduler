"""Trusted service-only PostgREST access and atomic database draft-save RPC.

No Supabase secret is returned to the client. User roles are checked before access.
"""
from __future__ import annotations
from typing import Any
import httpx


class StoreError(Exception):
    pass


class Phase9Store:
    def __init__(self, url: str, secret: str, client: httpx.Client | None = None):
        self.url = url.rstrip('/')
        self.secret = secret
        self.client = client

    def _request(self, method: str, path: str, *, params=None, body=None) -> Any:
        headers = {'apikey': self.secret, 'Accept': 'application/json', 'Content-Type': 'application/json'}
        if self.secret.startswith('eyJ'):
            headers['Authorization'] = 'Bearer ' + self.secret
        owned = self.client is None
        client = self.client or httpx.Client(timeout=35, follow_redirects=False)
        try:
            try:
                response = client.request(method, self.url + '/rest/v1/' + path,
                                          headers=headers, params=params, json=body)
            except httpx.HTTPError as exc:
                raise StoreError('Database request failed') from exc
            if not 200 <= response.status_code < 300:
                # Never print the request (secret URL/header) or raw DB error to users.
                raise StoreError(f'Database operation rejected (HTTP {response.status_code}); check SQL migration and server logs')
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError as exc:
                raise StoreError('Unexpected database response') from exc
        finally:
            if owned:
                client.close()

    def _all_rows(self, table: str, params: dict) -> list[dict]:
        """Avoid Supabase's default per-request row cap of 1000."""
        results = []
        offset = 0
        page_size = 500
        while True:
            page = self._request('GET', table, params={
                **params, 'limit': page_size, 'offset': offset,
            })
            if not isinstance(page, list):
                raise StoreError('Unexpected table response')
            results.extend(page)
            if len(page) < page_size:
                return results
            offset += page_size
            if offset > 10000:
                raise StoreError('Too many records to display safely')

    def role(self, uid: str) -> dict | None:
        admin = self._request('GET', 'system_admins', params={
            'select': 'auth_user_id', 'auth_user_id': 'eq.' + uid, 'limit': 1})
        if admin:
            return {'role': 'admin', 'staff_id': None, 'full_name': None}
        staff = self._request('GET', 'staff', params={
            'select': 'id,full_name,is_active', 'auth_user_id': 'eq.' + uid, 'limit': 1})
        if staff and staff[0]['is_active']:
            return {'role': 'staff', 'staff_id': staff[0]['id'], 'full_name': staff[0]['full_name']}
        return None

    def list_drafts(self, period_id: str) -> list[dict]:
        rows = self._request('GET', 'schedule_versions', params={
            'select': 'id,exam_period_id,version_number,status,solver_status,generated_at,notes',
            'exam_period_id': 'eq.' + period_id, 'order': 'version_number.desc', 'limit': 100,
        })
        return rows

    def save_draft(self, period_id: str, solver_status: str, assignments: list[dict],
                   chairs: list[dict], expected_sittings: int, note: str):
        return self._request('POST', 'rpc/save_exam_draft_v1', body={
            'p_period_id': period_id,
            'p_solver_status': solver_status,
            'p_assignments': assignments,
            'p_chairs': chairs,
            'p_expected_sittings': expected_sittings,
            'p_notes': note[:500],
        })

    def draft_assignments(self, period_id: str, version_id: str, raw: dict) -> dict:
        record = self._request('GET', 'schedule_versions', params={
            'select': 'id,exam_period_id,version_number,status,solver_status,generated_at,notes',
            'id': 'eq.' + version_id, 'exam_period_id': 'eq.' + period_id, 'limit': 1,
        })
        if not record:
            raise LookupError('Draft not found')
        rows = self._all_rows('invigilator_assignments', {
            'select': 'staff_id,room_sitting_id', 'schedule_version_id': 'eq.' + version_id,
            'order': 'room_sitting_id.asc',
        })
        staffs = {s['id']: s['source_ref'] for s in raw['staff']}
        rooms = {r['id']: r['code'] for r in raw['rooms']}
        sittings = {r['id']: r for r in raw['room_sittings']}
        from .snapshot import local  # existing Phase 6 helper
        out = []
        for a in rows:
            s = sittings.get(a['room_sitting_id'])
            if not s or a['staff_id'] not in staffs:
                raise StoreError('Saved draft references missing live records')
            day, start = local(s['starts_at'])
            _, end = local(s['ends_at'])
            out.append({'staff_id': staffs[a['staff_id']], 'sitting_id': a['room_sitting_id'],
                        'date': day, 'start': start, 'end': end, 'room_code': rooms.get(s['room_id'], '?')})
        out.sort(key=lambda a: (a['date'], a['start'], a['room_code'], a['staff_id']))
        return {'version': record[0], 'assignments': out}

    def replace_invigilator(self, *, version_id: str, sitting_id: str, old_id: str,
                            new_id: str, actor_uid: str, reason: str) -> dict:
        return self._request('POST', 'rpc/replace_invigilator_draft_v1', body={
            'p_source_version_id': version_id,
            'p_room_sitting_id': sitting_id,
            'p_old_staff_id': old_id,
            'p_new_staff_id': new_id,
            'p_actor_auth_user_id': actor_uid,
            'p_reason': reason,
        })

    def appoint_head(self, period_id: str, staff_id: str | None, actor_uid: str):
        return self._request('POST', 'rpc/appoint_head_of_control_v1', body={
            'p_period_id': period_id, 'p_staff_id': staff_id,
            'p_actor_auth_user_id': actor_uid,
        })

    def save_chair_plan(self, period_id: str, version_id: str,
                        chairs: list[dict], actor_uid: str, note: str):
        record = self._request('GET', 'schedule_versions', params={
            'select': 'id', 'id': 'eq.' + version_id,
            'exam_period_id': 'eq.' + period_id,
            'status': 'eq.draft', 'limit': 1,
        })
        if not record:
            raise LookupError('Source draft not found in this period')
        return self._request('POST', 'rpc/save_chair_plan_draft_v1', body={
            'p_source_version_id': version_id,
            'p_chairs': chairs, 'p_actor_auth_user_id': actor_uid,
            'p_note': note,
        })

    def saved_chair_plan(self, period_id: str, version_id: str, raw: dict):
        record = self._request('GET', 'schedule_versions', params={
            'select': 'id,version_number,status,exam_period_id',
            'id': 'eq.' + version_id, 'exam_period_id': 'eq.' + period_id,
            'limit': 1,
        })
        if not record:
            raise LookupError('Schedule version not found')
        rows = self._all_rows('chair_assignments', {
            'select': 'exam_id,staff_id', 'schedule_version_id': 'eq.' + version_id,
            'order': 'exam_id.asc',
        })
        code_by_id = {c['id']: c['code'] for c in raw['courses']}
        course_id_by_exam = {e['id']: e['course_id'] for e in raw['exams']}
        staff_by_id = {s['id']: s['source_ref'] for s in raw['staff']}
        assignments = []
        for row in rows:
            if row['exam_id'] not in course_id_by_exam:
                raise StoreError('Chair assignment refers to an exam outside period')
            assignments.append({
                'exam_id': row['exam_id'],
                'code': code_by_id[course_id_by_exam[row['exam_id']]],
                'staff_id': row['staff_id'],
                'staff_code': staff_by_id[row['staff_id']],
            })
        return {'version': record[0], 'chairs': assignments,
                'chair_count': len(assignments), 'total_exams': len(raw['exams']),
                'complete': len(assignments) == len(raw['exams']),
                'publication_blocked': True}

    def my_published_duties(self, staff_id: str) -> list[dict]:
        # IMPORTANT: the role check and staff_id come from backend verified identity,
        # never from a user-supplied staff_id request parameter.
        rows = self._all_rows('invigilator_assignments', {
            'select': 'room_sitting_id,schedule_versions!inner(id,status,exam_period_id)',
            'staff_id': 'eq.' + staff_id,
            'schedule_versions.status': 'eq.published',
            'order': 'room_sitting_id.asc',
        })
        if not rows:
            return []
        sitting_ids = {r['room_sitting_id'] for r in rows}
        result = []
        from .snapshot import local
        # Query each sitting via chunked IN filter, not one request per assignment.
        ids = list(sitting_ids)
        all_sittings = []
        for i in range(0, len(ids), 100):
            block = ids[i:i+100]
            sittings = self._request('GET', 'room_sittings', params={
                'select': 'id,room_id,starts_at,ends_at', 'id': 'in.(' + ','.join(block) + ')',
                'limit': 100,
            })
            all_sittings.extend(sittings)
        room_ids = {s['room_id'] for s in all_sittings}
        rooms = {}
        room_id_list = list(room_ids)
        for i in range(0, len(room_id_list), 100):
            fetched = self._request('GET', 'rooms', params={
                'select': 'id,code', 'id': 'in.(' + ','.join(room_id_list[i:i+100]) + ')',
                'limit': 100,
            })
            rooms.update({r['id']: r['code'] for r in fetched})
        for s in all_sittings:
            day, start = local(s['starts_at'])
            _, end = local(s['ends_at'])
            result.append({'date': day, 'start': start, 'end': end,
                           'room_code': rooms.get(s['room_id'], '?')})
        return sorted(result, key=lambda x: (x['date'], x['start']))
