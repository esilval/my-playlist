"""Interfaz pública de C2 (sesión y cola) para los demás módulos (plan Contratos).

- `EnqueueTrack(establishment_id, track_ref, title) -> QueueItem`: agrega una canción
  al final de la cola de la sesión abierta. Lanza `NoOpenSession` si no hay ninguna.

B03 y B05 la usarán sin tocar las tablas de C2 (S2: solo C2 modifica la cola).
"""

from app.sessions.application.enqueue_track import EnqueueTrack
from app.sessions.domain.music_session import NoOpenSession
from app.sessions.domain.queue import QueueItem

__all__ = ["EnqueueTrack", "NoOpenSession", "QueueItem"]
