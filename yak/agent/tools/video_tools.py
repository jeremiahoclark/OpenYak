"""Agent tools for Fal.ai video generation and outbound delivery."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from yak.agent.tools.base import Tool
from yak.bus.events import MediaAttachment, OutboundMessage
from yak.integrations.fal_video import FalVideoService


class GenerateVideoTool(Tool):
    """Generate a video via Fal.ai and store it locally."""

    def __init__(
        self,
        service: FalVideoService,
        *,
        default_user_id: str = "default",
        default_session_id: str = "default",
    ):
        self.service = service
        self._default_user_id = default_user_id
        self._default_session_id = default_session_id

    def set_context(self, *, user_id: str, session_id: str) -> None:
        self._default_user_id = user_id or self._default_user_id
        self._default_session_id = session_id or self._default_session_id

    @property
    def name(self) -> str:
        return "generate_video"

    @property
    def description(self) -> str:
        return (
            "Generate a video from text (or optional start image) using Fal.ai and store it "
            "in Yak local storage."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "minLength": 1},
                "image_path": {"type": "string"},
                "duration": {"type": "integer", "minimum": 3, "maximum": 15},
                "aspect_ratio": {
                    "type": "string",
                    "enum": ["16:9", "9:16", "1:1"],
                },
                "model_id": {"type": "string"},
                "generate_audio": {"type": "boolean"},
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str,
        image_path: str | None = None,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        model_id: str | None = None,
        generate_audio: bool = False,
        user_id: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        resolved_user_id = (user_id or self._default_user_id).strip() or "default"
        resolved_session_id = (session_id or self._default_session_id).strip() or "default"
        result = await self.service.generate_video(
            prompt=prompt,
            image_path=image_path,
            duration=duration,
            aspect_ratio=aspect_ratio,
            model_id=model_id,
            generate_audio=generate_audio,
            user_id=resolved_user_id,
            session_id=resolved_session_id,
        )
        return json.dumps(
            {
                "status": "ok",
                "request_id": result.request_id,
                "model": result.model,
                "remote_url": result.remote_url,
                "asset_id": result.asset_id,
                "file_path": result.file_path,
            },
            ensure_ascii=False,
        )


class SendVideoTool(Tool):
    """Send a stored video file to one or more configured channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id

    def set_context(self, channel: str, chat_id: str) -> None:
        self._default_channel = channel
        self._default_chat_id = chat_id

    @property
    def name(self) -> str:
        return "send_video"

    @property
    def description(self) -> str:
        return "Send a local video file to the current chat or selected channels."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "minLength": 1},
                "caption": {"type": "string"},
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of channels to send to. Defaults to current channel.",
                },
                "chat_id": {"type": "string"},
                "chat_ids": {
                    "type": "object",
                    "description": "Optional channel->chat_id mapping for multi-channel sends.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        caption: str = "",
        channels: list[str] | None = None,
        chat_id: str | None = None,
        chat_ids: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> str:
        if not self._send_callback:
            return "Error: Video sending not configured"

        targets = channels or ([self._default_channel] if self._default_channel else [])
        if not targets:
            return "Error: No target channel provided"

        explicit_chat_ids = chat_ids or {}
        sent: list[dict[str, str]] = []
        errors: list[str] = []

        for channel in targets:
            resolved_chat_id = (
                explicit_chat_ids.get(channel)
                or chat_id
                or (self._default_chat_id if channel == self._default_channel else "")
            )
            if not resolved_chat_id:
                errors.append(f"Missing chat_id for channel '{channel}'")
                continue

            msg = OutboundMessage(
                channel=channel,
                chat_id=resolved_chat_id,
                content=caption,
                message_type="video",
                attachments=[MediaAttachment(type="video", path=file_path, caption=caption)],
            )
            await self._send_callback(msg)
            sent.append({"channel": channel, "chat_id": resolved_chat_id})

        status = "ok" if sent and not errors else ("partial" if sent else "error")
        return json.dumps({"status": status, "sent": sent, "errors": errors}, ensure_ascii=False)
