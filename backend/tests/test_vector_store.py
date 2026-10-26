import math
import uuid
from types import SimpleNamespace

import pytest

from app.services.vector_store import VectorStore
from tests.fakes import HashingEmbedder


@pytest.fixture
def store(qdrant_client):
    return VectorStore(qdrant_client, "test_chunks", 384)


def make_document(document_id, title, texts):
    document = SimpleNamespace(id=document_id, title=title)
    chunks = [
        SimpleNamespace(id=uuid.uuid4(), page_number=1, chunk_index=i, text=text)
        for i, text in enumerate(texts)
    ]
    return document, chunks


def index(store, embedder, document, chunks):
    store.ensure_collection()
    store.upsert_chunks(document, chunks, embedder.embed_passages([c.text for c in chunks]))


def test_ensure_collection_is_idempotent(store, qdrant_client):
    store.ensure_collection()
    store.ensure_collection()

    assert qdrant_client.collection_exists("test_chunks")


def test_search_without_collection_is_empty(store):
    assert store.search([1.0] + [0.0] * 383, limit=3) == []
    assert store.count_for_document(1) == 0
    store.delete_document(1)  # no-op, no error


def test_upsert_and_search(store, qdrant_client):
    embedder = HashingEmbedder()
    document, chunks = make_document(
        7, "Billing", ["refund duplicate charge invoice", "sync conflict copy"]
    )
    index(store, embedder, document, chunks)

    hits = store.search(embedder.embed_query("duplicate charge refund"), limit=2)

    assert [chunk_id for chunk_id, _ in hits][0] == chunks[0].id
    assert hits[0][1] > hits[1][1]
    point = qdrant_client.retrieve("test_chunks", ids=[str(chunks[0].id)])[0]
    assert point.payload == {
        "document_id": 7,
        "document_title": "Billing",
        "page": 1,
        "chunk_index": 0,
    }


def test_delete_document_removes_only_its_points(store):
    embedder = HashingEmbedder()
    keep_doc, keep_chunks = make_document(1, "Keep", ["alpha beta", "gamma delta"])
    drop_doc, drop_chunks = make_document(2, "Drop", ["alpha gamma", "beta delta", "epsilon"])
    index(store, embedder, keep_doc, keep_chunks)
    index(store, embedder, drop_doc, drop_chunks)
    assert (store.count_for_document(1), store.count_for_document(2)) == (2, 3)

    store.delete_document(2)

    assert (store.count_for_document(1), store.count_for_document(2)) == (2, 0)
    remaining = {chunk_id for chunk_id, _ in store.search(embedder.embed_query("alpha"), 10)}
    assert remaining == {c.id for c in keep_chunks}


def test_hashing_embedder_is_deterministic_and_normalised():
    embedder = HashingEmbedder()

    first = embedder.embed_query("Refund for a duplicate charge")
    second = embedder.embed_passages(["refund for a duplicate CHARGE"])[0]

    assert first == second  # case and stopwords don't matter
    assert len(first) == 384
    assert math.isclose(math.sqrt(sum(v * v for v in first)), 1.0)


def test_hashing_embedder_similarity_follows_word_overlap():
    embedder = HashingEmbedder()
    query = embedder.embed_query("refund duplicate charge")

    def cosine(text):
        return sum(a * b for a, b in zip(query, embedder.embed_query(text)))

    assert cosine("duplicate charge refund policy") > cosine("sync conflict folder") + 0.3
