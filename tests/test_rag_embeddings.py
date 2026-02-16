from yak.rag.embeddings import EmbeddingConfig, EmbeddingService


def test_hash_embedding_is_deterministic() -> None:
    svc = EmbeddingService(EmbeddingConfig(backend="hash", dim=64))
    a = svc.embed_text("hello world")
    b = svc.embed_text("hello world")
    c = svc.embed_text("different text")

    assert len(a) == 64
    assert a == b
    assert a != c
