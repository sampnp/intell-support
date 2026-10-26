"""Qdrant access: one shared client, and the `kb_chunks` collection wrapper.

Point ids are the `document_chunks.id` UUIDs; Postgres stays the source of truth, so every search
result is joined back to it before being returned.
"""

import uuid
from collections.abc import Sequence
from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import get_settings
from app.models.document import Document, DocumentChunk


@lru_cache
def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, timeout=5)


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int) -> None:
        self.client = client
        self.collection = collection
        self.dim = dim

    def ensure_collection(self) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection,
                vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
            )

    def upsert_chunks(
        self,
        document: Document,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        points = [
            qm.PointStruct(
                id=str(chunk.id),
                vector=list(vector),
                payload={
                    "document_id": document.id,
                    "document_title": document.title,
                    "page": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                },
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        if points:
            self.client.upsert(self.collection, points=points, wait=True)

    def search(self, vector: Sequence[float], limit: int) -> list[tuple[uuid.UUID, float]]:
        # Nothing indexed yet is an empty result, not an error (an error means "fall back").
        if not self.client.collection_exists(self.collection):
            return []
        response = self.client.query_points(
            self.collection, query=list(vector), limit=limit, with_payload=False
        )
        return [(uuid.UUID(str(point.id)), point.score) for point in response.points]

    def _document_filter(self, document_id: int) -> qm.Filter:
        return qm.Filter(
            must=[qm.FieldCondition(key="document_id", match=qm.MatchValue(value=document_id))]
        )

    def delete_document(self, document_id: int) -> None:
        if not self.client.collection_exists(self.collection):
            return
        self.client.delete(
            self.collection,
            points_selector=qm.FilterSelector(filter=self._document_filter(document_id)),
            wait=True,
        )

    def count_for_document(self, document_id: int) -> int:
        if not self.client.collection_exists(self.collection):
            return 0
        result = self.client.count(
            self.collection, count_filter=self._document_filter(document_id), exact=True
        )
        return result.count


def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(get_qdrant_client(), settings.qdrant_collection, settings.embedding_dim)
