import time

import pytest

from app.accounts.domain.ports import PasswordHasher
from app.accounts.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.shared.config import Settings


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


def _elapsed(hasher: PasswordHasher, password_hash: str | None, password: str) -> float:
    start = time.perf_counter()
    hasher.verify(password_hash, password)
    return time.perf_counter() - start


def test_F001_R006_verificar_contra_hash_ficticio_devuelve_falso(hasher: PasswordHasher) -> None:
    assert hasher.verify(None, "cualquier-cosa") is False
    assert hasher.verify(None, "") is False


def test_F001_R006_hash_ficticio_cuesta_igual(hasher: PasswordHasher) -> None:
    stored = hasher.hash("contraseña-buena")
    wrong = min(_elapsed(hasher, stored, "contraseña-mala") for _ in range(3))
    missing = min(_elapsed(hasher, None, "contraseña-mala") for _ in range(3))

    # Ambos caminos hacen una verificación Argon2 completa con los mismos parámetros.
    assert 0.5 < missing / wrong < 2


def test_hash_es_argon2id_y_no_contiene_la_contrasena(hasher: PasswordHasher) -> None:
    password = "Café-Ñandú-2026"
    stored = hasher.hash(password)

    assert stored.startswith("$argon2id$")
    assert password not in stored
    assert stored != hasher.hash(password)  # sal aleatoria por hash


def test_verifica_la_correcta_y_rechaza_la_erronea_y_hashes_invalidos(
    hasher: PasswordHasher,
) -> None:
    stored = hasher.hash("12345678")

    assert hasher.verify(stored, "12345678") is True
    assert hasher.verify(stored, "12345679") is False
    assert hasher.verify("no-es-un-hash", "12345678") is False


def test_parametros_salen_de_la_configuracion() -> None:
    settings = Settings(argon2_time_cost=1, argon2_memory_cost_kib=8192, argon2_parallelism=1)

    stored = Argon2PasswordHasher.from_settings(settings).hash("12345678")

    assert stored.startswith("$argon2id$v=19$m=8192,t=1,p=1$")


def test_hash_corrupto_se_registra_sin_exponerlo(
    hasher: PasswordHasher, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        assert hasher.verify("$argon2id$roto", "12345678") is False
        assert hasher.verify("no-es-un-hash", "12345678") is False
        stored = hasher.hash("12345678")
        assert hasher.verify(stored, "otra") is False

    # Dos hashes corruptos se registran; una contraseña errónea no.
    assert caplog.text.count("hash de contraseña con formato inválido") == 2
    assert "$argon2id$roto" not in caplog.text
