"""Canciones de la cola y sus transiciones (plan D2).

    pending → playing → played
                      → skipped   (falló, con motivo: R007)
    pending → discarded           (al cerrar la sesión: R011)

Una canción en `played`, `skipped` o `discarded` no vuelve atrás: así cada
canción suena como mucho una vez en la sesión (R006).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class QueueItemState(StrEnum):
    # Los mismos valores que el tipo queue_item_state de la base de datos.
    PENDING = "pending"
    PLAYING = "playing"
    PLAYED = "played"
    SKIPPED = "skipped"
    DISCARDED = "discarded"


class InvalidTransition(Exception):
    """La canción no está en el estado del que sale la transición pedida."""


@dataclass(frozen=True)
class Track:
    """Lo que el reproductor necesita de una canción. `track_ref` es opaca para C2:
    solo la entiende el adaptador de proveedor del reproductor (S4, plan D5)."""

    item_id: UUID
    title: str
    track_ref: str


@dataclass
class QueueItem:
    id: UUID
    position: int
    track_ref: str
    title: str
    state: QueueItemState = QueueItemState.PENDING
    failure_reason: str | None = None
    # Cuando el reproductor informa de que empezó a sonar, no cuando le tocó.
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # El dispositivo anónimo que la pidió (feature 003, D4); None si no la pidió un
    # cliente (la herramienta de desarrollo y, más adelante, el propietario).
    requested_by: UUID | None = None

    @property
    def track(self) -> Track:
        return Track(item_id=self.id, title=self.title, track_ref=self.track_ref)

    def _require(self, state: QueueItemState) -> None:
        if self.state is not state:
            raise InvalidTransition(f"{self.state} no admite esta transición")

    def play(self) -> None:
        self._require(QueueItemState.PENDING)
        self.state = QueueItemState.PLAYING

    def restart(self) -> None:
        """Otro reproductor toma el control y la empieza desde el principio (R010)."""
        self._require(QueueItemState.PLAYING)
        self.started_at = None

    def mark_started(self, now: datetime) -> bool:
        """Registra el inicio real. Devuelve False si ya estaba registrado (R012)."""
        self._require(QueueItemState.PLAYING)
        if self.started_at is not None:
            return False
        self.started_at = now
        return True

    def finish(self, now: datetime) -> None:
        self._require(QueueItemState.PLAYING)
        self.state = QueueItemState.PLAYED
        self.finished_at = now

    def skip(self, reason: str, now: datetime) -> None:
        self._require(QueueItemState.PLAYING)
        if not reason.strip():
            raise ValueError("una canción saltada lleva el motivo del fallo")
        self.state = QueueItemState.SKIPPED
        self.failure_reason = reason
        self.finished_at = now

    def discard(self, now: datetime) -> None:
        self._require(QueueItemState.PENDING)
        self.state = QueueItemState.DISCARDED
        self.finished_at = now
