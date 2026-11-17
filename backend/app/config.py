"""Server-only environment settings. Old dev token is ignored in Phase 9."""
from __future__ import annotations
import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_secret_key: str
    admin_dev_token: str = ''  # backward compatible only; NOT used for authentication
    supabase_publishable_key: str = ''

    @classmethod
    def from_env(cls):
        config = cls(
            supabase_url=os.getenv('SUPABASE_URL', '').strip().rstrip('/'),
            supabase_secret_key=os.getenv('SUPABASE_SECRET_KEY', '').strip(),
            admin_dev_token='',
            supabase_publishable_key=os.getenv('SUPABASE_PUBLISHABLE_KEY', '').strip(),
        )
        config.validate()
        return config

    def validate(self):
        parts = urlsplit(self.supabase_url)
        if (parts.scheme != 'https' or not parts.hostname or
                not parts.hostname.endswith('.supabase.co') or
                parts.username or parts.password or parts.port or parts.path not in ('','/')):
            raise ValueError('SUPABASE_URL must be https://<project-ref>.supabase.co (without /rest/v1).')
        if not self.supabase_secret_key or self.supabase_secret_key.startswith('PASTE_') or self.supabase_secret_key.startswith('sb_publishable_'):
            raise ValueError('Set a server-only SUPABASE_SECRET_KEY in backend .env.')
        if not self.supabase_publishable_key or self.supabase_publishable_key.startswith('PASTE_') or self.supabase_publishable_key.startswith('sb_secret_'):
            raise ValueError('Set SUPABASE_PUBLISHABLE_KEY in backend .env (public key, not secret).')
