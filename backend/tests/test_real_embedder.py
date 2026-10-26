"""The real BAAI/bge-small-en-v1.5 model (baked into the image) over the sample KB.

Deselect with: pytest -m "not slow"."""

import math

import pytest

from app.config import get_settings
from app.services import retrieval
from app.services.embeddings import FastEmbedEmbedder
from app.services.ingestion import ingest_bytes
from app.services.vector_store import VectorStore

pytestmark = pytest.mark.slow

# Natural-language questions sharing few exact words with the answer.
QUERIES = [
    ("I was charged twice, how do I get my money back?", "billing-refund-policy"),
    ("my authenticator app codes are not accepted", "account-login-troubleshooting"),
    ("two versions of the same file appeared after editing offline", "sync-troubleshooting"),
    ("how do I make a shared link stop working after a date", "sharing-permissions-faq"),
]


@pytest.fixture(scope="module")
def real_embedder():
    settings = get_settings()
    return FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
    )


def test_real_vectors_are_384_dim_and_normalised(real_embedder):
    vector = real_embedder.embed_query("How do I reset my password?")

    assert len(vector) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, abs_tol=1e-3)


def test_real_model_finds_expected_documents(
    db_session, make_user, sample_kb, qdrant_client, real_embedder, monkeypatch
):
    threshold = 0.5
    monkeypatch.setattr(get_settings(), "retrieval_score_threshold", threshold)
    store = VectorStore(qdrant_client, "kb_chunks_real", 384)
    owner = make_user()
    documents = {
        path.stem: ingest_bytes(
            db_session,
            owner,
            path.name,
            path.read_bytes(),
            max_bytes=10 * 1024 * 1024,
            embedder=real_embedder,
            store=store,
        )
        for path in sorted(p for p in sample_kb.iterdir() if p.is_file())
    }
    assert all(d.vector_indexed for d in documents.values())

    for query, expected in QUERIES:
        result = retrieval.search(db_session, real_embedder, store, query, 3, mode="semantic")
        top3 = [hit.document_id for hit in result.results]
        assert result.mode == "semantic"
        assert not result.insufficient, query
        assert documents[expected].id in top3, (query, [h.document_title for h in result.results])
        assert result.results[0].score >= threshold
