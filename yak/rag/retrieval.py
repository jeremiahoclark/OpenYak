"""Semantic retrieval service bridging storage, embeddings, and vector index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yak.rag.cuvs_index import CuvsIndex, RetrievalHit
from yak.rag.embeddings import EmbeddingService
from yak.storage.service import StorageService


@dataclass
class SemanticResult:
    asset_id: str
    score: float
    prompt: str
    file_path: str
    asset_type: str
    model: str


class RetrievalService:
    """Builds and queries semantic index over stored asset metadata."""

    def __init__(
        self,
        storage: StorageService,
        embedder: EmbeddingService | None = None,
        index: CuvsIndex | None = None,
        index_path: Path | None = None,
    ):
        self.storage = storage
        self.embedder = embedder or EmbeddingService()
        self.index = index or CuvsIndex(index_path or (self.storage.base_dir / "retrieval_index.json"))

    def backfill(self, limit: int = 10000) -> int:
        assets = self.storage.list_recent(limit=limit)
        count = 0
        for asset in assets:
            self._index_asset(asset.asset_id)
            count += 1
        self.index.save()
        return count

    def search(self, query: str, top_k: int = 5, user_id: str | None = None, session_id: str | None = None) -> list[SemanticResult]:
        q_vec = self.embedder.embed_text(query)
        hits = self.index.query(q_vec, top_k=top_k * 3)
        return self._hits_to_results(hits, top_k=top_k, user_id=user_id, session_id=session_id)

    def search_by_asset_id(
        self,
        asset_id: str,
        top_k: int = 5,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> list[SemanticResult]:
        if self.index.get_vector(asset_id) is None:
            self._index_asset(asset_id)
            self.index.save()
        vec = self.index.get_vector(asset_id)
        if vec is None:
            return []
        hits = self.index.query(vec, top_k=top_k + 3)
        hits = [h for h in hits if h.item_id != asset_id]
        return self._hits_to_results(hits, top_k=top_k, user_id=user_id, session_id=session_id)

    def _index_asset(self, asset_id: str) -> None:
        asset = self.storage.get_asset(asset_id)
        if not asset:
            return
        text = f"prompt: {asset.prompt}\nmodel: {asset.model}\ntype: {asset.asset_type}"
        vec = self.embedder.embed_text(text)
        self.index.upsert(
            asset.asset_id,
            vec,
            metadata={
                "user_id": asset.user_id,
                "session_id": asset.session_id,
                "prompt": asset.prompt,
                "asset_type": asset.asset_type,
            },
        )

    def _hits_to_results(
        self,
        hits: list[RetrievalHit],
        *,
        top_k: int,
        user_id: str | None,
        session_id: str | None,
    ) -> list[SemanticResult]:
        out: list[SemanticResult] = []
        for hit in hits:
            asset = self.storage.get_asset(hit.item_id)
            if not asset:
                continue
            if user_id and asset.user_id != user_id:
                continue
            if session_id and asset.session_id != session_id:
                continue
            out.append(
                SemanticResult(
                    asset_id=asset.asset_id,
                    score=hit.score,
                    prompt=asset.prompt,
                    file_path=asset.file_path,
                    asset_type=asset.asset_type,
                    model=asset.model,
                )
            )
            if len(out) >= max(1, top_k):
                break
        return out
