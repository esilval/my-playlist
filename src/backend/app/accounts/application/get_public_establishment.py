"""Caso de uso: la página que abre el QR (R012, R013).

Sin sesión y sin pedir nada al visitante; devuelve solo el nombre del local.
"""

from dataclasses import dataclass

from app.accounts.domain.ports import AccountsUnitOfWork
from app.accounts.domain.public_code import is_public_code


@dataclass(frozen=True)
class PublicEstablishment:
    name: str


@dataclass(frozen=True)
class GetPublicEstablishment:
    unit_of_work: AccountsUnitOfWork

    async def __call__(self, public_code: str) -> PublicEstablishment | None:
        # Un código mal formado ni llega a la base: algunos (p. ej. con NUL) la harían fallar.
        if not is_public_code(public_code):
            return None
        async with self.unit_of_work() as accounts:
            name = await accounts.public_establishment_name(public_code)
        return PublicEstablishment(name=name) if name is not None else None
