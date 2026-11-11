"""Cuánta cuota diaria de la YouTube Data API se lleva gastada (feature 004, R021, plan D11).

Google cobra la cuota por llamada: 100 unidades por `search.list` y 1 por `videos.list`,
de 10 000 al día por proyecto, y el día termina a medianoche de la hora del Pacífico:
https://developers.google.com/youtube/v3/determine_quota_cost

El total del día vive en Redis, compartido por todos los procesos y tareas, en la clave
`catalog:youtube-units:{día}`. Tras cada llamada se emite como `YouTubeQuotaUsed`, y la
alarma salta con 8000. No es un dato de negocio (S10): si Redis falla, la búsqueda sigue
igual y solo se pierde la cifra.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import anyio
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.shared.metrics import Metrics

logger = logging.getLogger(__name__)

COST = {"search": 100, "videos": 1}
QUOTA_TIMEZONE = ZoneInfo("America/Los_Angeles")
# Más que un día: la clave del día anterior sigue a mano un rato después de cambiar.
KEY_TTL_SECONDS = 48 * 3600
# Redis está en el camino de la búsqueda: no puede comerse el presupuesto de Q1. Es el tope
# de toda la suma, con los reintentos del cliente incluidos.
TIMEOUT_SECONDS = 0.5


def quota_day(now: datetime) -> str:
    """El día de la cuota de YouTube al que pertenece `now`, en la hora del Pacífico."""
    return now.astimezone(QUOTA_TIMEZONE).date().isoformat()


def quota_key(day: str) -> str:
    return f"catalog:youtube-units:{day}"


class YouTubeQuotaCounter:
    def __init__(
        self,
        client: Redis,
        metrics: Metrics,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._metrics = metrics
        self._now = now

    @classmethod
    def from_url(cls, url: str, metrics: Metrics) -> "YouTubeQuotaCounter":
        return cls(
            Redis.from_url(
                url, socket_connect_timeout=TIMEOUT_SECONDS, socket_timeout=TIMEOUT_SECONDS
            ),
            metrics,
        )

    async def add(self, endpoint: str) -> int | None:
        """Suma lo que cuesta una llamada a `endpoint` y devuelve el total del día, o None si
        Redis no respondió."""
        key = quota_key(quota_day(self._now()))
        try:
            with anyio.fail_after(TIMEOUT_SECONDS):
                async with self._client.pipeline(transaction=True) as pipe:
                    pipe.incrby(key, COST[endpoint])
                    pipe.expire(key, KEY_TTL_SECONDS, nx=True)
                    total, _ = await pipe.execute()
        except (RedisError, TimeoutError) as error:
            logger.warning("contador de cuota de YouTube sin respuesta: %s", type(error).__name__)
            return None
        self._metrics.count("YouTubeQuotaUsed", int(total))
        return int(total)

    async def aclose(self) -> None:
        await self._client.aclose()
