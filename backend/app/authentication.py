"""Validate Supabase Auth tokens server-side; use DB membership, never user metadata roles."""
from __future__ import annotations
from dataclasses import dataclass
import httpx


class LoginError(Exception):
    pass


class AuthUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str | None


class AuthVerifier:
    def __init__(self, base_url: str, publishable_key: str, client: httpx.Client | None = None):
        self._url = base_url.rstrip('/')
        self._key = publishable_key
        self._client = client

    def verify(self, token: str) -> Identity:
        # IMPORTANT: A JWT is NOT authenticated by simply decoding its payload.
        # Supabase's /auth/v1/user validates signature + expiry on its own server.
        if not token or len(token) > 8192:
            raise LoginError('Invalid bearer token')
        if not self._key or self._key.startswith('PASTE_'):
            raise AuthUnavailable('SUPABASE_PUBLISHABLE_KEY is missing from backend .env')
        try:
            if self._client is None:
                with httpx.Client(timeout=15, follow_redirects=False) as client:
                    response = client.get(f'{self._url}/auth/v1/user', headers={
                        'apikey': self._key,
                        'Authorization': 'Bearer ' + token,
                    })
            else:
                response = self._client.get(f'{self._url}/auth/v1/user', headers={
                    'apikey': self._key,
                    'Authorization': 'Bearer ' + token,
                })
        except httpx.HTTPError as exc:
            raise AuthUnavailable('Unable to validate session with Supabase Auth') from exc
        if response.status_code in (401, 403):
            raise LoginError('Session expired or invalid')
        if response.status_code != 200:
            raise AuthUnavailable('Supabase Auth verification is unavailable')
        try:
            data = response.json()
            uid = data['id']
            if not isinstance(uid, str) or not uid:
                raise ValueError('missing id')
            return Identity(uid, data.get('email'))
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthUnavailable('Unexpected Supabase Auth response') from exc
