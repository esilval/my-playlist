"""Puertos del dominio de la sesión de música: lo que necesita del exterior (S1)."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.sessions.domain.music_session import MusicSession, SessionEvent


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual, con zona horaria."""
        ...


class EventPublisher(Protocol):
    """Difusión por tiempo real (ADR-0005, plan D6). Se llama después de confirmar la
    transacción: un evento perdido se recupera pidiendo el estado a la API."""

    async def publish(self, establishment_id: UUID, event: SessionEvent) -> None: ...


class SessionAlreadyOpen(Exception):
    """Otra transacción abrió una sesión de música a la vez (índice único, R003)."""


class SessionsRepository(Protocol):
    async def open_session(self, *, lock: bool) -> MusicSession | None:
        """La sesión abierta del establecimiento, con sus canciones. Con `lock`, queda
        bloqueada hasta el final de la transacción (`SELECT … FOR UPDATE`, plan D2):
        así se cambia. Sin bloquear, solo se consulta."""
        ...

    async def add(self, session: MusicSession) -> None:
        """Lanza SessionAlreadyOpen si el establecimiento ya tiene una abierta."""
        ...

    async def save(self, session: MusicSession) -> None:
        """Guarda la sesión y el estado de sus canciones."""
        ...


class SessionsUnitOfWork(Protocol):
    def __call__(self, establishment_id: UUID) -> AbstractAsyncContextManager[SessionsRepository]:
        """Una transacción con el contexto de aislamiento del establecimiento (ADR-0009)."""
        ...
