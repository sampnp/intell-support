"""Test doubles for retrieval: a deterministic embedder and failing embedder / vector store."""

import hashlib
import math
import re

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in is it its my "
    "no not of on or our so that the their them then there these they this to was we what "
    "when where which who why will with you your".split()
)


class HashingEmbedder:
    """Bag of words hashed into `dim` buckets, L2-normalised: cosine similarity reflects shared
    words, so "relevant result for a known query" is meaningful without the real model."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            # No content words: a fixed unit vector that matches nothing in particular.
            vector[0] = 1.0
            return vector
        return [v / norm for v in vector]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def check(self) -> None:
        return None


class FailingEmbedder(HashingEmbedder):
    def embed_passages(self, texts):
        raise RuntimeError("embedding model unavailable")

    def embed_query(self, text):
        raise RuntimeError("embedding model unavailable")

    def check(self):
        raise RuntimeError("embedding model unavailable")


class BrokenStore:
    """Stands in for a VectorStore whose Qdrant server is down."""

    def _fail(self, *args, **kwargs):
        raise ConnectionError("qdrant unreachable")

    ensure_collection = upsert_chunks = search = delete_document = count_for_document = _fail
