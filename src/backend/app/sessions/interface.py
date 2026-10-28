"""Interfaz pública de C2 (sesión y cola) para los demás módulos (plan Contratos).

- `EnqueueTrack(establishment_id, track_ref, title) -> QueueItem`: agrega una canción
  al final de la cola de la sesión abierta. Lanza `NoOpenSession` si no hay ninguna.
- `RequestTrack(establishment_id, device_id, ref) -> ClientState`: el pedido de un
  cliente (feature 003). Lanza `UnknownTrack`, `NoOpenSession`, `AlreadyQueued`,
  `QuotaExceeded` o `CatalogUnavailable`.
- `ClientView(establishment_id, device_id) -> ClientState`: lo que ve el cliente.

B05 usará `EnqueueTrack` sin tocar las tablas de C2 (S2: solo C2 modifica la cola).
"""

from app.catalog.interface import CatalogUnavailable
from app.sessions.application.client_view import ClientState, ClientView, RequestedTrack
from app.sessions.application.enqueue_track import EnqueueTrack
from app.sessions.application.request_track import RequestTrack, UnknownTrack
from app.sessions.domain.music_session import AlreadyQueued, NoOpenSession, QuotaExceeded
from app.sessions.domain.queue import QueueItem

__all__ = [
    "AlreadyQueued",
    "CatalogUnavailable",
    "ClientState",
    "ClientView",
    "EnqueueTrack",
    "NoOpenSession",
    "QueueItem",
    "QuotaExceeded",
    "RequestTrack",
    "RequestedTrack",
    "UnknownTrack",
]
