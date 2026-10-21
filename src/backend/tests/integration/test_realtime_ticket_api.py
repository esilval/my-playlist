"""POST /api/owner/realtime-ticket contra la API real (ADR-0014, plan Contratos)."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import httpx2
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from app.shared.config import Settings
from app.shared.realtime_ticket import verify_ticket
from tests.integration.api import api_client, api_settings, register

pytestmark = pytest.mark.anyio

TICKET_URL = "/api/owner/realtime-ticket"
PASSWORD = "contraseña-segura"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine
    settings: Settings


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    settings = api_settings(database_url)
    async with api_client(create_app(settings)) as client:
        await register(client, "b@ejemplo.com", PASSWORD, "Café Ñandú")
        await register(client, "a@ejemplo.com", PASSWORD, "Bar La Esquina")
        login = await client.post(
            "/api/auth/login", json={"email": "a@ejemplo.com", "password": PASSWORD}
        )
        assert login.status_code == 200
        yield Ctx(client=client, engine=engine, settings=settings)


async def _establishment(ctx: Ctx, name: str) -> UUID:
    async with ctx.engine.connect() as connection:
        found = await connection.execute(
            text("SELECT id FROM establishment WHERE name = :n"), {"n": name}
        )
        establishment_id: UUID = found.scalar_one()
        return establishment_id


async def test_F002_R013_ticket_lleva_el_establecimiento_de_la_sesion(ctx: Ctx) -> None:
    own = await _establishment(ctx, "Bar La Esquina")
    other = await _establishment(ctx, "Café Ñandú")

    # Aunque el cuerpo diga otro establecimiento, el ticket lleva el de la sesión.
    response = await ctx.client.post(
        TICKET_URL, json={"role": "owner", "establishment_id": str(other)}
    )

    assert response.status_code == 200
    claims = verify_ticket(
        ctx.settings.realtime_ticket_secret, response.json()["ticket"], datetime.now(UTC)
    )
    assert claims.establishment_id == own != other


async def test_F002_R014_post_realtime_ticket_200_con_rol_owner_o_player(ctx: Ctx) -> None:
    for role in ("owner", "player"):
        response = await ctx.client.post(TICKET_URL, json={"role": role})

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"ticket", "expires_in"}
        assert body["expires_in"] == 60
        assert response.headers["cache-control"] == "no-store"
        claims = verify_ticket(
            ctx.settings.realtime_ticket_secret, body["ticket"], datetime.now(UTC)
        )
        assert str(claims.role) == role

    assert (await ctx.client.post(TICKET_URL, json={"role": "client"})).status_code == 422
    ctx.client.cookies.clear()
    assert (await ctx.client.post(TICKET_URL, json={"role": "owner"})).status_code == 401
