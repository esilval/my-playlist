"""Rutas públicas del cliente que pide canciones desde el QR (feature 003, plan D5).

Bajo `/api/public/establishments/{code}/`, sin sesión iniciada. El establecimiento sale
del código del QR (C1, D5) y el cliente se identifica con la cookie `mp_device`: un
identificador anónimo, firmado y ligado a ese establecimiento (D3, ADR-0007). Su `Path`
la limita a las rutas de ese establecimiento, así que no viaja a las de otro.

Composición: resuelven el código con C1, buscan con C3 y piden y consultan con C2. Las
reglas viven en esos módulos; aquí solo se traducen a HTTP.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.accounts.interface import EstablishmentIdByPublicCode
from app.catalog.interface import (
    CatalogTrack,
    CatalogUnavailable,
    SearchRateExceeded,
    SearchTracks,
)
from app.sessions.interface import (
    AlreadyQueued,
    ClientState,
    ClientView,
    NoOpenSession,
    QuotaExceeded,
    RequestTrack,
    UnknownTrack,
)
from app.shared.device_token import DeviceTokens, InvalidDeviceToken
from app.shared.realtime_ticket import TICKET_TTL, RealtimeTicketIssuer, TicketRole

router = APIRouter(prefix="/public/establishments/{code}")

DEVICE_COOKIE = "mp_device"
# La cookie dura un año (D3); el cupo es de la sesión de música, no de la cookie.
DEVICE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
# Texto de búsqueda (D1) y referencia de un pedido (D5).
MAX_QUERY_LENGTH = 100
MAX_REF_LENGTH = 64

NOT_FOUND = {"error": "not_found"}
DEVICE_REQUIRED = {"error": "device_required"}
NO_OPEN_SESSION = {"error": "no_open_session"}
QUOTA_EXCEEDED = {"error": "quota_exceeded"}
ALREADY_QUEUED = {"error": "already_queued"}
UNKNOWN_TRACK = {"error": "unknown_track"}
SEARCH_UNAVAILABLE = {"error": "search_unavailable"}
TOO_MANY_SEARCHES = {"error": "too_many_searches"}


class NowPlayingOut(BaseModel):
    title: str


class RequestedTrackOut(BaseModel):
    item_id: UUID
    title: str


class QuotaOut(BaseModel):
    limit: int
    free: int


class ClientMusicOut(BaseModel):
    status: Literal["open", "closed"]
    now_playing: NowPlayingOut | None
    mine: list[RequestedTrackOut]
    quota: QuotaOut


class RequestsOut(BaseModel):
    mine: list[RequestedTrackOut]
    quota: QuotaOut


class TrackResultOut(BaseModel):
    ref: str
    title: str
    author: str


class SearchOut(BaseModel):
    results: list[TrackResultOut]


class TicketOut(BaseModel):
    ticket: str
    expires_in: int


class RequestIn(BaseModel):
    # La referencia opaca de un resultado de la búsqueda (S4): el título lo pone C3.
    ref: str = Field(min_length=1, max_length=MAX_REF_LENGTH)


def _mine(state: ClientState) -> list[RequestedTrackOut]:
    return [RequestedTrackOut(item_id=track.item_id, title=track.title) for track in state.mine]


def _quota(state: ClientState) -> QuotaOut:
    return QuotaOut(limit=state.quota_limit, free=state.quota_free)


def _music_out(state: ClientState) -> ClientMusicOut:
    return ClientMusicOut(
        status="open" if state.open else "closed",
        now_playing=NowPlayingOut(title=state.now_playing) if state.now_playing else None,
        mine=_mine(state),
        quota=_quota(state),
    )


def _results_out(tracks: list[CatalogTrack]) -> SearchOut:
    return SearchOut(
        results=[TrackResultOut(ref=t.ref, title=t.title, author=t.author) for t in tracks]
    )


def _error(status_code: int, body: dict[str, str], **headers: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body, headers=headers or None)


async def _establishment(request: Request, code: str) -> UUID | None:
    lookup: EstablishmentIdByPublicCode = request.app.state.establishment_id_by_public_code
    return await lookup(code)


def _device(request: Request, establishment_id: UUID) -> UUID | None:
    """El dispositivo de la cookie, si es válida para este establecimiento (R011)."""
    token = request.cookies.get(DEVICE_COOKIE)
    if token is None:
        return None
    tokens: DeviceTokens = request.app.state.device_tokens
    try:
        return tokens.verify(token, establishment_id)
    except InvalidDeviceToken:
        return None


def _set_device_cookie(response: Response, code: str, token: str) -> None:
    response.set_cookie(
        DEVICE_COOKIE,
        token,
        max_age=DEVICE_COOKIE_MAX_AGE,
        path=f"/api/public/establishments/{code}/",
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.get(
    "/music",
    response_model=ClientMusicOut,
    responses={404: {"description": "not_found"}},
)
async def client_music(
    code: str, request: Request, response: Response
) -> ClientMusicOut | JSONResponse:
    """El estado del cliente (R001, R008, R010). Emite la cookie del dispositivo si falta o
    no vale para este establecimiento: entonces es un dispositivo nuevo (R002, R011)."""
    establishment_id = await _establishment(request, code)
    if establishment_id is None:
        return _error(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    device_id = _device(request, establishment_id)
    if device_id is None:
        tokens: DeviceTokens = request.app.state.device_tokens
        token, device_id = tokens.issue(establishment_id)
        _set_device_cookie(response, code, token)
    view: ClientView = request.app.state.client_view
    return _music_out(await view(establishment_id, device_id))


@router.get(
    "/search",
    response_model=SearchOut,
    responses={
        401: {"description": "device_required"},
        404: {"description": "not_found"},
        409: {"description": "no_open_session"},
        429: {"description": "too_many_searches"},
        503: {"description": "search_unavailable"},
    },
)
async def client_search(
    code: str,
    request: Request,
    q: Annotated[
        str, Query(description=f"Texto a buscar, de 1 a {MAX_QUERY_LENGTH} caracteres.")
    ] = "",
) -> SearchOut | JSONResponse:
    """Busca en el catálogo (R003). Con la sesión cerrada no se busca (R008); más de 10
    búsquedas por minuto dan 429 (R013) y el proveedor caído, 503 (R012)."""
    establishment_id = await _establishment(request, code)
    if establishment_id is None:
        return _error(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    device_id = _device(request, establishment_id)
    if device_id is None:
        return _error(status.HTTP_401_UNAUTHORIZED, DEVICE_REQUIRED)
    query = q.strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        # Vacío o de más de 100 caracteres (D1), con el formato de los errores de campo.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"errors": {"q": "invalid"}}
        )
    view: ClientView = request.app.state.client_view
    if not (await view(establishment_id, device_id)).open:
        return _error(status.HTTP_409_CONFLICT, NO_OPEN_SESSION)
    search: SearchTracks = request.app.state.search_tracks
    try:
        tracks = await search(establishment_id, device_id, query)
    except SearchRateExceeded as limited:
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            TOO_MANY_SEARCHES,
            **{"Retry-After": str(limited.retry_after)},
        )
    except CatalogUnavailable:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, SEARCH_UNAVAILABLE)
    return _results_out(tracks)


@router.post(
    "/requests",
    response_model=RequestsOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "device_required"},
        404: {"description": "not_found"},
        409: {"description": "no_open_session · quota_exceeded · already_queued"},
        422: {"description": "unknown_track"},
        503: {"description": "search_unavailable"},
    },
)
async def client_request(
    code: str, body: RequestIn, request: Request
) -> RequestsOut | JSONResponse:
    """Pide una canción (R005). La rechazan la sesión cerrada (R008), el cupo lleno
    (R006), una canción ya pendiente (R009) o una que ya no se puede reproducir (R014)."""
    establishment_id = await _establishment(request, code)
    if establishment_id is None:
        return _error(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    device_id = _device(request, establishment_id)
    if device_id is None:
        return _error(status.HTTP_401_UNAUTHORIZED, DEVICE_REQUIRED)
    request_track: RequestTrack = request.app.state.request_track
    try:
        state = await request_track(establishment_id, device_id, body.ref)
    except NoOpenSession:
        return _error(status.HTTP_409_CONFLICT, NO_OPEN_SESSION)
    except QuotaExceeded:
        return _error(status.HTTP_409_CONFLICT, QUOTA_EXCEEDED)
    except AlreadyQueued:
        return _error(status.HTTP_409_CONFLICT, ALREADY_QUEUED)
    except UnknownTrack:
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, UNKNOWN_TRACK)
    except CatalogUnavailable:
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, SEARCH_UNAVAILABLE)
    return RequestsOut(mine=_mine(state), quota=_quota(state))


@router.post(
    "/realtime-ticket",
    response_model=TicketOut,
    responses={401: {"description": "device_required"}, 404: {"description": "not_found"}},
)
async def client_realtime_ticket(
    code: str, request: Request, response: Response
) -> TicketOut | JSONResponse:
    """Ticket de tiempo real de tipo `client` (ADR-0014, plan D6): con él, el navegador se
    une a la sala de este establecimiento y recibe los cambios de la cola (R010). Pide la
    cookie del dispositivo, así que solo vale para el establecimiento de esa cookie (R011)."""
    establishment_id = await _establishment(request, code)
    if establishment_id is None:
        return _error(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if _device(request, establishment_id) is None:
        return _error(status.HTTP_401_UNAUTHORIZED, DEVICE_REQUIRED)
    issuer: RealtimeTicketIssuer = request.app.state.realtime_tickets
    # Un ticket no se guarda en ninguna caché: se pide uno nuevo en cada conexión.
    response.headers["Cache-Control"] = "no-store"
    ticket = issuer.issue(establishment_id=establishment_id, role=TicketRole.CLIENT)
    return TicketOut(ticket=ticket, expires_in=int(TICKET_TTL.total_seconds()))
