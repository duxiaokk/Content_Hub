"""drop agent tables

Revision ID: e1f0d2a7c9b8
Revises: 09ae83bb82ab
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f0d2a7c9b8"
down_revision: Union[str, Sequence[str], None] = "09ae83bb82ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("agent_drafts")
    op.drop_table("agent_tasks")


def downgrade() -> None:
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("input_data", sa.Text(), nullable=True),
        sa.Column("result_data", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_tasks_task_type", "agent_tasks", ["task_type"])
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_target_type", "agent_tasks", ["target_type"])
    op.create_index("ix_agent_tasks_target_id", "agent_tasks", ["target_id"])
    op.create_index("ix_agent_tasks_created_at", "agent_tasks", ["created_at"])
    op.create_index("ix_agent_tasks_updated_at", "agent_tasks", ["updated_at"])

    op.create_table(
        "agent_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default="agent"),
        sa.Column("reviewed_by", sa.String(length=150), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_drafts_draft_type", "agent_drafts", ["draft_type"])
    op.create_index("ix_agent_drafts_status", "agent_drafts", ["status"])
    op.create_index("ix_agent_drafts_target_type", "agent_drafts", ["target_type"])
    op.create_index("ix_agent_drafts_target_id", "agent_drafts", ["target_id"])
    op.create_index("ix_agent_drafts_created_at", "agent_drafts", ["created_at"])
