"""Caso de uso: inicio de sesión del propietario (R005, R006, R007, plan D2, D3, D5)."""

from dataclasses import dataclass

from app.accounts.domain.login_throttle import LOOKBACK, is_locked
from app.accounts.domain.ports import AccountsUnitOfWork, Clock, PasswordHasher
from app.accounts.domain.registration import normalize_email
from app.accounts.domain.session_policy import new_session_token
from app.shared.cpu import run_cpu_bound


class InvalidCredentials(Exception):
    """Correo o contraseña incorrectos; nunca se dice cuál (R006)."""


class TooManyAttempts(Exception):
    """El correo está bloqueado por intentos fallidos (R007)."""


@dataclass(frozen=True)
class LoginOwner:
    unit_of_work: AccountsUnitOfWork
    hasher: PasswordHasher
    clock: Clock

    async def __call__(self, email: str, password: str) -> str:
        """Devuelve el token de la nueva sesión."""
        email_normalized = normalize_email(email)
        now = self.clock.now()

        token, token_hash = new_session_token()
        # Una sola transacción, serializada por correo: varias peticiones en paralelo no
        # pueden probar más contraseñas de las que permite el bloqueo (R007).
        async with self.unit_of_work() as accounts:
            await accounts.lock_login(email_normalized)
            failures = await accounts.login_failures_since(email_normalized, now - LOOKBACK)
            if is_locked(failures, now):
                # Bloqueado: no se verifica la contraseña ni se registra como fallo (D5).
                raise TooManyAttempts
            credentials = await accounts.credentials_by_email(email_normalized)
            # Sin cuenta se verifica contra el hash ficticio: mismo coste, mismo resultado (D3).
            # Argon2 es CPU (plan D3): fuera del bucle de eventos, también con el hash ficticio.
            stored = credentials.password_hash if credentials else None
            valid = await run_cpu_bound(self.hasher.verify, stored, password)
            await accounts.record_login_attempt(email_normalized, succeeded=valid, at=now)
            if valid and credentials is not None:
                await accounts.use_establishment(credentials.establishment_id)
                await accounts.create_session(
                    establishment_id=credentials.establishment_id,
                    account_id=credentials.account_id,
                    token_hash=token_hash,
                    now=now,
                )
        if not valid:
            raise InvalidCredentials
        return token
