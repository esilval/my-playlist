"""Caso de uso: pedir la recuperación de la contraseña (R016, plan D7).

La respuesta es la misma exista o no la cuenta: solo cambia que, si existe, se
encola el enlace a la dirección que guardó el titular.
"""

from dataclasses import dataclass

from app.accounts.domain.email_quota import WINDOW, quota_allows
from app.accounts.domain.email_token import RESET_TTL, TokenPurpose, new_token
from app.accounts.domain.ports import AccountsUnitOfWork, Clock
from app.accounts.domain.registration import normalize_email
from app.shared.email.templates import EmailTemplate


@dataclass(frozen=True)
class RequestPasswordReset:
    unit_of_work: AccountsUnitOfWork
    clock: Clock
    public_base_url: str

    async def __call__(self, email: str) -> None:
        email_normalized = normalize_email(email)
        async with self.unit_of_work() as accounts:
            account = await accounts.find_owner_by_email(email_normalized)
        if account is None:
            return

        now = self.clock.now()
        token, token_hash = new_token()
        # El establecimiento sale de la base, no del cliente (D4).
        async with self.unit_of_work(account.establishment_id) as accounts:
            holder_email = await accounts.account_email(account.account_id)
            previous = await accounts.recent_email_times(
                to_address_normalized=normalize_email(holder_email),
                template=EmailTemplate.PASSWORD_RESET,
                since=now - WINDOW,
            )
            if not quota_allows(previous, now):
                # Límite alcanzado: misma respuesta, sin enlace nuevo (R027).
                return
            await accounts.add_email_token(
                establishment_id=account.establishment_id,
                account_id=account.account_id,
                purpose=TokenPurpose.RESET,
                token_hash=token_hash,
                created_at=now,
                expires_at=now + RESET_TTL,
            )
            await accounts.enqueue_email(
                establishment_id=account.establishment_id,
                to_address=holder_email,
                to_address_normalized=normalize_email(holder_email),
                template=EmailTemplate.PASSWORD_RESET,
                payload={"link": f"{self.public_base_url}/restablecer?token={token}"},
                created_at=now,
            )
