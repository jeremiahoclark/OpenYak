from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from yak.agent.tools.video_tools import GenerateVideoTool, SendVideoTool
from yak.bus.events import OutboundMessage


@dataclass
class _FakeResult:
    request_id: str
    model: str
    remote_url: str
    asset_id: str
    file_path: str


class _FakeFalService:
    def __init__(self):
        self.calls: list[dict[str, object]] = []

    async def generate_video(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResult(
            request_id="req-1",
            model="fal-ai/model",
            remote_url="https://example.com/video.mp4",
            asset_id="asset-1",
            file_path="/tmp/video.mp4",
        )


@pytest.mark.asyncio
async def test_generate_video_tool_uses_context_defaults() -> None:
    service = _FakeFalService()
    tool = GenerateVideoTool(service)  # type: ignore[arg-type]
    tool.set_context(user_id="alice", session_id="email:alice@example.com")

    raw = await tool.execute(prompt="A rainy neon alley")
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["request_id"] == "req-1"
    assert service.calls[0]["user_id"] == "alice"
    assert service.calls[0]["session_id"] == "email:alice@example.com"


@pytest.mark.asyncio
async def test_send_video_tool_sends_to_multiple_channels(tmp_path: Path) -> None:
    sent: list[OutboundMessage] = []
    video = tmp_path / "out.mp4"
    video.write_bytes(b"mp4")

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = SendVideoTool(send_callback=_send, default_channel="email", default_chat_id="a@example.com")
    raw = await tool.execute(
        file_path=str(video),
        caption="preview",
        channels=["email", "telegram"],
        chat_ids={"telegram": "12345"},
    )
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert len(sent) == 2
    assert sent[0].message_type == "video"
    assert sent[0].attachments[0].path == str(video)
    assert sent[1].channel == "telegram"
    assert sent[1].chat_id == "12345"


@pytest.mark.asyncio
async def test_send_video_tool_reports_missing_target() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = SendVideoTool(send_callback=_send, default_channel="email", default_chat_id="a@example.com")
    raw = await tool.execute(file_path="/tmp/out.mp4", channels=["slack"])
    payload = json.loads(raw)

    assert payload["status"] == "error"
    assert payload["sent"] == []
    assert "Missing chat_id for channel 'slack'" in payload["errors"][0]
