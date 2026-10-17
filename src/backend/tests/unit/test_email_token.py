from datetime import UTC, datetime, timedelta

from app.accounts.domain.email_token import (
    RESET_TTL,
    VERIFY_TTL,
    VerificationTokenState,
    VerifyOutcome,
    classify_verification,
    hash_token,
    is_reset_usable,
    new_token,
)

ISSUED = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def _state(**overrides: object) -> VerificationTokenState:
    values: dict[str, object] = {
        "used_at": None,
        "superseded_at": None,
        "expires_at": ISSUED + RESET_TTL,
        "email_verified": False,
    }
    values.update(overrides)
    return VerificationTokenState(**values)  # type: ignore[arg-type]


def test_F001_R016_enlace_caducado_a_los_60_min() -> None:
    assert timedelta(minutes=60) == RESET_TTL
    assert is_reset_usable(_state(), ISSUED + timedelta(minutes=59, seconds=59))
    assert not is_reset_usable(_state(), ISSUED + timedelta(minutes=60))


def test_F001_R016_enlace_de_un_solo_uso_en_el_dominio() -> None:
    assert not is_reset_usable(_state(used_at=ISSUED), ISSUED + timedelta(minutes=1))
    assert not is_reset_usable(None, ISSUED)
    assert not is_reset_usable(_state(expires_at=None), ISSUED)


def test_token_de_enlace_se_guarda_como_hash() -> None:
    raw, stored = new_token()

    assert stored == hash_token(raw)
    assert raw.encode() not in stored
    assert new_token()[0] != raw


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def _verify_state(**overrides: object) -> VerificationTokenState:
    return _state(expires_at=ISSUED + VERIFY_TTL, **overrides)


def test_F001_R028_token_de_8_dias_caducado() -> None:
    clock = FakeClock(ISSUED)
    clock.advance(timedelta(days=8))

    assert timedelta(days=7) == VERIFY_TTL
    assert classify_verification(_verify_state(), clock.now()) is VerifyOutcome.EXPIRED


def test_F001_R028_token_de_6_dias_vigente() -> None:
    clock = FakeClock(ISSUED)
    clock.advance(timedelta(days=6))

    assert classify_verification(_verify_state(), clock.now()) is VerifyOutcome.VERIFY
    # El límite: a los 7 días justos ya caducó.
    clock.advance(timedelta(days=1))
    assert classify_verification(_verify_state(), clock.now()) is VerifyOutcome.EXPIRED


def test_F001_R028_usado_y_caducado_sigue_already_verified() -> None:
    clock = FakeClock(ISSUED + timedelta(days=30))
    used = _verify_state(used_at=ISSUED + timedelta(hours=1), email_verified=True)

    assert classify_verification(used, clock.now()) is VerifyOutcome.ALREADY_VERIFIED


def test_F001_R028_caducado_y_reemplazado_se_informa_como_caducado() -> None:
    superseded = _verify_state(superseded_at=ISSUED + timedelta(days=1))

    assert classify_verification(superseded, ISSUED + timedelta(days=8)) is VerifyOutcome.EXPIRED
    assert classify_verification(superseded, ISSUED + timedelta(days=2)) is VerifyOutcome.INVALID


def test_F001_R028_sin_fecha_de_caducidad_no_vale_para_siempre() -> None:
    assert classify_verification(_state(expires_at=None), ISSUED) is VerifyOutcome.EXPIRED
