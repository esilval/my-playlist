from datetime import UTC, datetime, timedelta

from app.accounts.domain.ports import Clock
from app.accounts.domain.session_policy import IDLE_TIMEOUT, is_session_active

START = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def test_F001_R020_caduca_tras_12h_sin_actividad() -> None:
    clock: Clock = FakeClock(START)
    assert isinstance(clock, FakeClock)
    clock.advance(timedelta(hours=12))
    assert is_session_active(last_seen_at=START, revoked_at=None, now=clock.now())

    clock.advance(timedelta(seconds=1))
    assert not is_session_active(last_seen_at=START, revoked_at=None, now=clock.now())
    assert timedelta(hours=12) == IDLE_TIMEOUT


def test_F001_R020_actividad_cada_pocas_horas_mantiene_14h() -> None:
    clock = FakeClock(START)
    last_seen = START
    for _ in range(5):  # 5 peticiones, una cada 3 h: 15 h de uso continuado
        clock.advance(timedelta(hours=3))
        assert is_session_active(last_seen_at=last_seen, revoked_at=None, now=clock.now())
        last_seen = clock.now()

    assert clock.now() - START >= timedelta(hours=14)
    # Sin renovar la actividad, a las 14 h la misma sesión ya habría caducado.
    assert not is_session_active(last_seen_at=START, revoked_at=None, now=clock.now())


def test_F001_R008_sesion_revocada_no_esta_activa() -> None:
    assert not is_session_active(last_seen_at=START, revoked_at=START, now=START)
