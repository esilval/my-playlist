from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.sessions.domain.music_session import (
    MusicSession,
    NoOpenSession,
    PlayerEvent,
    PlayerEventType,
    PlayerSuperseded,
    SessionEventType,
    open_music_session,
)
from app.sessions.domain.queue import QueueItem, QueueItemState

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


def _item(title: str, position: int) -> QueueItem:
    return QueueItem(id=uuid4(), position=position, track_ref=f"fake:{title}", title=title)


def _open(*titles: str) -> MusicSession:
    session = MusicSession.open(session_id=uuid4(), establishment_id=uuid4(), now=NOW)
    session.items = [_item(title, position) for position, title in enumerate(titles, start=1)]
    return session


def test_F002_R003_abrir_con_una_abierta_no_crea_otra() -> None:
    existing = _open("A", "B")
    existing.events.clear()

    session, created = open_music_session(
        existing, session_id=uuid4(), establishment_id=existing.establishment_id, now=NOW
    )

    assert created is False
    assert session is existing
    assert [item.state for item in session.items] == [QueueItemState.PENDING] * 2
    assert session.events == []

    # Sin sesión, o con la anterior cerrada, se crea una nueva con la cola vacía.
    existing.close(NOW)
    fresh, created = open_music_session(
        existing, session_id=uuid4(), establishment_id=existing.establishment_id, now=NOW
    )
    assert created is True
    assert fresh is not existing
    assert (fresh.is_open, fresh.items) == (True, [])
    assert [event.type for event in fresh.events] == [SessionEventType.SESSION_OPENED]


def test_F002_R010_poner_en_marcha_incrementa_la_epoca_y_rechaza_la_vieja() -> None:
    session = _open("A", "B")
    first = session.claim_player(NOW)
    second = session.claim_player(NOW + timedelta(seconds=5))

    assert (first.epoch, second.epoch) == (1, 2)
    assert session.events[-1].type is SessionEventType.PLAYER_CLAIMED
    assert session.events[-1].data == {"epoch": 2}

    assert first.current is not None
    with pytest.raises(PlayerSuperseded):
        session.apply(
            PlayerEvent(
                epoch=first.epoch, item_id=first.current.item_id, type=PlayerEventType.ENDED
            ),
            NOW,
        )
    with pytest.raises(PlayerSuperseded):
        session.heartbeat(first.epoch, NOW)
    # El informe rechazado no tocó la cola.
    assert [item.state for item in session.items] == [
        QueueItemState.PLAYING,
        QueueItemState.PENDING,
    ]


def test_F002_R010_poner_en_marcha_devuelve_la_que_sonaba_desde_el_principio() -> None:
    session = _open("A", "B")
    first = session.claim_player(NOW)
    assert first.current is not None
    session.apply(
        PlayerEvent(epoch=first.epoch, item_id=first.current.item_id, type=PlayerEventType.STARTED),
        NOW,
    )

    second = session.claim_player(NOW + timedelta(minutes=1))

    # El nuevo reproductor recibe A, que seguía sonando, y no salta a B.
    assert second.current == first.current
    # A vuelve a empezar: su inicio real lo informará el nuevo reproductor.
    a = session.items[0]
    assert a.started_at is None
    session.events.clear()
    session.apply(PlayerEvent(epoch=second.epoch, item_id=a.id, type=PlayerEventType.STARTED), NOW)
    assert [event.type for event in session.events] == [SessionEventType.TRACK_STARTED]
    assert second.next is not None and second.next.title == "B"
    assert [item.state for item in session.items] == [
        QueueItemState.PLAYING,
        QueueItemState.PENDING,
    ]


def test_F002_R011_cerrar_descarta_pendientes_y_conserva_sonadas() -> None:
    session = _open("A", "B", "C")
    claim = session.claim_player(NOW)
    assert claim.current is not None
    session.apply(
        PlayerEvent(epoch=claim.epoch, item_id=claim.current.item_id, type=PlayerEventType.ENDED),
        NOW,
    )
    a, b, c = session.items
    session.events.clear()

    assert session.close(NOW) is True

    assert session.is_open is False
    assert (a.state, c.state) == (QueueItemState.PLAYED, QueueItemState.DISCARDED)
    # Las canciones no se borran: siguen en la sesión, con su estado.
    assert len(session.items) == 3
    [closed] = session.events
    assert closed.type is SessionEventType.SESSION_CLOSED
    # Cerrar otra vez no cambia nada.
    assert session.close(NOW) is False
    assert b.state is QueueItemState.PLAYED


def test_F002_R011_cerrar_deja_la_que_sonaba_como_sonada() -> None:
    session = _open("A", "B")
    session.claim_player(NOW)
    a, b = session.items
    assert a.state is QueueItemState.PLAYING

    session.close(NOW)

    assert (a.state, b.state) == (QueueItemState.PLAYED, QueueItemState.DISCARDED)
    assert session.current is None


def test_F002_R008_enqueue_va_al_final_aunque_haya_sonadas_o_saltadas() -> None:
    session = _open("A", "B", "C")
    claim = session.claim_player(NOW)
    a, b, c = session.items
    session.apply(PlayerEvent(epoch=claim.epoch, item_id=a.id, type=PlayerEventType.ENDED), NOW)
    session.apply(PlayerEvent(epoch=claim.epoch, item_id=b.id, type=PlayerEventType.FAILED), NOW)
    version = session.version
    session.events.clear()

    added = session.enqueue(item_id=uuid4(), track_ref="fake:D", title="D")

    assert (added.position, added.state) == (4, QueueItemState.PENDING)
    assert session.version == version + 1
    assert [event.type for event in session.events] == [SessionEventType.QUEUE_CHANGED]
    assert [item.title for item in session.pending()] == ["D"]
    assert c.state is QueueItemState.PLAYING


def test_F002_R008_enqueue_con_la_sesion_cerrada_lanza_no_open_session() -> None:
    session = _open("A")
    session.close(NOW)

    with pytest.raises(NoOpenSession):
        session.enqueue(item_id=uuid4(), track_ref="fake:B", title="B")
    with pytest.raises(ValueError):
        _open().enqueue(item_id=uuid4(), track_ref="fake:B", title="  ")
    assert len(session.items) == 1
