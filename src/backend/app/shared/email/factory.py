"""Elige el adaptador de correo según la configuración."""

from app.accounts.domain.ports import EmailSender
from app.shared.config import Settings
from app.shared.email.memory import InMemoryEmailSender
from app.shared.email.ses import SesEmailSender
from app.shared.email.smtp_mailpit import SmtpEmailSender


def email_sender_from_settings(settings: Settings) -> EmailSender:
    if settings.email_backend == "ses":
        return SesEmailSender(sender=settings.email_from, region=settings.aws_region)
    if settings.email_backend == "smtp":
        return SmtpEmailSender(
            host=settings.smtp_host, port=settings.smtp_port, sender=settings.email_from
        )
    return InMemoryEmailSender()
