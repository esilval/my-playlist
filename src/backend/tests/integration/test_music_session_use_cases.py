"""Casos de uso de la sesión de música contra PostgreSQL real, con el rol app_api."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.accounts.interface import OwnerContext
from app.sessions.application.close_session import CloseMusicSession
from app.sessions.application.get_session import GetMusicSession
from app.sessions.application.open_session import OpenMusicSession
from app.sessions.domain.music_session import MusicSession, SessionEvent
from app.sessions.domain.ports import SessionAlreadyOpen
from app.sessions.infrastructure.memory_publisher import InMemoryEventPublisher
from app.sessions.infrastructure.repositories import (
    SqlSessionsRepository,
    SqlSessionsUnitOfWork,
)
from app.shared.db import Database

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class FailingPublisher:
    async def publish(self, establishment_id: uuid.UUID, event: SessionEvent) -> None:
        raise ConnectionError("Redis no responde")


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para preparar y comprobar sin RLS
    publisher: InMemoryEventPublisher
    open: OpenMusicSession
    close: CloseMusicSession
    get: GetMusicSession
    owner: OwnerContext


@pytest.fixture
async def ctx(engine: AsyncEngine, database_url: str) -> AsyncIterator[Ctx]:
    db = Database.from_url(database_url, role="app_api")
    unit_of_work = SqlSessionsUnitOfWork(db)
    publisher = InMemoryEventPublisher()
    clock = FixedClock()
    establishment_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO establishment (id, establishment_id, public_code, name) "
                "VALUES (:id, :id, 'AAAAAAAAAA', 'Bar La Esquina')"
            ),
            {"id": establishment_id},
        )
    try:
        yield Ctx(
            engine=engine,
            publisher=publisher,
            open=OpenMusicSession(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            close=CloseMusicSession(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            get=GetMusicSession(unit_of_work=unit_of_work, clock=clock),
            owner=OwnerContext(
                account_id=uuid.uuid4(), establishment_id=establishment_id, email_verified=True
            ),
        )
    finally:
        await db.dispose()


async def _rows(ctx: Ctx, sql: str, **params: Any) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        result = await connection.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


async def _add_items(ctx: Ctx, session_id: uuid.UUID, *states: str) -> None:
    async with ctx.engine.begin() as connection:
        for position, state in enumerate(states, start=1):
            await connection.execute(
                text(
                    "INSERT INTO queue_item (establishment_id, session_id, position, track_ref, title, state) "  # noqa: E501
                    "VALUES (:e, :s, :p, :ref, :title, CAST(:state AS queue_item_state))"
                ),
                {
                    "e": ctx.owner.establishment_id,
                    "s": session_id,
                    "p": position,
                    "ref": f"fake:{position}",
                    "title": "ABCDE"[position - 1],
                    "state": state,
                },
            )


async def _states(ctx: Ctx, session_id: uuid.UUID) -> dict[str, str]:
    rows = await _rows(
        ctx,
        "SELECT title, state::text AS state FROM queue_item WHERE session_id = :s",
        s=session_id,
    )
    return {row["title"]: row["state"] for row in rows}


async def test_F002_R001_abrir_deja_la_sesion_abierta_con_la_cola_vacia(ctx: Ctx) -> None:
    opened = await ctx.open(ctx.owner)

    assert opened.created is True
    assert (opened.state.now_playing, opened.state.failures) == (None, [])
    [row] = await _rows(ctx, "SELECT id, closed_at FROM music_session")
    assert (row["id"], row["closed_at"]) == (opened.state.id, None)
    assert await _states(ctx, opened.state.id) == {}
    assert ctx.publisher.types_for(ctx.owner.establishment_id) == ["session.opened"]

    state = await ctx.get(ctx.owner)
    assert state is not None and state.id == opened.state.id


async def test_F002_R003_dos_aperturas_concurrentes_dejan_una_sola_sesion(ctx: Ctx) -> None:
    # Sin sesión abierta, dos aperturas a la vez: una la crea y la otra recibe esa misma.
    first, second = await asyncio.gather(ctx.open(ctx.owner), ctx.open(ctx.owner))

    assert {first.created, second.created} == {True, False}
    assert first.state.id == second.state.id
    assert len(await _rows(ctx, "SELECT id FROM music_session WHERE closed_at IS NULL")) == 1
    assert ctx.publisher.types_for(ctx.owner.establishment_id) == ["session.opened"]

    # Con 2 pendientes, volver a abrir (dos veces a la vez) no la vacía ni crea otra.
    await _add_items(ctx, first.state.id, "pending", "pending")
    again = await asyncio.gather(ctx.open(ctx.owner), ctx.open(ctx.owner))

    assert {opened.created for opened in again} == {False}
    assert {opened.state.id for opened in again} == {first.state.id}
    assert await _states(ctx, first.state.id) == {"A": "pending", "B": "pending"}
    assert len(await _rows(ctx, "SELECT id FROM music_session")) == 1


class StaleFirstRead:
    """Repositorio que no ve la sesión en su primera lectura: es lo que le pasa a una
    transacción que consultó justo antes de que otra confirmara su apertura."""

    def __init__(self, inner: SqlSessionsRepository) -> None:
        self._inner = inner
        self._reads = 0

    async def open_session(self, *, lock: bool) -> MusicSession | None:
        self._reads += 1
        found = await self._inner.open_session(lock=lock)
        return None if self._reads == 1 else found

    async def add(self, session: MusicSession) -> None:
        await self._inner.add(session)

    async def save(self, session: MusicSession) -> None:
        await self._inner.save(session)


class StaleFirstReadUnitOfWork:
    def __init__(self, inner: SqlSessionsUnitOfWork) -> None:
        self._inner = inner

    @asynccontextmanager
    async def __call__(self, establishment_id: uuid.UUID) -> AsyncIterator[StaleFirstRead]:
        async with self._inner(establishment_id) as repository:
            yield StaleFirstRead(repository)


async def test_F002_R003_add_con_una_abierta_lanza_session_already_open(ctx: Ctx, database_url: str) -> None:  # noqa: E501  # fmt: skip
    existing = await ctx.open(ctx.owner)
    db = Database.from_url(database_url, role="app_api")
    try:
        async with SqlSessionsUnitOfWork(db)(ctx.owner.establishment_id) as sessions:
            rival = MusicSession.open(
                session_id=uuid.uuid4(), establishment_id=ctx.owner.establishment_id, now=NOW
            )
            with pytest.raises(SessionAlreadyOpen):
                await sessions.add(rival)
            # El savepoint deja la transacción utilizable: se lee la que ya estaba abierta.
            found = await sessions.open_session(lock=True)
            assert found is not None and found.id == existing.state.id
    finally:
        await db.dispose()
    assert len(await _rows(ctx, "SELECT id FROM music_session")) == 1


async def test_F002_R003_carrera_con_el_indice_unico_devuelve_la_abierta(ctx: Ctx, database_url: str) -> None:  # noqa: E501  # fmt: skip
    existing = await ctx.open(ctx.owner)
    await _add_items(ctx, existing.state.id, "pending", "pending")
    db = Database.from_url(database_url, role="app_api")
    try:
        racing = OpenMusicSession(
            unit_of_work=StaleFirstReadUnitOfWork(SqlSessionsUnitOfWork(db)),
            publisher=ctx.publisher,
            clock=FixedClock(),
        )

        # La primera lectura no ve la sesión, así que intenta crear otra y choca con el
        # índice único: el caso de uso relee y devuelve la que ya estaba abierta.
        opened = await racing(ctx.owner)
    finally:
        await db.dispose()

    assert (opened.created, opened.state.id) == (False, existing.state.id)
    assert len(await _rows(ctx, "SELECT id FROM music_session")) == 1
    assert await _states(ctx, existing.state.id) == {"A": "pending", "B": "pending"}
    assert ctx.publisher.types_for(ctx.owner.establishment_id) == ["session.opened"]


async def test_F002_R011_cerrar_descarta_pendientes_y_publica_session_closed(ctx: Ctx) -> None:
    opened = await ctx.open(ctx.owner)
    await _add_items(ctx, opened.state.id, "played", "pending", "pending")

    await ctx.close(ctx.owner)

    assert await _states(ctx, opened.state.id) == {
        "A": "played",
        "B": "discarded",
        "C": "discarded",
    }
    [row] = await _rows(ctx, "SELECT closed_at FROM music_session")
    assert row["closed_at"] == NOW
    assert ctx.publisher.types_for(ctx.owner.establishment_id) == [
        "session.opened",
        "session.closed",
    ]
    assert await ctx.get(ctx.owner) is None

    # Cerrar otra vez no hace nada, y se puede abrir una nueva con la cola vacía.
    await ctx.close(ctx.owner)
    assert ctx.publisher.types_for(ctx.owner.establishment_id)[-1] == "session.closed"
    fresh = await ctx.open(ctx.owner)
    assert fresh.created is True
    assert await _states(ctx, fresh.state.id) == {}


async def test_F002_R011_cerrar_con_una_sonando_la_deja_en_played(ctx: Ctx) -> None:
    opened = await ctx.open(ctx.owner)
    await _add_items(ctx, opened.state.id, "played", "playing", "pending")

    await ctx.close(ctx.owner)

    assert await _states(ctx, opened.state.id) == {
        "A": "played",
        "B": "played",
        "C": "discarded",
    }


async def test_fallo_al_publicar_no_rompe_el_caso_de_uso(ctx: Ctx, database_url: str) -> None:
    db = Database.from_url(database_url, role="app_api")
    try:
        unit_of_work = SqlSessionsUnitOfWork(db)
        failing = FailingPublisher()
        open_session = OpenMusicSession(
            unit_of_work=unit_of_work, publisher=failing, clock=FixedClock()
        )
        close_session = CloseMusicSession(
            unit_of_work=unit_of_work, publisher=failing, clock=FixedClock()
        )

        # Sin Redis, el cambio se guarda igual (plan D6: eventos por el mejor esfuerzo).
        opened = await open_session(ctx.owner)
        assert opened.created is True
        await close_session(ctx.owner)
        [row] = await _rows(ctx, "SELECT closed_at FROM music_session")
        assert row["closed_at"] == NOW
    finally:
        await db.dispose()
