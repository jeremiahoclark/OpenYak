from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from yak.storage.service import StorageService


def test_store_and_get_asset(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")

    asset = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"abc123",
        prompt="sunset beach",
        model="test-model",
        params={"seed": 7},
    )

    fetched = storage.get_asset(asset.asset_id)
    assert fetched is not None
    assert fetched.prompt == "sunset beach"
    assert fetched.model == "test-model"
    assert fetched.params["seed"] == 7
    assert Path(fetched.file_path).exists()


def test_search_and_list_recent(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")

    storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="image",
        ext="png",
        data=b"image-a",
        prompt="cat in hat",
        model="m1",
    )
    storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="video",
        ext="mp4",
        data=b"video-b",
        prompt="dog in fog",
        model="m2",
    )

    by_prompt = storage.search_by_prompt("cat", user_id="u1", session_id="s1")
    assert len(by_prompt) == 1
    assert by_prompt[0].prompt == "cat in hat"

    recent = storage.list_recent(user_id="u1", session_id="s1", limit=2)
    assert len(recent) == 2


def test_delete_asset_removes_file(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")
    asset = storage.store_bytes(
        user_id="u1",
        session_id="s1",
        asset_type="file",
        ext="txt",
        data=b"to-delete",
        prompt="cleanup test",
        model="m1",
    )

    p = Path(asset.file_path)
    assert p.exists()
    deleted = storage.delete_asset(asset.asset_id, remove_file=True)
    assert deleted is True
    assert not p.exists()
    assert storage.get_asset(asset.asset_id) is None


def test_concurrent_writes_are_safe(tmp_path: Path) -> None:
    storage = StorageService(base_dir=tmp_path / "storage")

    def writer(i: int) -> str:
        asset = storage.store_bytes(
            user_id="u1",
            session_id="s1",
            asset_type="image",
            ext="png",
            data=f"payload-{i}".encode(),
            prompt=f"prompt-{i}",
            model="m",
        )
        return asset.asset_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(writer, range(40)))

    assert len(ids) == 40
    assert len(set(ids)) == 40
    recent = storage.list_recent(user_id="u1", session_id="s1", limit=100)
    assert len(recent) == 40
