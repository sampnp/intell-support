"""GET /api/health — status of the database, Qdrant and the embedder.

Always 200: this is a status report. `status` is "degraded" when a dependency is down.
"""

import logging

from fastapi import APIRouter, Depends
from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.health import HealthResponse
from app.services.embeddings import Embedder, get_embedder
from app.services.vector_store import get_qdrant_client

logger = logging.getLogger("app.health")

router = APIRouter(tags=["health"])


def _check_db(db: Session) -> str:
    try:
        db.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("health_check component=db error=%r", exc)
        return "error"


def _check_qdrant(client: QdrantClient) -> str:
    try:
        client.get_collections()
        return "ok"
    except Exception as exc:
        logger.warning("health_check component=qdrant error=%r", exc)
        return "error"


def _check_embedder(embedder: Embedder) -> str:
    try:
        # Loads the model on first call (1-2 s), then it is cached.
        embedder.check()
        return "ok"
    except Exception as exc:
        logger.warning("health_check component=embedder error=%r", exc)
        return "error"


@router.get("/health", response_model=HealthResponse)
def health(
    db: Session = Depends(get_db),
    qdrant: QdrantClient = Depends(get_qdrant_client),
    embedder: Embedder = Depends(get_embedder),
) -> HealthResponse:
    db_status = _check_db(db)
    qdrant_status = _check_qdrant(qdrant)
    embedder_status = _check_embedder(embedder)
    degraded = "error" in (db_status, qdrant_status, embedder_status)
    return HealthResponse(
        status="degraded" if degraded else "ok",
        db=db_status,
        qdrant=qdrant_status,
        embedder=embedder_status,
    )
