"""Caso de uso: avanzar en espera (R008, plan D4).

Una canción que entra con la cola vacía se queda pendiente. El reproductor en espera
pide avanzar al recibir `queue.changed`, y C2 decide si empieza la primera pendiente.
Lleva la época, así que un reproductor superado no le quita el control a otro (R010).
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import NoOpenSession, Progress
from app.sessions.domain.ports import EventPublisher, SessionsUnitOfWork


@dataclass(frozen=True)
class AdvancePlayer:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher

    async def __call__(self, owner: OwnerContext, epoch: int) -> Progress:
        """Lanza NoOpenSession (R011) o PlayerSuperseded (R010)."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            progress = session.advance(epoch)
            await sessions.save(session)
        await publish_events(self.publisher, owner.establishment_id, session.events)
        return progress
