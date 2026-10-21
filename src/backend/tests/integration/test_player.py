"""Rutas del reproductor contra la API real (plan Contratos de la feature 002, D3)."""

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
from app.sessions.infrastructure.repositories import SqlSessionsUnitOfWork
from app.sessions.interface import EnqueueTrack
from tests.integration.api import api_client, api_settings, register

pytestmark = pytest.mark.anyio

EMAIL = "a@ejemplo.com"
PASSWORD = "contraseña-segura"
SESSION_URL = "/api/owner/music-session"
PLAYER_URL = f"{SESSION_URL}/player"
HEARTBEAT_URL = f"{PLAYER_URL}/heartbeat"
EVENTS_URL = f"{PLAYER_URL}/events"


@dataclass
class Ctx:
    client: httpx2.AsyncClient
    engine: AsyncEngine  # superusuario, para preparar y comprobar sin RLS
    redis_url: str
    enqueue: EnqueueTrack


async def _sql(ctx: Ctx, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with ctx.engine.begin() as connection:
        result = await connection.execute(text(sql), params)
        return [dict(row._mapping) for row in result] if result.returns_rows else []


async def _enqueue(ctx: Ctx, *titles: str) -> None:
    """Agrega canciones al final de la cola con el caso de uso de C2 (T008), con la
    misma base y el mismo publicador que la app."""
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")
    for title in titles:
        await ctx.enqueue(establishment["id"], f"fake:{title}", title)


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    settings = api_settings(database_url)
    app = create_app(settings)
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
        )
        await _sql(
            context, "UPDATE owner_account SET email_verified_at = now() WHERE email = :e", e=EMAIL
        )
        yield context


async def _open(ctx: Ctx) -> None:
    assert (await ctx.client.post(SESSION_URL)).status_code == 201


async def test_F002_R004_poner_en_marcha_devuelve_la_primera_pendiente(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B", "C")

    response = await ctx.client.post(PLAYER_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["epoch"] == 1
    assert (body["current"]["title"], body["next"]["title"]) == ("A", "B")
    assert set(body["current"]) == {"item_id", "title", "track_ref"}
    assert body["current"]["track_ref"] == "fake:A"
    states = await _sql(ctx, "SELECT title, state::text AS state FROM queue_item ORDER BY position")
    assert [(row["title"], row["state"]) for row in states] == [
        ("A", "playing"),
        ("B", "pending"),
        ("C", "pending"),
    ]


async def test_F002_R009_sin_sesion_abierta_da_409_no_open_session(ctx: Ctx) -> None:
    response = await ctx.client.post(PLAYER_URL)

    assert response.status_code == 409
    assert response.json() == {"error": "no_open_session"}
    beat = await ctx.client.post(HEARTBEAT_URL, json={"epoch": 1})
    assert (beat.status_code, beat.json()) == (409, {"error": "no_open_session"})


async def test_F002_R010_segunda_puesta_en_marcha_supera_a_la_primera(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A")
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")
    first = (await ctx.client.post(PLAYER_URL)).json()

    redis = Redis.from_url(ctx.redis_url)
    try:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(f"est:{establishment['id']}")
            second = (await ctx.client.post(PLAYER_URL)).json()
            async with asyncio.timeout(2):
                message = None
                while message is None:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    finally:
        await redis.aclose()

    assert (first["epoch"], second["epoch"]) == (1, 2)
    event = json.loads(message["data"])
    assert (event["type"], event["epoch"]) == ("player.claimed", 2)

    stale = await ctx.client.post(HEARTBEAT_URL, json={"epoch": first["epoch"]})
    assert (stale.status_code, stale.json()) == (409, {"error": "player_superseded"})
    current = await ctx.client.post(HEARTBEAT_URL, json={"epoch": second["epoch"]})
    assert current.status_code == 200


async def test_F002_R010_nuevo_reproductor_recibe_la_cancion_que_sonaba(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B")
    first = (await ctx.client.post(PLAYER_URL)).json()
    # A empezó a sonar en el primer reproductor (su informe `started` llega con T007).
    await _sql(ctx, "UPDATE queue_item SET started_at = now() WHERE title = 'A'")

    second = (await ctx.client.post(PLAYER_URL)).json()

    # A seguía sonando: la recibe el nuevo para empezarla desde el principio.
    assert second["current"] == first["current"]
    assert second["next"]["title"] == "B"
    [a] = await _sql(
        ctx, "SELECT state::text AS state, started_at FROM queue_item WHERE title = 'A'"
    )
    # Vuelve a empezar: su inicio real lo informará el nuevo reproductor.
    assert (a["state"], a["started_at"]) == ("playing", None)


async def test_F002_R014_player_active_segun_el_latido(ctx: Ctx) -> None:
    await _open(ctx)
    claim = (await ctx.client.post(PLAYER_URL)).json()

    async def active() -> bool:
        state = (await ctx.client.get(SESSION_URL)).json()
        return bool(state["session"]["player_active"])

    assert await active() is True
    # El plan (D3) cuenta como activo un latido de hace menos de 45 s: se prueba a
    # ambos lados del límite.
    await _sql(ctx, "UPDATE music_session SET player_seen_at = now() - interval '44 seconds'")
    assert await active() is True
    await _sql(ctx, "UPDATE music_session SET player_seen_at = now() - interval '46 seconds'")
    assert await active() is False

    beat = await ctx.client.post(HEARTBEAT_URL, json={"epoch": claim["epoch"]})
    assert beat.status_code == 200
    assert await active() is True


async def test_F002_R014_latido_mantiene_viva_la_sesion_iniciada(ctx: Ctx) -> None:
    await _open(ctx)
    claim = (await ctx.client.post(PLAYER_URL)).json()
    # La sesión iniciada lleva 11 h sin actividad: a 1 h de caducar (feature 001).
    await _sql(ctx, "UPDATE owner_session SET last_seen_at = now() - interval '11 hours'")

    beat = await ctx.client.post(HEARTBEAT_URL, json={"epoch": claim["epoch"]})

    assert beat.status_code == 200
    [row] = await _sql(
        ctx, "SELECT now() - last_seen_at < interval '1 minute' AS fresh FROM owner_session"
    )
    assert row["fresh"] is True


async def test_F002_R008_latido_devuelve_la_version_de_la_sesion(ctx: Ctx) -> None:
    await _open(ctx)
    claim = (await ctx.client.post(PLAYER_URL)).json()
    before = (await ctx.client.post(HEARTBEAT_URL, json={"epoch": claim["epoch"]})).json()

    # Entra una canción mientras el reproductor espera: si se perdió queue.changed, el
    # latido muestra que la versión creció y el reproductor pide el estado (D3).
    await _enqueue(ctx, "A")
    after = (await ctx.client.post(HEARTBEAT_URL, json={"epoch": claim["epoch"]})).json()

    state = (await ctx.client.get(SESSION_URL)).json()["session"]
    assert after["version"] == before["version"] + 1 == state["version"]


async def _report(
    ctx: Ctx, epoch: int, item: dict[str, Any], type: str, **extra: Any
) -> httpx2.Response:
    return await ctx.client.post(
        EVENTS_URL, json={"epoch": epoch, "item_id": item["item_id"], "type": type, **extra}
    )


async def _queue_states(ctx: Ctx) -> list[tuple[str, str]]:
    rows = await _sql(ctx, "SELECT title, state::text AS state FROM queue_item ORDER BY position")
    return [(row["title"], row["state"]) for row in rows]


async def test_F002_R005_ended_devuelve_la_siguiente_en_orden(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B", "C")
    claim = (await ctx.client.post(PLAYER_URL)).json()

    after_a = await _report(ctx, claim["epoch"], claim["current"], "ended")
    assert after_a.status_code == 200
    body = after_a.json()
    assert (body["current"]["title"], body["next"]["title"]) == ("B", "C")

    after_b = (await _report(ctx, claim["epoch"], body["current"], "ended")).json()
    assert (after_b["current"]["title"], after_b["next"]) == ("C", None)
    assert after_b["version"] > body["version"]
    assert await _queue_states(ctx) == [("A", "played"), ("B", "played"), ("C", "playing")]


async def test_F002_R006_poner_en_marcha_otra_vez_no_repite_sonadas_ni_saltadas(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B", "C")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    b = (await _report(ctx, claim["epoch"], claim["current"], "ended")).json()["current"]
    failed = await _report(ctx, claim["epoch"], b, "failed", reason="not_embeddable")
    assert failed.status_code == 200
    assert failed.json()["current"]["title"] == "C"

    # Por ejemplo, tras recargar la página del reproductor.
    again = (await ctx.client.post(PLAYER_URL)).json()

    assert (again["current"]["title"], again["next"]) == ("C", None)
    assert await _queue_states(ctx) == [("A", "played"), ("B", "skipped"), ("C", "playing")]


async def test_F002_R007_failed_salta_y_publica_track_failed(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    [establishment] = await _sql(ctx, "SELECT id FROM establishment")

    redis = Redis.from_url(ctx.redis_url)
    try:
        async with redis.pubsub() as pubsub:
            await pubsub.subscribe(f"est:{establishment['id']}")
            response = await _report(
                ctx, claim["epoch"], claim["current"], "failed", reason="not_embeddable"
            )
            async with asyncio.timeout(2):
                message = None
                while message is None:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    finally:
        await redis.aclose()

    assert response.status_code == 200
    assert (response.json()["current"]["title"], response.json()["next"]) == ("B", None)
    event = json.loads(message["data"])
    assert (event["type"], event["title"], event["item_id"]) == (
        "track.failed",
        "A",
        claim["current"]["item_id"],
    )
    [a] = await _sql(
        ctx, "SELECT state::text AS state, failure_reason FROM queue_item WHERE title = 'A'"
    )
    assert (a["state"], a["failure_reason"]) == ("skipped", "not_embeddable")


async def test_F002_R007_la_unica_pendiente_falla_y_queda_en_espera(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A")
    claim = (await ctx.client.post(PLAYER_URL)).json()

    response = await _report(ctx, claim["epoch"], claim["current"], "failed", reason="error")

    assert response.status_code == 200
    assert (response.json()["current"], response.json()["next"]) == (None, None)
    assert await _queue_states(ctx) == [("A", "skipped")]


async def test_F002_R007_motivo_de_mas_de_100_caracteres_da_422(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A")
    claim = (await ctx.client.post(PLAYER_URL)).json()

    response = await _report(ctx, claim["epoch"], claim["current"], "failed", reason="x" * 101)

    assert response.status_code == 422
    assert await _queue_states(ctx) == [("A", "playing")]


async def test_F002_R007_get_music_session_devuelve_el_fallo(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    await _report(ctx, claim["epoch"], claim["current"], "failed", reason="not_embeddable")

    # El panel recarga la página: el aviso de fallo sigue ahí (plan D7).
    session = (await ctx.client.get(SESSION_URL)).json()["session"]

    assert [failure["title"] for failure in session["failures"]] == ["A"]
    assert session["now_playing"]["title"] == "B"


async def test_F002_R010_informe_de_epoca_vieja_da_409_player_superseded(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B")
    first = (await ctx.client.post(PLAYER_URL)).json()
    await ctx.client.post(PLAYER_URL)

    response = await _report(ctx, first["epoch"], first["current"], "ended")

    assert (response.status_code, response.json()) == (409, {"error": "player_superseded"})
    assert await _queue_states(ctx) == [("A", "playing"), ("B", "pending")]


async def test_F002_R011_informe_con_la_sesion_cerrada_da_409_no_open_session(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    assert (await ctx.client.delete(SESSION_URL)).status_code == 204

    response = await _report(ctx, claim["epoch"], claim["current"], "ended")

    assert (response.status_code, response.json()) == (409, {"error": "no_open_session"})
    assert await _queue_states(ctx) == [("A", "played"), ("B", "discarded")]


async def test_F002_R012_informe_reenviado_tras_un_corte_es_idempotente(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A", "B", "C")
    claim = (await ctx.client.post(PLAYER_URL)).json()
    await _report(ctx, claim["epoch"], claim["current"], "started")
    first = (await _report(ctx, claim["epoch"], claim["current"], "ended")).json()

    # Tras un corte, el reproductor reenvía los informes de A que no sabe si llegaron.
    resent = [
        (await _report(ctx, claim["epoch"], claim["current"], type)).json()
        for type in ("started", "ended", "failed")
    ]

    assert all(body == first for body in resent)
    assert (first["current"]["title"], first["next"]["title"]) == ("B", "C")
    assert await _queue_states(ctx) == [("A", "played"), ("B", "playing"), ("C", "pending")]


async def test_F002_R013_informe_de_una_cancion_ajena_da_404(ctx: Ctx) -> None:
    await _open(ctx)
    await _enqueue(ctx, "A")
    claim = (await ctx.client.post(PLAYER_URL)).json()

    response = await _report(
        ctx, claim["epoch"], {"item_id": "00000000-0000-0000-0000-000000000000"}, "ended"
    )

    assert (response.status_code, response.json()) == (404, {"error": "not_found"})
    assert await _queue_states(ctx) == [("A", "playing")]
