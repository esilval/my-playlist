"""El catálogo de música visto desde el resto del sistema (plan D1, S4).

Una canción del catálogo es su referencia opaca, su título y su autor. La referencia
es lo que se guarda en la cola: solo la entienden el adaptador del catálogo y el del
reproductor (`yt:<id>` en YouTube, `fake:…` en el falso).
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class CatalogTrack:
    ref: str
    title: str
    author: str


class CatalogUnavailable(Exception):
    """El proveedor no responde, responde con un error o se quedó sin cuota (R012)."""


class MusicCatalog(Protocol):
    async def search(self, query: str, limit: int) -> list[CatalogTrack]:
        """Canciones que coinciden por nombre, artista o álbum (R003), solo de las que se
        pueden reproducir en el local (R004). Lanza CatalogUnavailable."""
        ...

    async def lookup(self, ref: str) -> CatalogTrack | None:
        """La canción de la referencia, o None si ya no existe o ya no se puede
        reproducir en el local (R004, R014). Lanza CatalogUnavailable."""
        ...


class CatalogCache(Protocol):
    """Caché de búsquedas y límite de búsquedas por dispositivo (plan D2). Las canciones
    sueltas no se guardan: un pedido se valida siempre con el proveedor (R014). No es
    fuente de verdad (S10): si no responde, se comporta como vacía y sin límite."""

    async def search(self, establishment_id: UUID, query_key: str) -> list[CatalogTrack] | None:
        """Los resultados guardados de una búsqueda, o None si no están."""
        ...

    async def store_search(
        self, establishment_id: UUID, query_key: str, tracks: list[CatalogTrack]
    ) -> None: ...

    async def count_search(self, establishment_id: UUID, device_id: UUID) -> tuple[int, int]:
        """Cuenta una búsqueda del dispositivo en la ventana de un minuto. Devuelve las que
        lleva en la ventana y los segundos que faltan para que termine."""
        ...
