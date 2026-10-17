"""Adaptador Argon2id del puerto PasswordHasher (plan D3, ADR-0007)."""

import logging
import secrets

from argon2 import PasswordHasher as _Argon2
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.shared.config import Settings

logger = logging.getLogger(__name__)


class Argon2PasswordHasher:
    def __init__(
        self,
        *,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> None:
        self._argon2 = _Argon2(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            type=Type.ID,
        )
        # Hash de una contraseña aleatoria que nadie conoce, con los mismos parámetros.
        self._dummy_hash = self._argon2.hash(secrets.token_urlsafe(32))

    @classmethod
    def from_settings(cls, settings: Settings) -> "Argon2PasswordHasher":
        return cls(
            time_cost=settings.argon2_time_cost,
            memory_cost=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        )

    def hash(self, password: str) -> str:
        return self._argon2.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        if password_hash is None:
            self._check(self._dummy_hash, password)
            return False
        return self._check(password_hash, password)

    def _check(self, password_hash: str, password: str) -> bool:
        try:
            return self._argon2.verify(password_hash, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError):
            # Un hash guardado corrupto no debe pasar inadvertido; nunca se registra el hash.
            logger.warning("hash de contraseña con formato inválido")
            return False
