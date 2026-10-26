from pydantic import BaseModel, ConfigDict

from app.schemas.tickets import TicketSummary


class DashboardCounts(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    my_open: int
    unassigned: int
    waiting_for_user: int
    urgent: int


class AgentDashboard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    counts: DashboardCounts
    my_queue: list[TicketSummary]
    unassigned: list[TicketSummary]
