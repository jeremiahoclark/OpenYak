from __future__ import annotations

from pathlib import Path

from yak.rag.retrieval import RetrievalService
from yak.storage.service import StorageService


def test_backfill_and_semantic_search(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    a1 = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"1",
        prompt="sunset over mountain lake",
        model="img-model",
    )
    storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="video",
        ext="mp4",
        data=b"2",
        prompt="fast race car downtown",
        model="vid-model",
    )

    retrieval = RetrievalService(storage)
    indexed = retrieval.backfill(limit=100)
    assert indexed == 2

    hits = retrieval.search("mountain sunset", top_k=2, user_id="u1", session_id="s1")
    assert hits
    assert hits[0].asset_id == a1.asset_id


def test_search_by_asset_id(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    a1 = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"1",
        prompt="anime portrait with blue hair",
        model="m1",
    )
    a2 = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"2",
        prompt="anime portrait with red hair",
        model="m1",
    )

    retrieval = RetrievalService(storage)
    retrieval.backfill(limit=100)

    hits = retrieval.search_by_asset_id(a1.asset_id, top_k=3, user_id="u1", session_id="s1")
    assert any(h.asset_id == a2.asset_id for h in hits)
