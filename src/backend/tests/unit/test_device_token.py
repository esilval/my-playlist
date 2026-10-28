import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.shared.device_token import (
    DeviceTokens,
    InvalidDeviceToken,
    issue_device_token,
    verify_device_token,
)

SECRET = "secreto-de-pruebas-del-dispositivo-0123456789"
NOW = datetime(2026, 10, 27, 20, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


def test_F003_R002_el_token_del_dispositivo_se_verifica_con_su_establecimiento() -> None:
    establishment_id = uuid4()
    token, device = issue_device_token(SECRET, establishment_id=establishment_id, now=NOW)

    assert verify_device_token(SECRET, token, establishment_id=establishment_id) == device
    # Lo mismo con el emisor de la app, con el secreto y el reloj de la configuración.
    tokens = DeviceTokens(secret=SECRET, clock=FixedClock())
    issued, issued_device = tokens.issue(establishment_id)
    assert tokens.verify(issued, establishment_id) == issued_device


def test_F003_R002_dos_tokens_tienen_dispositivos_distintos() -> None:
    establishment_id = uuid4()
    first, first_device = issue_device_token(SECRET, establishment_id=establishment_id, now=NOW)
    second, second_device = issue_device_token(SECRET, establishment_id=establishment_id, now=NOW)

    assert first_device != second_device
    assert first != second
    # El token solo lleva el establecimiento, el dispositivo y la fecha: ningún dato del
    # cliente (S9).
    segment = first.split(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    assert set(payload) == {"est", "dev", "iat"}


def test_F003_R011_token_de_otro_establecimiento_no_vale() -> None:
    token, _ = issue_device_token(SECRET, establishment_id=uuid4(), now=NOW)

    with pytest.raises(InvalidDeviceToken, match="otro establecimiento"):
        verify_device_token(SECRET, token, establishment_id=uuid4())


def test_F003_R011_token_alterado_o_de_otro_secreto_no_vale() -> None:
    establishment_id = uuid4()
    token, _ = issue_device_token(SECRET, establishment_id=establishment_id, now=NOW)
    segment, signature = token.split(".")
    # Un carácter del medio cambiado: la firma, calculada sobre el segmento, ya no vale.
    middle = len(segment) // 2
    altered = segment[:middle] + ("B" if segment[middle] == "A" else "A") + segment[middle + 1 :]
    other_secret, _ = issue_device_token(
        "otro-secreto-de-al-menos-32-caracteres!", establishment_id=establishment_id, now=NOW
    )

    for forged in (
        f"{altered}.{signature}",
        f"{segment}.{signature[:-1]}",
        segment,
        "",
        "no-es-un-token",
        f"{segment}.firma-con-ñ",
        other_secret,
    ):
        with pytest.raises(InvalidDeviceToken):
            verify_device_token(SECRET, forged, establishment_id=establishment_id)


def test_F003_R011_token_bien_firmado_pero_mal_formado_no_vale() -> None:
    establishment_id = uuid4()
    for payload in (
        {"est": str(establishment_id), "iat": 0},
        {"est": str(establishment_id), "dev": "no-es-un-uuid", "iat": 0},
        ["no", "es", "un", "objeto"],
    ):
        segment = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        signature = (
            base64.urlsafe_b64encode(
                hmac.new(SECRET.encode(), segment.encode(), hashlib.sha256).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        with pytest.raises(InvalidDeviceToken, match="mal formado"):
            verify_device_token(SECRET, f"{segment}.{signature}", establishment_id=establishment_id)
