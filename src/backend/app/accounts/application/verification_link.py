"""Emisión del enlace de verificación: lo usan el registro (R017) y el reenvío (R018)."""

from datetime import datetime
from uuid import UUID

from app.accounts.domain.email_token import VERIFY_TTL, TokenPurpose, new_token
from app.accounts.domain.ports import AccountsRepository
from app.shared.email.templates import EmailTemplate


async def issue_verification_link(
    accounts: AccountsRepository,
    *,
    establishment_id: UUID,
    account_id: UUID,
    email: str,
    email_normalized: str,
    establishment_name: str,
    now: datetime,
    public_base_url: str,
    origin: str | None = None,
) -> None:
    """`origin="resend"` marca los reenvíos, que son los que cuenta el límite de R027."""
    token, token_hash = new_token()
    await accounts.add_email_token(
        establishment_id=establishment_id,
        account_id=account_id,
        purpose=TokenPurpose.VERIFY,
        token_hash=token_hash,
        # Una sola fuente de tiempo para crear y caducar el token (R028).
        created_at=now,
        expires_at=now + VERIFY_TTL,
    )
    await accounts.enqueue_email(
        establishment_id=establishment_id,
        to_address=email,
        to_address_normalized=email_normalized,
        template=EmailTemplate.VERIFY_EMAIL,
        payload={
            "establishment_name": establishment_name,
            "link": f"{public_base_url}/verificar?token={token}",
            **({"origin": origin} if origin else {}),
        },
        created_at=now,
    )
