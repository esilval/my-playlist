"""Caso de uso: fijar una contraseña nueva con el enlace de recuperación (R016, R021).

En la misma transacción se guarda el hash nuevo, se gasta el enlace y se revocan
todas las sesiones abiertas de la cuenta (plan D2).
"""

from dataclasses import dataclass

from app.accounts.domain.email_token import TokenPurpose, hash_token, is_reset_usable
from app.accounts.domain.ports import AccountsUnitOfWork, Clock, PasswordHasher
from app.accounts.domain.registration import RegistrationRejected, password_error
from app.shared.cpu import run_cpu_bound


class InvalidResetToken(Exception):
    """Enlace inexistente, alterado, ya usado o caducado."""


@dataclass(frozen=True)
class ConfirmPasswordReset:
    unit_of_work: AccountsUnitOfWork
    hasher: PasswordHasher
    clock: Clock

    async def __call__(self, token: str, password: str) -> None:
        """Lanza RegistrationRejected si la contraseña nueva no vale, o InvalidResetToken."""
        if (error := password_error(password)) is not None:
            raise RegistrationRejected({"password": error})
        # Argon2 es CPU (plan D3): fuera del bucle de eventos.
        password_hash = await run_cpu_bound(self.hasher.hash, password)
        now = self.clock.now()

        async with self.unit_of_work() as accounts:
            record = await accounts.email_token_by_hash(hash_token(token), TokenPurpose.RESET)
            if record is None or not is_reset_usable(record.state, now):
                raise InvalidResetToken
            await accounts.use_establishment(record.establishment_id)
            # Atómico: si otra petición lo gastó o caducó desde la lectura, no vale.
            if not await accounts.use_email_token(record.token_id, now):
                raise InvalidResetToken
            await accounts.set_password_hash(record.account_id, password_hash)
            await accounts.revoke_all_sessions(record.account_id, now)
