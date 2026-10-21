from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.sessions.domain.music_session import (
    MusicSession,
    PlayerEvent,
    PlayerEventType,
    SessionEventType,
)
from app.sessions.domain.queue import InvalidTransition, QueueItem, QueueItemState

NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


def _session_with(*titles: str) -> tuple[MusicSession, list[QueueItem]]:
    session = MusicSession.open(session_id=uuid4(), establishment_id=uuid4(), now=NOW)
    # Posiciones desordenadas a propósito: manda `position`, no el orden de la lista.
    items = [
        QueueItem(id=uuid4(), position=(index + 1) * 10, track_ref=f"fake:{title}", title=title)
        for index, title in enumerate(titles)
    ]
    session.items = list(reversed(items))
    session.events.clear()
    return session, items


def _report(session: MusicSession, item_id: UUID, type: PlayerEventType) -> PlayerEvent:
    return PlayerEvent(epoch=session.player_epoch, item_id=item_id, type=type, reason="error")


def test_F002_R005_avanza_en_el_orden_de_la_cola() -> None:
    session, (a, b, c) = _session_with("A", "B", "C")

    claim = session.claim_player(NOW)
    assert claim.current is not None and claim.current.item_id == a.id
    assert claim.next is not None and claim.next.item_id == b.id

    after_a = session.apply(_report(session, a.id, PlayerEventType.ENDED), NOW)
    assert after_a.current is not None and after_a.current.item_id == b.id
    assert after_a.next is not None and after_a.next.item_id == c.id

    after_b = session.apply(_report(session, b.id, PlayerEventType.ENDED), NOW)
    assert after_b.current is not None and after_b.current.item_id == c.id
    assert after_b.next is None

    after_c = session.apply(_report(session, c.id, PlayerEventType.ENDED), NOW)
    assert (after_c.current, after_c.next) == (None, None)
    assert [item.state for item in (a, b, c)] == [QueueItemState.PLAYED] * 3


def test_F002_R006_terminada_o_saltada_no_vuelve_a_sonar() -> None:
    session, (a, b, c) = _session_with("A", "B", "C")
    session.claim_player(NOW)
    session.apply(_report(session, a.id, PlayerEventType.ENDED), NOW)
    session.apply(_report(session, b.id, PlayerEventType.FAILED), NOW)

    # Poner en marcha otra vez (por ejemplo, tras recargar la página) sigue con C.
    claim = session.claim_player(NOW)
    assert claim.current is not None and claim.current.item_id == c.id

    for item in (a, b):
        with pytest.raises(InvalidTransition):
            item.play()
        with pytest.raises(InvalidTransition):
            item.discard(NOW)
    assert (a.state, b.state) == (QueueItemState.PLAYED, QueueItemState.SKIPPED)


def test_F002_R007_fallida_se_salta_con_motivo() -> None:
    session, (a, b) = _session_with("A", "B")
    session.claim_player(NOW)
    session.events.clear()

    progress = session.apply(
        PlayerEvent(
            epoch=session.player_epoch,
            item_id=a.id,
            type=PlayerEventType.FAILED,
            reason="not_embeddable",
        ),
        NOW,
    )

    assert (a.state, a.failure_reason) == (QueueItemState.SKIPPED, "not_embeddable")
    assert progress.current is not None and progress.current.item_id == b.id
    [failed] = session.events
    assert failed.type is SessionEventType.TRACK_FAILED
    assert failed.data == {"item_id": str(a.id), "title": "A"}

    # La única pendiente también falla, sin motivo: se salta igual y no queda nada.
    last = session.apply(
        PlayerEvent(
            epoch=session.player_epoch, item_id=b.id, type=PlayerEventType.FAILED, reason="  "
        ),
        NOW,
    )
    assert (last.current, last.next) == (None, None)
    assert (b.state, b.failure_reason) == (QueueItemState.SKIPPED, "unknown")


def test_F002_R012_informe_repetido_no_cambia_nada() -> None:
    session, (a, b, c) = _session_with("A", "B", "C")
    session.claim_player(NOW)
    session.apply(_report(session, a.id, PlayerEventType.STARTED), NOW)
    session.apply(_report(session, a.id, PlayerEventType.ENDED), NOW + timedelta(minutes=3))
    version = session.version
    session.events.clear()

    # El reproductor reenvía tras un corte informes que ya se habían aplicado.
    for type in (PlayerEventType.STARTED, PlayerEventType.ENDED, PlayerEventType.FAILED):
        progress = session.apply(_report(session, a.id, type), NOW + timedelta(minutes=4))
        assert progress.current is not None and progress.current.item_id == b.id
        assert progress.next is not None and progress.next.item_id == c.id

    assert session.version == version
    assert session.events == []
    assert (a.state, b.state, c.state) == (
        QueueItemState.PLAYED,
        QueueItemState.PLAYING,
        QueueItemState.PENDING,
    )

    # Un `started` repetido sobre la que suena tampoco cuenta dos veces.
    session.apply(_report(session, b.id, PlayerEventType.STARTED), NOW)
    session.apply(_report(session, b.id, PlayerEventType.STARTED), NOW)
    assert [event.type for event in session.events] == [SessionEventType.TRACK_STARTED]
