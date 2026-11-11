"""Registros del trabajador sin direcciones ni contenido (feature 004, R016, plan D11)."""

import json
import os
import smtplib
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from app.accounts.domain.ports import EmailMessage
from app.shared.email.templates import EmailTemplate
from app.shared.outbox import MAX_ATTEMPTS, OutboxDispatcher, _Claimed

pytestmark = pytest.mark.anyio

BACKEND_DIR = Path(__file__).resolve().parents[2]
ADDRESS = "cliente-privado@ejemplo.com"
LINK = "https://myplaylist.200oklabs.com/verificar?token=token-de-un-solo-uso"


class _Connection:
    async def execute(self, *_: Any) -> None:
        return None


class _Database:
    """Lo justo para marcar el resultado: `_mark` abre una transacción y ejecuta."""

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_Connection]:
        yield _Connection()


class _Sender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(message)


def _message(payload: dict[str, str] | None = None) -> _Claimed:
    return _Claimed(
        id=uuid4(),
        to_address=ADDRESS,
        template=EmailTemplate.VERIFY_EMAIL,
        payload=payload if payload is not None else {"link": LINK, "establishment_name": "Bar"},
        attempts=1,
    )


async def _send(sender: _Sender, message: _Claimed) -> list[dict[str, Any]]:
    lines: list[str] = []
    dispatcher = OutboxDispatcher(_Database(), sender, write=lines.append)  # type: ignore[arg-type]
    await dispatcher._send(message)
    return [json.loads(line) for line in lines]


async def test_F004_R016_el_trabajador_registra_plantilla_e_id_sin_la_direccion() -> None:
    sender = _Sender()
    message = _message()

    [entry] = await _send(sender, message)

    # El correo salió de verdad, con su dirección y su enlace.
    assert sender.sent[0].to == ADDRESS
    assert LINK in sender.sent[0].text
    assert entry == {
        "ts": entry["ts"],
        "level": "info",
        "event": "email",
        "result": "sent",
        "message_id": str(message.id),
        "template": "verify_email",
        "attempt": 1,
    }
    output = json.dumps(entry, ensure_ascii=False)
    assert ADDRESS not in output
    assert "token-de-un-solo-uso" not in output


async def test_F004_R016_un_envio_fallido_no_escribe_el_contenido_del_correo() -> None:
    # El error de SMTP repite el destinatario en su mensaje.
    refused = smtplib.SMTPRecipientsRefused({ADDRESS: (550, b"buzon inexistente")})

    [failed] = await _send(_Sender(refused), _message())
    [incomplete] = await _send(_Sender(), _message(payload={"link": LINK}))

    # Con intentos por delante, se reintenta; en el último, queda como fallido.
    assert (failed["result"], failed["error"]) == ("retry", "SMTPRecipientsRefused")
    last = _message()
    object.__setattr__(last, "attempts", MAX_ATTEMPTS)
    [given_up] = await _send(_Sender(refused), last)
    assert given_up["result"] == "failed"
    assert (incomplete["result"], incomplete["error"]) == ("incomplete", "KeyError")
    output = json.dumps([failed, incomplete], ensure_ascii=False)
    for secret in (ADDRESS, "buzon inexistente", "token-de-un-solo-uso", "Bar"):
        assert secret not in output


def test_F004_R016_el_trabajador_con_configuracion_invalida_no_escribe_valores() -> None:
    visible = "secreto-del-ticket-que-no-debe-aparecer-en-el-registro"
    env = {
        **os.environ,
        "ENV": "production",
        "EMAIL_BACKEND": "ses",
        "DATA_POLICY_VERSION": "2026-10",
        "REALTIME_TICKET_SECRET": visible,
        "CATALOG_PROVIDER": "youtube",
        "YOUTUBE_API_KEY": "clave-de-youtube-que-no-debe-aparecer",
        "DEVICE_TOKEN_SECRET": "corto",
    }
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--once"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 1
    assert "configuración inválida" in result.stderr
    assert "DEVICE_TOKEN_SECRET" in result.stderr
    for value in (visible, "clave-de-youtube-que-no-debe-aparecer", "'corto'"):
        assert value not in result.stderr
    assert "Traceback" not in result.stderr
