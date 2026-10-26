"""GET /api/users/agents — the agents an agent can assign tickets to."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_agent
from app.db import get_db
from app.models.user import User
from app.schemas.tickets import UserSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/agents", response_model=list[UserSummary])
def list_agents(
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> list[UserSummary]:
    return [UserSummary.model_validate(user) for user in dashboard_service.list_agents(db)]
