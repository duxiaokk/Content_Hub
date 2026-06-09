"""add content_items

Revision ID: f3a1c2d4e5f6
Revises: e1f0d2a7c9b8
Create Date: 2026-06-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "f3a1c2d4e5f6"
down_revision = "e1f0d2a7c9b8"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "content_items"):
        op.create_table(
            "content_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_id", sa.String(length=255), nullable=False),
            sa.Column("source_url", sa.String(length=1024), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("raw_content", sa.Text(), nullable=True),
            sa.Column("processed_content", sa.Text(), nullable=True),
            sa.Column("publish_target", sa.String(length=128), nullable=True),
            sa.Column("publish_status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("pipeline_status", sa.String(length=32), nullable=False, server_default="fetched"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes("content_items")}
    if "uq_content_items_source" not in existing:
        op.create_index(
            "uq_content_items_source",
            "content_items",
            ["source_type", "source_id"],
            unique=True,
        )
    if "ix_content_items_pipeline_created" not in existing:
        op.create_index(
            "ix_content_items_pipeline_created",
            "content_items",
            ["pipeline_status", "created_at"],
            unique=False,
        )
    if "ix_content_items_publish_created" not in existing:
        op.create_index(
            "ix_content_items_publish_created",
            "content_items",
            ["publish_status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _has_table(inspector, "content_items"):
        existing = {index["name"] for index in inspector.get_indexes("content_items")}
        for index_name in [
            "ix_content_items_publish_created",
            "ix_content_items_pipeline_created",
            "uq_content_items_source",
        ]:
            if index_name in existing:
                op.drop_index(index_name, table_name="content_items")
        op.drop_table("content_items")
