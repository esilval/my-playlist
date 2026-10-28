import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.shared.config import LOCAL_REALTIME_TICKET_SECRET, Settings
from app.shared.realtime_ticket import InvalidTicket, TicketRole, issue_ticket, verify_ticket

SECRET = "secreto-de-pruebas-del-ticket-0123456789"
NOW = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)
# Los mismos vectores que valida el servicio de tiempo real (ADR-0014).
VECTORS = Path(__file__).resolve().parents[3] / "realtime" / "test" / "fixtures"
VECTORS = VECTORS / "ticket-vectors.json"


def test_F002_R013_ticket_caduca_a_los_60_s() -> None:
    establishment_id = uuid4()
    ticket = issue_ticket(SECRET, establishment_id=establishment_id, role=TicketRole.OWNER, now=NOW)

    claims = verify_ticket(SECRET, ticket, NOW + timedelta(seconds=59))
    assert (claims.establishment_id, claims.role) == (establishment_id, TicketRole.OWNER)

    with pytest.raises(InvalidTicket, match="caducado"):
        verify_ticket(SECRET, ticket, NOW + timedelta(seconds=60))


def test_F002_R013_ticket_alterado_o_de_otro_secreto_no_vale() -> None:
    ticket = issue_ticket(SECRET, establishment_id=uuid4(), role=TicketRole.PLAYER, now=NOW)
    segment, signature = ticket.split(".")
    # Un carácter distinto del último, para que el contenido cambie de verdad.
    altered = segment[:-1] + ("B" if segment[-1] == "A" else "A")

    for forged in (
        f"{altered}.{signature}",
        f"{segment}.{signature[:-1]}",
        segment,
        issue_ticket(
            "otro-secreto-de-al-menos-32-caracteres!",
            establishment_id=uuid4(),
            role=TicketRole.OWNER,
            now=NOW,
        ),
    ):
        with pytest.raises(InvalidTicket):
            verify_ticket(SECRET, forged, NOW)


def test_F002_R013_vectores_del_ticket_coinciden_con_el_monolito() -> None:
    vectors = json.loads(VECTORS.read_text())
    secret = vectors["secret"]
    issued_at = datetime.fromtimestamp(vectors["issued_at"], UTC)

    for vector in vectors["valid"]:
        # El archivo que valida C6 es exactamente lo que firma el monolito.
        assert vector["ticket"] == issue_ticket(
            secret,
            establishment_id=UUID(vector["establishment_id"]),
            role=TicketRole(vector["role"]),
            now=issued_at,
            ticket_id=vector["ticket_id"],
        )
        claims = verify_ticket(secret, vector["ticket"], datetime.fromtimestamp(vector["now"], UTC))
        assert (str(claims.establishment_id), str(claims.role)) == (
            vector["establishment_id"],
            vector["role"],
        )
    # Cada vector inválido falla por el motivo que dice su campo `reason`.
    expected = {"expired": "caducado", "signature": "firma"}
    for vector in vectors["invalid"]:
        with pytest.raises(InvalidTicket, match=expected[vector["reason"]]):
            verify_ticket(secret, vector["ticket"], datetime.fromtimestamp(vector["now"], UTC))


def test_F002_R013_produccion_no_arranca_sin_secreto_propio() -> None:
    def production(secret: str) -> Settings:
        return Settings(
            env="production",
            email_backend="ses",
            data_policy_version="2026-10",
            realtime_ticket_secret=secret,
            catalog_provider="youtube",
            youtube_api_key="clave-de-produccion-de-pruebas",
            device_token_secret="secreto-de-produccion-de-al-menos-32-caracteres",
        )

    for secret in (LOCAL_REALTIME_TICKET_SECRET, "", "corto"):
        with pytest.raises(ValidationError, match="REALTIME_TICKET_SECRET"):
            production(secret)

    assert production("x" * 32).realtime_ticket_secret == "x" * 32
