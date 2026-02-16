from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from yak.agent.tools.workflow_tools import TextToVideoWorkflowTool


@dataclass
class _FakeResult:
    image_path: str
    video_path: str
    request_id: str
    remote_url: str
    image_model: str
    video_model: str


class _FakeWorkflow:
    def __init__(self):
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResult(
            image_path="/tmp/img.png",
            video_path="/tmp/vid.mp4",
            request_id="req-1",
            remote_url="https://example.com/v.mp4",
            image_model="flux",
            video_model="kling",
        )

    @staticmethod
    def result_to_json(result):
        return json.dumps({
            "status": "ok",
            "image_path": result.image_path,
            "video_path": result.video_path,
            "request_id": result.request_id,
            "remote_url": result.remote_url,
            "image_model": result.image_model,
            "video_model": result.video_model,
        })


@pytest.mark.asyncio
async def test_workflow_tool_uses_context_defaults() -> None:
    workflow = _FakeWorkflow()
    tool = TextToVideoWorkflowTool(workflow)  # type: ignore[arg-type]
    tool.set_context(user_id="u1", session_id="email:abc")

    raw = await tool.execute(prompt="test prompt")
    body = json.loads(raw)

    assert body["status"] == "ok"
    assert workflow.calls[0]["user_id"] == "u1"
    assert workflow.calls[0]["session_id"] == "email:abc"


@pytest.mark.asyncio
async def test_workflow_tool_passes_video_prompt_override() -> None:
    workflow = _FakeWorkflow()
    tool = TextToVideoWorkflowTool(workflow)  # type: ignore[arg-type]

    await tool.execute(prompt="base", video_prompt="Animate as watercolor anime")

    assert workflow.calls[0]["video_prompt"] == "Animate as watercolor anime"
