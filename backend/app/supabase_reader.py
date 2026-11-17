"""Supabase PostgREST *GET-only* adapter with pagination and safe failures.

The secret key bypasses RLS: this class is for a trusted backend only.
No insert/update/delete/rpc methods exist in this phase.
"""
from __future__ import annotations

from typing import Any
import httpx

PAGE_SIZE = 500  # smaller than Supabase's default 1000-row API response cap


class DatabaseReadError(Exception):
    pass


class SupabaseReader:
    def __init__(self, url: str, secret_key: str, client: httpx.Client | None = None):
        self._url = url.rstrip('/')
        self._key = secret_key
        self._client = client

    def list_rows(
        self,
        table: str,
        select: str,
        *,
        filters: dict[str, str] | None = None,
        order: str = 'id.asc',
    ) -> list[dict[str, Any]]:
        permitted = {
            'staff', 'exam_periods', 'rooms', 'courses', 'exams',
            'exam_sessions', 'room_sittings', 'session_room_links',
            'staff_unavailability', 'scheduling_rules',
        }
        if table not in permitted:
            raise ValueError('Table not allowed for the read-only API')
        result: list[dict[str, Any]] = []
        offset = 0
        owned = self._client is None
        client = self._client or httpx.Client(timeout=25, follow_redirects=False)
        try:
            while True:
                params = {'select': select, 'order': order, 'limit': PAGE_SIZE, 'offset': offset}
                params.update(filters or {})
                headers = {
                    'apikey': self._key,
                    'Accept': 'application/json',
                    'User-Agent': 'DeltaExamSchedulerBackend/phase6',
                }
                # sb_secret_* is an opaque key, NOT a JWT. Older service_role JWT
                # may additionally be used as a Bearer token with PostgREST.
                if self._key.startswith('eyJ'):
                    headers['Authorization'] = 'Bearer ' + self._key
                try:
                    response = client.get(
                        f'{self._url}/rest/v1/{table}', params=params, headers=headers
                    )
                    response.raise_for_status()
                    rows = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    # Never include response body, request URL, headers or keys.
                    raise DatabaseReadError(
                        f'Unable to read table {table} from Supabase. Check server credentials, Data API access and connectivity.'
                    ) from exc
                if not isinstance(rows, list):
                    raise DatabaseReadError(f'Unexpected response reading table {table}')
                result.extend(rows)
                if len(rows) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
                if offset > 100000:
                    raise DatabaseReadError('Excessive pagination; adjust the query filters')
            return result
        finally:
            if owned:
                client.close()

    def list_periods(self) -> list[dict[str, Any]]:
        return self.list_rows(
            'exam_periods',
            'id,name,start_date,end_date,status,head_of_control_staff_id',
        )

    def period_data(self, period_id: str) -> dict[str, list[dict[str, Any]]]:
        periods = self.list_rows(
            'exam_periods', 'id,name,start_date,end_date,status,head_of_control_staff_id',
            filters={'id': f'eq.{period_id}'},
        )
        if not periods:
            raise LookupError('Examination period not found')
        tables: dict[str, tuple[str, str, dict[str, str]]] = {
            'staff': (
                'id,source_ref,academic_rank,can_invigilate,can_chair,is_active',
                'id.asc', {},
            ),
            'courses': ('id,code,title', 'id.asc', {}),
            'rooms': ('id,code,is_active', 'id.asc', {}),
            'exams': ('id,course_id,exam_period_id', 'id.asc', {'exam_period_id': f'eq.{period_id}'}),
            'exam_sessions': (
                'id,exam_id,source_ref,starts_at,ends_at,student_count',
                'id.asc', {'exam_period_id': f'eq.{period_id}'},
            ),
            'room_sittings': (
                'id,room_id,starts_at,ends_at',
                'id.asc', {'exam_period_id': f'eq.{period_id}'},
            ),
            'session_room_links': (
                'exam_session_id,room_sitting_id',
                'exam_session_id.asc,room_sitting_id.asc',
                {'exam_period_id': f'eq.{period_id}'},
            ),
            'staff_unavailability': (
                'id,staff_id,starts_at,ends_at,status', 'id.asc', {},
            ),
            'scheduling_rules': (
                'exam_period_id,invigilators_per_room,chairs_per_exam,max_daily_invigilation_minutes,'
                'min_break_minutes,extra_preparation_minutes,allow_parallel_chair_assignments,head_can_chair',
                'exam_period_id.asc', {'exam_period_id': f'eq.{period_id}'},
            ),
        }
        data: dict[str, list[dict[str, Any]]] = {'exam_periods': periods}
        for table, (cols, order, filts) in tables.items():
            data[table] = self.list_rows(table, cols, order=order, filters=filts)
        return data
