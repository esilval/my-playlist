"""Caso de uso: registro de un propietario (R023, R024, plan D11).

La respuesta es la misma tenga o no cuenta el correo, para que el registro no
revele qué correos están registrados (R024):

- Correo nuevo: crea establecimiento, cuenta y autorización sin iniciar sesión y
  encola el correo de verificación (R017). La sesión se abre al verificar (R025).
- Correo con cuenta: no crea nada y encola al titular un aviso del intento con
  enlaces para entrar y para recuperar la contraseña.

Las dos ramas calculan un hash Argon2 y escriben en la bandeja de salida, para que
el tiempo de respuesta tampoco las distinga. Excepción aceptada: tras 3 avisos en una
hora al mismo correo (R027), la rama del correo existente ya no escribe.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.accounts.application.verification_link import issue_verification_link
from app.accounts.domain.email_quota import WINDOW, quota_allows
from app.accounts.domain.ports import (
    AccountRef,
    AccountsUnitOfWork,
    Clock,
    EmailAlreadyRegistered,
    PasswordHasher,
)
from app.accounts.domain.registration import (
    RegistrationForm,
    ValidRegistration,
    normalize_email,
    validate_registration,
)
from app.shared.cpu import run_cpu_bound
from app.shared.email.templates import EmailTemplate


@dataclass(frozen=True)
class RegisterOwner:
    unit_of_work: AccountsUnitOfWork
    hasher: PasswordHasher
    clock: Clock
    current_policy_version: str
    public_base_url: str

    async def __call__(self, form: RegistrationForm) -> None:
        """Lanza RegistrationRejected con todos los campos inválidos (R003, R004, R022)."""
        registration = validate_registration(form, self.current_policy_version)
        # El hash, fuera de la transacción y en las dos ramas: es CPU y no depende de la base.
        # Argon2 es CPU (plan D3): fuera del bucle de eventos.
        password_hash = await run_cpu_bound(self.hasher.hash, registration.password)

        existing = await self._find(registration)
        if existing is None:
            try:
                await self._create(registration, password_hash)
                return
            except EmailAlreadyRegistered:
                # Otro registro con el mismo correo ganó la carrera entre buscar y crear;
                # la transacción de alta se deshizo entera.
                existing = await self._find(registration)
        if existing is not None:
            await self._notify_existing(registration, existing)

    async def _find(self, registration: ValidRegistration) -> AccountRef | None:
        async with self.unit_of_work() as accounts:
            return await accounts.find_owner_by_email(registration.email_normalized)

    async def _create(self, registration: ValidRegistration, password_hash: str) -> None:
        now: datetime = self.clock.now()
        establishment_id = uuid4()

        async with self.unit_of_work(establishment_id) as accounts:
            account_id = await accounts.create_owner(
                establishment_id=establishment_id,
                registration=registration,
                password_hash=password_hash,
                granted_at=now,
            )
            await issue_verification_link(
                accounts,
                establishment_id=establishment_id,
                account_id=account_id,
                email=registration.email,
                email_normalized=registration.email_normalized,
                establishment_name=registration.establishment_name,
                now=now,
                public_base_url=self.public_base_url,
            )

    async def _notify_existing(self, registration: ValidRegistration, existing: AccountRef) -> None:
        # El establecimiento sale de la base (auth_account_by_email), no del cliente (D4).
        async with self.unit_of_work(existing.establishment_id) as accounts:
            # El aviso va a la dirección que guardó el titular, no a la que escribió el
            # visitante: el destino no lo decide un desconocido.
            holder_email = await accounts.account_email(existing.account_id)
            now = self.clock.now()
            previous = await accounts.recent_email_times(
                to_address_normalized=normalize_email(holder_email),
                template=EmailTemplate.REGISTRATION_ATTEMPT,
                since=now - WINDOW,
            )
            if not quota_allows(previous, now):
                # Límite alcanzado: la respuesta al visitante no cambia (R024, R027).
                return
            await accounts.enqueue_email(
                establishment_id=existing.establishment_id,
                to_address=holder_email,
                to_address_normalized=normalize_email(holder_email),
                template=EmailTemplate.REGISTRATION_ATTEMPT,
                payload={
                    "login_link": f"{self.public_base_url}/entrar",
                    "reset_link": f"{self.public_base_url}/recuperar",
                },
                created_at=now,
            )
