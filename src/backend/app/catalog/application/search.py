"""Casos de uso del catálogo: buscar y consultar una canción (plan D1, D2).

- `SearchTracks` aplica el límite por dispositivo (R013), sirve las búsquedas repetidas
  desde la caché y solo pregunta al proveedor cuando no están.
- `TrackLookup` es la interfaz que usa C2 para validar un pedido (S4). Pregunta siempre al
  proveedor (1 unidad de cuota en YouTube), aunque la canción haya salido en una búsqueda
  reciente: así una que dejó de existir o de poder reproducirse se rechaza (R014).

Una búsqueda que el proveedor no puede atender no se guarda (R012).
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from app.catalog.domain.catalog import CatalogCache, CatalogTrack, MusicCatalog

# Resultados por búsqueda, y búsquedas por dispositivo y minuto (R013).
RESULTS = 10
SEARCHES_PER_MINUTE = 10


class SearchRateExceeded(Exception):
    """El dispositivo pasó de SEARCHES_PER_MINUTE búsquedas en un minuto (R013)."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"reintentar en {retry_after} s")
        self.retry_after = retry_after


def query_key(query: str) -> str:
    """La clave de una búsqueda: sin tildes, en minúsculas y con los espacios colapsados,
    para que «Café  Tacvba» y «cafe tacvba» compartan resultados. Es un hash: el texto
    buscado no queda escrito en la clave."""
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", query) if not unicodedata.combining(char)
    )
    normalized = re.sub(r"\s+", " ", plain).strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


@dataclass(frozen=True)
class SearchTracks:
    catalog: MusicCatalog
    cache: CatalogCache

    async def __call__(
        self, establishment_id: UUID, device_id: UUID, query: str
    ) -> list[CatalogTrack]:
        """Lanza SearchRateExceeded (R013) o CatalogUnavailable (R012)."""
        searches, retry_after = await self.cache.count_search(establishment_id, device_id)
        if searches > SEARCHES_PER_MINUTE:
            raise SearchRateExceeded(retry_after)
        key = query_key(query)
        cached = await self.cache.search(establishment_id, key)
        if cached is not None:
            return cached
        tracks = await self.catalog.search(query, RESULTS)
        await self.cache.store_search(establishment_id, key, tracks)
        return tracks


@dataclass(frozen=True)
class TrackLookup:
    catalog: MusicCatalog

    async def __call__(self, establishment_id: UUID, ref: str) -> CatalogTrack | None:
        """La canción de la referencia, o None si ya no existe o ya no se puede reproducir
        (R014). Lanza CatalogUnavailable (R012). El establecimiento es parte del contrato
        de C3 (plan, Contratos), aunque hoy la consulta no lo necesita."""
        return await self.catalog.lookup(ref)
