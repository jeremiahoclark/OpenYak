from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from yak.bus.events import MediaAttachment, OutboundMessage
from yak.bus.queue import MessageBus
from yak.channels.email import EmailChannel
from yak.config.loader import _migrate_config
from yak.config.schema import EmailConfig, GoogleCalendarConfig
from yak.integrations.google_calendar import GoogleCalendarClient


def _email_config() -> EmailConfig:
    return EmailConfig(
        enabled=True,
        consent_granted=True,
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="bot@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="bot@example.com",
        smtp_password="secret",
    )


def test_migrate_config_removes_non_phase2_channels_and_moves_groq_key() -> None:
    data = {
        "channels": {
            "telegram": {"enabled": True, "token": "t"},
            "whatsapp": {"enabled": True},
            "feishu": {"enabled": True},
            "mochat": {"enabled": True},
            "dingtalk": {"enabled": True},
            "qq": {"enabled": True},
        },
        "providers": {"groq": {"apiKey": "groq-secret"}},
    }

    migrated = _migrate_config(data)
    channels = migrated["channels"]

    assert "whatsapp" not in channels
    assert "feishu" not in channels
    assert "mochat" not in channels
    assert "dingtalk" not in channels
    assert "qq" not in channels
    assert channels["telegram"]["groqApiKey"] == "groq-secret"


@pytest.mark.asyncio
async def test_email_channel_sends_attachment(monkeypatch, tmp_path: Path) -> None:
    attachment = tmp_path / "note.txt"
    attachment.write_text("hello attachment")

    class FakeSMTP:
        def __init__(self, _host: str, _port: int, timeout: int = 30) -> None:
            self.sent_messages: list[EmailMessage] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self, context=None):
            return None

        def login(self, _user: str, _pw: str):
            return None

        def send_message(self, msg: EmailMessage):
            self.sent_messages.append(msg)

    instances: list[FakeSMTP] = []

    def _smtp_factory(host: str, port: int, timeout: int = 30):
        smtp = FakeSMTP(host, port, timeout=timeout)
        instances.append(smtp)
        return smtp

    monkeypatch.setattr("yak.channels.email.smtplib.SMTP", _smtp_factory)

    channel = EmailChannel(_email_config(), MessageBus())
    await channel.send(
        OutboundMessage(
            channel="email",
            chat_id="alice@example.com",
            content="see attached",
            message_type="file",
            attachments=[MediaAttachment(type="file", path=str(attachment))],
        )
    )

    assert len(instances) == 1
    sent = instances[0].sent_messages[0]
    attachments = list(sent.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "note.txt"


def test_google_calendar_authorization_url_has_required_oauth_params() -> None:
    client = GoogleCalendarClient(
        GoogleCalendarConfig(
            enabled=True,
            client_id="client-123",
            client_secret="secret",
            redirect_uri="http://localhost:8080/oauth2callback",
        )
    )

    url = client.build_authorization_url(state="yak-state")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert "accounts.google.com" in parsed.netloc
    assert query["client_id"] == ["client-123"]
    assert query["state"] == ["yak-state"]
    assert query["response_type"] == ["code"]
