"""Ticket de tiempo real para el panel y el reproductor (ADR-0014, plan D6).

El navegador lo pide antes de cada conexión o reconexión al servicio de tiempo real.
El establecimiento sale de la sesión iniciada, nunca del cuerpo (R013).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from app.accounts.api.deps import CurrentOwner
from app.shared.realtime_ticket import TICKET_TTL, RealtimeTicketIssuer, TicketRole

router = APIRouter(prefix="/owner")


class TicketIn(BaseModel):
    role: Literal["owner", "player"]


class TicketOut(BaseModel):
    ticket: str
    expires_in: int


def _issuer(request: Request) -> RealtimeTicketIssuer:
    issuer: RealtimeTicketIssuer = request.app.state.realtime_tickets
    return issuer


@router.post("/realtime-ticket", response_model=TicketOut)
async def realtime_ticket(
    owner: CurrentOwner,
    body: TicketIn,
    issuer: Annotated[RealtimeTicketIssuer, Depends(_issuer)],
    response: Response,
) -> TicketOut:
    # Un ticket no se guarda en ninguna caché: se pide uno nuevo en cada conexión.
    response.headers["Cache-Control"] = "no-store"
    ticket = issuer.issue(establishment_id=owner.establishment_id, role=TicketRole(body.role))
    return TicketOut(ticket=ticket, expires_in=int(TICKET_TTL.total_seconds()))
