"""Caso de uso: reenviar el enlace de verificación (R018, plan D11).

El enlace nuevo reemplaza a los anteriores: abrir uno viejo ya no verifica (R026).
"""

from dataclasses import dataclass

from app.accounts.application.verification_link import issue_verification_link
from app.accounts.domain.email_quota import WINDOW, quota_allows
from app.accounts.domain.email_token import TokenPurpose
from app.accounts.domain.ports import AccountsUnitOfWork, Clock
from app.accounts.domain.registration import normalize_email
from app.accounts.interface import OwnerContext
from app.shared.email.templates import EmailTemplate


class AlreadyVerified(Exception):
    pass


class ResendRateLimited(Exception):
    """Ya se reenviaron 3 enlaces en la última hora (R027)."""


RESEND_ORIGIN = "resend"


@dataclass(frozen=True)
class ResendVerification:
    unit_of_work: AccountsUnitOfWork
    clock: Clock
    public_base_url: str

    async def __call__(self, owner: OwnerContext) -> None:
        if owner.email_verified:
            raise AlreadyVerified
        now = self.clock.now()
        async with self.unit_of_work(owner.establishment_id) as accounts:
            # La sesión pudo resolverse antes de una verificación concurrente.
            if await accounts.email_verified(owner.account_id):
                raise AlreadyVerified
            email = await accounts.account_email(owner.account_id)
            previous = await accounts.recent_email_times(
                to_address_normalized=normalize_email(email),
                template=EmailTemplate.VERIFY_EMAIL,
                since=now - WINDOW,
                origin=RESEND_ORIGIN,
            )
            if not quota_allows(previous, now):
                raise ResendRateLimited
            await accounts.supersede_email_tokens(owner.account_id, TokenPurpose.VERIFY, now)
            await issue_verification_link(
                accounts,
                establishment_id=owner.establishment_id,
                account_id=owner.account_id,
                email=email,
                email_normalized=normalize_email(email),
                establishment_name=await accounts.establishment_name(owner.establishment_id),
                now=now,
                public_base_url=self.public_base_url,
                origin=RESEND_ORIGIN,
            )
