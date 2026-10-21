"""Publicación de los eventos de la sesión después de confirmar la transacción (plan D6).

Los eventos van por la vía del mejor esfuerzo: si Redis no responde, el cambio ya está
guardado y la petición no falla. El panel y el reproductor lo recuperan pidiendo el
estado a la API al ver un salto de versión o al reconectar (S10).
"""

import logging
from collections.abc import Iterable
from uuid import UUID

from app.sessions.domain.music_session import SessionEvent
from app.sessions.domain.ports import EventPublisher

logger = logging.getLogger(__name__)


async def publish_events(
    publisher: EventPublisher, establishment_id: UUID, events: Iterable[SessionEvent]
) -> None:
    for event in events:
        try:
            await publisher.publish(establishment_id, event)
        except Exception:
            # Solo el tipo y la versión: el evento no lleva datos de la cuenta, pero
            # tampoco hace falta en el log más de lo que identifica el fallo.
            logger.exception("no se pudo publicar %s (versión %s)", event.type, event.version)
