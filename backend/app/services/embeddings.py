"""Text embeddings. `Embedder` is the interface the rest of the app uses; FastEmbedEmbedder runs
BAAI/bge-small-en-v1.5 locally on CPU (ONNX). Tests swap in a deterministic fake."""

import logging
import threading
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

logger = logging.getLogger("app.embeddings")


class Embedder(Protocol):
    dim: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def check(self) -> None:
        """Raise if the embedder can't be used."""


class FastEmbedEmbedder:
    def __init__(self, model_name: str, dim: int, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.dim = dim
        self.cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _get_model(self):
        # Loaded lazily (1-2 s) so app start and tests that don't need it stay fast.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    model = TextEmbedding(self.model_name, cache_dir=self.cache_dir)
                    probe = next(iter(model.query_embed("dimension check")))
                    if len(probe) != self.dim:
                        raise RuntimeError(
                            f"{self.model_name} produces {len(probe)}-dim vectors, "
                            f"expected {self.dim}"
                        )
                    self._model = model
                    logger.info("embedder_loaded model=%s dim=%s", self.model_name, self.dim)
        return self._model

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [vector.tolist() for vector in self._get_model().passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._get_model().query_embed(text))).tolist()

    def check(self) -> None:
        self._get_model()


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
    )
