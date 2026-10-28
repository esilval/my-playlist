from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.sessions.domain.music_session import (
    QUOTA,
    AlreadyQueued,
    MusicSession,
    NoOpenSession,
    PlayerEvent,
    PlayerEventType,
    PlayerSuperseded,
    QuotaExceeded,
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


def test_F002_R008_avanzar_en_espera_empieza_la_primera_pendiente() -> None:
    session = _open()
    claim = session.claim_player(NOW)
    assert claim.current is None
    session.enqueue(item_id=uuid4(), track_ref="fake:A", title="A")
    session.enqueue(item_id=uuid4(), track_ref="fake:B", title="B")
    session.events.clear()
    version = session.version

    progress = session.advance(claim.epoch)

    assert progress.current is not None and progress.current.title == "A"
    assert progress.next is not None and progress.next.title == "B"
    assert [item.state for item in session.items] == [
        QueueItemState.PLAYING,
        QueueItemState.PENDING,
    ]
    assert progress.version == session.version == version + 1
    assert [event.type for event in session.events] == [SessionEventType.QUEUE_CHANGED]


def test_F002_R008_avanzar_con_una_cancion_sonando_no_cambia_nada() -> None:
    session = _open("A", "B")
    claim = session.claim_player(NOW)
    session.events.clear()
    version = session.version

    # Repetido: la que suena sigue sonando y no se publica nada.
    for _ in range(2):
        progress = session.advance(claim.epoch)
        assert progress.current is not None and progress.current.title == "A"
        assert progress.next is not None and progress.next.title == "B"
    assert [item.state for item in session.items] == [
        QueueItemState.PLAYING,
        QueueItemState.PENDING,
    ]
    assert (session.version, session.events) == (version, [])

    # Sin pendientes, tampoco cambia nada.
    empty = _open()
    epoch = empty.claim_player(NOW).epoch
    empty.events.clear()
    before = empty.version
    progress = empty.advance(epoch)
    assert (progress.current, progress.next, progress.version) == (None, None, before)
    assert empty.events == []


def test_F002_R010_avanzar_con_epoca_vieja_lanza_player_superseded() -> None:
    session = _open()
    first = session.claim_player(NOW)
    session.claim_player(NOW)
    session.enqueue(item_id=uuid4(), track_ref="fake:A", title="A")

    with pytest.raises(PlayerSuperseded):
        session.advance(first.epoch)
    assert [item.state for item in session.items] == [QueueItemState.PENDING]


def test_F002_R011_avanzar_con_la_sesion_cerrada_lanza_no_open_session() -> None:
    session = _open("A")
    epoch = session.claim_player(NOW).epoch
    session.close(NOW)

    with pytest.raises(NoOpenSession):
        session.advance(epoch)


def _request(session: MusicSession, device: UUID, ref: str) -> QueueItem:
    return session.request(item_id=uuid4(), device_id=device, track_ref=ref, title=ref)


def test_F003_R005_pedir_pone_la_cancion_al_final_con_su_dispositivo() -> None:
    session = _open("A")
    session.events.clear()
    device = uuid4()

    item = _request(session, device, "yt:BBBBBBBBBBB")

    assert [queued.title for queued in session.pending()] == ["A", "yt:BBBBBBBBBBB"]
    assert item.requested_by == device
    assert item.state is QueueItemState.PENDING
    assert [event.type for event in session.events] == [SessionEventType.QUEUE_CHANGED]
    assert session.pending_of(device) == [item]


def test_F003_R006_con_5_pendientes_lanza_quota_exceeded() -> None:
    session = _open()
    device = uuid4()
    for number in range(QUOTA):
        _request(session, device, f"yt:{number}")
    session.events.clear()
    before = list(session.items)

    with pytest.raises(QuotaExceeded):
        _request(session, device, "yt:otra")

    # Un pedido rechazado no cambia la cola ni publica nada.
    assert session.items == before
    assert session.events == []
    assert QUOTA == 5


def test_F003_R006_el_cupo_es_de_cada_dispositivo() -> None:
    session = _open()
    full, other = uuid4(), uuid4()
    for number in range(QUOTA):
        _request(session, full, f"yt:{number}")

    item = _request(session, other, "yt:otra")

    assert session.pending_of(other) == [item]
    assert len(session.pending_of(full)) == QUOTA


def test_F003_R007_la_que_suena_se_salta_o_se_descarta_no_cuenta() -> None:
    session = _open()
    device = uuid4()
    items = [_request(session, device, f"yt:{number}") for number in range(QUOTA)]

    # Empieza a sonar la primera: deja de contar y hay cupo para otra.
    claim = session.claim_player(NOW)
    assert claim.current is not None and claim.current.item_id == items[0].id
    assert len(session.pending_of(device)) == QUOTA - 1
    _request(session, device, "yt:nueva")

    # La que suena se salta: sigue sin contar, y la siguiente que empieza tampoco.
    session.apply(
        PlayerEvent(epoch=claim.epoch, item_id=items[0].id, type=PlayerEventType.FAILED),
        NOW,
    )
    assert len(session.pending_of(device)) == QUOTA - 1

    # Al cerrar, las pendientes se descartan y ninguna cuenta.
    session.close(NOW)
    assert session.pending_of(device) == []


def test_F003_R008_pedir_con_la_sesion_cerrada_lanza_no_open_session() -> None:
    session = _open("A")
    session.close(NOW)
    session.events.clear()
    before = list(session.items)

    with pytest.raises(NoOpenSession):
        _request(session, uuid4(), "yt:BBBBBBBBBBB")
    assert session.items == before
    assert session.events == []


def test_F003_R009_una_pendiente_no_se_puede_volver_a_pedir() -> None:
    session = _open()
    first, second = uuid4(), uuid4()
    _request(session, first, "yt:AAAAAAAAAAA")
    session.events.clear()

    # Ni otro dispositivo ni el mismo: ya está pendiente.
    for device in (second, first):
        with pytest.raises(AlreadyQueued):
            _request(session, device, "yt:AAAAAAAAAAA")

    # El rechazo no gasta cupo ni cambia la cola.
    assert session.pending_of(second) == []
    assert len(session.pending()) == 1
    assert session.events == []

    # Con el cupo lleno, el aviso es que ya está en la cola: esperar a tener cupo no
    # serviría de nada.
    for number in range(QUOTA - 1):
        _request(session, first, f"yt:{number}")
    assert len(session.pending_of(first)) == QUOTA
    with pytest.raises(AlreadyQueued):
        _request(session, first, "yt:AAAAAAAAAAA")


def test_F003_R009_una_que_ya_sono_si_se_puede_pedir() -> None:
    session = _open()
    device = uuid4()
    played = _request(session, device, "yt:AAAAAAAAAAA")
    claim = session.claim_player(NOW)
    session.apply(
        PlayerEvent(epoch=claim.epoch, item_id=played.id, type=PlayerEventType.ENDED), NOW
    )
    assert played.state is QueueItemState.PLAYED

    again = _request(session, device, "yt:AAAAAAAAAAA")

    assert again.state is QueueItemState.PENDING
    assert again.id != played.id


def test_F003_R005_la_herramienta_de_desarrollo_agrega_sin_dispositivo() -> None:
    session = _open()

    item = session.enqueue(item_id=uuid4(), track_ref="fake:3s", title="Canción")

    assert item.requested_by is None
