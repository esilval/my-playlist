"""Ticket de tiempo real (ADR-0014).

El monolito lo emite y el servicio de tiempo real (C6) lo valida con el secreto que
comparten, sin leer la base de datos ni llamar a la API. Solo sirve para unirse a la sala
del establecimiento y recibir eventos: las acciones siguen pidiendo la sesión iniciada.

Formato, pensado para validarse igual en Python y en Node:

    base64url(payload) "." base64url(HMAC-SHA256(secreto, base64url(payload)))

`payload` es JSON con `est` (establecimiento), `role`, `exp` (segundos UNIX) y `jti`.
La firma se calcula sobre el segmento tal como viaja, no sobre el JSON vuelto a
serializar: así el orden de las claves o los espacios no importan al validar.
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

# `exp` se guarda en segundos enteros: según la fracción de segundo en que se emite, el
# ticket dura entre 59 y 60 s. Sobra para conectar justo después de pedirlo.
TICKET_TTL = timedelta(seconds=60)


class TicketRole(StrEnum):
    OWNER = "owner"
    PLAYER = "player"
    # El cliente que pide canciones desde el QR (feature 003, plan D6).
    CLIENT = "client"


class InvalidTicket(Exception):
    """Ticket mal formado, con la firma alterada o caducado."""


@dataclass(frozen=True)
class TicketClaims:
    establishment_id: UUID
    role: TicketRole
    expires_at: int
    ticket_id: str


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(secret: str, segment: str) -> str:
    return _b64(hmac.new(secret.encode(), segment.encode(), hashlib.sha256).digest())


def issue_ticket(
    secret: str,
    *,
    establishment_id: UUID,
    role: TicketRole,
    now: datetime,
    ticket_id: str | None = None,
) -> str:
    payload = {
        "est": str(establishment_id),
        "role": str(role),
        "exp": int((now + TICKET_TTL).timestamp()),
        "jti": ticket_id or secrets.token_urlsafe(12),
    }
    segment = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{segment}.{_signature(secret, segment)}"


def verify_ticket(secret: str, ticket: str, now: datetime) -> TicketClaims:
    """La misma comprobación que hace C6: firma en tiempo constante y caducidad."""
    segment, separator, signature = ticket.partition(".")
    # En bytes: compare_digest no admite texto no ASCII, y eso también es una firma mala.
    received = signature.encode()
    if not separator or not hmac.compare_digest(received, _signature(secret, segment).encode()):
        raise InvalidTicket("firma no válida")
    try:
        payload = json.loads(_unb64(segment))
        claims = TicketClaims(
            establishment_id=UUID(payload["est"]),
            role=TicketRole(payload["role"]),
            expires_at=int(payload["exp"]),
            ticket_id=str(payload["jti"]),
        )
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidTicket("ticket mal formado") from error
    if now.timestamp() >= claims.expires_at:
        raise InvalidTicket("ticket caducado")
    return claims


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True)
class RealtimeTicketIssuer:
    """Emite tickets con el secreto de la configuración y el reloj de la app."""

    secret: str
    clock: Clock

    def issue(self, *, establishment_id: UUID, role: TicketRole) -> str:
        return issue_ticket(
            self.secret, establishment_id=establishment_id, role=role, now=self.clock.now()
        )
