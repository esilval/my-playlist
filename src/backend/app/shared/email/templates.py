"""Plantillas de los correos transaccionales: primera línea, asunto; el resto, cuerpo."""

from collections.abc import Mapping
from enum import StrEnum
from functools import cache
from pathlib import Path
from string import Template

from app.accounts.domain.ports import EmailMessage

TEMPLATES_DIR = Path(__file__).parent / "templates"


class EmailTemplate(StrEnum):
    # Los mismos valores que el tipo email_template de la base de datos.
    VERIFY_EMAIL = "verify_email"
    PASSWORD_RESET = "password_reset"
    REGISTRATION_ATTEMPT = "registration_attempt"


@cache
def _load(template: EmailTemplate) -> tuple[Template, Template]:
    subject, body = (TEMPLATES_DIR / f"{template}.txt").read_text().split("\n", 1)
    return Template(subject), Template(body.lstrip("\n"))


def render(template: EmailTemplate, to: str, payload: Mapping[str, str]) -> EmailMessage:
    """Falla con KeyError si al payload le falta un dato: mejor no enviar que enviar roto."""
    subject, body = _load(template)
    return EmailMessage(to=to, subject=subject.substitute(payload), text=body.substitute(payload))
