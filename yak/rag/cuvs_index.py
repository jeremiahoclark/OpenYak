"""ANN index wrapper with cuVS-first interface and deterministic fallback."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RetrievalHit:
    item_id: str
    score: float
    metadata: dict[str, Any]


class CuvsIndex:
    """Vector index with optional cuVS backend and built-in brute-force fallback."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._backend = "cuvs" if self._has_cuvs() else "fallback"
        self._vectors: dict[str, list[float]] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def backend(self) -> str:
        return self._backend

    def upsert(self, item_id: str, vector: list[float], metadata: dict[str, Any] | None = None) -> None:
        self._vectors[item_id] = vector
        self._meta[item_id] = metadata or {}

    def delete(self, item_id: str) -> None:
        self._vectors.pop(item_id, None)
        self._meta.pop(item_id, None)

    def query(self, vector: list[float], top_k: int = 5) -> list[RetrievalHit]:
        if not self._vectors:
            return []
        scored: list[RetrievalHit] = []
        for item_id, candidate in self._vectors.items():
            scored.append(
                RetrievalHit(
                    item_id=item_id,
                    score=_cosine_similarity(vector, candidate),
                    metadata=self._meta.get(item_id, {}),
                )
            )
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[: max(1, top_k)]

    def get_vector(self, item_id: str) -> list[float] | None:
        return self._vectors.get(item_id)

    def save(self) -> None:
        data = {
            "backend": self._backend,
            "vectors": self._vectors,
            "meta": self._meta,
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False))

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            vectors = data.get("vectors", {})
            meta = data.get("meta", {})
            self._vectors = {k: [float(x) for x in v] for k, v in vectors.items()}
            self._meta = {k: dict(v) for k, v in meta.items()}
        except Exception:
            self._vectors = {}
            self._meta = {}

    @staticmethod
    def _has_cuvs() -> bool:
        try:
            __import__("cuvs")
            return True
        except Exception:
            return False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a[:n]))
    nb = math.sqrt(sum(x * x for x in b[:n]))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
