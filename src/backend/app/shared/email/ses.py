"""Adaptador Amazon SES (API v2) del puerto EmailSender (ADR-0011)."""

import asyncio
from typing import TYPE_CHECKING

import boto3

from app.accounts.domain.ports import EmailMessage

if TYPE_CHECKING:
    from mypy_boto3_sesv2 import SESV2Client


class SesEmailSender:
    def __init__(
        self, *, sender: str, client: "SESV2Client | None" = None, region: str = "us-east-1"
    ) -> None:
        self._sender = sender
        self._client = client or boto3.client("sesv2", region_name=region)

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(
            self._client.send_email,
            FromEmailAddress=self._sender,
            Destination={"ToAddresses": [message.to]},
            Content={
                "Simple": {
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": message.text, "Charset": "UTF-8"}},
                }
            },
        )
