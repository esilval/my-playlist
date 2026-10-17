from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio

EMAIL = "dueno@ejemplo.com"
PASSWORD = "contraseña-segura"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, EMAIL, PASSWORD, "Bar La Esquina")
        yield Ctx(client=client, engine=engine)


async def _login(ctx: Ctx, email: str = EMAIL, password: str = PASSWORD) -> httpx2.Response:
    return await ctx.client.post("/api/auth/login", json={"email": email, "password": password})


async def _scalar(ctx: Ctx, sql: str) -> object:
    async with ctx.engine.connect() as connection:
        return (await connection.execute(text(sql))).scalar_one()


async def test_F001_R005_login_correcto_da_acceso_al_panel(ctx: Ctx) -> None:
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401

    response = await _login(ctx)

    assert response.status_code == 200
    assert response.json() == {"status": "authenticated"}
    panel = await ctx.client.get("/api/owner/_probe")
    assert panel.status_code == 200
    assert panel.json()["establishment_id"] == str(
        await _scalar(ctx, "SELECT establishment_id FROM owner_account")
    )


async def test_F001_R023_registro_y_login_posterior_entra_al_panel(ctx: Ctx) -> None:
    await register(ctx.client, "otra@ejemplo.com", "otra-contraseña", "Café Ñandú")

    assert (await _login(ctx, " OTRA@ejemplo.com ", "otra-contraseña")).status_code == 200
    panel = (await ctx.client.get("/api/owner/_probe")).json()

    async with ctx.engine.connect() as connection:
        own = (
            await connection.execute(
                text(
                    "SELECT e.id, e.name FROM establishment e JOIN owner_account a "
                    "ON a.establishment_id = e.id WHERE a.email_normalized = 'otra@ejemplo.com'"
                )
            )
        ).all()
    assert [(str(row.id), row.name) for row in own] == [(panel["establishment_id"], "Café Ñandú")]
    # Con el correo sin verificar también entra (F001-R019).
    assert panel["email_verified"] is False


async def test_F001_R006_mismo_401_para_password_erronea_y_correo_inexistente(ctx: Ctx) -> None:
    wrong_password = await _login(ctx, password="no-es-esta")
    unknown_email = await _login(ctx, email="nadie@ejemplo.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.content == unknown_email.content == b'{"error":"invalid_credentials"}'
    assert "set-cookie" not in wrong_password.headers
    assert "set-cookie" not in unknown_email.headers


async def test_F001_R007_sexto_intento_da_429_aun_con_password_correcta(ctx: Ctx) -> None:
    for _ in range(5):
        assert (await _login(ctx, password="no-es-esta")).status_code == 401

    blocked = await _login(ctx)

    assert blocked.status_code == 429
    assert blocked.json() == {"error": "too_many_attempts"}
    assert "set-cookie" not in blocked.headers
    # Los intentos rechazados por el bloqueo no cuentan como fallos (D5).
    assert await _scalar(ctx, "SELECT count(*) FROM login_attempt WHERE NOT succeeded") == 5


async def test_F001_R007_pasados_15_min_la_correcta_vuelve_a_entrar(ctx: Ctx) -> None:
    for _ in range(5):
        await _login(ctx, password="no-es-esta")
    assert (await _login(ctx)).status_code == 429

    async with ctx.engine.begin() as connection:
        await connection.execute(
            text("UPDATE login_attempt SET attempted_at = attempted_at - interval '15 minutes'")
        )

    assert (await _login(ctx)).status_code == 200


async def test_cookie_httponly_secure_y_hsts(ctx: Ctx) -> None:
    response = await _login(ctx)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith("mp_session=")
    for flag in ("HttpOnly", "Secure", "SameSite=lax", "Path=/api"):
        assert flag.lower() in cookie.lower(), flag
    assert "max-age" not in cookie.lower()
    assert response.headers["strict-transport-security"].startswith("max-age=")


async def test_csrf_post_sin_cabecera_o_con_origin_ajeno_da_403(ctx: Ctx) -> None:
    body = {"email": EMAIL, "password": PASSWORD}
    transport = ctx.client._transport
    async with httpx2.AsyncClient(transport=transport, base_url="https://api") as bare:
        without_header = await bare.post("/api/auth/login", json=body)
        foreign_origin = await bare.post(
            "/api/auth/login",
            json=body,
            headers={"X-MyPlaylist-Client": "web", "Origin": "https://malicioso.example"},
        )

    assert without_header.status_code == foreign_origin.status_code == 403
    assert without_header.json() == {"error": "csrf"}
    assert await _scalar(ctx, "SELECT count(*) FROM owner_session") == 0


async def test_F001_R007_intentos_en_paralelo_no_superan_el_bloqueo(ctx: Ctx) -> None:
    import asyncio

    results = await asyncio.gather(*(_login(ctx, password="no-es-esta") for _ in range(8)))

    assert sorted(r.status_code for r in results) == [401] * 5 + [429] * 3
    assert await _scalar(ctx, "SELECT count(*) FROM login_attempt WHERE NOT succeeded") == 5
