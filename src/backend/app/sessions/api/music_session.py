"""Rutas de la sesión de música del panel (plan Contratos: /api/owner/music-session).

Ninguna recibe el establecimiento: sale de la sesión iniciada del propietario, igual
que el resto del panel (R013, plan D1).
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.accounts.api.deps import CurrentOwner
from app.sessions.application.close_session import CloseMusicSession
from app.sessions.application.get_session import GetMusicSession, MusicSessionState
from app.sessions.application.open_session import EmailNotVerified, OpenMusicSession

router = APIRouter(prefix="/owner/music-session")


class TrackOut(BaseModel):
    item_id: UUID
    title: str
    track_ref: str


class FailureOut(BaseModel):
    title: str
    failed_at: datetime


class SessionOut(BaseModel):
    id: UUID
    opened_at: datetime
    version: int
    now_playing: TrackOut | None
    player_active: bool
    failures: list[FailureOut]


class SessionEnvelope(BaseModel):
    session: SessionOut


class MusicSessionOut(BaseModel):
    status: Literal["open", "closed"]
    session: SessionOut | None = None


def _session_out(state: MusicSessionState) -> SessionOut:
    playing = state.now_playing
    return SessionOut(
        id=state.id,
        opened_at=state.opened_at,
        version=state.version,
        now_playing=(
            TrackOut(item_id=playing.item_id, title=playing.title, track_ref=playing.track_ref)
            if playing is not None
            else None
        ),
        player_active=state.player_active,
        failures=[FailureOut(title=f.title, failed_at=f.failed_at) for f in state.failures],
    )


def _open(request: Request) -> OpenMusicSession:
    use_case: OpenMusicSession = request.app.state.open_music_session
    return use_case


def _close(request: Request) -> CloseMusicSession:
    use_case: CloseMusicSession = request.app.state.close_music_session
    return use_case


def _get(request: Request) -> GetMusicSession:
    use_case: GetMusicSession = request.app.state.get_music_session
    return use_case


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionEnvelope,
    responses={
        200: {"model": SessionEnvelope, "description": "ya estaba abierta (R003)"},
        403: {"description": "email_not_verified"},
    },
)
async def open_music_session(
    owner: CurrentOwner,
    open_session: Annotated[OpenMusicSession, Depends(_open)],
    response: Response,
) -> SessionEnvelope | JSONResponse:
    try:
        opened = await open_session(owner)
    except EmailNotVerified:
        return JSONResponse(status_code=403, content={"error": "email_not_verified"})
    if not opened.created:
        response.status_code = status.HTTP_200_OK
    return SessionEnvelope(session=_session_out(opened.state))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def close_music_session(
    owner: CurrentOwner, close_session: Annotated[CloseMusicSession, Depends(_close)]
) -> Response:
    # Idempotente: sin una sesión abierta también responde 204 (R011).
    await close_session(owner)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=MusicSessionOut)
async def get_music_session(
    owner: CurrentOwner, get_session: Annotated[GetMusicSession, Depends(_get)]
) -> MusicSessionOut:
    state = await get_session(owner)
    if state is None:
        return MusicSessionOut(status="closed")
    return MusicSessionOut(status="open", session=_session_out(state))
