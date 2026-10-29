"""Repositorio SQL de cuentas y establecimientos (C1) sobre la unidad de trabajo con RLS."""

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.accounts.domain.email_token import TokenPurpose, VerificationTokenState
from app.accounts.domain.establishment import EstablishmentChanges
from app.accounts.domain.ports import (
    AccountRef,
    Credentials,
    EmailAlreadyRegistered,
    EmailTokenRecord,
    OwnerProfile,
    SessionRecord,
)
from app.accounts.domain.public_code import generate_public_code
from app.accounts.domain.registration import ValidRegistration
from app.shared.db import Database, set_establishment
from app.shared.email.templates import EmailTemplate
from app.shared.outbox import enqueue

# Con ~50 bits por código, repetir uno ya es improbable; dos seguidos, imposible en la práctica.
PUBLIC_CODE_ATTEMPTS = 3


def _violates(error: IntegrityError, constraint: str) -> bool:
    return constraint in str(error.orig)


class SqlAccountsRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def use_establishment(self, establishment_id: UUID) -> None:
        await set_establishment(self._connection, establishment_id)

    async def lock_login(self, email_normalized: str) -> None:
        await self._connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:e, 0))"), {"e": email_normalized}
        )

    async def credentials_by_email(self, email_normalized: str) -> Credentials | None:
        row = (
            await self._connection.execute(
                text(
                    "SELECT account_id, establishment_id, password_hash "
                    "FROM auth_account_by_email(:e)"
                ),
                {"e": email_normalized},
            )
        ).one_or_none()
        if row is None:
            return None
        return Credentials(
            account_id=row.account_id,
            establishment_id=row.establishment_id,
            password_hash=row.password_hash,
        )

    async def login_failures_since(self, email_normalized: str, since: datetime) -> list[datetime]:
        rows = await self._connection.execute(
            text(
                "SELECT attempted_at FROM login_attempt WHERE email_normalized = :e "
                "AND NOT succeeded AND attempted_at >= :since"
            ),
            {"e": email_normalized, "since": since},
        )
        return list(rows.scalars())

    async def record_login_attempt(
        self, email_normalized: str, *, succeeded: bool, at: datetime
    ) -> None:
        await self._connection.execute(
            text(
                "INSERT INTO login_attempt (email_normalized, attempted_at, succeeded) "
                "VALUES (:e, :at, :ok)"
            ),
            {"e": email_normalized, "at": at, "ok": succeeded},
        )

    async def create_session(
        self, *, establishment_id: UUID, account_id: UUID, token_hash: bytes, now: datetime
    ) -> None:
        await self._connection.execute(
            text(
                "INSERT INTO owner_session (establishment_id, account_id, token_hash, "
                "created_at, last_seen_at) VALUES (:e, :a, :h, :now, :now)"
            ),
            {"e": establishment_id, "a": account_id, "h": token_hash, "now": now},
        )

    async def session_by_token_hash(self, token_hash: bytes) -> SessionRecord | None:
        row = (
            await self._connection.execute(
                text("SELECT * FROM auth_session(:h)"), {"h": token_hash}
            )
        ).one_or_none()
        if row is None:
            return None
        return SessionRecord(
            session_id=row.session_id,
            account_id=row.account_id,
            establishment_id=row.establishment_id,
            last_seen_at=row.last_seen_at,
            revoked_at=row.revoked_at,
        )

    async def touch_session(self, session_id: UUID, now: datetime) -> None:
        await self._connection.execute(
            text("UPDATE owner_session SET last_seen_at = :now WHERE id = :id"),
            {"id": session_id, "now": now},
        )

    async def revoke_session(self, session_id: UUID, now: datetime) -> None:
        await self._connection.execute(
            text(
                "UPDATE owner_session SET revoked_at = :now WHERE id = :id AND revoked_at IS NULL"
            ),
            {"id": session_id, "now": now},
        )

    async def email_verified(self, account_id: UUID) -> bool:
        verified: bool = (
            await self._connection.execute(
                text("SELECT email_verified_at IS NOT NULL FROM owner_account WHERE id = :id"),
                {"id": account_id},
            )
        ).scalar_one()
        return verified

    async def email_token_by_hash(
        self, token_hash: bytes, purpose: TokenPurpose
    ) -> EmailTokenRecord | None:
        row = (
            await self._connection.execute(
                text("SELECT * FROM auth_email_token(:h, CAST(:p AS email_token_purpose))"),
                {"h": token_hash, "p": str(purpose)},
            )
        ).one_or_none()
        if row is None:
            return None
        return EmailTokenRecord(
            token_id=row.token_id,
            account_id=row.account_id,
            establishment_id=row.establishment_id,
            state=VerificationTokenState(
                used_at=row.used_at,
                superseded_at=row.superseded_at,
                expires_at=row.expires_at,
                email_verified=row.email_verified,
            ),
        )

    async def use_email_token(self, token_id: UUID, now: datetime) -> bool:
        result = await self._connection.execute(
            # Se vuelve a comprobar en el UPDATE: un reenvío concurrente pudo reemplazarlo
            # después de leerlo (R026).
            text(
                "UPDATE email_token SET used_at = :now "
                "WHERE id = :id AND used_at IS NULL AND superseded_at IS NULL "
                "AND (expires_at IS NULL OR expires_at > :now)"
            ),
            {"id": token_id, "now": now},
        )
        return bool(result.rowcount)

    async def mark_email_verified(self, account_id: UUID, now: datetime) -> None:
        await self._connection.execute(
            text(
                "UPDATE owner_account SET email_verified_at = :now "
                "WHERE id = :id AND email_verified_at IS NULL"
            ),
            {"id": account_id, "now": now},
        )

    async def supersede_email_tokens(
        self, account_id: UUID, purpose: TokenPurpose, now: datetime
    ) -> None:
        await self._connection.execute(
            text(
                "UPDATE email_token SET superseded_at = :now WHERE account_id = :a "
                "AND purpose = CAST(:p AS email_token_purpose) "
                "AND used_at IS NULL AND superseded_at IS NULL"
            ),
            {"a": account_id, "p": str(purpose), "now": now},
        )

    async def establishment_name(self, establishment_id: UUID) -> str:
        name: str = (
            await self._connection.execute(
                text("SELECT name FROM establishment WHERE id = :id"), {"id": establishment_id}
            )
        ).scalar_one()
        return name

    async def owner_profile(self, account_id: UUID, establishment_id: UUID) -> OwnerProfile:
        row = (
            await self._connection.execute(
                text(
                    "SELECT a.email, a.email_verified_at IS NOT NULL AS email_verified, "
                    "e.name, e.address, e.phone, e.public_code "
                    "FROM owner_account a JOIN establishment e ON e.id = a.establishment_id "
                    "WHERE a.id = :a AND e.id = :e"
                ),
                {"a": account_id, "e": establishment_id},
            )
        ).one()
        return OwnerProfile(
            email=row.email,
            email_verified=row.email_verified,
            name=row.name,
            address=row.address,
            phone=row.phone,
            public_code=row.public_code,
        )

    async def update_establishment(
        self, establishment_id: UUID, changes: EstablishmentChanges, now: datetime
    ) -> None:
        if not changes.values:
            return
        # Las columnas salen de una lista cerrada, nunca de la petición.
        allowed = ("name", "address", "phone")
        assignments = ", ".join(f"{col} = :{col}" for col in allowed if col in changes.values)
        await self._connection.execute(
            text(f"UPDATE establishment SET {assignments}, updated_at = :now WHERE id = :id"),
            {**changes.values, "id": establishment_id, "now": now},
        )

    async def public_establishment_name(self, public_code: str) -> str | None:
        name: str | None = (
            await self._connection.execute(
                text("SELECT name FROM public_establishment(:code)"), {"code": public_code}
            )
        ).scalar_one_or_none()
        return name

    async def public_establishment_id(self, public_code: str) -> UUID | None:
        establishment_id: UUID | None = (
            await self._connection.execute(
                text("SELECT establishment_id FROM public_establishment_id(:code)"),
                {"code": public_code},
            )
        ).scalar_one_or_none()
        return establishment_id

    async def recent_email_times(
        self,
        *,
        to_address_normalized: str,
        template: str,
        since: datetime,
        origin: str | None = None,
    ) -> list[datetime]:
        # Dentro del contexto RLS del establecimiento ya resuelto (plan D7).
        rows = await self._connection.execute(
            text(
                "SELECT created_at FROM email_outbox WHERE to_address_normalized = :to "
                "AND template = CAST(:t AS email_template) AND created_at >= :since "
                "AND (CAST(:origin AS text) IS NULL OR payload->>'origin' = :origin)"
            ),
            {"to": to_address_normalized, "t": template, "since": since, "origin": origin},
        )
        return list(rows.scalars())

    async def set_password_hash(self, account_id: UUID, password_hash: str) -> None:
        await self._connection.execute(
            text("UPDATE owner_account SET password_hash = :h WHERE id = :id"),
            {"id": account_id, "h": password_hash},
        )

    async def revoke_all_sessions(self, account_id: UUID, now: datetime) -> None:
        await self._connection.execute(
            text(
                "UPDATE owner_session SET revoked_at = :now "
                "WHERE account_id = :a AND revoked_at IS NULL"
            ),
            {"a": account_id, "now": now},
        )

    async def find_owner_by_email(self, email_normalized: str) -> AccountRef | None:
        row = (
            await self._connection.execute(
                text("SELECT account_id, establishment_id FROM auth_account_by_email(:e)"),
                {"e": email_normalized},
            )
        ).one_or_none()
        if row is None:
            return None
        return AccountRef(account_id=row.account_id, establishment_id=row.establishment_id)

    async def account_email(self, account_id: UUID) -> str:
        email: str = (
            await self._connection.execute(
                text("SELECT email FROM owner_account WHERE id = :id"), {"id": account_id}
            )
        ).scalar_one()
        return email

    async def create_owner(
        self,
        *,
        establishment_id: UUID,
        registration: ValidRegistration,
        password_hash: str,
        granted_at: datetime,
    ) -> UUID:
        await self._insert_establishment(establishment_id, registration)
        try:
            async with self._connection.begin_nested():
                account_id: UUID = (
                    await self._connection.execute(
                        text(
                            "INSERT INTO owner_account (establishment_id, email, "
                            "email_normalized, password_hash) "
                            "VALUES (:e, :email, :email_n, :hash) RETURNING id"
                        ),
                        {
                            "e": establishment_id,
                            "email": registration.email,
                            "email_n": registration.email_normalized,
                            "hash": password_hash,
                        },
                    )
                ).scalar_one()
        except IntegrityError as error:
            if _violates(error, "owner_account_email_normalized_key"):
                raise EmailAlreadyRegistered from None
            raise
        await self._connection.execute(
            text(
                "INSERT INTO data_authorization (establishment_id, account_id, "
                "policy_version, granted_at) VALUES (:e, :a, :v, :t)"
            ),
            {
                "e": establishment_id,
                "a": account_id,
                "v": registration.policy_version,
                "t": granted_at,
            },
        )
        return account_id

    async def _insert_establishment(
        self, establishment_id: UUID, registration: ValidRegistration
    ) -> None:
        for attempt in range(PUBLIC_CODE_ATTEMPTS):
            try:
                async with self._connection.begin_nested():
                    await self._connection.execute(
                        text(
                            "INSERT INTO establishment (id, establishment_id, public_code, "
                            "name, address, phone) "
                            "VALUES (:id, :id, :code, :name, :address, :phone)"
                        ),
                        {
                            "id": establishment_id,
                            "code": generate_public_code(),
                            "name": registration.establishment_name,
                            "address": registration.address,
                            "phone": registration.phone,
                        },
                    )
                return
            except IntegrityError as error:
                if not _violates(error, "establishment_public_code_key"):
                    raise
                if attempt == PUBLIC_CODE_ATTEMPTS - 1:
                    raise

    async def add_email_token(
        self,
        *,
        establishment_id: UUID,
        account_id: UUID,
        purpose: TokenPurpose,
        token_hash: bytes,
        created_at: datetime,
        expires_at: datetime,
    ) -> None:
        await self._connection.execute(
            text(
                "INSERT INTO email_token (establishment_id, account_id, purpose, token_hash, "
                "created_at, expires_at) "
                "VALUES (:e, :a, CAST(:p AS email_token_purpose), :h, :c, :x)"
            ),
            {
                "e": establishment_id,
                "a": account_id,
                "p": str(purpose),
                "h": token_hash,
                "c": created_at,
                "x": expires_at,
            },
        )

    async def enqueue_email(
        self,
        *,
        establishment_id: UUID,
        to_address: str,
        to_address_normalized: str,
        template: str,
        payload: Mapping[str, str],
        created_at: datetime,
    ) -> None:
        await enqueue(
            self._connection,
            establishment_id=establishment_id,
            to_address=to_address,
            to_address_normalized=to_address_normalized,
            template=EmailTemplate(template),
            payload=payload,
            created_at=created_at,
        )


class SqlAccountsUnitOfWork:
    """Abre una transacción con el rol de la API y el establecimiento fijado (D4)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @asynccontextmanager
    async def __call__(
        self, establishment_id: UUID | None = None
    ) -> AsyncIterator[SqlAccountsRepository]:
        async with self._db.transaction(establishment_id) as connection:
            yield SqlAccountsRepository(connection)
