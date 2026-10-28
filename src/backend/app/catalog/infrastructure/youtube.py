"""Adaptador de YouTube del catálogo: YouTube Data API v3 (plan D1, ADR-0010).

- La búsqueda usa `search.list` solo con videos que se pueden insertar (R004).
- La consulta de una referencia usa `videos.list` y comprueba `status.embeddable`, para
  validar un pedido sin fiarse del navegador (S4, R014).

Cada llamada espera como mucho 1,5 s, dentro de los 2 s de Q1. Ni la clave ni el texto
buscado se escriben en el log ni en los mensajes de error (constitución): la clave viaja
en una cabecera, no en la URL, y el cliente HTTP no registra sus peticiones.
"""

import html
import json
import logging
import re
from typing import Any

import anyio
import httpx2

from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable

logger = logging.getLogger(__name__)
# httpx2 registra cada petición con su URL en INFO, con el texto buscado, y httpcore2 sus
# cabeceras en DEBUG, con la clave. Solo los avisos y los errores.
for _noisy in ("httpx2", "httpcore2"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

API = "https://www.googleapis.com/youtube/v3"
# Tope de toda la llamada (plan D1, Q1). La espera de httpx2 es por fase (conectar,
# leer…) y por sí sola podría sumar varias veces este tiempo.
TOTAL_TIMEOUT = 1.5
TIMEOUT = httpx2.Timeout(TOTAL_TIMEOUT)
# Cuota agotada o clave rechazada (403), o demasiadas peticiones (429): YouTube no
# puede atender, como un 5xx. Otro 4xx es un fallo de la propia petición.
UNAVAILABLE_4XX = frozenset({403, 429})
REF_PREFIX = "yt:"
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _ref(video_id: str) -> str:
    return f"{REF_PREFIX}{video_id}"


def _track(video_id: str, snippet: dict[str, Any]) -> CatalogTrack:
    # La API devuelve el título y el canal con entidades HTML («&amp;», «&#39;»).
    return CatalogTrack(
        ref=_ref(video_id),
        title=html.unescape(str(snippet.get("title", ""))),
        author=html.unescape(str(snippet.get("channelTitle", ""))),
    )


class YouTubeCatalog:
    def __init__(
        self,
        api_key: str,
        client: httpx2.AsyncClient | None = None,
        total_timeout: float = TOTAL_TIMEOUT,
    ) -> None:
        self._key = api_key
        self._client = client or httpx2.AsyncClient(timeout=TIMEOUT)
        self._total_timeout = total_timeout

    async def _get(self, endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
        try:
            with anyio.fail_after(self._total_timeout):
                response = await self._client.get(
                    f"{API}/{endpoint}",
                    params=params,
                    # Las APIs de Google aceptan la clave en esta cabecera: fuera de la
                    # URL, no aparece en ningún registro de peticiones.
                    headers={"X-Goog-Api-Key": self._key},
                    timeout=TIMEOUT,
                )
        except (httpx2.HTTPError, TimeoutError) as error:
            # Sin la URL: lleva el texto buscado.
            logger.warning("YouTube no respondió a %s: %s", endpoint, type(error).__name__)
            raise CatalogUnavailable from None
        status = response.status_code
        if status != 200:
            if status >= 500 or status in UNAVAILABLE_4XX:
                logger.warning("YouTube respondió %s a %s", status, endpoint)
            else:
                logger.error("YouTube rechazó la petición a %s con %s", endpoint, status)
            raise CatalogUnavailable
        try:
            body = response.json()
        except json.JSONDecodeError:
            logger.warning("YouTube respondió a %s con un cuerpo que no es JSON", endpoint)
            raise CatalogUnavailable from None
        if not isinstance(body, dict):
            logger.warning("YouTube respondió a %s con un JSON que no es un objeto", endpoint)
            raise CatalogUnavailable
        return body

    async def search(self, query: str, limit: int) -> list[CatalogTrack]:
        body = await self._get(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "videoEmbeddable": "true",
                "maxResults": limit,
                "q": query,
            },
        )
        tracks = []
        for item in body.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if isinstance(video_id, str) and VIDEO_ID.match(video_id):
                tracks.append(_track(video_id, item.get("snippet", {})))
        return tracks

    async def lookup(self, ref: str) -> CatalogTrack | None:
        video_id = ref.removeprefix(REF_PREFIX)
        if not ref.startswith(REF_PREFIX) or not VIDEO_ID.match(video_id):
            return None
        body = await self._get("videos", {"part": "snippet,status", "id": video_id})
        items = body.get("items", [])
        if not items:
            # El video ya no existe o es privado (R014).
            return None
        item = items[0]
        if not item.get("status", {}).get("embeddable", False):
            # Ya no se puede reproducir fuera de YouTube (R004, R014).
            return None
        return _track(video_id, item.get("snippet", {}))

    async def aclose(self) -> None:
        await self._client.aclose()
