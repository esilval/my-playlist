"""Caso de uso: latido del reproductor (R008, R014, plan D3).

Cada 15 s el reproductor marca que sigue activo. La respuesta lleva la versión de la
sesión: si creció sin que llegara el evento, el reproductor pide el estado completo.
La propia petición mantiene viva la sesión iniciada del propietario, porque toda ruta
del panel actualiza su última actividad.
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.domain.music_session import NoOpenSession
from app.sessions.domain.ports import Clock, SessionsUnitOfWork


@dataclass(frozen=True)
class PlayerHeartbeat:
    unit_of_work: SessionsUnitOfWork
    clock: Clock

    async def __call__(self, owner: OwnerContext, epoch: int) -> int:
        """Devuelve la versión. Lanza NoOpenSession o PlayerSuperseded (R010)."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            version = session.heartbeat(epoch, self.clock.now())
            await sessions.save(session)
        return version
