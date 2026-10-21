"""Caso de uso: cerrar la sesión de música (R011).

La que sonaba cuenta como sonada, las pendientes se descartan y las que ya sonaron se
conservan. Cerrar sin una sesión abierta no hace nada.
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.application.publishing import publish_events
from app.sessions.domain.ports import Clock, EventPublisher, SessionsUnitOfWork


@dataclass(frozen=True)
class CloseMusicSession:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    clock: Clock

    async def __call__(self, owner: OwnerContext) -> None:
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None or not session.close(self.clock.now()):
                return
            await sessions.save(session)
        # Después del commit: el reproductor se detiene al recibir session.closed.
        await publish_events(self.publisher, owner.establishment_id, session.events)
