"""La sesión de música de un establecimiento y su reproductor (plan D2, D3, D4).

El servidor decide el avance de la cola: el reproductor solo informa de que una
canción empezó, terminó o falló, y la sesión aplica la transición y dice cuál
suena ahora y cuál va después. Cada puesta en marcha del reproductor incrementa
la época; un informe o un latido de una época vieja se rechaza (R010).

Cada cambio incrementa `version` y deja un evento en `events`, que la capa de
aplicación publica después de confirmar la transacción (plan D6).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from app.sessions.domain.queue import QueueItem, QueueItemState, Track

# Un reproductor cuenta como activo si su último latido es de hace menos de esto
# (R014); late cada 15 s (plan D3).
PLAYER_ACTIVE_WINDOW = timedelta(seconds=45)

# Motivo que se guarda cuando el reproductor informa de un fallo sin decir cuál.
UNKNOWN_FAILURE = "unknown"


class NoOpenSession(Exception):
    """El establecimiento no tiene una sesión de música abierta (R009, R011)."""


class PlayerSuperseded(Exception):
    """El informe o el latido llega de una época vieja: otro reproductor tomó el
    control (R010)."""


class QueueItemNotFound(Exception):
    """La canción no pertenece a esta sesión de música."""


class SessionEventType(StrEnum):
    SESSION_OPENED = "session.opened"
    SESSION_CLOSED = "session.closed"
    PLAYER_CLAIMED = "player.claimed"
    TRACK_STARTED = "track.started"
    TRACK_FAILED = "track.failed"
    QUEUE_CHANGED = "queue.changed"


@dataclass(frozen=True)
class SessionEvent:
    """Lo que se difunde por tiempo real: solo lo que se muestra en pantalla, nunca
    datos de la cuenta (ADR-0014)."""

    type: SessionEventType
    session_id: UUID
    version: int
    data: Mapping[str, str | int] = field(default_factory=dict)


class PlayerEventType(StrEnum):
    STARTED = "started"
    ENDED = "ended"
    FAILED = "failed"


@dataclass(frozen=True)
class PlayerEvent:
    epoch: int
    item_id: UUID
    type: PlayerEventType
    reason: str | None = None


@dataclass(frozen=True)
class PlayerClaim:
    epoch: int
    current: Track | None
    next: Track | None


@dataclass(frozen=True)
class Progress:
    current: Track | None
    next: Track | None
    version: int


@dataclass
class MusicSession:
    id: UUID
    establishment_id: UUID
    opened_at: datetime
    closed_at: datetime | None = None
    player_epoch: int = 0
    player_seen_at: datetime | None = None
    version: int = 0
    items: list[QueueItem] = field(default_factory=list)
    events: list[SessionEvent] = field(default_factory=list, compare=False)

    @classmethod
    def open(cls, *, session_id: UUID, establishment_id: UUID, now: datetime) -> "MusicSession":
        """Una sesión nueva empieza con la cola vacía (R001)."""
        session = cls(id=session_id, establishment_id=establishment_id, opened_at=now)
        session.events.append(
            SessionEvent(SessionEventType.SESSION_OPENED, session.id, session.version)
        )
        return session

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def current(self) -> QueueItem | None:
        return next((item for item in self.items if item.state is QueueItemState.PLAYING), None)

    def pending(self) -> list[QueueItem]:
        """Las pendientes, en el orden de la cola (R005)."""
        return sorted(
            (item for item in self.items if item.state is QueueItemState.PENDING),
            key=lambda item: item.position,
        )

    def player_active(self, now: datetime) -> bool:
        return (
            self.is_open
            and self.player_seen_at is not None
            and now - self.player_seen_at < PLAYER_ACTIVE_WINDOW
        )

    def close(self, now: datetime) -> bool:
        """Cierra la sesión (R011): la que sonaba cuenta como sonada, las pendientes
        se descartan y las que ya sonaron se conservan. Devuelve False si ya estaba
        cerrada."""
        if not self.is_open:
            return False
        playing = self.current
        if playing is not None:
            playing.finish(now)
        for item in self.pending():
            item.discard(now)
        self.closed_at = now
        self._changed(SessionEventType.SESSION_CLOSED)
        return True

    def enqueue(self, *, item_id: UUID, track_ref: str, title: str) -> QueueItem:
        """Agrega una canción al final de la cola (R008). La agregarán los clientes (B03)
        y el propietario (B05); en esta feature, solo la herramienta de desarrollo."""
        self._require_open()
        if not track_ref.strip() or not title.strip():
            raise ValueError("una canción de la cola lleva referencia y título")
        position = max((item.position for item in self.items), default=0) + 1
        item = QueueItem(id=item_id, position=position, track_ref=track_ref, title=title)
        self.items.append(item)
        self._changed(SessionEventType.QUEUE_CHANGED)
        return item

    def claim_player(self, now: datetime) -> PlayerClaim:
        """Pone en marcha un reproductor y lo hace el único activo (R004, R010).

        Si una canción estaba sonando, el nuevo reproductor la recibe para empezarla
        desde el principio; si no, empieza la primera pendiente."""
        self._require_open()
        self.player_epoch += 1
        self.player_seen_at = now
        current = self.current
        if current is not None:
            # Vuelve a empezar: su inicio real será el que informe el nuevo reproductor.
            current.restart()
        else:
            current = self._play_next()
        self._changed(SessionEventType.PLAYER_CLAIMED, epoch=self.player_epoch)
        return PlayerClaim(epoch=self.player_epoch, current=_track(current), next=self._next())

    def heartbeat(self, epoch: int, now: datetime) -> int:
        """Latido del reproductor (R014). Devuelve la versión, para que el reproductor
        detecte un evento perdido (plan D3)."""
        self._require_player(epoch)
        self.player_seen_at = now
        return self.version

    def apply(self, event: PlayerEvent, now: datetime) -> Progress:
        """Aplica un informe del reproductor (plan D4).

        Un informe sobre una canción que ya no suena (por ejemplo, reenviado tras un
        corte) no cambia nada y devuelve el estado actual (R012)."""
        self._require_player(event.epoch)
        item = self._item(event.item_id)
        if item.state is QueueItemState.PLAYING:
            if event.type is PlayerEventType.STARTED:
                if item.mark_started(now):
                    self._changed(
                        SessionEventType.TRACK_STARTED, item_id=str(item.id), title=item.title
                    )
            elif event.type is PlayerEventType.ENDED:
                item.finish(now)
                self._play_next()
                self._changed(SessionEventType.QUEUE_CHANGED)
            else:
                # Un fallo sin motivo se guarda igual: el salto no depende de que el
                # reproductor sepa explicar qué pasó (R007).
                item.skip((event.reason or "").strip() or UNKNOWN_FAILURE, now)
                self._play_next()
                self._changed(SessionEventType.TRACK_FAILED, item_id=str(item.id), title=item.title)
        return Progress(current=_track(self.current), next=self._next(), version=self.version)

    def advance(self, epoch: int) -> Progress:
        """Avanza en espera (R008, plan D4): si no suena ninguna canción, empieza la
        primera pendiente. Si ya suena una, o no hay pendientes, no cambia nada y
        devuelve el estado actual, así que repetirlo no tiene efecto."""
        self._require_player(epoch)
        if self.current is None and self._play_next() is not None:
            self._changed(SessionEventType.QUEUE_CHANGED)
        return Progress(current=_track(self.current), next=self._next(), version=self.version)

    def _require_open(self) -> None:
        if not self.is_open:
            raise NoOpenSession

    def _require_player(self, epoch: int) -> None:
        self._require_open()
        if epoch != self.player_epoch:
            raise PlayerSuperseded

    def _item(self, item_id: UUID) -> QueueItem:
        for item in self.items:
            if item.id == item_id:
                return item
        raise QueueItemNotFound

    def _play_next(self) -> QueueItem | None:
        pending = self.pending()
        if not pending:
            return None
        pending[0].play()
        return pending[0]

    def _next(self) -> Track | None:
        pending = self.pending()
        return pending[0].track if pending else None

    def _changed(self, type: SessionEventType, **data: str | int) -> None:
        self.version += 1
        self.events.append(SessionEvent(type, self.id, self.version, data))


def _track(item: QueueItem | None) -> Track | None:
    return item.track if item is not None else None


def open_music_session(
    existing: MusicSession | None, *, session_id: UUID, establishment_id: UUID, now: datetime
) -> tuple[MusicSession, bool]:
    """Abrir con una sesión ya abierta la devuelve tal cual, sin crear otra ni vaciar
    su cola (R003). Devuelve la sesión y si se creó."""
    if existing is not None and existing.establishment_id != establishment_id:
        # La unidad de trabajo y RLS ya lo impiden; esto es defensa en profundidad.
        raise ValueError("la sesión es de otro establecimiento")
    if existing is not None and existing.is_open:
        return existing, False
    return MusicSession.open(
        session_id=session_id, establishment_id=establishment_id, now=now
    ), True
