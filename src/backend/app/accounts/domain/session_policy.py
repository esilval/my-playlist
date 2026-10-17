"""Vida de la sesión del propietario (R008, R020, plan D2)."""

import hashlib
import secrets
from datetime import datetime, timedelta

IDLE_TIMEOUT = timedelta(hours=12)


def is_session_active(
    *, last_seen_at: datetime, revoked_at: datetime | None, now: datetime
) -> bool:
    """Una sesión caduca tras 12 h sin actividad; no hay caducidad absoluta (R020).

    Cada petición autenticada renueva `last_seen_at`, así que el plazo se mide desde
    la última actividad.
    """
    if revoked_at is not None:
        return False
    return now - last_seen_at <= IDLE_TIMEOUT


def new_session_token() -> tuple[str, bytes]:
    """Token opaco de la cookie y el SHA-256 que se guarda (plan D2)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_session_token(raw)


def hash_session_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()
