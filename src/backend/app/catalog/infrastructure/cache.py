"""Caché del catálogo y límite de búsquedas en Redis (plan D2, ADR-0004).

Claves, todas con el prefijo del establecimiento (S8):

- `est:{id}:catalog:search:<hash>`: los resultados de una búsqueda, 24 h;
- `est:{id}:search-rate:{device}`: las búsquedas del dispositivo en el minuto.

Las canciones sueltas no se guardan: un pedido se valida siempre con el proveedor (R014).

Nada de esto es un dato de negocio (S10). Si Redis no responde, la caché se comporta
como vacía, el límite no se aplica y la búsqueda sigue: el fallo queda en el log.
"""

import json
import logging
from datetime import timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.catalog.domain.catalog import CatalogTrack

logger = logging.getLogger(__name__)

TTL = timedelta(hours=24)
RATE_WINDOW = timedelta(minutes=1)
# Redis está en el camino de cada búsqueda: no puede comerse el presupuesto de Q1.
TIMEOUT_SECONDS = 0.5


def _prefix(establishment_id: UUID) -> str:
    return f"est:{establishment_id}"


def _search_key(establishment_id: UUID, query_key: str) -> str:
    return f"{_prefix(establishment_id)}:catalog:search:{query_key}"


def _rate_key(establishment_id: UUID, device_id: UUID) -> str:
    return f"{_prefix(establishment_id)}:search-rate:{device_id}"


def _encode(track: CatalogTrack) -> dict[str, str]:
    return {"ref": track.ref, "title": track.title, "author": track.author}


def _decode(raw: dict[str, str]) -> CatalogTrack:
    return CatalogTrack(ref=raw["ref"], title=raw["title"], author=raw["author"])


class RedisCatalogCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> "RedisCatalogCache":
        return cls(
            Redis.from_url(
                url, socket_connect_timeout=TIMEOUT_SECONDS, socket_timeout=TIMEOUT_SECONDS
            )
        )

    async def search(self, establishment_id: UUID, query_key: str) -> list[CatalogTrack] | None:
        try:
            raw = await self._client.get(_search_key(establishment_id, query_key))
        except RedisError as error:
            logger.warning("caché del catálogo sin respuesta: %s", type(error).__name__)
            return None
        if raw is None:
            return None
        try:
            return [_decode(item) for item in json.loads(raw)]
        except (ValueError, KeyError, TypeError):
            # Una entrada que no se entiende (otro formato, una versión anterior) es como
            # si no estuviera: la búsqueda no se rompe por la caché.
            logger.warning("caché del catálogo con una entrada que no se entiende")
            return None

    async def store_search(
        self, establishment_id: UUID, query_key: str, tracks: list[CatalogTrack]
    ) -> None:
        try:
            await self._client.set(
                _search_key(establishment_id, query_key),
                json.dumps([_encode(track) for track in tracks]),
                ex=TTL,
            )
        except RedisError as error:
            logger.warning("caché del catálogo sin respuesta: %s", type(error).__name__)

    async def count_search(self, establishment_id: UUID, device_id: UUID) -> tuple[int, int]:
        key = _rate_key(establishment_id, device_id)
        window = int(RATE_WINDOW.total_seconds())
        try:
            async with self._client.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                # La ventana empieza con la primera búsqueda y no se alarga con las demás.
                pipe.expire(key, window, nx=True)
                pipe.ttl(key)
                count, _, ttl = await pipe.execute()
        except RedisError as error:
            # Sin Redis no hay límite: la búsqueda sigue (plan D2).
            logger.warning("límite de búsquedas sin respuesta: %s", type(error).__name__)
            return 0, 0
        return int(count), max(int(ttl), 1)

    async def aclose(self) -> None:
        await self._client.aclose()
