"""Caso de uso: abrir la sesión de música (R001, R002, R003).

Hace falta el correo verificado: sin él tampoco se puede descargar el QR por el que
llegan los clientes (R002).

Abrir con una sesión ya abierta la devuelve tal cual, sin crear otra ni vaciar su cola.
Si dos peticiones la abren a la vez, el índice único deja pasar a una sola y la otra
recibe la sesión que abrió la primera.
"""

from dataclasses import dataclass
from uuid import uuid4

from app.accounts.interface import OwnerContext
from app.sessions.application.get_session import MusicSessionState, session_state
from app.sessions.application.publishing import publish_events
from app.sessions.domain.music_session import open_music_session
from app.sessions.domain.ports import Clock, EventPublisher, SessionAlreadyOpen, SessionsUnitOfWork


class EmailNotVerified(Exception):
    """El propietario aún no verificó su correo (R002)."""


@dataclass(frozen=True)
class OpenedSession:
    state: MusicSessionState
    created: bool


@dataclass(frozen=True)
class OpenMusicSession:
    unit_of_work: SessionsUnitOfWork
    publisher: EventPublisher
    clock: Clock

    async def __call__(self, owner: OwnerContext) -> OpenedSession:
        """Lanza EmailNotVerified sin tocar nada si el correo no está verificado."""
        if not owner.email_verified:
            raise EmailNotVerified
        now = self.clock.now()
        async with self.unit_of_work(owner.establishment_id) as sessions:
            existing = await sessions.open_session(lock=True)
            session, created = open_music_session(
                existing, session_id=uuid4(), establishment_id=owner.establishment_id, now=now
            )
            if created:
                try:
                    await sessions.add(session)
                except SessionAlreadyOpen:
                    # La otra petición ya confirmó su sesión: se lee y se devuelve esa.
                    raced = await sessions.open_session(lock=True)
                    if raced is None:
                        raise
                    session, created = raced, False
            events = list(session.events) if created else []
        await publish_events(self.publisher, owner.establishment_id, events)
        return OpenedSession(state=session_state(session, now), created=created)
