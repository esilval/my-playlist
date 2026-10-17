"""Tokens de los enlaces de correo (plan D7, D11).

El token viaja en claro solo en el enlace; en la base se guarda su SHA-256.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

VERIFY_TTL = timedelta(days=7)  # R028
RESET_TTL = timedelta(minutes=60)  # R016


class TokenPurpose(StrEnum):
    # Los mismos valores que el tipo email_token_purpose de la base de datos.
    VERIFY = "verify"
    RESET = "reset"


def hash_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()


def new_token() -> tuple[str, bytes]:
    """Devuelve el token para el enlace y el hash que se guarda."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


@dataclass(frozen=True)
class VerificationTokenState:
    used_at: datetime | None
    superseded_at: datetime | None
    expires_at: datetime | None
    email_verified: bool


class VerifyOutcome(StrEnum):
    VERIFY = "verify"
    ALREADY_VERIFIED = "already_verified"
    EXPIRED = "expired"
    INVALID = "invalid"


def classify_verification(state: VerificationTokenState | None, now: datetime) -> VerifyOutcome:
    """Qué hacer con un enlace de verificación (plan D11).

    Orden: usado → ya verificado (R017), aunque haya caducado; sin usar y con más de
    7 días → caducado (R028); reemplazado por un reenvío o inexistente → inválido
    (R026); si no, vigente (R025).
    """
    if state is None:
        return VerifyOutcome.INVALID
    if state.used_at is not None:
        return VerifyOutcome.ALREADY_VERIFIED if state.email_verified else VerifyOutcome.INVALID
    # Sin fecha de caducidad no vale para siempre: se trata como caducado.
    if state.expires_at is None or now >= state.expires_at:
        return VerifyOutcome.EXPIRED
    if state.superseded_at is not None:
        return VerifyOutcome.INVALID
    return VerifyOutcome.VERIFY


def is_reset_usable(state: VerificationTokenState | None, now: datetime) -> bool:
    """Un enlace de recuperación vale una sola vez y durante 60 minutos (R016)."""
    if state is None or state.used_at is not None or state.superseded_at is not None:
        return False
    return state.expires_at is not None and now < state.expires_at
