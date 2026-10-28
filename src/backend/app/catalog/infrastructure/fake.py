"""Catálogo falso, para desarrollo, pruebas e2e y carga (plan D1, D8).

Devuelve resultados deterministas, con referencias `fake:…` que entiende el proveedor
de reproducción falso de la web (suenan 3 s, salvo `fake:error`, que falla). Algunos
textos tienen un comportamiento especial:

- `error`: una canción que falla al sonar (`fake:error`).
- `caído`: el proveedor no responde (CatalogUnavailable, R012).
- `nada`: ningún resultado.
- `retirada`: una canción que, al pedirla, ya no existe (R014).

Los títulos salen de la referencia, así que la búsqueda y la consulta coinciden. No se
puede usar en producción (D8).
"""

import re
import unicodedata

from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable

PREFIX = "fake:"
AUTHOR = "Catálogo falso"
FAILING = CatalogTrack(ref="fake:error", title="Canción que falla", author=AUTHOR)
RESULTS = 5


def _slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-") or "cancion"


def _track(ref: str) -> CatalogTrack:
    slug, _, number = ref.removeprefix(PREFIX).rpartition("-")
    return CatalogTrack(ref=ref, title=f"Canción {number} de {slug}", author=AUTHOR)


class FakeCatalog:
    async def search(self, query: str, limit: int) -> list[CatalogTrack]:
        slug = _slug(query)
        if slug == "caido":
            raise CatalogUnavailable
        if slug == "nada":
            return []
        if slug == "error":
            return [FAILING]
        return [_track(f"{PREFIX}{slug}-{number}") for number in range(1, RESULTS + 1)][:limit]

    async def lookup(self, ref: str) -> CatalogTrack | None:
        if ref == FAILING.ref:
            return FAILING
        if not ref.startswith(PREFIX) or ref.startswith(f"{PREFIX}retirada-"):
            return None
        slug, _, number = ref.removeprefix(PREFIX).rpartition("-")
        if not slug or not number.isdigit():
            return None
        return _track(ref)
