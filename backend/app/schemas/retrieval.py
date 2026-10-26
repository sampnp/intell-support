import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SearchHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: int
    document_title: str
    page: int | None
    snippet: str
    score: float


class SearchResponse(BaseModel):
    """docs/PLAN.md §8: `mode` is the mode actually used."""

    model_config = ConfigDict(from_attributes=True)

    mode: Literal["semantic", "keyword"]
    insufficient: bool
    results: list[SearchHitOut]


class SuggestionsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Null when no snapshot exists yet, or when retrieval failed while taking it.
    mode: Literal["semantic", "keyword"] | None
    insufficient: bool
    updated_at: datetime | None
    results: list[SearchHitOut]
