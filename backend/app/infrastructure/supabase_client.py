"""Supabase client singleton — avoids recreating clients on every request.

C4 fix: Two cached instances — one for service role (bypasses RLS) and
one for anon key (client-level auth operations).
"""

from __future__ import annotations

import threading

from supabase import Client, create_client

from app.core.config import settings

_lock = threading.Lock()
_service_client: Client | None = None
_anon_client: Client | None = None


def get_service_client() -> Client:
    """Supabase client with the service-role key (bypasses RLS)."""
    global _service_client
    if _service_client is not None:
        return _service_client
    with _lock:
        if _service_client is None:
            _service_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        return _service_client


def get_anon_client() -> Client:
    """Supabase client with the anon key (client-level auth)."""
    global _anon_client
    if _anon_client is not None:
        return _anon_client
    with _lock:
        if _anon_client is None:
            _anon_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_ANON_KEY,
            )
        return _anon_client
