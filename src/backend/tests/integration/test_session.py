from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.integration.api import api_client, build_app_with_probe, register

pytestmark = pytest.mark.anyio


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    async with api_client(build_app_with_probe(database_url)) as client:
        await register(client, "dueno@ejemplo.com", "contraseña-segura", "Bar La Esquina")
        login = await client.post(
            "/api/auth/login",
            json={"email": "dueno@ejemplo.com", "password": "contraseña-segura"},
        )
        assert login.status_code == 200
        yield Ctx(client=client, engine=engine)


async def _set_last_seen(ctx: Ctx, ago: timedelta) -> None:
    async with ctx.engine.begin() as connection:
        await connection.execute(
            text("UPDATE owner_session SET last_seen_at = now() - CAST(:ago AS interval)"),
            {"ago": ago},
        )


async def test_F001_R008_logout_revoca_la_sesion(ctx: Ctx) -> None:
    token = ctx.client.cookies["mp_session"]
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 200

    response = await ctx.client.post("/api/auth/logout")

    assert response.status_code == 204
    cleared = response.headers["set-cookie"].lower()
    assert cleared.startswith('mp_session=""') and "max-age=0" in cleared
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401
    # Aunque alguien conserve la cookie, la sesión está revocada en el servidor.
    ctx.client.cookies.set("mp_session", token)
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401
    async with ctx.engine.connect() as connection:
        revoked = await connection.execute(text("SELECT revoked_at FROM owner_session"))
        assert revoked.scalar_one() is not None


async def test_F001_R008_logout_sin_sesion_no_falla(ctx: Ctx) -> None:
    ctx.client.cookies.clear()
    assert (await ctx.client.post("/api/auth/logout")).status_code == 204


async def test_F001_R020_sesion_inactiva_12h_da_401(ctx: Ctx) -> None:
    await _set_last_seen(ctx, timedelta(hours=12, minutes=1))

    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401


async def test_F001_R020_casi_12h_inactiva_sigue_abierta(ctx: Ctx) -> None:
    await _set_last_seen(ctx, timedelta(hours=11, minutes=59))

    assert (await ctx.client.get("/api/owner/_probe")).status_code == 200


async def test_F001_R020_cada_peticion_actualiza_last_seen(ctx: Ctx) -> None:
    await _set_last_seen(ctx, timedelta(hours=11))

    assert (await ctx.client.get("/api/owner/_probe")).status_code == 200

    async with ctx.engine.connect() as connection:
        last_seen = (
            await connection.execute(text("SELECT last_seen_at FROM owner_session"))
        ).scalar_one()
    assert datetime.now(UTC) - last_seen < timedelta(seconds=5)
    # Renovada: otras 11 h más tarde seguiría abierta.
    await _set_last_seen(ctx, timedelta(hours=11))
    assert (await ctx.client.get("/api/owner/_probe")).status_code == 200


async def test_F001_R015_cookie_alterada_da_401(ctx: Ctx) -> None:
    ctx.client.cookies.clear()
    ctx.client.cookies.set("mp_session", "inventada")

    assert (await ctx.client.get("/api/owner/_probe")).status_code == 401
