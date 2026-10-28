"""Interfaz pública de C3, el catálogo de plataformas, para los demás módulos (plan
Contratos).

- `SearchTracks(establishment_id, device_id, query) -> list[CatalogTrack]`: para la API
  pública del cliente. Lanza `SearchRateExceeded` o `CatalogUnavailable`.
- `TrackLookup(establishment_id, ref) -> CatalogTrack | None`: para C2, que valida con
  ella cada pedido (S4). Lanza `CatalogUnavailable`.
"""

from app.catalog.application.search import SearchRateExceeded, SearchTracks, TrackLookup
from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable

__all__ = [
    "CatalogTrack",
    "CatalogUnavailable",
    "SearchRateExceeded",
    "SearchTracks",
    "TrackLookup",
]
