"""Adaptador SMTP del puerto EmailSender, para el buzón local Mailpit (plan D7, D10)."""

import asyncio
import smtplib
from email.message import EmailMessage as MimeMessage

from app.accounts.domain.ports import EmailMessage


class SmtpEmailSender:
    def __init__(self, *, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        await asyncio.to_thread(self._deliver, mime)

    def _deliver(self, mime: MimeMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.send_message(mime)
