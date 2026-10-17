import urllib.parse
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio

EMAIL = "dueno@ejemplo.com"
OLD_PASSWORD = "contraseña-vieja"
NEW_PASSWORD = "contraseña-nueva"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, EMAIL, OLD_PASSWORD, "Bar La Esquina")
        yield Ctx(client=client, engine=engine)


async def _rows(ctx: Ctx, sql: str) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        return [dict(row._mapping) for row in await connection.execute(text(sql))]


async def _request(ctx: Ctx, email: str = EMAIL) -> httpx2.Response:
    return await ctx.client.post("/api/auth/password-reset", json={"email": email})


async def _reset_tokens(ctx: Ctx) -> list[str]:
    messages = await _rows(
        ctx,
        "SELECT payload FROM email_outbox WHERE template = 'password_reset' ORDER BY created_at",
    )
    links = [urllib.parse.urlsplit(m["payload"]["link"]) for m in messages]
    assert all(link.path == "/restablecer" for link in links)
    return [urllib.parse.parse_qs(link.query)["token"][0] for link in links]


async def _confirm(ctx: Ctx, token: str, password: str = NEW_PASSWORD) -> httpx2.Response:
    return await ctx.client.post(
        "/api/auth/password-reset/confirm", json={"token": token, "password": password}
    )


async def _login(client: httpx2.AsyncClient, password: str) -> httpx2.Response:
    return await client.post("/api/auth/login", json={"email": EMAIL, "password": password})


async def test_F001_R016_mismo_202_exista_o_no_la_cuenta(ctx: Ctx) -> None:
    existing = await _request(ctx, " DUENO@ejemplo.com ")
    missing = await _request(ctx, "nadie@ejemplo.com")

    assert existing.status_code == missing.status_code == 202
    assert existing.content == missing.content == b'{"status":"check_email"}'
    assert dict(existing.headers) == dict(missing.headers)
    # Solo la cuenta existente recibe el enlace, en su dirección guardada.
    [message] = await _rows(
        ctx, "SELECT to_address FROM email_outbox WHERE template = 'password_reset'"
    )
    assert message["to_address"] == EMAIL


async def test_F001_R016_enlace_de_un_solo_uso(ctx: Ctx) -> None:
    await _request(ctx)
    [token] = await _reset_tokens(ctx)

    assert (await _confirm(ctx, token)).status_code == 204
    assert (await _login(ctx.client, NEW_PASSWORD)).status_code == 200

    reused = await _confirm(ctx, token, "otra-contraseña-1")
    assert reused.status_code == 400
    assert reused.json() == {"error": "invalid_or_expired_token"}
    assert (await _login(ctx.client, NEW_PASSWORD)).status_code == 200


async def test_F001_R016_enlace_de_mas_de_60_min_se_rechaza(ctx: Ctx) -> None:
    await _request(ctx)
    [token] = await _reset_tokens(ctx)
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE email_token SET expires_at = now() - interval '1 second' "
                "WHERE purpose = 'reset'"
            )
        )

    response = await _confirm(ctx, token)

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_or_expired_token"}
    assert (await _login(ctx.client, OLD_PASSWORD)).status_code == 200


async def test_F001_R016_contrasena_nueva_corta_da_422(ctx: Ctx) -> None:
    await _request(ctx)
    [token] = await _reset_tokens(ctx)

    response = await _confirm(ctx, token, "1234567")

    assert response.status_code == 422
    assert response.json() == {"errors": {"password": "password_too_short"}}
    assert "1234567" not in response.text
    # El enlace sigue sirviendo para un segundo intento con una contraseña válida.
    assert (await _confirm(ctx, token)).status_code == 204


async def test_F001_R021_confirmar_revoca_todas_las_sesiones(ctx: Ctx) -> None:
    transport = ctx.client._transport
    headers = dict(ctx.client.headers)
    async with httpx2.AsyncClient(
        transport=transport, base_url="https://api", headers=headers
    ) as second:
        assert (await _login(ctx.client, OLD_PASSWORD)).status_code == 200
        assert (await _login(second, OLD_PASSWORD)).status_code == 200
        assert (await ctx.client.get("/api/owner/_probe")).status_code == 200
        assert (await second.get("/api/owner/_probe")).status_code == 200

        await _request(ctx)
        [token] = await _reset_tokens(ctx)
        assert (await _confirm(ctx, token)).status_code == 204

        assert (await ctx.client.get("/api/owner/_probe")).status_code == 401
        assert (await second.get("/api/owner/_probe")).status_code == 401
        sessions = await _rows(ctx, "SELECT revoked_at FROM owner_session")
        assert len(sessions) == 2 and all(s["revoked_at"] is not None for s in sessions)
        # Entra con la contraseña nueva.
        assert (await _login(second, NEW_PASSWORD)).status_code == 200


async def test_F001_R021_password_anterior_da_invalid_credentials(ctx: Ctx) -> None:
    await _request(ctx)
    [token] = await _reset_tokens(ctx)
    await _confirm(ctx, token)

    response = await _login(ctx.client, OLD_PASSWORD)

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_credentials"}
