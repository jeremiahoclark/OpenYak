"""Semantic retrieval tools."""

from __future__ import annotations

import json
from typing import Any

from yak.agent.tools.base import Tool
from yak.rag.retrieval import RetrievalService


class SearchSimilarTool(Tool):
    """Search semantically similar assets by query text."""

    def __init__(self, retrieval: RetrievalService):
        self.retrieval = retrieval

    @property
    def name(self) -> str:
        return "search_similar"

    @property
    def description(self) -> str:
        return "Search stored assets by semantic similarity to a query."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        hits = self.retrieval.search(query, top_k=top_k, user_id=user_id, session_id=session_id)
        return json.dumps([h.__dict__ for h in hits], ensure_ascii=False)


class SearchByAssetIdTool(Tool):
    """Search semantically similar assets starting from one asset."""

    def __init__(self, retrieval: RetrievalService):
        self.retrieval = retrieval

    @property
    def name(self) -> str:
        return "search_by_asset_id"

    @property
    def description(self) -> str:
        return "Find assets similar to a known asset_id."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
                "user_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["asset_id"],
        }

    async def execute(
        self,
        asset_id: str,
        top_k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        hits = self.retrieval.search_by_asset_id(
            asset_id,
            top_k=top_k,
            user_id=user_id,
            session_id=session_id,
        )
        return json.dumps([h.__dict__ for h in hits], ensure_ascii=False)
