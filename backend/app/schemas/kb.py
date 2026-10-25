from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus
from app.schemas.tickets import UserSummary


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    error_message: str | None
    vector_indexed: bool
    chunk_count: int
    uploaded_by: UserSummary = Field(validation_alias="uploader")
    created_at: datetime
