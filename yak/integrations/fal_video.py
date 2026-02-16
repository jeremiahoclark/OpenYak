"""Fal.ai video generation integration."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from yak.storage.service import StorageService


class FalVideoError(RuntimeError):
    """Raised when Fal API operations fail."""


@dataclass
class FalVideoResult:
    """Normalized video generation result."""

    request_id: str
    model: str
    remote_url: str
    asset_id: str
    file_path: str


class FalVideoService:
    """Queue-based Fal video generation with local persistence."""

    def __init__(
        self,
        storage: StorageService,
        *,
        api_key: str | None = None,
        queue_base_url: str = "https://queue.fal.run",
        default_text_model: str = "fal-ai/kling-video/o3/pro/text-to-video",
        default_image_model: str = "fal-ai/kling-video/v3/pro/image-to-video",
        poll_interval_seconds: float = 2.0,
        poll_timeout_seconds: float = 600.0,
        object_lifecycle_seconds: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.storage = storage
        self.api_key = (api_key or os.getenv("FAL_KEY", "")).strip()
        self.queue_base_url = queue_base_url.rstrip("/")
        self.default_text_model = default_text_model
        self.default_image_model = default_image_model
        self.poll_interval_seconds = poll_interval_seconds
        self.poll_timeout_seconds = poll_timeout_seconds
        self.object_lifecycle_seconds = object_lifecycle_seconds
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise FalVideoError("FAL_KEY is not configured")
        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.object_lifecycle_seconds and self.object_lifecycle_seconds > 0:
            lifecycle = {"expiration_duration_seconds": self.object_lifecycle_seconds}
            headers["X-Fal-Object-Lifecycle-Preference"] = json.dumps(lifecycle)
        return headers

    def _model_url(self, model_id: str) -> str:
        return f"{self.queue_base_url}/{model_id}"

    async def _submit(self, model_id: str, payload: dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
            response = await client.post(
                self._model_url(model_id),
                headers=self._headers(),
                json=payload,
            )
            if response.status_code >= 400:
                raise FalVideoError(
                    f"Fal submit failed ({response.status_code}): {response.text[:300]}"
                )
            data = response.json()
            request_id = data.get("request_id")
            if not request_id:
                raise FalVideoError("Fal submit response missing request_id")
            return str(request_id)

    async def _status(self, model_id: str, request_id: str, *, logs: bool = True) -> dict[str, Any]:
        params = {"logs": "1"} if logs else {}
        url = f"{self._model_url(model_id)}/requests/{request_id}/status"
        async with httpx.AsyncClient(timeout=60.0, transport=self._transport) as client:
            response = await client.get(url, headers=self._headers(), params=params)
            if response.status_code >= 400:
                raise FalVideoError(
                    f"Fal status failed ({response.status_code}): {response.text[:300]}"
                )
            return response.json()

    async def _result(self, model_id: str, request_id: str) -> dict[str, Any]:
        url = f"{self._model_url(model_id)}/requests/{request_id}"
        async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
            response = await client.get(url, headers=self._headers())
            if response.status_code >= 400:
                raise FalVideoError(
                    f"Fal result failed ({response.status_code}): {response.text[:300]}"
                )
            return response.json()

    async def _download_bytes(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=300.0, transport=self._transport) as client:
            response = await client.get(url)
            if response.status_code >= 400:
                raise FalVideoError(
                    f"Fal media download failed ({response.status_code}): {response.text[:300]}"
                )
            return response.content

    def _image_to_data_uri(self, image_path: str) -> str:
        path = Path(image_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "image/png"
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{payload}"

    def _extract_video_url(self, payload: dict[str, Any]) -> str:
        # Queue result shape commonly nests model output under "response".
        body = payload.get("response", payload)
        candidate = body.get("video")
        if isinstance(candidate, dict) and candidate.get("url"):
            return str(candidate["url"])
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        videos = body.get("videos")
        if isinstance(videos, list):
            for item in videos:
                if isinstance(item, dict) and item.get("url"):
                    return str(item["url"])
        raise FalVideoError("Fal result does not include a video URL")

    async def generate_video(
        self,
        *,
        prompt: str,
        user_id: str,
        session_id: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        image_path: str | None = None,
        model_id: str | None = None,
        generate_audio: bool = False,
    ) -> FalVideoResult:
        if not prompt.strip():
            raise ValueError("prompt is required")
        if duration < 3 or duration > 15:
            raise ValueError("duration must be between 3 and 15 seconds")
        if aspect_ratio not in {"16:9", "9:16", "1:1"}:
            raise ValueError("aspect_ratio must be one of: 16:9, 9:16, 1:1")

        selected_model = model_id or (
            self.default_image_model if image_path else self.default_text_model
        )
        payload: dict[str, Any] = {
            "prompt": prompt,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
            "generate_audio": bool(generate_audio),
        }
        if image_path:
            payload["start_image_url"] = self._image_to_data_uri(image_path)

        request_id = await self._submit(selected_model, payload)

        elapsed = 0.0
        while True:
            status = await self._status(selected_model, request_id, logs=True)
            state = str(status.get("status", "")).upper()
            if state == "COMPLETED":
                break
            if state in {"FAILED", "CANCELLED", "ERROR"}:
                raise FalVideoError(f"Fal request {request_id} failed with status: {state}")
            elapsed += self.poll_interval_seconds
            if elapsed > self.poll_timeout_seconds:
                raise FalVideoError(f"Fal request {request_id} timed out after {elapsed:.0f}s")
            await asyncio.sleep(self.poll_interval_seconds)

        result = await self._result(selected_model, request_id)
        video_url = self._extract_video_url(result)
        video_bytes = await self._download_bytes(video_url)
        record = self.storage.store_bytes(
            user_id=user_id,
            session_id=session_id,
            asset_type="video",
            ext="mp4",
            data=video_bytes,
            prompt=prompt,
            model=selected_model,
            params={
                "request_id": request_id,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "image_path": image_path,
                "generate_audio": generate_audio,
            },
        )
        return FalVideoResult(
            request_id=request_id,
            model=selected_model,
            remote_url=video_url,
            asset_id=record.asset_id,
            file_path=record.file_path,
        )
