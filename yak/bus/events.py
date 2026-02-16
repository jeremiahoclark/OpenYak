"""Event types for the message bus."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MediaAttachment:
    """Unified attachment envelope for outbound channel delivery."""

    type: str  # image | video | file
    path: str | None = None
    url: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    caption: str | None = None


@dataclass
class InboundMessage:
    """Message received from a chat channel."""

    channel: str  # telegram, discord, slack, email, etc.
    sender_id: str  # User identifier
    chat_id: str  # Chat/channel identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Local media file paths (downloaded attachments)
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""

    channel: str
    chat_id: str
    content: str
    message_type: str = "text"  # text | image | video | file
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    attachments: list[MediaAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
