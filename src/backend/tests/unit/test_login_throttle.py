from datetime import UTC, datetime, timedelta

from app.accounts.domain.login_throttle import LOOKBACK, is_locked, locked_until

START = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)


def _minutes(*offsets: float) -> list[datetime]:
    return [START + timedelta(minutes=m) for m in offsets]


def test_F001_R007_bloquea_tras_5_fallos_en_15_min() -> None:
    failures = _minutes(0, 1, 2, 3, 4)

    assert not is_locked(failures[:4], START + timedelta(minutes=4))
    assert is_locked(failures, START + timedelta(minutes=4, seconds=1))


def test_F001_R007_desbloquea_pasados_15_min() -> None:
    failures = _minutes(0, 1, 2, 3, 4)

    # 15 minutos completos desde el quinto fallo (minuto 4), no desde el primero.
    assert is_locked(failures, START + timedelta(minutes=18, seconds=59))
    assert not is_locked(failures, START + timedelta(minutes=19))
    assert locked_until(failures) == START + timedelta(minutes=19)


def test_F001_R007_cinco_fallos_repartidos_en_mas_de_15_min_no_bloquean() -> None:
    failures = _minutes(0, 4, 8, 12, 15.5)

    assert locked_until(failures) is None
    assert not is_locked(failures, START + timedelta(minutes=16))


def test_F001_R007_cinco_fallos_justo_en_15_min_bloquean() -> None:
    assert locked_until(_minutes(0, 5, 10, 14, 15)) == START + timedelta(minutes=30)


def test_F001_R007_fallos_desordenados_y_varios_bloqueos() -> None:
    first = _minutes(0, 1, 2, 3, 4)
    second = _minutes(40, 41, 42, 43, 44)

    assert locked_until(list(reversed(second + first))) == START + timedelta(minutes=59)


def test_F001_R007_basta_consultar_los_ultimos_30_minutos() -> None:
    assert timedelta(minutes=30) == LOOKBACK
