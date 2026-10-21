"""Caso de uso: agregar una canción al final de la cola de la sesión abierta (R008, D9).

No tiene endpoint en esta feature: lo usan la herramienta de desarrollo y las pruebas.
B03 (pedidos de clientes) y B05 (canciones del propietario) lo llamarán desde sus
propias rutas, a través de la interfaz de C2.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import NoOpenSession
from app.sessions.domain.ports import EventPublisher, SessionsUnitOfWork
from app.sessions.domain.queue import QueueItem


@dataclass(frozen=True)
class EnqueueTrack:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher

    async def __call__(self, establishment_id: UUID, track_ref: str, title: str) -> QueueItem:
        """Lanza NoOpenSession si el establecimiento no tiene una sesión abierta. Publica
        `queue.changed`: un reproductor en espera la empieza al recibirlo (R008)."""
        async with self.unit_of_work(establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            item = session.enqueue(item_id=uuid4(), track_ref=track_ref, title=title)
            await sessions.save(session)
        await publish_events(self.publisher, establishment_id, session.events)
        return item
