from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from yak.integrations.fal_video import FalVideoError, FalVideoService
from yak.storage.service import StorageService


@pytest.mark.asyncio
async def test_generate_video_text_to_video_happy_path(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    status_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "kling-video/o3/pro/text-to-video" in request.url.path:
            return httpx.Response(200, json={"request_id": "req-123"})
        if request.method == "GET" and request.url.path.endswith("/requests/req-123/status"):
            status_calls["count"] += 1
            state = "IN_PROGRESS" if status_calls["count"] == 1 else "COMPLETED"
            return httpx.Response(200, json={"status": state})
        if request.method == "GET" and request.url.path.endswith("/requests/req-123"):
            return httpx.Response(
                200,
                json={"response": {"video": {"url": "https://cdn.example.com/out.mp4"}}},
            )
        if request.method == "GET" and str(request.url) == "https://cdn.example.com/out.mp4":
            return httpx.Response(200, content=b"fake-mp4-data")
        return httpx.Response(404, json={"error": "not found"})

    service = FalVideoService(
        storage,
        api_key="test-key",
        poll_interval_seconds=0.01,
        poll_timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    result = await service.generate_video(
        prompt="A mountain time-lapse",
        user_id="u1",
        session_id="s1",
        duration=5,
        aspect_ratio="16:9",
    )

    assert result.request_id == "req-123"
    assert result.model == "fal-ai/kling-video/o3/pro/text-to-video"
    assert Path(result.file_path).exists()
    asset = storage.get_asset(result.asset_id)
    assert asset is not None
    assert asset.asset_type == "video"
    assert asset.prompt == "A mountain time-lapse"


@pytest.mark.asyncio
async def test_generate_video_image_to_video_passes_data_uri(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    image_path = tmp_path / "seed.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    submitted: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "kling-video/v3/pro/image-to-video" in request.url.path:
            submitted.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"request_id": "req-image"})
        if request.method == "GET" and request.url.path.endswith("/requests/req-image/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.method == "GET" and request.url.path.endswith("/requests/req-image"):
            return httpx.Response(
                200,
                json={"response": {"videos": [{"url": "https://cdn.example.com/image.mp4"}]}},
            )
        if request.method == "GET" and str(request.url) == "https://cdn.example.com/image.mp4":
            return httpx.Response(200, content=b"fake-mp4")
        return httpx.Response(404, json={"error": "not found"})

    service = FalVideoService(
        storage,
        api_key="test-key",
        poll_interval_seconds=0.01,
        poll_timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    await service.generate_video(
        prompt="Animate this still frame",
        image_path=str(image_path),
        user_id="u2",
        session_id="s2",
    )

    assert isinstance(submitted.get("start_image_url"), str)
    assert str(submitted["start_image_url"]).startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_generate_video_raises_on_failed_status(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "req-fail"})
        if request.method == "GET" and request.url.path.endswith("/requests/req-fail/status"):
            return httpx.Response(200, json={"status": "FAILED"})
        return httpx.Response(404)

    service = FalVideoService(
        storage,
        api_key="test-key",
        poll_interval_seconds=0.01,
        poll_timeout_seconds=1.0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(FalVideoError):
        await service.generate_video(prompt="Broken run", user_id="u1", session_id="s1")
