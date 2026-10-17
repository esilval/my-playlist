"""Caso de uso: la imagen del QR del establecimiento (R009, R010, R018, plan D6).

Solo con el correo verificado: el bloqueo vive en el servidor, no en la pantalla.
"""

from dataclasses import dataclass

import anyio

from app.accounts.domain.ports import AccountsUnitOfWork, QrImageRenderer
from app.accounts.interface import OwnerContext


class EmailNotVerified(Exception):
    pass


@dataclass(frozen=True)
class QrImage:
    png: bytes
    public_code: str


@dataclass(frozen=True)
class GetQr:
    unit_of_work: AccountsUnitOfWork
    renderer: QrImageRenderer
    public_base_url: str

    async def __call__(self, owner: OwnerContext) -> QrImage:
        if not owner.email_verified:
            raise EmailNotVerified
        async with self.unit_of_work(owner.establishment_id) as accounts:
            profile = await accounts.owner_profile(owner.account_id, owner.establishment_id)
        # El QR codifica el código público, que no cambia; el nombre solo va impreso (R009).
        url = f"{self.public_base_url}/l/{profile.public_code}"
        # Componer el PNG es CPU: fuera del bucle de eventos.
        png = await anyio.to_thread.run_sync(self.renderer.render, url, profile.name)
        return QrImage(png=png, public_code=profile.public_code)
