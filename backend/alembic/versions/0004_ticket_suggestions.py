"""ticket suggestions snapshot

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshot metadata on the ticket, so an empty snapshot still records its mode and time.
    op.add_column("tickets", sa.Column("suggestions_mode", sa.String(length=20), nullable=True))
    op.add_column(
        "tickets",
        sa.Column("suggestions_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_tickets_suggestions_mode_valid"),
        "tickets",
        "suggestions_mode IN ('semantic', 'keyword')",
    )

    op.create_table(
        "ticket_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("retrieval_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_suggestions")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_suggestions_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name=op.f("fk_ticket_suggestions_chunk_id_document_chunks"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "ticket_id", "rank", name=op.f("uq_ticket_suggestions_ticket_rank")
        ),
        sa.CheckConstraint(
            "retrieval_mode IN ('semantic', 'keyword')",
            name=op.f("ck_ticket_suggestions_retrieval_mode_valid"),
        ),
    )
    op.create_index(
        op.f("ix_ticket_suggestions_ticket_id"), "ticket_suggestions", ["ticket_id"]
    )
    op.create_index(op.f("ix_ticket_suggestions_chunk_id"), "ticket_suggestions", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("ticket_suggestions")
    op.drop_constraint(op.f("ck_tickets_suggestions_mode_valid"), "tickets", type_="check")
    op.drop_column("tickets", "suggestions_updated_at")
    op.drop_column("tickets", "suggestions_mode")
