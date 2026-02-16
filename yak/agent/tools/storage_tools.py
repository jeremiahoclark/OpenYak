"""Agent tools for storage retrieval operations."""

from __future__ import annotations

import json
from typing import Any

from yak.agent.tools.base import Tool
from yak.storage.service import StorageService


def _serialize_assets(items: list[Any]) -> str:
    return json.dumps(
        [
            {
                "asset_id": a.asset_id,
                "user_id": a.user_id,
                "session_id": a.session_id,
                "asset_type": a.asset_type,
                "prompt": a.prompt,
                "model": a.model,
                "params": a.params,
                "file_path": a.file_path,
                "created_at": a.created_at.isoformat(),
                "updated_at": a.updated_at.isoformat(),
            }
            for a in items
        ],
        ensure_ascii=False,
    )


class StorageListRecentTool(Tool):
    """List recently stored assets."""

    def __init__(self, storage: StorageService):
        self.storage = storage

    @property
    def name(self) -> str:
        return "storage_list_recent"

    @property
    def description(self) -> str:
        return "List recent stored assets, optionally filtered by user_id and session_id."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": [],
        }

    async def execute(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        assets = self.storage.list_recent(user_id=user_id, session_id=session_id, limit=limit)
        return _serialize_assets(assets)


class StorageSearchPromptTool(Tool):
    """Search stored assets by prompt text."""

    def __init__(self, storage: StorageService):
        self.storage = storage

    @property
    def name(self) -> str:
        return "storage_search_prompt"

    @property
    def description(self) -> str:
        return "Search stored assets by prompt text, optionally filtered by user and session."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
        **kwargs: Any,
    ) -> str:
        assets = self.storage.search_by_prompt(
            query,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
        )
        return _serialize_assets(assets)


class StorageGetAssetTool(Tool):
    """Fetch one stored asset by ID."""

    def __init__(self, storage: StorageService):
        self.storage = storage

    @property
    def name(self) -> str:
        return "storage_get_asset"

    @property
    def description(self) -> str:
        return "Get one stored asset by asset_id."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "minLength": 1},
            },
            "required": ["asset_id"],
        }

    async def execute(self, asset_id: str, **kwargs: Any) -> str:
        asset = self.storage.get_asset(asset_id)
        if not asset:
            return "Error: Asset not found"
        return _serialize_assets([asset])
