"""Casos de uso del cliente en C2 (feature 003, plan D4) contra PostgreSQL real, con el
rol de la API y el catálogo falso."""

import asyncio
import contextlib
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
from app.catalog.infrastructure.fake import FakeCatalog
from app.catalog.interface import TrackLookup
from app.sessions.application.claim_player import ClaimPlayer
from app.sessions.application.close_session import CloseMusicSession
from app.sessions.application.open_session import OpenMusicSession
from app.sessions.application.report_player_event import ReportPlayerEvent
from app.sessions.domain.music_session import QUOTA, MusicSession, PlayerEvent, PlayerEventType
from app.sessions.infrastructure.memory_publisher import InMemoryEventPublisher
from app.sessions.infrastructure.repositories import SqlSessionsRepository, SqlSessionsUnitOfWork
from app.sessions.interface import (
    AlreadyQueued,
    CatalogUnavailable,
    ClientView,
    NoOpenSession,
    QuotaExceeded,
    RequestTrack,
    UnknownTrack,
)
from app.shared.db import Database

pytestmark = pytest.mark.anyio


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 10, 27, 20, 0, tzinfo=UTC)


class Rendezvous:
    """Dos pedidos que se esperan después de leer la sesión, para que se crucen de verdad.
    Sin el bloqueo de la sesión, los dos leen la misma cola antes de que ninguno guarde.
    Con el bloqueo, el segundo no puede leer hasta que el primero confirma: la espera
    caduca y todo sale en orden."""

    def __init__(self, parties: int = 2, timeout: float = 0.3) -> None:
        self._parties = parties
        self._arrived = 0
        self._all_here = asyncio.Event()
        self._timeout = timeout

    async def meet(self) -> None:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_here.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._all_here.wait(), self._timeout)


class MeetingRepository:
    def __init__(self, inner: SqlSessionsRepository, rendezvous: Rendezvous | None) -> None:
        self._inner = inner
        self._rendezvous = rendezvous

    async def open_session(self, *, lock: bool) -> MusicSession | None:
        found = await self._inner.open_session(lock=lock)
        if self._rendezvous is not None:
            await self._rendezvous.meet()
        return found

    async def add(self, session: MusicSession) -> None:
        await self._inner.add(session)

    async def save(self, session: MusicSession) -> None:
        await self._inner.save(session)


class MeetingUnitOfWork:
    """Cada pedido abre dos transacciones: la lectura previa de la sesión y la que aplica
    las reglas. El cruce se fuerza en la segunda de cada pedido, la que importa."""

    def __init__(self, inner: SqlSessionsUnitOfWork, rendezvous: Rendezvous) -> None:
        self._inner = inner
        self._rendezvous = rendezvous
        self._opened: dict[object, int] = {}

    @asynccontextmanager
    async def __call__(self, establishment_id: uuid.UUID) -> AsyncIterator[MeetingRepository]:
        task = asyncio.current_task()
        self._opened[task] = self._opened.get(task, 0) + 1
        meets = self._rendezvous if self._opened[task] == 2 else None
        async with self._inner(establishment_id) as repository:
            yield MeetingRepository(repository, meets)


@dataclass
class Ctx:
    engine: AsyncEngine  # superusuario, para comprobar sin RLS
    publisher: InMemoryEventPublisher
    request: RequestTrack
    view: ClientView
    open: OpenMusicSession
    close: CloseMusicSession
    claim: ClaimPlayer
    report: ReportPlayerEvent
    owner: OwnerContext
    unit_of_work: SqlSessionsUnitOfWork

    def crossing_request(self) -> RequestTrack:
        """Un RequestTrack cuyos pedidos simultáneos se cruzan tras leer la sesión."""
        return RequestTrack(
            unit_of_work=MeetingUnitOfWork(self.unit_of_work, Rendezvous()),
            publisher=self.publisher,
            lookup=TrackLookup(catalog=FakeCatalog()),
        )

    @property
    def establishment(self) -> uuid.UUID:
        return self.owner.establishment_id


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
            request=RequestTrack(
                unit_of_work=unit_of_work,
                publisher=publisher,
                lookup=TrackLookup(catalog=FakeCatalog()),
            ),
            view=ClientView(unit_of_work=unit_of_work),
            open=OpenMusicSession(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            close=CloseMusicSession(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            claim=ClaimPlayer(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            report=ReportPlayerEvent(unit_of_work=unit_of_work, publisher=publisher, clock=clock),
            owner=OwnerContext(
                account_id=uuid.uuid4(), establishment_id=establishment_id, email_verified=True
            ),
            unit_of_work=unit_of_work,
        )
    finally:
        await db.dispose()


async def _rows(ctx: Ctx, sql: str) -> list[dict[str, Any]]:
    async with ctx.engine.connect() as connection:
        return [dict(row._mapping) for row in await connection.execute(text(sql))]


async def test_F003_R005_request_track_agrega_al_final_y_publica_queue_changed(ctx: Ctx) -> None:
    await ctx.open(ctx.owner)
    device = uuid.uuid4()
    await ctx.request(ctx.establishment, uuid.uuid4(), "fake:rock-1")
    ctx.publisher.published.clear()

    state = await ctx.request(ctx.establishment, device, "fake:rock-2")

    rows = await _rows(
        ctx, "SELECT track_ref, position, requested_by FROM queue_item ORDER BY position"
    )
    assert [(row["track_ref"], row["position"]) for row in rows] == [
        ("fake:rock-1", 1),
        ("fake:rock-2", 2),
    ]
    assert rows[1]["requested_by"] == device
    assert ctx.publisher.types_for(ctx.establishment) == ["queue.changed"]
    assert (state.open, state.quota_limit, state.quota_free) == (True, QUOTA, QUOTA - 1)
    assert [track.title for track in state.mine] == ["Canción 2 de rock"]


async def test_F003_R005_el_titulo_lo_pone_el_catalogo_no_el_cliente(ctx: Ctx) -> None:
    await ctx.open(ctx.owner)

    # El cliente solo manda la referencia; el título es el que da el catálogo (S4).
    await ctx.request(ctx.establishment, uuid.uuid4(), "fake:salsa-3")

    [row] = await _rows(ctx, "SELECT title FROM queue_item")
    assert row["title"] == "Canción 3 de salsa"


async def test_F003_R006_dos_pedidos_concurrentes_no_superan_el_cupo(ctx: Ctx) -> None:
    await ctx.open(ctx.owner)
    device = uuid.uuid4()
    for number in range(1, QUOTA):
        await ctx.request(ctx.establishment, device, f"fake:rock-{number}")

    # Le queda un cupo y pide dos canciones a la vez, desde dos conexiones que se cruzan.
    crossing = ctx.crossing_request()
    results = await asyncio.gather(
        crossing(ctx.establishment, device, "fake:jazz-1"),
        crossing(ctx.establishment, device, "fake:jazz-2"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, QuotaExceeded) for result in results) == 1
    async with ctx.engine.connect() as connection:
        pending = await connection.execute(
            text("SELECT count(*) FROM queue_item WHERE requested_by = :d"), {"d": device}
        )
        assert pending.scalar_one() == QUOTA


async def test_F003_R007_tras_started_failed_o_cerrar_el_cupo_vuelve(ctx: Ctx) -> None:
    await ctx.open(ctx.owner)
    device = uuid.uuid4()
    for number in range(1, QUOTA + 1):
        await ctx.request(ctx.establishment, device, f"fake:rock-{number}")
    assert (await ctx.view(ctx.establishment, device)).quota_free == 0

    # Empieza a sonar la primera: deja de contar.
    claim = await ctx.claim(ctx.owner)
    assert claim.current is not None
    assert (await ctx.view(ctx.establishment, device)).quota_free == 1
    # Y con ese cupo puede pedir otra.
    assert (await ctx.request(ctx.establishment, device, "fake:jazz-1")).quota_free == 0
    await ctx.report(
        ctx.owner,
        PlayerEvent(epoch=claim.epoch, item_id=claim.current.item_id, type=PlayerEventType.STARTED),
    )
    # Se salta: la siguiente empieza y tampoco cuenta.
    await ctx.report(
        ctx.owner,
        PlayerEvent(epoch=claim.epoch, item_id=claim.current.item_id, type=PlayerEventType.FAILED),
    )
    assert (await ctx.view(ctx.establishment, device)).quota_free == 1

    # Al cerrar y abrir otra sesión, el cupo vuelve entero.
    await ctx.close(ctx.owner)
    assert (await ctx.view(ctx.establishment, device)).open is False
    await ctx.open(ctx.owner)
    reopened = await ctx.view(ctx.establishment, device)
    assert (reopened.open, reopened.quota_free, reopened.mine) == (True, QUOTA, [])


async def test_F003_R009_dos_pedidos_concurrentes_de_la_misma_cancion_dejan_una(ctx: Ctx) -> None:
    await ctx.open(ctx.owner)
    first, second = uuid.uuid4(), uuid.uuid4()

    crossing = ctx.crossing_request()
    results = await asyncio.gather(
        crossing(ctx.establishment, first, "fake:rock-1"),
        crossing(ctx.establishment, second, "fake:rock-1"),
        return_exceptions=True,
    )

    assert sum(isinstance(result, AlreadyQueued) for result in results) == 1
    [row] = await _rows(ctx, "SELECT count(*) AS n FROM queue_item WHERE track_ref = 'fake:rock-1'")
    assert row["n"] == 1
    # Al que se le rechazó no se le gastó cupo.
    loser = second if isinstance(results[1], AlreadyQueued) else first
    assert (await ctx.view(ctx.establishment, loser)).quota_free == QUOTA


async def test_F003_R010_client_view_da_lo_que_suena_las_pendientes_propias_y_el_cupo(
    ctx: Ctx,
) -> None:
    device, other = uuid.uuid4(), uuid.uuid4()
    # Sin sesión abierta: cerrada, sin nada que mostrar.
    closed = await ctx.view(ctx.establishment, device)
    assert (closed.open, closed.now_playing, closed.mine) == (False, None, [])

    await ctx.open(ctx.owner)
    await ctx.request(ctx.establishment, device, "fake:rock-1")
    await ctx.request(ctx.establishment, other, "fake:rock-2")
    await ctx.request(ctx.establishment, device, "fake:rock-3")
    await ctx.request(ctx.establishment, device, "fake:rock-4")
    await ctx.claim(ctx.owner)

    state = await ctx.view(ctx.establishment, device)

    # Suena la primera; las pendientes son solo las suyas, en el orden en que sonarán.
    assert state.now_playing == "Canción 1 de rock"
    assert [track.title for track in state.mine] == ["Canción 3 de rock", "Canción 4 de rock"]
    assert state.quota_free == QUOTA - 2
    # La del otro dispositivo no aparece (R011).
    assert "Canción 2 de rock" not in [track.title for track in state.mine]


async def test_F003_R014_una_cancion_que_el_catalogo_ya_no_reconoce_lanza_unknown_track(
    ctx: Ctx,
) -> None:
    await ctx.open(ctx.owner)
    device = uuid.uuid4()
    ctx.publisher.published.clear()

    for ref in ("fake:retirada-1", "yt:AAAAAAAAAAA", "inventada"):
        with pytest.raises(UnknownTrack):
            await ctx.request(ctx.establishment, device, ref)

    # Ni la cola ni el cupo cambian, y no se publica nada.
    assert await _rows(ctx, "SELECT id FROM queue_item") == []
    assert (await ctx.view(ctx.establishment, device)).quota_free == QUOTA
    assert ctx.publisher.published == []


class UnavailableCatalog:
    """Un catálogo que no puede atender, y cuenta las veces que se le pregunta."""

    def __init__(self) -> None:
        self.lookups = 0

    async def __call__(self, establishment_id: uuid.UUID, ref: str) -> None:
        self.lookups += 1
        raise CatalogUnavailable


async def test_F003_R008_request_track_con_la_sesion_cerrada_lanza_no_open_session(
    ctx: Ctx,
) -> None:
    device = uuid.uuid4()
    unavailable = UnavailableCatalog()
    request = RequestTrack(
        unit_of_work=ctx.unit_of_work, publisher=ctx.publisher, lookup=unavailable
    )

    # Sin sesión abierta: el aviso es el de R008, ni el de una canción retirada ni el del
    # proveedor caído, y no se pregunta al catálogo (no se gasta cuota).
    for pedido, ref in ((ctx.request, "fake:retirada-1"), (request, "fake:rock-1")):
        with pytest.raises(NoOpenSession):
            await pedido(ctx.establishment, device, ref)
    assert unavailable.lookups == 0

    # Lo mismo después de cerrarla.
    await ctx.open(ctx.owner)
    await ctx.close(ctx.owner)
    ctx.publisher.published.clear()
    with pytest.raises(NoOpenSession):
        await ctx.request(ctx.establishment, device, "fake:rock-1")
    assert await _rows(ctx, "SELECT id FROM queue_item") == []
    assert ctx.publisher.published == []

    # Con la sesión abierta, el proveedor caído sí llega como tal (R012).
    await ctx.open(ctx.owner)
    with pytest.raises(CatalogUnavailable):
        await request(ctx.establishment, device, "fake:rock-1")
    assert unavailable.lookups == 1
