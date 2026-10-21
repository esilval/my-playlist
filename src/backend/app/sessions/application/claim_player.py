"""Caso de uso: poner en marcha el reproductor del local (R004, R009, R010, plan D3).

Cada puesta en marcha incrementa la época y hace de este el único reproductor activo:
el anterior se entera por `player.claimed` (en menos de 1 s) o por el `409` de su
siguiente latido o informe.
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import NoOpenSession, PlayerClaim
from app.sessions.domain.ports import Clock, EventPublisher, SessionsUnitOfWork


@dataclass(frozen=True)
class ClaimPlayer:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    clock: Clock

    async def __call__(self, owner: OwnerContext) -> PlayerClaim:
        """Lanza NoOpenSession si el establecimiento no tiene una sesión abierta (R009)."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            claim = session.claim_player(self.clock.now())
            await sessions.save(session)
        await publish_events(self.publisher, owner.establishment_id, session.events)
        return claim
