"""Caso de uso: consultar la sesión de música del establecimiento (plan D7, Contratos).

Es la vista que pide el panel al cargar y que piden el panel y el reproductor cuando
detectan un evento perdido (plan D6).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.accounts.interface import OwnerContext
from app.sessions.domain.music_session import MusicSession
from app.sessions.domain.ports import Clock, SessionsUnitOfWork
from app.sessions.domain.queue import QueueItemState, Track


@dataclass(frozen=True)
class Failure:
    title: str
    failed_at: datetime


@dataclass(frozen=True)
class MusicSessionState:
    id: UUID
    opened_at: datetime
    version: int
    now_playing: Track | None
    player_active: bool
    failures: list[Failure]


def session_state(session: MusicSession, now: datetime) -> MusicSessionState:
    current = session.current
    return MusicSessionState(
        id=session.id,
        opened_at=session.opened_at,
        version=session.version,
        now_playing=current.track if current is not None else None,
        player_active=session.player_active(now),
        # Los avisos de fallo sobreviven a recargar el panel (plan D7).
        failures=[
            Failure(title=item.title, failed_at=item.finished_at)
            for item in session.items
            if item.state is QueueItemState.SKIPPED and item.finished_at is not None
        ],
    )


@dataclass(frozen=True)
class GetMusicSession:
    unit_of_work: SessionsUnitOfWork
    clock: Clock

    async def __call__(self, owner: OwnerContext) -> MusicSessionState | None:
        """None si el establecimiento no tiene una sesión de música abierta."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=False)
        return session_state(session, self.clock.now()) if session is not None else None
