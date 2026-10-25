"""create tickets, ticket_comments, ticket_events

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Values are written out (not imported from app.models) so this revision never changes.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    # Constraint and index names match the naming convention in app/db.py.
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("priority", sa.String(length=20), server_default="medium", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("assigned_to", sa.Integer(), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_SQL, persisted=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tickets_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to"], ["users.id"], name=op.f("fk_tickets_assigned_to_users")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'waiting_for_user', 'resolved', 'closed')",
            name=op.f("ck_tickets_status_valid"),
        ),
        sa.CheckConstraint(
            "category IN ('account', 'billing', 'technical', 'sync', 'other')",
            name=op.f("ck_tickets_category_valid"),
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name=op.f("ck_tickets_priority_valid"),
        ),
    )
    op.create_index(op.f("ix_tickets_status"), "tickets", ["status"])
    op.create_index(op.f("ix_tickets_created_by"), "tickets", ["created_by"])
    op.create_index(op.f("ix_tickets_assigned_to"), "tickets", ["assigned_to"])
    op.create_index(
        "ix_tickets_search_vector", "tickets", ["search_vector"], postgresql_using="gin"
    )

    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_comments")),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_comments_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_ticket_comments_author_id_users")
        ),
    )
    op.create_index(op.f("ix_ticket_comments_ticket_id"), "ticket_comments", ["ticket_id"])

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _timestamp("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_ticket_events_ticket_id_tickets")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_ticket_events_actor_id_users")
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'status_changed', 'assigned', 'comment_added', "
            "'internal_note_added', 'ticket_updated')",
            name=op.f("ck_ticket_events_event_type_valid"),
        ),
    )
    op.create_index(op.f("ix_ticket_events_ticket_id"), "ticket_events", ["ticket_id"])

    # ticket_events is append-only (docs/PLAN.md §5).
    op.execute(
        """
        CREATE FUNCTION ticket_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ticket_events is append-only (% not allowed)', TG_OP;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER ticket_events_append_only
        BEFORE UPDATE OR DELETE ON ticket_events
        FOR EACH ROW EXECUTE FUNCTION ticket_events_append_only()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ticket_events_append_only ON ticket_events")
    op.execute("DROP FUNCTION IF EXISTS ticket_events_append_only()")
    op.drop_table("ticket_events")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
