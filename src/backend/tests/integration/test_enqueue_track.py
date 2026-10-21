"""EnqueueTrack (interfaz de C2) y la herramienta de desarrollo, contra PostgreSQL real."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.interface import OwnerContext
from app.sessions import devtools
from app.sessions.application.open_session import OpenMusicSession
from app.sessions.infrastructure.memory_publisher import InMemoryEventPublisher
from app.sessions.infrastructure.repositories import SqlSessionsUnitOfWork
from app.sessions.interface import EnqueueTrack, NoOpenSession
from app.shared.config import Settings
from app.shared.db import Database
from tests.integration.api import api_settings

pytestmark = pytest.mark.anyio

EMAIL = "dueno@ejemplo.com"


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para preparar y comprobar sin RLS
    publisher: InMemoryEventPublisher
    enqueue: EnqueueTrack
    open: OpenMusicSession
    owner: OwnerContext


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    db = Database.from_url(database_url, role="app_api")
    unit_of_work = SqlSessionsUnitOfWork(db)
    publisher = InMemoryEventPublisher()
    establishment_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO establishment (id, establishment_id, public_code, name) "
                "VALUES (:id, :id, 'AAAAAAAAAA', 'Bar La Esquina')"
            ),
            {"id": establishment_id},
        )
        await connection.execute(
            text(
                "INSERT INTO owner_account (establishment_id, email, email_normalized, "
                "password_hash, email_verified_at) VALUES (:id, :email, :email, 'hash', now())"
            ),
            {"id": establishment_id, "email": EMAIL},
        )
    try:
        yield Ctx(
            engine=engine,
            publisher=publisher,
            enqueue=EnqueueTrack(unit_of_work=unit_of_work, publisher=publisher),
            open=OpenMusicSession(
                unit_of_work=unit_of_work, publisher=publisher, clock=FixedClock()
            ),
            owner=OwnerContext(
                account_id=uuid.uuid4(), establishment_id=establishment_id, email_verified=True
            ),
        )
    finally:
        await db.dispose()


async def _rows(ctx: Ctx, sql: str) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        return [dict(row._mapping) for row in await connection.execute(text(sql))]


async def test_F002_R008_enqueue_agrega_al_final_y_publica_queue_changed(ctx: Ctx) -> None:
    opened = await ctx.open(ctx.owner)
    await ctx.enqueue(ctx.owner.establishment_id, "fake:3s", "A")
    ctx.publisher.published.clear()

    item = await ctx.enqueue(ctx.owner.establishment_id, "fake:4s", "B")

    assert (item.title, item.position, str(item.state)) == ("B", 2, "pending")
    rows = await _rows(
        ctx, "SELECT title, position, state::text AS state FROM queue_item ORDER BY position"
    )
    assert [(row["title"], row["position"], row["state"]) for row in rows] == [
        ("A", 1, "pending"),
        ("B", 2, "pending"),
    ]
    [session] = await _rows(ctx, "SELECT version FROM music_session")
    [(target, event)] = ctx.publisher.published
    assert (target, str(event.type)) == (ctx.owner.establishment_id, "queue.changed")
    assert event.version == session["version"] == opened.state.version + 2


async def test_F002_R008_enqueue_sin_sesion_abierta_lanza_no_open_session(ctx: Ctx) -> None:
    with pytest.raises(NoOpenSession):
        await ctx.enqueue(ctx.owner.establishment_id, "fake:3s", "A")

    assert await _rows(ctx, "SELECT id FROM queue_item") == []
    assert ctx.publisher.published == []


async def test_F002_R008_devtools_agrega_la_cancion(ctx: Ctx, database_url: str) -> None:
    await ctx.open(ctx.owner)

    result = await devtools.enqueue(
        api_settings(database_url), email=EMAIL.upper(), title="Canción", ref="fake:3s"
    )

    assert result == "«Canción» en la posición 1"
    [row] = await _rows(ctx, "SELECT title, track_ref FROM queue_item")
    assert (row["title"], row["track_ref"]) == ("Canción", "fake:3s")


def test_F002_R008_devtools_se_niega_con_env_production(database_url: str) -> None:
    production = Settings(
        env="production",
        database_url=database_url,
        email_backend="ses",
        data_policy_version="2026-10",
        realtime_ticket_secret="secreto-de-produccion-de-al-menos-32-caracteres",
    )

    code = devtools.main(
        ["enqueue", "--email", EMAIL, "--title", "Canción", "--ref", "fake:3s"],
        settings=production,
    )

    assert code == 2
