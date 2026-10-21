"""Rutas /api/owner/music-session contra la API real (plan Contratos de la feature 002)."""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from tests.integration.api import api_client, api_settings, register

pytestmark = pytest.mark.anyio

EMAIL = "a@ejemplo.com"
PASSWORD = "contraseña-segura"
SESSION_URL = "/api/owner/music-session"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine  # superusuario, para preparar y comprobar sin RLS
    redis_url: str


async def _sql(ctx: Ctx, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with ctx.engine.begin() as connection:
        result = await connection.execute(text(sql), params)
        return [dict(row._mapping) for row in result] if result.returns_rows else []


async def _verify_email(ctx: Ctx) -> None:
    await _sql(ctx, "UPDATE owner_account SET email_verified_at = now() WHERE email = :e", e=EMAIL)


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    settings = api_settings(database_url)
    async with api_client(create_app(settings)) as client:
        await register(client, EMAIL, PASSWORD, "Bar La Esquina")
        login = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200
        yield Ctx(client=client, engine=engine, redis_url=settings.redis_url)


async def test_F002_R001_post_abre_la_sesion_201(ctx: Ctx) -> None:
    await _verify_email(ctx)
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")
    channel = f"est:{establishment['id']}"
    redis = Redis.from_url(ctx.redis_url)
    try:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            response = await ctx.client.post(SESSION_URL)
            async with asyncio.timeout(2):
                message = None
                while message is None:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    finally:
        await redis.aclose()

    assert response.status_code == 201
    session = response.json()["session"]
    assert (session["now_playing"], session["player_active"], session["failures"]) == (
        None,
        False,
        [],
    )
    assert json.loads(message["data"])["type"] == "session.opened"

    state = await ctx.client.get(SESSION_URL)
    assert state.status_code == 200
    assert state.json() == {"status": "open", "session": session}


async def test_F002_R002_correo_sin_verificar_da_403_y_sigue_cerrada(ctx: Ctx) -> None:
    response = await ctx.client.post(SESSION_URL)

    assert response.status_code == 403
    assert response.json() == {"error": "email_not_verified"}
    assert await _sql(ctx, "SELECT id FROM music_session") == []
    assert (await ctx.client.get(SESSION_URL)).json() == {"status": "closed", "session": None}


async def test_F002_R003_post_con_sesion_abierta_da_200_sin_vaciar_la_cola(ctx: Ctx) -> None:
    await _verify_email(ctx)
    first = await ctx.client.post(SESSION_URL)
    session_id = first.json()["session"]["id"]
    await _sql(
        ctx,
        "INSERT INTO queue_item (establishment_id, session_id, position, track_ref, title) "
        "SELECT establishment_id, id, p, 'fake:3s', 'Canción ' || p "
        "FROM music_session, generate_series(1, 2) AS p",
    )

    again = await ctx.client.post(SESSION_URL)

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["session"]["id"] == session_id
    assert len(await _sql(ctx, "SELECT id FROM music_session")) == 1
    states = await _sql(ctx, "SELECT state::text AS state FROM queue_item")
    assert [row["state"] for row in states] == ["pending", "pending"]


async def test_F002_R011_delete_cierra_y_es_idempotente(ctx: Ctx) -> None:
    await _verify_email(ctx)
    opened = await ctx.client.post(SESSION_URL)
    assert opened.status_code == 201

    closed = await ctx.client.delete(SESSION_URL)
    again = await ctx.client.delete(SESSION_URL)

    assert (closed.status_code, again.status_code) == (204, 204)
    [row] = await _sql(ctx, "SELECT closed_at FROM music_session")
    assert row["closed_at"] is not None
    assert (await ctx.client.get(SESSION_URL)).json() == {"status": "closed", "session": None}


async def test_F002_R013_sin_sesion_iniciada_da_401(ctx: Ctx) -> None:
    await _verify_email(ctx)
    ctx.client.cookies.clear()

    responses = [
        await ctx.client.post(SESSION_URL),
        await ctx.client.delete(SESSION_URL),
        await ctx.client.get(SESSION_URL),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert await _sql(ctx, "SELECT id FROM music_session") == []


async def test_get_music_session_sigue_el_contrato(ctx: Ctx) -> None:
    await _verify_email(ctx)
    await ctx.client.post(SESSION_URL)
    await _sql(
        ctx,
        "INSERT INTO queue_item (establishment_id, session_id, position, track_ref, title, "
        "state, failure_reason, finished_at) "
        "SELECT establishment_id, id, 1, 'fake:error', 'Retirada', 'skipped', 'not_embeddable', now() "  # noqa: E501
        "FROM music_session",
    )
    await _sql(
        ctx,
        "INSERT INTO queue_item (establishment_id, session_id, position, track_ref, title, state) "
        "SELECT establishment_id, id, 2, 'fake:3s', 'Sonando', 'playing' FROM music_session",
    )

    body = (await ctx.client.get(SESSION_URL)).json()

    assert body["status"] == "open"
    session = body["session"]
    assert set(session) == {
        "id",
        "opened_at",
        "version",
        "now_playing",
        "player_active",
        "failures",
    }
    assert set(session["now_playing"]) == {"item_id", "title", "track_ref"}
    assert session["now_playing"]["title"] == "Sonando"
    assert [failure["title"] for failure in session["failures"]] == ["Retirada"]
    assert set(session["failures"][0]) == {"title", "failed_at"}
