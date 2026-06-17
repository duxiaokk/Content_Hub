"""add workflow_run

Revision ID: b7c8d9e0f1a2
Revises: f3a1c2d4e5f6
Create Date: 2026-06-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b7c8d9e0f1a2"
down_revision = "f3a1c2d4e5f6"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "workflow_run"):
        op.create_table(
            "workflow_run",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("workflow_name", sa.String(length=64), nullable=False),
            sa.Column("trigger_type", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("items_succeeded", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("items_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", sa.Text(), nullable=True),
            sa.Column("trace_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)
    if not _has_index(inspector, "workflow_run", "ix_workflow_run_name_status_created"):
        op.create_index(
            "ix_workflow_run_name_status_created",
            "workflow_run",
            ["workflow_name", "status", "created_at"],
            unique=False,
        )

    if _has_table(inspector, "publish_records") and not _has_index(
        inspector, "publish_records", "uq_publish_records_run_content_target"
    ):
        op.create_index(
            "uq_publish_records_run_content_target",
            "publish_records",
            ["run_id", "content_item_id", "target_type"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "publish_records") and _has_index(
        inspector, "publish_records", "uq_publish_records_run_content_target"
    ):
        op.drop_index("uq_publish_records_run_content_target", table_name="publish_records")

    if _has_table(inspector, "workflow_run"):
        if _has_index(inspector, "workflow_run", "ix_workflow_run_name_status_created"):
            op.drop_index("ix_workflow_run_name_status_created", table_name="workflow_run")
        op.drop_table("workflow_run")
