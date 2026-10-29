"""Caso de uso: lo que ve un cliente de la sesión de música (feature 003, plan D4, D6).

Lo que suena (solo el título), las pendientes que pidió su dispositivo, en el orden en
que sonarán, y su cupo libre (R010). Nunca los pedidos de otros dispositivos (R011).
"""

from dataclasses import dataclass
from uuid import UUID

from app.sessions.domain.music_session import QUOTA, MusicSession
from app.sessions.domain.ports import ClientReadUnitOfWork


@dataclass(frozen=True)
class RequestedTrack:
    item_id: UUID
    title: str


@dataclass(frozen=True)
class ClientState:
    open: bool
    now_playing: str | None
    mine: list[RequestedTrack]
    quota_limit: int
    quota_free: int


CLOSED = ClientState(open=False, now_playing=None, mine=[], quota_limit=QUOTA, quota_free=QUOTA)


def client_state(session: MusicSession | None, device_id: UUID) -> ClientState:
    if session is None or not session.is_open:
        return CLOSED
    current = session.current
    mine = [
        RequestedTrack(item_id=item.id, title=item.title) for item in session.pending_of(device_id)
    ]
    return ClientState(
        open=True,
        now_playing=current.title if current is not None else None,
        mine=mine,
        quota_limit=QUOTA,
        quota_free=max(QUOTA - len(mine), 0),
    )


@dataclass(frozen=True)
class ClientView:
    unit_of_work: ClientReadUnitOfWork

    async def __call__(self, establishment_id: UUID, device_id: UUID) -> ClientState:
        # La piden todos los clientes conectados con cada cambio de la cola (plan D6), y la
        # búsqueda: lee sin bloquear y solo lo que se muestra, no la cola entera (D4).
        async with self.unit_of_work(establishment_id) as sessions:
            session = await sessions.client_snapshot(device_id)
        return client_state(session, device_id)
