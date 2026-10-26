"""GET /api/dashboard/agent — counts, my queue and unassigned (agents only)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_agent
from app.db import get_db
from app.models.user import User
from app.schemas.dashboard import AgentDashboard
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/agent", response_model=AgentDashboard)
def agent_dashboard(
    agent: User = Depends(require_agent),
    db: Session = Depends(get_db),
) -> AgentDashboard:
    return AgentDashboard.model_validate(dashboard_service.agent_dashboard(db, agent))
