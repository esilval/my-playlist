"""Puertos del dominio de cuentas: lo que el dominio necesita del exterior (S1)."""

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.accounts.domain.data_policy import DataPolicy
from app.accounts.domain.email_token import TokenPurpose, VerificationTokenState
from app.accounts.domain.establishment import EstablishmentChanges
from app.accounts.domain.registration import ValidRegistration


class Clock(Protocol):
    def now(self) -> datetime:
        """Instante actual, con zona horaria."""
        ...


class PasswordHasher(Protocol):
    """Hash de contraseñas (plan D3). Ninguna contraseña se guarda ni se lee en claro."""

    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str | None, password: str) -> bool:
        """`password_hash=None` es un correo sin cuenta: se verifica contra un hash
        ficticio y se devuelve False, con el mismo coste que una contraseña errónea
        (R006: el tiempo de respuesta no revela si el correo existe)."""
        ...


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    """Envío de correo transaccional (ADR-0011). Lanza una excepción si el envío falla;
    los reintentos los gestiona la bandeja de salida, no el adaptador."""

    async def send(self, message: EmailMessage) -> None: ...


class PolicyStore(Protocol):
    def get(self, version: str) -> DataPolicy:
        """Lanza KeyError si esa versión de la política no existe."""
        ...


class EmailAlreadyRegistered(Exception):
    """El correo normalizado ya pertenece a una cuenta (R024)."""


@dataclass(frozen=True)
class AccountRef:
    account_id: UUID
    establishment_id: UUID


@dataclass(frozen=True)
class Credentials:
    account_id: UUID
    establishment_id: UUID
    password_hash: str


@dataclass(frozen=True)
class EmailTokenRecord:
    token_id: UUID
    account_id: UUID
    establishment_id: UUID
    state: VerificationTokenState


@dataclass(frozen=True)
class OwnerProfile:
    email: str
    email_verified: bool
    name: str
    address: str | None
    phone: str | None
    public_code: str


@dataclass(frozen=True)
class SessionRecord:
    session_id: UUID
    account_id: UUID
    establishment_id: UUID
    last_seen_at: datetime
    revoked_at: datetime | None


class AccountsRepository(Protocol):
    """Operaciones de C1 dentro de una transacción con el contexto RLS ya fijado."""

    async def use_establishment(self, establishment_id: UUID) -> None:
        """Fija el contexto RLS a mitad de transacción, con un id resuelto por el servidor."""
        ...

    async def lock_login(self, email_normalized: str) -> None:
        """Serializa los inicios de sesión de un mismo correo hasta fin de transacción."""
        ...

    async def credentials_by_email(self, email_normalized: str) -> Credentials | None: ...

    async def login_failures_since(
        self, email_normalized: str, since: datetime
    ) -> list[datetime]: ...

    async def record_login_attempt(
        self, email_normalized: str, *, succeeded: bool, at: datetime
    ) -> None: ...

    async def create_session(
        self, *, establishment_id: UUID, account_id: UUID, token_hash: bytes, now: datetime
    ) -> None: ...

    async def session_by_token_hash(self, token_hash: bytes) -> SessionRecord | None: ...

    async def touch_session(self, session_id: UUID, now: datetime) -> None: ...

    async def revoke_session(self, session_id: UUID, now: datetime) -> None: ...

    async def email_verified(self, account_id: UUID) -> bool: ...

    async def email_token_by_hash(
        self, token_hash: bytes, purpose: TokenPurpose
    ) -> EmailTokenRecord | None: ...

    async def use_email_token(self, token_id: UUID, now: datetime) -> bool:
        """Marca el token como usado si sigue vigente; False si otra petición lo usó o lo
        reemplazó entre la lectura y el marcado (un solo uso, R026)."""
        ...

    async def mark_email_verified(self, account_id: UUID, now: datetime) -> None: ...

    async def supersede_email_tokens(
        self, account_id: UUID, purpose: TokenPurpose, now: datetime
    ) -> None: ...

    async def establishment_name(self, establishment_id: UUID) -> str: ...

    async def set_password_hash(self, account_id: UUID, password_hash: str) -> None: ...

    async def recent_email_times(
        self,
        *,
        to_address_normalized: str,
        template: str,
        since: datetime,
        origin: str | None = None,
    ) -> list[datetime]:
        """Cuándo se encolaron los correos de una plantilla a un destinatario (R027).

        Con `origin`, solo los marcados así en su payload (p. ej. los reenvíos).
        """
        ...

    async def owner_profile(self, account_id: UUID, establishment_id: UUID) -> OwnerProfile: ...

    async def update_establishment(
        self, establishment_id: UUID, changes: EstablishmentChanges, now: datetime
    ) -> None: ...

    async def public_establishment_name(self, public_code: str) -> str | None:
        """Solo el nombre, por el código del QR, sin sesión (R012, R013)."""
        ...

    async def public_establishment_id(self, public_code: str) -> UUID | None:
        """Solo el identificador, por el código del QR, sin sesión (feature 003, plan
        D5): para fijar el contexto de las rutas del cliente."""
        ...

    async def revoke_all_sessions(self, account_id: UUID, now: datetime) -> None: ...

    async def find_owner_by_email(self, email_normalized: str) -> AccountRef | None:
        """Busca la cuenta por correo antes de conocer el establecimiento (plan D4)."""
        ...

    async def account_email(self, account_id: UUID) -> str:
        """Dirección guardada de la cuenta, leída con RLS en su establecimiento."""
        ...

    async def create_owner(
        self,
        *,
        establishment_id: UUID,
        registration: ValidRegistration,
        password_hash: str,
        granted_at: datetime,
    ) -> UUID:
        """Crea establecimiento, cuenta y autorización; devuelve el id de la cuenta.

        Lanza EmailAlreadyRegistered si el correo ya tiene cuenta.
        """
        ...

    async def add_email_token(
        self,
        *,
        establishment_id: UUID,
        account_id: UUID,
        purpose: TokenPurpose,
        token_hash: bytes,
        created_at: datetime,
        expires_at: datetime,
    ) -> None: ...

    async def enqueue_email(
        self,
        *,
        establishment_id: UUID,
        to_address: str,
        to_address_normalized: str,
        template: str,
        payload: Mapping[str, str],
        created_at: datetime,
    ) -> None: ...


class AccountsUnitOfWork(Protocol):
    def __call__(
        self, establishment_id: UUID | None = None
    ) -> AbstractAsyncContextManager[AccountsRepository]: ...


class QrImageRenderer(Protocol):
    def render(self, url: str, establishment_name: str) -> bytes:
        """PNG con el QR que codifica `url` y el nombre del local debajo (R010, D6)."""
        ...
