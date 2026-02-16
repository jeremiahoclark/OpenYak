from __future__ import annotations

import json
from pathlib import Path

import pytest

from yak.agent.tools.storage_tools import (
    StorageGetAssetTool,
    StorageListRecentTool,
    StorageSearchPromptTool,
)
from yak.storage.service import StorageService


@pytest.mark.asyncio
async def test_storage_tools_roundtrip(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    a = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"img",
        prompt="hello world",
        model="m",
    )

    list_tool = StorageListRecentTool(storage)
    search_tool = StorageSearchPromptTool(storage)
    get_tool = StorageGetAssetTool(storage)

    listed = json.loads(await list_tool.execute(user_id="u1", session_id="s1", limit=10))
    assert len(listed) == 1

    searched = json.loads(await search_tool.execute(query="hello", user_id="u1", session_id="s1", limit=10))
    assert len(searched) == 1
    assert searched[0]["asset_id"] == a.asset_id

    single = json.loads(await get_tool.execute(asset_id=a.asset_id))
    assert len(single) == 1
    assert single[0]["asset_id"] == a.asset_id
