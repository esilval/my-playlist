"""Rutas del reproductor del local (plan Contratos: /api/owner/music-session/player).

Piden la sesión iniciada del propietario; el establecimiento sale de ella (R013).
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.accounts.api.deps import CurrentOwner
from app.sessions.api.music_session import TrackOut
from app.sessions.application.advance_player import AdvancePlayer
from app.sessions.application.claim_player import ClaimPlayer
from app.sessions.application.heartbeat import PlayerHeartbeat
from app.sessions.application.report_player_event import ReportPlayerEvent
from app.sessions.domain.music_session import (
    NoOpenSession,
    PlayerEvent,
    PlayerEventType,
    PlayerSuperseded,
    QueueItemNotFound,
)
from app.sessions.domain.queue import Track

router = APIRouter(prefix="/owner/music-session/player")

NO_OPEN_SESSION = {"error": "no_open_session"}
PLAYER_SUPERSEDED = {"error": "player_superseded"}
# Una canción que no es de esta sesión, por ejemplo la de otro establecimiento: el
# mismo cuerpo exista o no, sin revelar nada de ella (R013).
NOT_FOUND = {"error": "not_found"}


class ClaimOut(BaseModel):
    epoch: int
    current: TrackOut | None
    next: TrackOut | None


class PlayerEventIn(BaseModel):
    epoch: int
    item_id: UUID
    type: Literal["started", "ended", "failed"]
    # Por qué falló, tal como lo detectó el adaptador del proveedor (plan D5).
    reason: str | None = Field(default=None, max_length=100)


class ProgressOut(BaseModel):
    current: TrackOut | None
    next: TrackOut | None
    version: int


class HeartbeatIn(BaseModel):
    epoch: int


class HeartbeatOut(BaseModel):
    version: int


def track_out(track: Track | None) -> TrackOut | None:
    if track is None:
        return None
    return TrackOut(item_id=track.item_id, title=track.title, track_ref=track.track_ref)


def _claim(request: Request) -> ClaimPlayer:
    use_case: ClaimPlayer = request.app.state.claim_player
    return use_case


def _report(request: Request) -> ReportPlayerEvent:
    use_case: ReportPlayerEvent = request.app.state.report_player_event
    return use_case


def _advance(request: Request) -> AdvancePlayer:
    use_case: AdvancePlayer = request.app.state.advance_player
    return use_case


def _heartbeat(request: Request) -> PlayerHeartbeat:
    use_case: PlayerHeartbeat = request.app.state.player_heartbeat
    return use_case


@router.post(
    "",
    response_model=ClaimOut,
    responses={409: {"description": "no_open_session"}},
)
async def claim_player(
    owner: CurrentOwner, claim: Annotated[ClaimPlayer, Depends(_claim)]
) -> ClaimOut | JSONResponse:
    try:
        claimed = await claim(owner)
    except NoOpenSession:
        return JSONResponse(status_code=409, content=NO_OPEN_SESSION)
    return ClaimOut(
        epoch=claimed.epoch, current=track_out(claimed.current), next=track_out(claimed.next)
    )


@router.post(
    "/heartbeat",
    response_model=HeartbeatOut,
    responses={409: {"description": "player_superseded · no_open_session"}},
)
async def player_heartbeat(
    owner: CurrentOwner,
    body: HeartbeatIn,
    heartbeat: Annotated[PlayerHeartbeat, Depends(_heartbeat)],
) -> HeartbeatOut | JSONResponse:
    try:
        version = await heartbeat(owner, body.epoch)
    except NoOpenSession:
        return JSONResponse(status_code=409, content=NO_OPEN_SESSION)
    except PlayerSuperseded:
        return JSONResponse(status_code=409, content=PLAYER_SUPERSEDED)
    return HeartbeatOut(version=version)


@router.post(
    "/events",
    response_model=ProgressOut,
    responses={
        404: {"description": "not_found"},
        409: {"description": "player_superseded · no_open_session"},
    },
)
async def report_player_event(
    owner: CurrentOwner,
    body: PlayerEventIn,
    report: Annotated[ReportPlayerEvent, Depends(_report)],
) -> ProgressOut | JSONResponse:
    event = PlayerEvent(
        epoch=body.epoch, item_id=body.item_id, type=PlayerEventType(body.type), reason=body.reason
    )
    try:
        progress = await report(owner, event)
    except NoOpenSession:
        return JSONResponse(status_code=409, content=NO_OPEN_SESSION)
    except PlayerSuperseded:
        return JSONResponse(status_code=409, content=PLAYER_SUPERSEDED)
    except QueueItemNotFound:
        return JSONResponse(status_code=404, content=NOT_FOUND)
    return ProgressOut(
        current=track_out(progress.current),
        next=track_out(progress.next),
        version=progress.version,
    )


class AdvanceIn(BaseModel):
    epoch: int


@router.post(
    "/advance",
    response_model=ProgressOut,
    responses={409: {"description": "player_superseded · no_open_session"}},
)
async def advance_player(
    owner: CurrentOwner,
    body: AdvanceIn,
    advance: Annotated[AdvancePlayer, Depends(_advance)],
) -> ProgressOut | JSONResponse:
    """El reproductor en espera pide empezar la canción que entró (R008, D4)."""
    try:
        progress = await advance(owner, body.epoch)
    except NoOpenSession:
        return JSONResponse(status_code=409, content=NO_OPEN_SESSION)
    except PlayerSuperseded:
        return JSONResponse(status_code=409, content=PLAYER_SUPERSEDED)
    return ProgressOut(
        current=track_out(progress.current),
        next=track_out(progress.next),
        version=progress.version,
    )
