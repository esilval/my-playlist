"""Caso de uso: abrir el enlace de verificación (R017, R025, R026, R028, plan D11).

El primer uso verifica el correo y abre una sesión; reabrirlo dice «ya verificado»
sin abrir otra; un enlace inexistente, alterado, reemplazado o caducado no hace nada.
"""

from dataclasses import dataclass

from app.accounts.domain.email_token import (
    TokenPurpose,
    VerifyOutcome,
    classify_verification,
    hash_token,
)
from app.accounts.domain.ports import AccountsUnitOfWork, Clock
from app.accounts.domain.session_policy import new_session_token


class InvalidVerificationToken(Exception):
    """Enlace inexistente, alterado o reemplazado (R026)."""


class ExpiredVerificationToken(Exception):
    """Enlace sin usar emitido hace más de 7 días (R028)."""


@dataclass(frozen=True)
class Verified:
    # Token de la sesión nueva; None si el correo ya estaba verificado.
    session_token: str | None


@dataclass(frozen=True)
class VerifyEmail:
    unit_of_work: AccountsUnitOfWork
    clock: Clock

    async def __call__(self, token: str) -> Verified:
        now = self.clock.now()
        async with self.unit_of_work() as accounts:
            record = await accounts.email_token_by_hash(hash_token(token), TokenPurpose.VERIFY)
            outcome = classify_verification(record.state if record else None, now)
            if outcome is VerifyOutcome.EXPIRED:
                raise ExpiredVerificationToken
            if record is None or outcome is VerifyOutcome.INVALID:
                raise InvalidVerificationToken
            if outcome is VerifyOutcome.ALREADY_VERIFIED:
                return Verified(session_token=None)

            await accounts.use_establishment(record.establishment_id)
            if not await accounts.use_email_token(record.token_id, now):
                # Otra petición lo usó o lo reemplazó entre la lectura y el marcado: se decide
                # con el estado actual, sin abrir sesión.
                current = await accounts.email_token_by_hash(hash_token(token), TokenPurpose.VERIFY)
                latest = classify_verification(current.state if current else None, now)
                if latest is VerifyOutcome.ALREADY_VERIFIED:
                    return Verified(session_token=None)
                if latest is VerifyOutcome.EXPIRED:
                    raise ExpiredVerificationToken
                raise InvalidVerificationToken
            await accounts.mark_email_verified(record.account_id, now)
            session_token, session_hash = new_session_token()
            await accounts.create_session(
                establishment_id=record.establishment_id,
                account_id=record.account_id,
                token_hash=session_hash,
                now=now,
            )
        return Verified(session_token=session_token)
