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
from app.accounts.interface import (
    EstablishmentByPublicCode,
    EstablishmentIdByPublicCode,
    ResolveOwner,
)
from app.catalog.domain.catalog import MusicCatalog
from app.catalog.infrastructure.cache import RedisCatalogCache
from app.catalog.infrastructure.fake import FakeCatalog
from app.catalog.infrastructure.youtube import YouTubeCatalog
from app.catalog.interface import SearchTracks, TrackLookup
from app.sessions.api import client, music_session, player, realtime
from app.sessions.application.advance_player import AdvancePlayer
from app.sessions.application.claim_player import ClaimPlayer
from app.sessions.application.client_view import ClientView
from app.sessions.application.close_session import CloseMusicSession
from app.sessions.application.get_session import GetMusicSession
from app.sessions.application.heartbeat import PlayerHeartbeat
from app.sessions.application.open_session import OpenMusicSession
from app.sessions.application.report_player_event import ReportPlayerEvent
from app.sessions.application.request_track import RequestTrack
from app.sessions.infrastructure.redis_publisher import RedisEventPublisher
from app.sessions.infrastructure.repositories import SqlSessionsUnitOfWork
from app.shared.clock import SystemClock
from app.shared.config import Settings, get_settings
from app.shared.csrf import CsrfMiddleware, HstsMiddleware
from app.shared.db import Database
from app.shared.device_token import DeviceTokens
from app.shared.realtime_ticket import RealtimeTicketIssuer

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
    # Eventos de la sesión de música hacia el tiempo real (plan D6 de la feature 002).
    publisher = RedisEventPublisher.from_url(settings.redis_url)
    # Catálogo de música (feature 003, plan D1, D2, D8).
    youtube = (
        YouTubeCatalog(settings.youtube_api_key) if settings.catalog_provider == "youtube" else None
    )
    catalog: MusicCatalog = youtube or FakeCatalog()
    catalog_cache = RedisCatalogCache.from_url(settings.redis_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await publisher.aclose()
        await catalog_cache.aclose()
        if youtube is not None:
            await youtube.aclose()
        await db.dispose()

    app = FastAPI(title="MyPlaylist API", lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_middleware(CsrfMiddleware, allowed_origin=settings.public_base_url)
    app.add_middleware(HstsMiddleware)
    app.state.settings = settings
    app.state.db = db
    app.state.event_publisher = publisher
    app.state.policy_store = policy_store
    unit_of_work = SqlAccountsUnitOfWork(db)
    hasher = Argon2PasswordHasher.from_settings(settings)
    clock = SystemClock()
    app.state.login_owner = LoginOwner(unit_of_work=unit_of_work, hasher=hasher, clock=clock)
    app.state.logout_owner = LogoutOwner(unit_of_work=unit_of_work, clock=clock)
    app.state.resolve_owner = ResolveOwner(unit_of_work=unit_of_work, clock=clock)
    app.state.establishment_by_public_code = EstablishmentByPublicCode(unit_of_work=unit_of_work)
    app.state.establishment_id_by_public_code = EstablishmentIdByPublicCode(
        unit_of_work=unit_of_work
    )
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
    sessions = SqlSessionsUnitOfWork(db)
    app.state.open_music_session = OpenMusicSession(
        unit_of_work=sessions, publisher=publisher, clock=clock
    )
    app.state.close_music_session = CloseMusicSession(
        unit_of_work=sessions, publisher=publisher, clock=clock
    )
    app.state.get_music_session = GetMusicSession(unit_of_work=sessions, clock=clock)
    app.state.claim_player = ClaimPlayer(unit_of_work=sessions, publisher=publisher, clock=clock)
    app.state.player_heartbeat = PlayerHeartbeat(unit_of_work=sessions, clock=clock)
    app.state.advance_player = AdvancePlayer(unit_of_work=sessions, publisher=publisher)
    app.state.realtime_tickets = RealtimeTicketIssuer(
        secret=settings.realtime_ticket_secret, clock=clock
    )
    app.state.report_player_event = ReportPlayerEvent(
        unit_of_work=sessions, publisher=publisher, clock=clock
    )
    # El cliente que pide canciones desde el QR (feature 003).
    track_lookup = TrackLookup(catalog=catalog)
    app.state.search_tracks = SearchTracks(catalog=catalog, cache=catalog_cache)
    app.state.track_lookup = track_lookup
    app.state.request_track = RequestTrack(
        unit_of_work=sessions, publisher=publisher, lookup=track_lookup
    )
    app.state.client_view = ClientView(unit_of_work=sessions)
    app.state.device_tokens = DeviceTokens(secret=settings.device_token_secret, clock=clock)
    app.include_router(health_router, prefix="/api")
    # Antes que `public`: su ruta `/public/establishments/{code:path}` atraparía también
    # las del cliente, `…/{code}/music` (feature 003, plan D5).
    app.include_router(client.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(owner.router, prefix="/api")
    app.include_router(music_session.router, prefix="/api")
    app.include_router(player.router, prefix="/api")
    app.include_router(realtime.router, prefix="/api")
    return app


app = create_app()
