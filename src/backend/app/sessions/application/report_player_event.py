"""Caso de uso: informe del reproductor (R005, R006, R007, R010, R011, R012, plan D4).

El reproductor informa de que una canción empezó, terminó o falló, y C2 decide cuál
suena ahora: es el servidor quien hace avanzar la cola. Un informe repetido (por
ejemplo, reenviado tras un corte) no cambia nada y devuelve el estado actual.

Cuenta las canciones que empiezan y fallan, y mide el hueco entre una y la siguiente: son
las cifras de SG5 (feature 004, plan D11).
"""

from dataclasses import dataclass

from app.accounts.interface import OwnerContext
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import (
    NoOpenSession,
    PlayerEvent,
    Progress,
    SessionEventType,
)
from app.sessions.domain.ports import Clock, EventPublisher, SessionsUnitOfWork
from app.shared.metrics import Metrics


@dataclass(frozen=True)
class ReportPlayerEvent:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    clock: Clock
    metrics: Metrics

    async def __call__(self, owner: OwnerContext, event: PlayerEvent) -> Progress:
        """Lanza NoOpenSession (R011), PlayerSuperseded (R010) o QueueItemNotFound."""
        async with self.unit_of_work(owner.establishment_id) as sessions:
            session = await sessions.open_session(lock=True)
            if session is None:
                raise NoOpenSession
            progress = session.apply(event, self.clock.now())
            await sessions.save(session)
        await publish_events(self.publisher, owner.establishment_id, session.events)
        # Después del commit: solo cuenta lo que quedó guardado.
        for published in session.events:
            if published.type is SessionEventType.TRACK_STARTED:
                self.metrics.count("TrackStarted")
                gap = session.track_gap(event.item_id)
                if gap is not None:
                    self.metrics.timing("TrackGap", gap.total_seconds() * 1000)
            elif published.type is SessionEventType.TRACK_FAILED:
                self.metrics.count("TrackFailed")
        return progress
