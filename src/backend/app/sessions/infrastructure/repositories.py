"""Repositorio SQL de la sesión de música (C2) sobre la unidad de trabajo con RLS.

Toda transición carga la sesión abierta con `SELECT … FOR UPDATE` (plan D2): dos
informes del reproductor, un cierre y un alta en la cola no se cruzan. Al guardar,
solo se escriben las canciones que cambiaron desde que se cargaron.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import astuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.sessions.domain.music_session import MusicSession
from app.sessions.domain.ports import SessionAlreadyOpen
from app.sessions.domain.queue import QueueItem, QueueItemState
from app.shared.db import Database

ONE_OPEN_INDEX = "music_session_one_open_idx"

_SESSION_COLUMNS = (
    "id, establishment_id, opened_at, closed_at, player_epoch, player_seen_at, version"
)
_ITEM_COLUMNS = "id, position, track_ref, title, state, failure_reason, started_at, finished_at"


class SqlSessionsRepository:
    def __init__(self, connection: AsyncConnection, establishment_id: UUID) -> None:
        self._connection = connection
        self._establishment_id = establishment_id
        # Estado de cada canción al cargarla: lo que no cambió no se vuelve a escribir.
        self._loaded: dict[UUID, tuple[object, ...]] = {}

    async def open_session(self, *, lock: bool) -> MusicSession | None:
        locking = " FOR UPDATE" if lock else ""
        found = await self._connection.execute(
            text(
                f"SELECT {_SESSION_COLUMNS} FROM music_session "
                f"WHERE establishment_id = :e AND closed_at IS NULL{locking}"
            ),
            {"e": self._establishment_id},
        )
        row = found.mappings().one_or_none()
        if row is None:
            return None
        items = await self._connection.execute(
            text(f"SELECT {_ITEM_COLUMNS} FROM queue_item WHERE session_id = :s ORDER BY position"),
            {"s": row["id"]},
        )
        session = MusicSession(
            id=row["id"],
            establishment_id=row["establishment_id"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            player_epoch=row["player_epoch"],
            player_seen_at=row["player_seen_at"],
            version=row["version"],
            items=[
                QueueItem(
                    id=item["id"],
                    position=item["position"],
                    track_ref=item["track_ref"],
                    title=item["title"],
                    state=QueueItemState(item["state"]),
                    failure_reason=item["failure_reason"],
                    started_at=item["started_at"],
                    finished_at=item["finished_at"],
                )
                for item in items.mappings()
            ],
        )
        self._loaded = {item.id: astuple(item) for item in session.items}
        return session

    async def add(self, session: MusicSession) -> None:
        try:
            # Un savepoint: si choca con el índice, la transacción sigue utilizable.
            async with self._connection.begin_nested():
                await self._connection.execute(
                    text(
                        "INSERT INTO music_session "
                        "(id, establishment_id, opened_at, player_epoch, version) "
                        "VALUES (:id, :e, :opened_at, :epoch, :version)"
                    ),
                    {
                        "id": session.id,
                        "e": session.establishment_id,
                        "opened_at": session.opened_at,
                        "epoch": session.player_epoch,
                        "version": session.version,
                    },
                )
        except IntegrityError as error:
            if ONE_OPEN_INDEX in str(error.orig):
                raise SessionAlreadyOpen from error
            raise
        await self._write_items(session)

    async def save(self, session: MusicSession) -> None:
        await self._connection.execute(
            text(
                "UPDATE music_session SET closed_at = :closed_at, player_epoch = :epoch, "
                "player_seen_at = :seen_at, version = :version WHERE id = :id"
            ),
            {
                "id": session.id,
                "closed_at": session.closed_at,
                "epoch": session.player_epoch,
                "seen_at": session.player_seen_at,
                "version": session.version,
            },
        )
        await self._write_items(session)

    async def _write_items(self, session: MusicSession) -> None:
        for item in session.items:
            snapshot = astuple(item)
            if item.id not in self._loaded:
                await self._insert_item(session, item)
            elif self._loaded[item.id] != snapshot:
                await self._connection.execute(
                    text(
                        "UPDATE queue_item SET state = CAST(:state AS queue_item_state), "
                        "failure_reason = :reason, started_at = :started_at, "
                        "finished_at = :finished_at WHERE id = :id"
                    ),
                    {
                        "id": item.id,
                        "state": str(item.state),
                        "reason": item.failure_reason,
                        "started_at": item.started_at,
                        "finished_at": item.finished_at,
                    },
                )
            self._loaded[item.id] = snapshot

    async def _insert_item(self, session: MusicSession, item: QueueItem) -> None:
        await self._connection.execute(
            text(
                "INSERT INTO queue_item (id, establishment_id, session_id, position, "
                "track_ref, title, state, failure_reason, started_at, finished_at) "
                "VALUES (:id, :e, :s, :position, :track_ref, :title, "
                "CAST(:state AS queue_item_state), :reason, :started_at, :finished_at)"
            ),
            {
                "id": item.id,
                "e": session.establishment_id,
                "s": session.id,
                "position": item.position,
                "track_ref": item.track_ref,
                "title": item.title,
                "state": str(item.state),
                "reason": item.failure_reason,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
            },
        )


class SqlSessionsUnitOfWork:
    """Abre una transacción con el rol de la API y el establecimiento fijado (ADR-0009)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @asynccontextmanager
    async def __call__(self, establishment_id: UUID) -> AsyncIterator[SqlSessionsRepository]:
        async with self._db.transaction(establishment_id) as connection:
            yield SqlSessionsRepository(connection, establishment_id)
