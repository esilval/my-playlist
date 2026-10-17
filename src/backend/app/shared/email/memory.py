"""Adaptador en memoria del puerto EmailSender, para pruebas."""

from app.accounts.domain.ports import EmailMessage


class InMemoryEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
