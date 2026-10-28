"""Adaptador de YouTube del catálogo, sin red: las respuestas son de ejemplo, con la forma
que documenta la YouTube Data API v3 (plan D8)."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

import anyio
import httpx2
import pytest

from app.catalog.domain.catalog import CatalogTrack, CatalogUnavailable
from app.catalog.infrastructure.youtube import YouTubeCatalog

pytestmark = pytest.mark.anyio

KEY = "clave-de-pruebas-de-youtube"
QUERY = "Shakira La tortura"
# Una sola palabra: así aparecería igual en una URL registrada, sin codificar espacios.
WORD = "Shakira"
VIDEO = "AAAAAAAAAAA"


def _catalog(
    handler: Callable[[httpx2.Request], httpx2.Response],
) -> tuple[YouTubeCatalog, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    client = httpx2.AsyncClient(transport=httpx2.MockTransport(record))
    return YouTubeCatalog(KEY, client), seen


def _slow_catalog(
    handler: Callable[[httpx2.Request], Coroutine[None, None, httpx2.Response]],
    total_timeout: float,
) -> YouTubeCatalog:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return YouTubeCatalog(KEY, client, total_timeout=total_timeout)


def _json(body: dict[str, Any], status: int = 200) -> Callable[[httpx2.Request], httpx2.Response]:
    return lambda _request: httpx2.Response(status, json=body)


SEARCH = {
    "items": [
        {
            "id": {"kind": "youtube#video", "videoId": VIDEO},
            "snippet": {
                "title": "La Tortura &amp; Alejandro Sanz",
                "channelTitle": "Shakira&#39;s",
            },
        },
        # Un canal o una lista no es una canción: no tiene videoId.
        {"id": {"kind": "youtube#channel", "channelId": "UC123"}, "snippet": {"title": "Canal"}},
    ]
}


def _video(embeddable: bool) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": VIDEO,
                "snippet": {"title": "La Tortura", "channelTitle": "Shakira"},
                "status": {"embeddable": embeddable},
            }
        ]
    }


async def test_F003_R003_youtube_normaliza_titulo_y_canal_y_forma_yt_id() -> None:
    catalog, _ = _catalog(_json(SEARCH))

    results = await catalog.search(QUERY, 10)

    assert results == [
        CatalogTrack(ref=f"yt:{VIDEO}", title="La Tortura & Alejandro Sanz", author="Shakira's")
    ]


async def test_F003_R004_la_busqueda_pide_solo_videos_que_se_pueden_insertar() -> None:
    catalog, seen = _catalog(_json(SEARCH))

    await catalog.search(QUERY, 10)

    [request] = seen
    assert request.url.path == "/youtube/v3/search"
    params = dict(request.url.params)
    assert params["type"] == "video"
    assert params["videoEmbeddable"] == "true"
    assert (params["q"], params["maxResults"]) == (QUERY, "10")
    # La clave va en una cabecera, nunca en la URL (que acaba en registros de peticiones).
    assert request.headers["X-Goog-Api-Key"] == KEY
    assert KEY not in str(request.url)


async def test_F003_R004_lookup_de_un_video_que_no_se_puede_insertar_da_none() -> None:
    catalog, seen = _catalog(_json(_video(embeddable=False)))

    assert await catalog.lookup(f"yt:{VIDEO}") is None
    [request] = seen
    assert request.url.path == "/youtube/v3/videos"
    assert dict(request.url.params)["part"] == "snippet,status"

    # El que sí se puede insertar se reconoce, con su título y su canal.
    catalog, _ = _catalog(_json(_video(embeddable=True)))
    assert await catalog.lookup(f"yt:{VIDEO}") == CatalogTrack(
        ref=f"yt:{VIDEO}", title="La Tortura", author="Shakira"
    )


async def test_F003_R014_lookup_de_un_video_que_ya_no_existe_da_none() -> None:
    catalog, seen = _catalog(_json({"items": []}))
    assert await catalog.lookup(f"yt:{VIDEO}") is None
    assert len(seen) == 1

    # Una referencia que no es de YouTube ni se consulta.
    catalog, seen = _catalog(_json(_video(embeddable=True)))
    for ref in ("fake:3s", "yt:corto", f"spotify:{VIDEO}", VIDEO):
        assert await catalog.lookup(ref) is None
    assert seen == []


def _timeout(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("sin respuesta", request=request)


def _unreachable(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("sin conexión", request=request)


async def test_F003_R012_youtube_lanza_catalog_unavailable_ante_5xx_cuota_o_espera() -> None:
    quota = {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}}
    for handler in (
        _json({}, status=500),
        _json({}, status=503),
        _json(quota, status=403),
        _timeout,
        _unreachable,
    ):
        catalog, _ = _catalog(handler)
        with pytest.raises(CatalogUnavailable):
            await catalog.search(QUERY, 10)
        with pytest.raises(CatalogUnavailable):
            await catalog.lookup(f"yt:{VIDEO}")


async def test_F003_R012_ni_la_clave_ni_el_texto_buscado_van_al_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Todo el registro en DEBUG, como si la app lo tuviera así: nada debe filtrarse.
    caplog.set_level(logging.DEBUG)
    for handler in (_json(SEARCH), _json({}, status=403), _timeout, _unreachable):
        catalog, _ = _catalog(handler)
        try:
            await catalog.search(WORD, 10)
        except CatalogUnavailable as raised:
            # Tampoco en la excepción, que llega a los logs de la API.
            assert KEY not in repr(raised) and WORD not in repr(raised)
            assert raised.__cause__ is None

    messages = [record.getMessage() for record in caplog.records]
    assert any("YouTube" in message for message in messages)
    # El cliente HTTP no registra sus peticiones: la URL lleva el texto buscado.
    assert not [r for r in caplog.records if r.name.startswith(("httpx2", "httpcore2"))]
    assert all(KEY not in message and WORD not in message for message in messages)


async def test_F003_R012_la_espera_es_un_tope_de_toda_la_llamada() -> None:
    # Cada fase por separado cabría en la espera de httpx2; toda la llamada no.
    async def slow(_request: httpx2.Request) -> httpx2.Response:
        await anyio.sleep(0.5)
        return httpx2.Response(200, json=SEARCH)

    catalog = _slow_catalog(slow, total_timeout=0.1)
    with anyio.fail_after(0.4), pytest.raises(CatalogUnavailable):
        await catalog.search(WORD, 10)


async def test_F003_R012_un_cuerpo_que_no_es_json_da_catalog_unavailable() -> None:
    for handler in (
        lambda _request: httpx2.Response(200, text="<html>error</html>"),
        _json({}, status=400),
    ):
        catalog, _ = _catalog(handler)
        with pytest.raises(CatalogUnavailable):
            await catalog.search(WORD, 10)
