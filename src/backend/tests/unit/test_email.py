from datetime import timedelta

import boto3
import pytest
from botocore.stub import Stubber
from pydantic import ValidationError

from app.accounts.domain.ports import EmailMessage
from app.shared.config import Settings
from app.shared.email.ses import SesEmailSender
from app.shared.email.templates import EmailTemplate, render
from app.shared.outbox import RETRY_CAP, retry_delay

PAYLOADS = {
    EmailTemplate.VERIFY_EMAIL: {"establishment_name": "Café Ñandú", "link": "http://x/v"},
    EmailTemplate.PASSWORD_RESET: {"link": "http://x/r"},
    EmailTemplate.REGISTRATION_ATTEMPT: {"login_link": "http://x/e", "reset_link": "http://x/r"},
}


@pytest.mark.parametrize("template", list(EmailTemplate))
def test_cada_plantilla_se_renderiza_con_su_payload(template: EmailTemplate) -> None:
    message = render(template, "dueno@ejemplo.com", PAYLOADS[template])

    assert message.to == "dueno@ejemplo.com"
    assert message.subject and "\n" not in message.subject
    assert all(value in message.text for value in PAYLOADS[template].values())
    assert "$" not in message.text


def test_plantilla_sin_datos_falla_en_lugar_de_enviar_roto() -> None:
    with pytest.raises(KeyError):
        render(EmailTemplate.PASSWORD_RESET, "dueno@ejemplo.com", {})


def test_espera_exponencial_con_tope() -> None:
    assert [retry_delay(n) for n in (1, 2, 3)] == [
        timedelta(seconds=30),
        timedelta(seconds=60),
        timedelta(seconds=120),
    ]
    assert retry_delay(20) == RETRY_CAP


@pytest.mark.anyio
async def test_ses_envia_con_la_api_v2() -> None:
    client = boto3.client(
        "sesv2", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x"
    )
    message = EmailMessage(to="dueno@ejemplo.com", subject="Asunto ñ", text="Cuerpo")
    with Stubber(client) as stub:
        stub.add_response(
            "send_email",
            {"MessageId": "1"},
            {
                "FromEmailAddress": "MyPlaylist <no@example.com>",
                "Destination": {"ToAddresses": ["dueno@ejemplo.com"]},
                "Content": {
                    "Simple": {
                        "Subject": {"Data": "Asunto ñ", "Charset": "UTF-8"},
                        "Body": {"Text": {"Data": "Cuerpo", "Charset": "UTF-8"}},
                    }
                },
            },
        )
        await SesEmailSender(sender="MyPlaylist <no@example.com>", client=client).send(message)
        stub.assert_no_pending_responses()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_produccion_exige_ses() -> None:
    with pytest.raises(ValidationError, match="SES"):
        Settings(env="production", email_backend="smtp", data_policy_version="2026-10")
    settings = Settings(
        env="production",
        email_backend="ses",
        data_policy_version="2026-10",
        # Producción también exige el secreto propio del tiempo real (feature 002, ADR-0014).
        realtime_ticket_secret="secreto-de-produccion-de-al-menos-32-caracteres",
    )
    assert settings.email_backend == "ses"
