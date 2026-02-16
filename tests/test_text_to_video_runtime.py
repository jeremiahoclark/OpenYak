from __future__ import annotations

import time
from pathlib import Path

import pytest

from yak.workflows.text_to_video import TextToVideoWorkflow, WorkflowError


class _FakeCuda:
    @staticmethod
    def is_available() -> bool:
        return True

    @staticmethod
    def get_device_capability(index: int) -> tuple[int, int]:
        return (12, 1)

    @staticmethod
    def get_arch_list() -> list[str]:
        return ["sm_80", "sm_90", "sm_120"]


class _FakeTorch:
    cuda = _FakeCuda()


def test_cuda_capability_detection_blackwell_minor_gap() -> None:
    assert (
        TextToVideoWorkflow._supports_cuda_capability(_FakeTorch, (12, 1)) is False
    )


@pytest.mark.asyncio
async def test_run_times_out_on_image_stage(tmp_path: Path) -> None:
    workflow = TextToVideoWorkflow(
        project_root=tmp_path,
        fal_api_key="dummy",
        image_timeout_seconds=0.01,
    )

    def _slow_image(**kwargs):  # type: ignore[no-untyped-def]
        time.sleep(0.2)
        return str(tmp_path / "img.png")

    async def _never_called(**kwargs):  # type: ignore[no-untyped-def]
        return ("", "", "")

    workflow._generate_image_sync = _slow_image  # type: ignore[method-assign]
    workflow._generate_video_from_image = _never_called  # type: ignore[method-assign]

    with pytest.raises(WorkflowError, match="timed out"):
        await workflow.run(prompt="p", user_id="u1", session_id="s1")
