"""Rutas públicas del cliente contra la API real (feature 003, plan D5, Contratos), con
PostgreSQL, el Redis del compose y el catálogo falso."""

from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.catalog.interface import CatalogTrack, CatalogUnavailable
from app.main import create_app
from app.sessions.domain.music_session import QUOTA
from app.sessions.interface import RequestTrack
from app.shared.realtime_ticket import TicketRole, verify_ticket
from tests.integration.api import PUBLIC_BASE_URL, api_client, api_settings, register

pytestmark = pytest.mark.anyio

EMAIL = "a@ejemplo.com"
PASSWORD = "contraseña-segura"
SESSION_URL = "/api/owner/music-session"


@dataclass
class Ctx:
    owner: httpx2.AsyncClient  # el propietario, con su sesión iniciada
    app: FastAPI
    engine: AsyncEngine  # superusuario, para comprobar sin RLS
    code: str
    visitor: Callable[[], httpx2.AsyncClient]  # un móvil nuevo, sin sesión

    def url(self, route: str, code: str | None = None) -> str:
        return f"/api/public/establishments/{code or self.code}/{route}"


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    app: FastAPI = create_app(api_settings(database_url))
    async with api_client(app) as owner, AsyncExitStack() as stack:
        await register(owner, EMAIL, PASSWORD, "Bar La Esquina")
        login = await owner.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE owner_account SET email_verified_at = now() WHERE email = :e"),
                {"e": EMAIL},
            )
            code = (
                await connection.execute(text("SELECT public_code FROM establishment"))
            ).scalar_one()
        assert (await owner.post(SESSION_URL)).status_code == 201

        def visitor() -> httpx2.AsyncClient:
            # Otro navegador: el mismo origen y la cabecera de la SPA, sin la cookie del
            # propietario. Se cierra al terminar la prueba.
            phone = httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="https://api",
                headers={"X-MyPlaylist-Client": "web", "Origin": PUBLIC_BASE_URL},
            )
            stack.push_async_callback(phone.aclose)
            return phone

        yield Ctx(owner=owner, app=app, engine=engine, code=code.strip(), visitor=visitor)


async def _rows(ctx: Ctx, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        result = await connection.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


async def _arrive(ctx: Ctx) -> httpx2.AsyncClient:
    """Un cliente que abre la página del QR: recibe la cookie de su dispositivo."""
    phone = ctx.visitor()
    assert (await phone.get(ctx.url("music"))).status_code == 200
    return phone


async def _request(phone: httpx2.AsyncClient, ctx: Ctx, ref: str) -> httpx2.Response:
    return await phone.post(ctx.url("requests"), json={"ref": ref})


async def test_F003_R001_get_music_con_la_sesion_abierta_sin_sesion_iniciada(ctx: Ctx) -> None:
    phone = ctx.visitor()

    response = await phone.get(ctx.url("music"))

    assert response.status_code == 200
    assert response.json() == {
        "status": "open",
        "now_playing": None,
        "mine": [],
        "quota": {"limit": QUOTA, "free": QUOTA},
    }
    # Sin pedir ningún dato: no hay cookie de sesión del propietario.
    assert "mp_session" not in phone.cookies


async def test_F003_R002_get_music_emite_la_cookie_con_path_httponly_y_secure(ctx: Ctx) -> None:
    phone = ctx.visitor()

    first = await phone.get(ctx.url("music"))

    cookie = first.headers["set-cookie"]
    assert cookie.startswith("mp_device=")
    assert f"Path=/api/public/establishments/{ctx.code}/" in cookie
    for attribute in ("HttpOnly", "Secure", "SameSite=lax", "Max-Age=31536000"):
        assert attribute in cookie, attribute
    # Con una cookie válida no se emite otra: es el mismo dispositivo.
    again = await phone.get(ctx.url("music"))
    assert "set-cookie" not in again.headers


async def test_F003_R002_con_la_misma_cookie_se_ven_las_mismas_pendientes(ctx: Ctx) -> None:
    phone = await _arrive(ctx)
    for ref in ("fake:rock-1", "fake:rock-2"):
        assert (await _request(phone, ctx, ref)).status_code == 201

    # Cierra la página y vuelve a abrirla en el mismo navegador: la misma cookie.
    reopened = ctx.visitor()
    reopened.cookies = phone.cookies
    state = (await reopened.get(ctx.url("music"))).json()

    assert [track["title"] for track in state["mine"]] == ["Canción 1 de rock", "Canción 2 de rock"]
    assert state["quota"] == {"limit": QUOTA, "free": QUOTA - 2}
    # Otro móvil es otro dispositivo, con su cupo completo.
    other = (await ctx.visitor().get(ctx.url("music"))).json()
    assert (other["mine"], other["quota"]["free"]) == ([], QUOTA)


async def test_F003_R003_search_devuelve_titulo_autor_y_ref(ctx: Ctx) -> None:
    phone = await _arrive(ctx)

    response = await phone.get(ctx.url("search"), params={"q": "rock"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 5
    assert results[0] == {
        "ref": "fake:rock-1",
        "title": "Canción 1 de rock",
        "author": "Catálogo falso",
    }
    # Sin coincidencias, una lista vacía; un texto vacío o demasiado largo no se busca.
    nothing = await phone.get(ctx.url("search"), params={"q": "nada"})
    assert nothing.json() == {"results": []}
    for invalid in ("   ", "x" * 101):
        rejected = await phone.get(ctx.url("search"), params={"q": invalid})
        assert (rejected.status_code, rejected.json()) == (422, {"errors": {"q": "invalid"}})


async def test_F003_R005_post_requests_da_201_con_el_cupo(ctx: Ctx) -> None:
    phone = await _arrive(ctx)

    response = await _request(phone, ctx, "fake:rock-1")

    assert response.status_code == 201
    body = response.json()
    assert [track["title"] for track in body["mine"]] == ["Canción 1 de rock"]
    assert body["quota"] == {"limit": QUOTA, "free": QUOTA - 1}
    rows = await _rows(ctx, "SELECT track_ref, title, requested_by FROM queue_item")
    assert [(row["track_ref"], row["title"]) for row in rows] == [
        ("fake:rock-1", "Canción 1 de rock")
    ]
    assert rows[0]["requested_by"] is not None


async def test_F003_R006_post_requests_con_el_cupo_lleno_da_409_quota_exceeded(ctx: Ctx) -> None:
    phone = await _arrive(ctx)
    for number in range(1, QUOTA + 1):
        assert (await _request(phone, ctx, f"fake:rock-{number}")).status_code == 201

    response = await _request(phone, ctx, "fake:jazz-1")

    assert (response.status_code, response.json()) == (409, {"error": "quota_exceeded"})
    assert len(await _rows(ctx, "SELECT id FROM queue_item")) == QUOTA


async def test_F003_R008_con_la_sesion_cerrada_music_da_closed_y_search_y_requests_409(
    ctx: Ctx,
) -> None:
    phone = await _arrive(ctx)
    assert (await ctx.owner.delete(SESSION_URL)).status_code == 204

    music = await phone.get(ctx.url("music"))
    search = await phone.get(ctx.url("search"), params={"q": "rock"})
    requested = await _request(phone, ctx, "fake:rock-1")

    assert music.json() == {
        "status": "closed",
        "now_playing": None,
        "mine": [],
        "quota": {"limit": QUOTA, "free": QUOTA},
    }
    assert (search.status_code, search.json()) == (409, {"error": "no_open_session"})
    assert (requested.status_code, requested.json()) == (409, {"error": "no_open_session"})
    assert await _rows(ctx, "SELECT id FROM queue_item") == []


async def test_F003_R009_post_requests_de_una_pendiente_da_409_already_queued(ctx: Ctx) -> None:
    first, second = await _arrive(ctx), await _arrive(ctx)
    assert (await _request(first, ctx, "fake:rock-1")).status_code == 201

    response = await _request(second, ctx, "fake:rock-1")

    assert (response.status_code, response.json()) == (409, {"error": "already_queued"})
    state = (await second.get(ctx.url("music"))).json()
    assert state["quota"]["free"] == QUOTA
    assert len(await _rows(ctx, "SELECT id FROM queue_item")) == 1


async def test_F003_R014_post_requests_de_una_cancion_no_disponible_da_422_sin_gastar_cupo(
    ctx: Ctx,
) -> None:
    phone = await _arrive(ctx)

    response = await _request(phone, ctx, "fake:retirada-1")

    assert (response.status_code, response.json()) == (422, {"error": "unknown_track"})
    assert (await phone.get(ctx.url("music"))).json()["quota"]["free"] == QUOTA
    assert await _rows(ctx, "SELECT id FROM queue_item") == []


async def test_F003_R014_una_referencia_de_mas_de_64_caracteres_da_422_sin_consultar_al_catalogo(
    ctx: Ctx,
) -> None:
    phone = await _arrive(ctx)

    # Es la validación de la entrada, antes de la ruta: el catálogo ni se consulta.
    response = await _request(phone, ctx, "fake:" + "x" * 60)

    assert (response.status_code, response.json()) == (422, {"errors": {"ref": "invalid"}})
    assert (await _request(phone, ctx, "")).status_code == 422
    assert await _rows(ctx, "SELECT id FROM queue_item") == []


async def test_F003_R010_music_refleja_la_cancion_que_empieza_a_sonar(ctx: Ctx) -> None:
    phone = await _arrive(ctx)
    for ref in ("fake:rock-1", "fake:rock-2"):
        await _request(phone, ctx, ref)

    # El reproductor del local se pone en marcha y empieza la primera.
    assert (await ctx.owner.post(f"{SESSION_URL}/player")).status_code == 200
    state = (await phone.get(ctx.url("music"))).json()

    assert state["now_playing"] == {"title": "Canción 1 de rock"}
    assert [track["title"] for track in state["mine"]] == ["Canción 2 de rock"]
    assert state["quota"]["free"] == QUOTA - 1


async def test_F003_R012_search_con_el_proveedor_caido_da_503(ctx: Ctx) -> None:
    phone = await _arrive(ctx)

    response = await phone.get(ctx.url("search"), params={"q": "caído"})

    assert (response.status_code, response.json()) == (503, {"error": "search_unavailable"})
    assert await _rows(ctx, "SELECT id FROM queue_item") == []
    assert (await phone.get(ctx.url("music"))).json()["quota"]["free"] == QUOTA


async def test_F003_R012_post_requests_con_el_proveedor_caido_da_503(ctx: Ctx) -> None:
    # Al pedir, el catálogo no puede validar la canción (el falso nunca falla al
    # consultar: se sustituye por uno que no responde).
    async def unavailable(establishment_id: UUID, ref: str) -> CatalogTrack | None:
        raise CatalogUnavailable

    current: RequestTrack = ctx.app.state.request_track
    ctx.app.state.request_track = replace(current, lookup=unavailable)
    phone = await _arrive(ctx)

    response = await _request(phone, ctx, "fake:rock-1")

    assert (response.status_code, response.json()) == (503, {"error": "search_unavailable"})
    assert await _rows(ctx, "SELECT id FROM queue_item") == []
    assert (await phone.get(ctx.url("music"))).json()["quota"]["free"] == QUOTA


async def test_F003_R013_search_11_en_un_minuto_da_429_con_retry_after(ctx: Ctx) -> None:
    phone = await _arrive(ctx)
    for _ in range(10):
        assert (await phone.get(ctx.url("search"), params={"q": "rock"})).status_code == 200

    response = await phone.get(ctx.url("search"), params={"q": "rock"})

    assert (response.status_code, response.json()) == (429, {"error": "too_many_searches"})
    assert 1 <= int(response.headers["retry-after"]) <= 60
    # El límite es de cada dispositivo: otro móvil sigue buscando.
    other = await _arrive(ctx)
    assert (await other.get(ctx.url("search"), params={"q": "rock"})).status_code == 200


async def test_F003_R001_codigo_inexistente_da_404_en_todas_las_rutas(ctx: Ctx) -> None:
    phone = await _arrive(ctx)

    for code in ("ZZZZZZZZZZ", "abc", ctx.code + "X"):
        for response in (
            await phone.get(ctx.url("music", code)),
            await phone.get(ctx.url("search", code), params={"q": "rock"}),
            await phone.post(ctx.url("requests", code), json={"ref": "fake:rock-1"}),
        ):
            assert (response.status_code, response.json()) == (404, {"error": "not_found"}), code
    assert await _rows(ctx, "SELECT id FROM queue_item") == []


async def test_F003_R002_sin_cookie_search_y_requests_dan_401_device_required(ctx: Ctx) -> None:
    phone = ctx.visitor()

    search = await phone.get(ctx.url("search"), params={"q": "rock"})
    requested = await _request(phone, ctx, "fake:rock-1")
    # Una cookie alterada tampoco vale.
    phone.cookies.set("mp_device", "alterada.firma", path=f"/api/public/establishments/{ctx.code}/")
    tampered = await _request(phone, ctx, "fake:rock-1")

    for response in (search, requested, tampered):
        assert (response.status_code, response.json()) == (401, {"error": "device_required"})
    assert await _rows(ctx, "SELECT id FROM queue_item") == []


async def test_F003_R010_post_realtime_ticket_da_un_ticket_client_del_establecimiento(
    ctx: Ctx,
) -> None:
    phone = await _arrive(ctx)
    [row] = await _rows(ctx, "SELECT establishment_id FROM establishment")

    response = await phone.post(ctx.url("realtime-ticket"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["expires_in"] == 60
    claims = verify_ticket(
        ctx.app.state.settings.realtime_ticket_secret, body["ticket"], datetime.now(UTC)
    )
    # Un ticket de cliente, para la sala de este establecimiento (R011).
    assert (claims.role, claims.establishment_id) == (TicketRole.CLIENT, row["establishment_id"])

    # Sin la cookie del dispositivo no hay ticket; con un código inexistente, 404.
    without_cookie = await ctx.visitor().post(ctx.url("realtime-ticket"))
    assert (without_cookie.status_code, without_cookie.json()) == (
        401,
        {"error": "device_required"},
    )
    missing = await phone.post(ctx.url("realtime-ticket", "ZZZZZZZZZZ"))
    assert (missing.status_code, missing.json()) == (404, {"error": "not_found"})
