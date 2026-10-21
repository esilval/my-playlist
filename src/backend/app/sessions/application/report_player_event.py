"""Caso de uso: informe del reproductor (R005, R006, R007, R010, R011, R012, plan D4).

El reproductor informa de que una canción empezó, terminó o falló, y C2 decide cuál
suena ahora: es el servidor quien hace avanzar la cola. Un informe repetido (por
ejemplo, reenviado tras un corte) no cambia nada y devuelve el estado actual.
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import NoOpenSession, PlayerEvent, Progress
from app.sessions.domain.ports import Clock, EventPublisher, SessionsUnitOfWork


@dataclass(frozen=True)
class ReportPlayerEvent:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    clock: Clock

    async def __call__(self, owner: OwnerContext, event: PlayerEvent) -> Progress:
        """Lanza NoOpenSession (R011), PlayerSuperseded (R010) o QueueItemNotFound."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            progress = session.apply(event, self.clock.now())
            await sessions.save(session)
        await publish_events(self.publisher, owner.establishment_id, session.events)
        return progress
