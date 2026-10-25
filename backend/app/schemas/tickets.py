from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.ticket import EventType, TicketCategory, TicketPriority, TicketStatus
from app.models.user import Role

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)]
Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)
]
CommentBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: Role


class TicketCreate(BaseModel):
    # Extra keys (status, assigned_to, ...) are ignored: new tickets always start open, unassigned.
    title: Title
    description: Description
    category: TicketCategory
    priority: TicketPriority = TicketPriority.medium


class TicketUpdate(BaseModel):
    title: Title | None = None
    description: Description | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "TicketUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide title and/or description")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TicketSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_by: UserSummary = Field(validation_alias="creator")
    assigned_to: UserSummary | None = Field(validation_alias="assignee")
    created_at: datetime
    updated_at: datetime


class TicketOut(TicketSummary):
    description: str
    # Status moves the current user may make (docs/PLAN.md §6); filled in by the router.
    allowed_transitions: list[TicketStatus] = []


class StatusChange(BaseModel):
    status: TicketStatus


class AssignRequest(BaseModel):
    # Required key; null unassigns.
    agent_id: int | None


class TicketPage(BaseModel):
    items: list[TicketSummary]
    total: int
    page: int
    page_size: int


class CommentCreate(BaseModel):
    body: CommentBody
    is_internal: bool = False


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author: UserSummary
    body: str
    is_internal: bool
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    actor: UserSummary
    event_type: EventType
    data: dict[str, Any]
    created_at: datetime
