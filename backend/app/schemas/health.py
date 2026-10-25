from typing import Literal

from pydantic import BaseModel

ComponentStatus = Literal["ok", "error", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: ComponentStatus
    qdrant: ComponentStatus
    embedder: ComponentStatus
