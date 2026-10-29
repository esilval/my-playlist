"""Caso de uso: el pedido de una canción por un cliente (feature 003, plan D4).

1. Con la sesión cerrada se rechaza enseguida (R008), con una lectura sin bloqueo: el
   cliente ve el aviso que toca y no se pregunta al catálogo ni se gasta cuota.
2. La canción se valida con el catálogo (C3) fuera de la transacción: el navegador solo
   manda la referencia, y el título lo pone C3 (S4). Si ya no existe o ya no se puede
   reproducir, se rechaza (R014).
3. Con la sesión bloqueada, el dominio aplica las reglas: sesión abierta (R008), sin
   duplicadas pendientes (R009) y con cupo (R006). Dos pedidos a la vez no se cruzan.
4. Tras el commit se publica `queue.changed`: un reproductor en espera la empieza.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from app.catalog.interface import CatalogTrack
from app.sessions.application.client_view import ClientState, client_state
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import NoOpenSession
from app.sessions.domain.ports import EventPublisher, SessionsUnitOfWork


class UnknownTrack(Exception):
    """La canción ya no existe o ya no se puede reproducir en el local (R014)."""


class TrackResolver(Protocol):
    """La interfaz de C3 que usa C2 para validar un pedido (`TrackLookup`, S4)."""

    async def __call__(self, establishment_id: UUID, ref: str) -> CatalogTrack | None: ...


@dataclass(frozen=True)
class RequestTrack:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    lookup: TrackResolver

    async def __call__(self, establishment_id: UUID, device_id: UUID, ref: str) -> ClientState:
        """Lanza UnknownTrack (R014), CatalogUnavailable (R012), NoOpenSession (R008),
        AlreadyQueued (R009) o QuotaExceeded (R006)."""
        # Una lectura sin bloqueo: si la sesión está cerrada, el aviso es el de R008. La
        # comprobación que cuenta es la de abajo, con la sesión bloqueada.
        async with self.unit_of_work(establishment_id) as sessions:
            if await sessions.open_session(lock=False) is None:
                raise NoOpenSession
        track = await self.lookup(establishment_id, ref)
        if track is None:
            raise UnknownTrack
        async with self.unit_of_work(establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            session.request(
                item_id=uuid4(), device_id=device_id, track_ref=track.ref, title=track.title
            )
            await sessions.save(session)
        await publish_events(self.publisher, establishment_id, session.events)
        return client_state(session, device_id)
