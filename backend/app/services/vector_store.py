"""Qdrant access. WP1 only needs a client for the health check; the KB wrapper is added in WP6."""

from collections.abc import Iterator

from qdrant_client import QdrantClient

from app.config import get_settings


def get_qdrant_client() -> Iterator[QdrantClient]:
    client = QdrantClient(url=get_settings().qdrant_url, timeout=2)
    try:
        yield client
    finally:
        client.close()
