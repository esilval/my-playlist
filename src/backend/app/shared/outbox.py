"""Bandeja de salida de correo (plan D7).

Los casos de uso encolan el mensaje en la misma transacción que el resto de sus
cambios; el trabajador lo envía después. Un fallo del proveedor nunca rompe la
petición del usuario, y un mensaje no se pierde si el proceso se reinicia.
"""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.accounts.domain.ports import EmailSender
from app.shared.db import Database
from app.shared.email.templates import EmailTemplate, render

logger = logging.getLogger(__name__)

RETRY_BASE = timedelta(seconds=30)
RETRY_CAP = timedelta(hours=1)
MAX_ATTEMPTS = 8  # 30 s, 1, 2, 4, 8, 16, 32 min y 1 h: unas 2 h de reintentos


async def enqueue(
    connection: AsyncConnection,
    *,
    establishment_id: UUID,
    to_address: str,
    to_address_normalized: str,
    template: EmailTemplate,
    payload: Mapping[str, str],
    created_at: datetime | None = None,
) -> None:
    """Encola un correo dentro de la transacción en curso, con su contexto RLS.

    `created_at` es la hora del caso de uso: el límite de R027 la compara con su propio
    reloj, así que no se mezcla con la de la base. Sin ella, la pone la base.
    """
    await connection.execute(
        text(
            "INSERT INTO email_outbox (establishment_id, to_address, to_address_normalized, "
            "template, payload, created_at) VALUES (:e, :to, :to_n, :template, "
            "CAST(:payload AS jsonb), COALESCE(:created_at, now()))"
        ),
        {
            "created_at": created_at,
            "e": establishment_id,
            "to": to_address,
            "to_n": to_address_normalized,
            "template": str(template),
            "payload": json.dumps(dict(payload)),
        },
    )


def retry_delay(attempts: int) -> timedelta:
    """Espera exponencial tras el intento número `attempts` (1, 2, …), con tope."""
    delay: timedelta = RETRY_BASE * (2 ** (attempts - 1))
    return min(delay, RETRY_CAP)


@dataclass(frozen=True)
class _Claimed:
    id: UUID
    to_address: str
    template: EmailTemplate
    payload: dict[str, Any]
    attempts: int


class OutboxDispatcher:
    """Envía los mensajes pendientes con el rol app_worker (plan D4)."""

    def __init__(self, db: Database, sender: EmailSender) -> None:
        self._db = db
        self._sender = sender

    async def dispatch(self, batch: int = 20) -> int:
        """Reclama y envía un lote; devuelve cuántos mensajes se enviaron."""
        async with self._db.transaction() as connection:
            rows = await connection.execute(
                text("SELECT * FROM outbox_claim(:batch)"), {"batch": batch}
            )
            claimed = [
                _Claimed(
                    id=row.id,
                    to_address=row.to_address,
                    template=EmailTemplate(row.template),
                    payload=row.payload,
                    attempts=row.attempts,
                )
                for row in rows
            ]

        sent = 0
        for message in claimed:
            if await self._send(message):
                sent += 1
        return sent

    async def _send(self, message: _Claimed) -> bool:
        try:
            rendered = render(message.template, message.to_address, message.payload)
        except KeyError:
            # Al payload le falta un dato: reintentar no lo arregla.
            logger.exception("correo %s con datos incompletos para su plantilla", message.id)
            await self._mark(message.id, "failed")
            return False
        try:
            await self._sender.send(rendered)
        except Exception:
            # No se registra el destinatario: es un dato personal (Q7).
            logger.exception(
                "fallo al enviar el correo %s (intento %s)", message.id, message.attempts
            )
            await self._mark_failure(message)
            return False
        return await self._mark(message.id, "sent")

    async def _mark_failure(self, message: _Claimed) -> None:
        if message.attempts >= MAX_ATTEMPTS:
            await self._mark(message.id, "failed")
            return
        await self._mark(message.id, "pending", retry_in=retry_delay(message.attempts))

    async def _mark(self, message_id: UUID, status: str, retry_in: timedelta | None = None) -> bool:
        """Registra el resultado; un fallo aquí no detiene el resto del lote.

        Puede fallar porque otro trabajador ya cerró el mensaje (su arrendamiento venció
        durante un envío lento: entrega «al menos una vez», plan D4) o por un error
        pasajero de la base de datos; en ese caso el mensaje vuelve a salir al vencer su
        arrendamiento.
        """
        try:
            async with self._db.transaction() as connection:
                await connection.execute(
                    text(
                        "SELECT outbox_mark(:id, CAST(:status AS email_status), "
                        "now() + CAST(:retry_in AS interval))"
                    ),
                    {"id": message_id, "status": status, "retry_in": retry_in},
                )
        except Exception:
            logger.exception("no se pudo marcar el correo %s como %s", message_id, status)
            return False
        return True
