"""Agent dashboard (docs/PLAN.md §8, §11.5): count cards plus "My queue" and "Unassigned".

"My open" is personal; "unassigned", "waiting for user" and "urgent" show the whole team's load.
Only active tickets (open, in progress, waiting for user) are counted or listed.
"""

from dataclasses import dataclass

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.ticket import Ticket, TicketPriority, TicketStatus
from app.models.user import Role, User

ACTIVE_STATUSES = (TicketStatus.open, TicketStatus.in_progress, TicketStatus.waiting_for_user)
QUEUE_LIMIT = 20

# Urgent first, then high, medium, low.
PRIORITY_ORDER = case(
    {
        TicketPriority.urgent.value: 0,
        TicketPriority.high.value: 1,
        TicketPriority.medium.value: 2,
        TicketPriority.low.value: 3,
    },
    value=Ticket.priority,
)


@dataclass(frozen=True)
class DashboardCounts:
    my_open: int
    unassigned: int
    waiting_for_user: int
    urgent: int


@dataclass(frozen=True)
class AgentDashboard:
    counts: DashboardCounts
    my_queue: list[Ticket]
    unassigned: list[Ticket]


def _count(db: Session, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(Ticket).where(*conditions)) or 0


def _queue(db: Session, stmt: Select, limit: int) -> list[Ticket]:
    stmt = (
        stmt.options(selectinload(Ticket.creator), selectinload(Ticket.assignee))
        .order_by(PRIORITY_ORDER, Ticket.updated_at.desc(), Ticket.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def agent_dashboard(db: Session, agent: User, limit: int = QUEUE_LIMIT) -> AgentDashboard:
    active = Ticket.status.in_(ACTIVE_STATUSES)
    mine = Ticket.assigned_to == agent.id
    nobody = Ticket.assigned_to.is_(None)

    counts = DashboardCounts(
        my_open=_count(db, active, mine),
        unassigned=_count(db, active, nobody),
        waiting_for_user=_count(db, Ticket.status == TicketStatus.waiting_for_user),
        urgent=_count(db, active, Ticket.priority == TicketPriority.urgent),
    )
    return AgentDashboard(
        counts=counts,
        my_queue=_queue(db, select(Ticket).where(active, mine), limit),
        unassigned=_queue(db, select(Ticket).where(active, nobody), limit),
    )


def list_agents(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == Role.agent).order_by(User.full_name, User.id))
    )
