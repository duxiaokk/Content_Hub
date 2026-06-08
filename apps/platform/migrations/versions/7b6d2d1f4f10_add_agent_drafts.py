"""add agent drafts

Revision ID: 7b6d2d1f4f10
Revises: e1f0d2a7c9b8
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b6d2d1f4f10"
down_revision: Union[str, Sequence[str], None] = "e1f0d2a7c9b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_type", sa.String(length=64), nullable=False, server_default="youtube_repost"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending_review"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_platform", sa.String(length=64), nullable=False),
        sa.Column("source_link", sa.String(length=1024), nullable=False),
        sa.Column("source_external_id", sa.String(length=255), nullable=True),
        sa.Column("source_dedup_key", sa.String(length=255), nullable=True),
        sa.Column("markdown_path", sa.String(length=512), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False, server_default="ado_repost"),
        sa.Column("reviewed_by", sa.String(length=150), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_agent_drafts_id", "agent_drafts", ["id"])
    op.create_index("ix_agent_drafts_draft_type", "agent_drafts", ["draft_type"])
    op.create_index("ix_agent_drafts_status", "agent_drafts", ["status"])
    op.create_index("ix_agent_drafts_title", "agent_drafts", ["title"])
    op.create_index("ix_agent_drafts_source_platform", "agent_drafts", ["source_platform"])
    op.create_index("ix_agent_drafts_source_link", "agent_drafts", ["source_link"])
    op.create_index("ix_agent_drafts_source_external_id", "agent_drafts", ["source_external_id"])
    op.create_index("ix_agent_drafts_source_dedup_key", "agent_drafts", ["source_dedup_key"], unique=True)
    op.create_index("ix_agent_drafts_markdown_path", "agent_drafts", ["markdown_path"])
    op.create_index("ix_agent_drafts_target_type", "agent_drafts", ["target_type"])
    op.create_index("ix_agent_drafts_target_id", "agent_drafts", ["target_id"])
    op.create_index("ix_agent_drafts_created_by", "agent_drafts", ["created_by"])
    op.create_index("ix_agent_drafts_reviewed_by", "agent_drafts", ["reviewed_by"])
    op.create_index("ix_agent_drafts_created_at", "agent_drafts", ["created_at"])
    op.create_index("ix_agent_drafts_reviewed_at", "agent_drafts", ["reviewed_at"])
    op.create_index("ix_agent_drafts_updated_at", "agent_drafts", ["updated_at"])
    op.create_index("ix_agent_drafts_status_created", "agent_drafts", ["status", "created_at"])
    op.create_index(
        "ix_agent_drafts_source_platform_created",
        "agent_drafts",
        ["source_platform", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_drafts_source_platform_created", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_status_created", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_updated_at", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_reviewed_at", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_created_at", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_reviewed_by", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_created_by", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_target_id", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_target_type", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_markdown_path", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_source_dedup_key", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_source_external_id", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_source_link", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_source_platform", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_title", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_status", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_draft_type", table_name="agent_drafts")
    op.drop_index("ix_agent_drafts_id", table_name="agent_drafts")
    op.drop_table("agent_drafts")
