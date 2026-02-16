"""Embedding service with NVIDIA-first configuration and safe fallbacks."""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass

import httpx


DEFAULT_MODEL_ID = "nvidia/llama-nemotron-embed-vl-1b-v2"
DEFAULT_OLLAMA_MODEL = "nemotron-mini"


@dataclass
class EmbeddingConfig:
    model_id: str = DEFAULT_MODEL_ID
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    dim: int = 256
    timeout_s: float = 15.0
    backend: str = "auto"  # auto | ollama | hash


class EmbeddingService:
    """Produces text embeddings.

    Backend selection:
    - `ollama`: uses Ollama `/api/embeddings`
    - `hash`: deterministic local fallback
    - `auto`: tries ollama first, then hash
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or EmbeddingConfig(
            ollama_base_url=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_OLLAMA_MODEL),
        )

    def embed_text(self, text: str) -> list[float]:
        if self.config.backend in ("auto", "ollama"):
            vec = self._embed_with_ollama(text)
            if vec is not None:
                return vec
            if self.config.backend == "ollama":
                raise RuntimeError("Ollama embedding backend unavailable")
        return self._embed_with_hash(text)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]

    def _embed_with_ollama(self, text: str) -> list[float] | None:
        payload = {"model": self.config.ollama_model, "prompt": text}
        try:
            with httpx.Client(timeout=self.config.timeout_s) as client:
                response = client.post(
                    f"{self.config.ollama_base_url.rstrip('/')}/api/embeddings",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list) or not embedding:
                return None
            return [float(x) for x in embedding]
        except Exception:
            return None

    def _embed_with_hash(self, text: str) -> list[float]:
        dim = max(32, int(self.config.dim))
        values = [0.0] * dim
        tokens = text.lower().split()
        if not tokens:
            tokens = [""]
        for token in tokens:
            h = hashlib.sha256(token.encode("utf-8")).digest()
            for i, b in enumerate(h):
                values[i % dim] += (b / 255.0) - 0.5
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
