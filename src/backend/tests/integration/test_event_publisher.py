"""Publicación de eventos contra el Redis real de docker-compose (plan D6)."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.sessions.domain.music_session import (
    MusicSession,
    PlayerEvent,
    PlayerEventType,
    SessionEvent,
    SessionEventType,
)
from app.sessions.domain.queue import QueueItem
from app.sessions.infrastructure.redis_publisher import RedisEventPublisher, channel_for
from app.shared.config import get_settings

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)

# Plan, Contratos: los campos de cada evento, además de type, session_id y version.
CONTRACT_FIELDS: dict[str, set[str]] = {
    "session.opened": set(),
    "session.closed": set(),
    "player.claimed": {"epoch"},
    "track.started": {"item_id", "title"},
    "track.failed": {"item_id", "title"},
    "queue.changed": set(),
}
BASE_FIELDS = {"type", "session_id", "version"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url)
    try:
        yield client
    finally:
        await client.aclose()


@pytest.fixture
async def publisher(redis: Redis) -> RedisEventPublisher:
    return RedisEventPublisher(redis)


async def _received(redis: Redis, channel: str, publish: Any, count: int) -> list[dict[str, Any]]:
    """Se suscribe al canal, publica y devuelve los `count` mensajes que llegan."""
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(channel)
        await publish()
        messages: list[dict[str, Any]] = []
        async with asyncio.timeout(2):
            while len(messages) < count:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if message is not None:
                    messages.append(json.loads(message["data"]))
        return messages


def _session_events() -> tuple[UUID, list[SessionEvent]]:
    """Un recorrido real del dominio que produce los seis tipos de evento."""
    establishment_id = uuid4()
    session = MusicSession.open(session_id=uuid4(), establishment_id=establishment_id, now=NOW)
    session.items = [
        QueueItem(id=uuid4(), position=position, track_ref=f"fake:{title}", title=title)
        for position, title in enumerate(("A", "B", "C"), start=1)
    ]
    claim = session.claim_player(NOW)
    a, b, _ = session.items
    for item_id, type in (
        (a.id, PlayerEventType.STARTED),
        (a.id, PlayerEventType.ENDED),
        (b.id, PlayerEventType.FAILED),
    ):
        session.apply(PlayerEvent(epoch=claim.epoch, item_id=item_id, type=type), NOW)
    session.close(NOW)
    return establishment_id, list(session.events)


async def test_F002_R014_publica_en_el_canal_del_establecimiento(redis: Redis, publisher: RedisEventPublisher) -> None:  # noqa: E501  # fmt: skip
    establishment_id = uuid4()
    session_id = uuid4()
    event = SessionEvent(type=SessionEventType.SESSION_OPENED, session_id=session_id, version=7)

    [message] = await _received(
        redis,
        f"est:{establishment_id}",
        lambda: publisher.publish(establishment_id, event),
        count=1,
    )

    assert message == {"type": "session.opened", "session_id": str(session_id), "version": 7}


async def test_F002_R014_no_llega_al_canal_de_otro_establecimiento(redis: Redis, publisher: RedisEventPublisher) -> None:  # noqa: E501  # fmt: skip
    a, b = uuid4(), uuid4()
    event = SessionEvent(type=SessionEventType.SESSION_CLOSED, session_id=uuid4(), version=1)
    async with redis.pubsub() as pubsub:
        await pubsub.subscribe(channel_for(b))
        await publisher.publish(a, event)
        # El suscriptor de b no recibe nada en el tiempo en que a recibiría su evento.
        assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=1) is None


async def test_F002_R008_evento_sin_datos_de_la_cuenta(redis: Redis, publisher: RedisEventPublisher) -> None:  # noqa: E501  # fmt: skip
    establishment_id, events = _session_events()

    async def publish_all() -> None:
        for event in events:
            await publisher.publish(establishment_id, event)

    messages = await _received(redis, channel_for(establishment_id), publish_all, count=len(events))

    assert {message["type"] for message in messages} == set(CONTRACT_FIELDS)
    for message in messages:
        assert set(message) == BASE_FIELDS | CONTRACT_FIELDS[message["type"]], message
    # Las versiones crecen en el orden en que se publican.
    versions = [message["version"] for message in messages]
    assert versions == sorted(versions)
