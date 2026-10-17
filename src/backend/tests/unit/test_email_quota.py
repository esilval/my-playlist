from datetime import UTC, datetime, timedelta

from app.accounts.domain.email_quota import MAX_PER_WINDOW, WINDOW, quota_allows

START = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def test_F001_R027_cuarto_en_60_min_no_se_permite() -> None:
    clock = FakeClock(START)
    sent: list[datetime] = []
    for _ in range(MAX_PER_WINDOW):
        assert quota_allows(sent, clock.now())
        sent.append(clock.now())
        clock.advance(timedelta(minutes=10))

    assert MAX_PER_WINDOW == 3
    assert not quota_allows(sent, clock.now())


def test_F001_R027_pasada_la_hora_se_permite() -> None:
    sent = [START, START + timedelta(minutes=1), START + timedelta(minutes=2)]
    clock = FakeClock(START + timedelta(minutes=59, seconds=59))
    assert not quota_allows(sent, clock.now())

    # A los 60 minutos del primero, ese ya no cuenta.
    clock.advance(timedelta(seconds=1))
    assert timedelta(minutes=60) == WINDOW
    assert quota_allows(sent, clock.now())
