"""Métricas del reproductor y hora de publicación de los eventos (feature 004, plan D11)."""

import asyncio
import dataclasses
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.main import create_app
from app.sessions.infrastructure.repositories import SqlSessionsUnitOfWork
from app.sessions.interface import EnqueueTrack
from app.shared.metrics import InMemoryMetrics
from tests.integration.api import api_client, api_settings, register

pytestmark = pytest.mark.anyio

EMAIL = "a@ejemplo.com"
PASSWORD = "contraseña-segura"
SESSION_URL = "/api/owner/music-session"
PLAYER_URL = f"{SESSION_URL}/player"
EVENTS_URL = f"{PLAYER_URL}/events"
ADVANCE_URL = f"{PLAYER_URL}/advance"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine  # superusuario, para preparar y comprobar sin RLS
    redis_url: str
    enqueue: EnqueueTrack
    metrics: InMemoryMetrics


async def _sql(ctx: Ctx, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with ctx.engine.begin() as connection:
        result = await connection.execute(text(sql), params)
        return [dict(row._mapping) for row in result] if result.returns_rows else []


async def _enqueue(ctx: Ctx, *titles: str) -> None:
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")
    for title in titles:
        await ctx.enqueue(establishment["id"], f"fake:{title}", title)


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    settings = api_settings(database_url)
    app = create_app(settings)
    metrics = InMemoryMetrics()
    # El mismo caso de uso, con métricas en memoria para poder leerlas.
    app.state.report_player_event = dataclasses.replace(
        app.state.report_player_event, metrics=metrics
    )
    async with api_client(app) as client:
        await register(client, EMAIL, PASSWORD, "Bar La Esquina")
        login = await client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200
        context = Ctx(
            client=client,
            engine=engine,
            redis_url=settings.redis_url,
            enqueue=EnqueueTrack(
                unit_of_work=SqlSessionsUnitOfWork(app.state.db),
                publisher=app.state.event_publisher,
            ),
            metrics=metrics,
        )
        await _sql(
            context, "UPDATE owner_account SET email_verified_at = now() WHERE email = :e", e=EMAIL
        )
        assert (await client.post(SESSION_URL)).status_code == 201
        yield context


async def _report(ctx: Ctx, epoch: int, item: dict[str, Any], type: str, **extra: Any) -> Any:
    response = await ctx.client.post(
        EVENTS_URL, json={"epoch": epoch, "item_id": item["item_id"], "type": type, **extra}
    )
    assert response.status_code == 200
    return response.json()


async def test_F004_R011_started_y_failed_emiten_track_started_y_track_failed(ctx: Ctx) -> None:
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    epoch, a = claim["epoch"], claim["current"]

    await _report(ctx, epoch, a, "started")
    # Un informe repetido (R012 de 002) no vuelve a contar.
    await _report(ctx, epoch, a, "started")
    b = (await _report(ctx, epoch, a, "failed", reason="not_embeddable"))["current"]
    await _report(ctx, epoch, b, "started")

    assert ctx.metrics.values("TrackStarted") == [1, 1]
    assert ctx.metrics.values("TrackFailed") == [1]
    assert all(item.dimensions == {} for item in ctx.metrics.recorded)


async def test_F004_R011_track_gap_mide_desde_el_finished_at_de_la_anterior(ctx: Ctx) -> None:
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    epoch, a = claim["epoch"], claim["current"]
    await _report(ctx, epoch, a, "started")
    b = (await _report(ctx, epoch, a, "ended"))["current"]
    await asyncio.sleep(0.2)

    await _report(ctx, epoch, b, "started")

    [gap] = ctx.metrics.values("TrackGap")
    [row] = await _sql(
        ctx,
        "SELECT EXTRACT(EPOCH FROM b.started_at - a.finished_at) * 1000 AS ms "
        "FROM queue_item a, queue_item b WHERE a.title = 'A' AND b.title = 'B'",
    )
    assert gap == pytest.approx(float(row["ms"]), abs=1)
    assert gap >= 200


async def test_F004_R011_track_gap_no_se_mide_si_la_cola_estaba_vacia_o_la_anterior_se_salto(
    ctx: Ctx,
) -> None:
    # Con la cola vacía: B entra después de que A termine y empieza al avanzar en espera.
    await _enqueue(ctx, "A")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    epoch, a = claim["epoch"], claim["current"]
    await _report(ctx, epoch, a, "started")
    assert (await _report(ctx, epoch, a, "ended"))["current"] is None
    await _enqueue(ctx, "B", "C")
    b = (await ctx.client.post(ADVANCE_URL, json={"epoch": epoch})).json()["current"]
    await _report(ctx, epoch, b, "started")
    # Tras un salto: B falla y C empieza.
    c = (await _report(ctx, epoch, b, "failed", reason="error"))["current"]
    await _report(ctx, epoch, c, "started")

    assert ctx.metrics.values("TrackStarted") == [1, 1, 1]
    assert ctx.metrics.values("TrackGap") == []


async def test_F004_R011_cada_evento_publicado_lleva_published_at(ctx: Ctx) -> None:
    await _enqueue(ctx, "A")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")

    redis = Redis.from_url(ctx.redis_url)
    try:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(f"est:{establishment['id']}")
            before = int(time.time() * 1000)
            await _report(ctx, claim["epoch"], claim["current"], "started")
            async with asyncio.timeout(2):
                message = None
                while message is None:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            after = int(time.time() * 1000)
    finally:
        await redis.aclose()

    event = json.loads(message["data"])
    assert event["type"] == "track.started"
    assert isinstance(event["published_at"], int)
    assert before <= event["published_at"] <= after


async def test_F004_R011_track_gap_no_se_mide_tras_una_toma_de_control(ctx: Ctx) -> None:
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    epoch, a = claim["epoch"], claim["current"]
    await _report(ctx, epoch, a, "started")
    b = (await _report(ctx, epoch, a, "ended"))["current"]
    await _report(ctx, epoch, b, "started")
    assert len(ctx.metrics.values("TrackGap")) == 1
    await asyncio.sleep(0.2)

    # Otro equipo toma el control a mitad de B (o se recarga la página): B vuelve a empezar.
    takeover = (await ctx.client.post(PLAYER_URL)).json()
    assert takeover["current"]["title"] == "B"
    await _report(ctx, takeover["epoch"], takeover["current"], "started")

    # El reinicio cuenta como inicio, pero no como hueco entre canciones.
    assert ctx.metrics.values("TrackStarted") == [1, 1, 1]
    assert len(ctx.metrics.values("TrackGap")) == 1


async def test_F004_R011_la_puesta_en_marcha_guarda_player_claimed_at(ctx: Ctx) -> None:
    [before] = await _sql(ctx, "SELECT player_claimed_at FROM music_session")
    assert before["player_claimed_at"] is None

    await ctx.client.post(PLAYER_URL)
    [first] = await _sql(ctx, "SELECT player_claimed_at, now() AS db_now FROM music_session")
    await ctx.client.post(PLAYER_URL)
    [second] = await _sql(ctx, "SELECT player_claimed_at FROM music_session")

    assert first["player_claimed_at"] is not None
    assert abs((first["db_now"] - first["player_claimed_at"]).total_seconds()) < 5
    assert second["player_claimed_at"] > first["player_claimed_at"]


async def test_F004_R011_track_gap_no_se_mide_si_el_reproductor_vuelve_tras_una_ausencia(
    ctx: Ctx,
) -> None:
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    epoch, a = claim["epoch"], claim["current"]
    await _report(ctx, epoch, a, "started")
    await _report(ctx, epoch, a, "ended")
    # El reproductor desaparece antes de empezar B y vuelve más tarde.
    await asyncio.sleep(0.2)
    back = (await ctx.client.post(PLAYER_URL)).json()
    await _report(ctx, back["epoch"], back["current"], "started")

    assert ctx.metrics.values("TrackStarted") == [1, 1]
    assert ctx.metrics.values("TrackGap") == []
