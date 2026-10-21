"""Publicador en memoria para las pruebas de los casos de uso: guarda lo publicado."""

from uuid import UUID

from app.sessions.domain.music_session import SessionEvent


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.published: list[tuple[UUID, SessionEvent]] = []

    async def publish(self, establishment_id: UUID, event: SessionEvent) -> None:
        self.published.append((establishment_id, event))

    def types_for(self, establishment_id: UUID) -> list[str]:
        return [str(event.type) for target, event in self.published if target == establishment_id]
