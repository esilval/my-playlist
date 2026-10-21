"""Publicación de los eventos de la sesión de música por Redis pub/sub (ADR-0005, plan D6).

El monolito publica en el canal `est:{establishment_id}` y el servicio de tiempo real
lo reenvía a la sala del mismo nombre (S8: canales con prefijo de establecimiento).
Redis solo transporta: nada de lo publicado es la única copia de un dato (S10).
"""

import json
from uuid import UUID

from redis.asyncio import Redis

from app.sessions.domain.music_session import SessionEvent

# Publicar va por el mejor esfuerzo, después del commit (plan D6): si Redis no
# responde, la petición no puede quedarse esperando más allá del presupuesto de Q5.
PUBLISH_TIMEOUT_SECONDS = 1.0


def channel_for(establishment_id: UUID) -> str:
    return f"est:{establishment_id}"


def event_message(event: SessionEvent) -> str:
    """El cuerpo del evento: `{type, session_id, version, …}` con los datos del evento.
    Solo lleva lo que se muestra en pantalla, nunca datos de la cuenta (ADR-0014)."""
    return json.dumps(
        {
            **event.data,
            "type": str(event.type),
            "session_id": str(event.session_id),
            "version": event.version,
        },
        separators=(",", ":"),
    )


class RedisEventPublisher:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> "RedisEventPublisher":
        return cls(
            Redis.from_url(
                url,
                socket_connect_timeout=PUBLISH_TIMEOUT_SECONDS,
                socket_timeout=PUBLISH_TIMEOUT_SECONDS,
            )
        )

    async def publish(self, establishment_id: UUID, event: SessionEvent) -> None:
        await self._client.publish(channel_for(establishment_id), event_message(event))

    async def aclose(self) -> None:
        await self._client.aclose()
