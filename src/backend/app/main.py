"""Punto de entrada de la API del monolito."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.accounts.api import auth, owner, public
from app.accounts.application.confirm_password_reset import ConfirmPasswordReset
from app.accounts.application.get_owner import GetOwnerProfile
from app.accounts.application.get_qr import GetQr
from app.accounts.application.login import LoginOwner
from app.accounts.application.logout import LogoutOwner
from app.accounts.application.register import RegisterOwner
from app.accounts.application.request_password_reset import RequestPasswordReset
from app.accounts.application.resend_verification import ResendVerification
from app.accounts.application.update_establishment import UpdateEstablishment
from app.accounts.application.verify_email import VerifyEmail
from app.accounts.domain.ports import PolicyStore
from app.accounts.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.accounts.infrastructure.policy_files import FilePolicyStore
from app.accounts.infrastructure.qr_image import SegnoQrImageRenderer
from app.accounts.infrastructure.repositories import SqlAccountsUnitOfWork
from app.accounts.interface import EstablishmentByPublicCode, ResolveOwner
from app.shared.clock import SystemClock
from app.shared.config import Settings, get_settings
from app.shared.csrf import CsrfMiddleware, HstsMiddleware
from app.shared.db import Database

health_router = APIRouter()


@health_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    """422 con el formato del contrato `{errors: {campo: código}}`.

    Nunca devuelve el valor recibido: podría ser una contraseña (R003).
    """
    assert isinstance(exc, RequestValidationError)
    errors: dict[str, str] = {}
    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part != "body"]
        errors[location[0] if location else "body"] = "invalid"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"errors": errors}
    )


def create_app(
    settings: Settings | None = None, *, policy_store: PolicyStore | None = None
) -> FastAPI:
    settings = settings or get_settings()
    policy_store = policy_store or FilePolicyStore()
    # Comprobación de arranque: la versión vigente de la política tiene que existir (R022).
    policy_store.get(settings.data_policy_version)

    db = Database.from_url(settings.database_url, role="app_api")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await db.dispose()

    app = FastAPI(title="MyPlaylist API", lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_middleware(CsrfMiddleware, allowed_origin=settings.public_base_url)
    app.add_middleware(HstsMiddleware)
    app.state.settings = settings
    app.state.db = db
    app.state.policy_store = policy_store
    unit_of_work = SqlAccountsUnitOfWork(db)
    hasher = Argon2PasswordHasher.from_settings(settings)
    clock = SystemClock()
    app.state.login_owner = LoginOwner(unit_of_work=unit_of_work, hasher=hasher, clock=clock)
    app.state.logout_owner = LogoutOwner(unit_of_work=unit_of_work, clock=clock)
    app.state.resolve_owner = ResolveOwner(unit_of_work=unit_of_work, clock=clock)
    app.state.establishment_by_public_code = EstablishmentByPublicCode(unit_of_work=unit_of_work)
    app.state.verify_email = VerifyEmail(unit_of_work=unit_of_work, clock=clock)
    app.state.get_owner_profile = GetOwnerProfile(unit_of_work=unit_of_work)
    app.state.get_qr = GetQr(
        unit_of_work=unit_of_work,
        renderer=SegnoQrImageRenderer(),
        public_base_url=settings.public_base_url,
    )
    app.state.update_establishment = UpdateEstablishment(unit_of_work=unit_of_work, clock=clock)
    app.state.request_password_reset = RequestPasswordReset(
        unit_of_work=unit_of_work, clock=clock, public_base_url=settings.public_base_url
    )
    app.state.confirm_password_reset = ConfirmPasswordReset(
        unit_of_work=unit_of_work, hasher=hasher, clock=clock
    )
    app.state.resend_verification = ResendVerification(
        unit_of_work=unit_of_work, clock=clock, public_base_url=settings.public_base_url
    )
    app.state.register_owner = RegisterOwner(
        unit_of_work=unit_of_work,
        hasher=hasher,
        clock=clock,
        current_policy_version=settings.data_policy_version,
        public_base_url=settings.public_base_url,
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(owner.router, prefix="/api")
    return app


app = create_app()
