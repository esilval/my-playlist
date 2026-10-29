"""Identificación anónima del dispositivo de un cliente (feature 003, plan D3; ADR-0007).

El cliente que llega por el QR recibe un identificador aleatorio de dispositivo, firmado
por el monolito y ligado al establecimiento. No se le pide ningún dato, y no se guarda
nada de él salvo ese identificador en las canciones que pide (S9). Viaja en la cookie
`mp_device`, cuya ruta la limita a las rutas públicas de su establecimiento.

Formato, el mismo que el ticket de tiempo real (ADR-0014):

    base64url(payload) "." base64url(HMAC-SHA256(secreto, base64url(payload)))

`payload` es JSON con `est` (establecimiento), `dev` (el dispositivo, un UUID aleatorio)
e `iat` (segundos UNIX en que se emitió). No caduca: dura lo que la cookie. Solo lo
emite y lo valida el monolito, con un secreto propio (`DEVICE_TOKEN_SECRET`).
"""

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4


class InvalidDeviceToken(Exception):
    """Token mal formado, con la firma alterada o de otro establecimiento."""


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(secret: str, segment: str) -> str:
    return _b64(hmac.new(secret.encode(), segment.encode(), hashlib.sha256).digest())


def issue_device_token(
    secret: str, *, establishment_id: UUID, now: datetime, device_id: UUID | None = None
) -> tuple[str, UUID]:
    """Devuelve el token y el dispositivo que identifica (uno nuevo y aleatorio)."""
    device = device_id if device_id is not None else uuid4()
    payload = {"est": str(establishment_id), "dev": str(device), "iat": int(now.timestamp())}
    segment = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{segment}.{_signature(secret, segment)}", device


def verify_device_token(secret: str, token: str, *, establishment_id: UUID) -> UUID:
    """El dispositivo del token, si la firma vale y es de este establecimiento (R011)."""
    segment, separator, signature = token.partition(".")
    # En bytes: compare_digest no admite texto no ASCII, y eso también es una firma mala.
    received = signature.encode()
    if not separator or not hmac.compare_digest(received, _signature(secret, segment).encode()):
        raise InvalidDeviceToken("firma no válida")
    try:
        payload = json.loads(_unb64(segment))
        establishment = UUID(payload["est"])
        device = UUID(payload["dev"])
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidDeviceToken("token mal formado") from error
    # La identificación de otro establecimiento no vale aquí: se trata como un
    # dispositivo nuevo (R011).
    if establishment != establishment_id:
        raise InvalidDeviceToken("token de otro establecimiento")
    return device


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class DeviceTokens:
    """Emite y valida tokens con el secreto de la configuración y el reloj de la app."""

    secret: str
    clock: Clock

    def issue(self, establishment_id: UUID) -> tuple[str, UUID]:
        return issue_device_token(
            self.secret, establishment_id=establishment_id, now=self.clock.now()
        )

    def verify(self, token: str, establishment_id: UUID) -> UUID:
        return verify_device_token(self.secret, token, establishment_id=establishment_id)
