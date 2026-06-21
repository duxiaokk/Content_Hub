"""add agent memory table

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f7, b7c8d9e0f1a2, b0c1d2e3f4a5, dc7b5505f37c
Create Date: 2026-06-21 17:12:00
"""

from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c4d5e6f7a8b9"
down_revision: Sequence[str] = ("a1b2c3d4e5f7", "b7c8d9e0f1a2", "b0c1d2e3f4a5", "dc7b5505f37c")
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "agent_memory"):
        op.create_table(
            "agent_memory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("scope_key", sa.String(length=255), nullable=True),
            sa.Column("memory_type", sa.String(length=32), nullable=False),
            sa.Column("memory_key", sa.String(length=128), nullable=False),
            sa.Column("value_json", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)
    for index_name, columns, unique in [
        ("ix_agent_memory_id", ["id"], False),
        ("ix_agent_memory_scope", ["scope"], False),
        ("ix_agent_memory_scope_key", ["scope_key"], False),
        ("ix_agent_memory_memory_type", ["memory_type"], False),
        ("ix_agent_memory_memory_key", ["memory_key"], False),
        ("ix_agent_memory_source", ["source"], False),
        ("ix_agent_memory_expires_at", ["expires_at"], False),
        ("ix_agent_memory_created_at", ["created_at"], False),
        ("ix_agent_memory_updated_at", ["updated_at"], False),
        ("ix_agent_memory_scope_scope_key_type", ["scope", "scope_key", "memory_type"], False),
        ("uq_agent_memory_scope_scope_key_memory_key", ["scope", "scope_key", "memory_key"], True),
    ]:
        if not _has_index(inspector, "agent_memory", index_name):
            op.create_index(index_name, "agent_memory", columns, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not _has_table(inspector, "agent_memory"):
        return

    for index_name in [
        "uq_agent_memory_scope_scope_key_memory_key",
        "ix_agent_memory_scope_scope_key_type",
        "ix_agent_memory_updated_at",
        "ix_agent_memory_created_at",
        "ix_agent_memory_expires_at",
        "ix_agent_memory_source",
        "ix_agent_memory_memory_key",
        "ix_agent_memory_memory_type",
        "ix_agent_memory_scope_key",
        "ix_agent_memory_scope",
        "ix_agent_memory_id",
    ]:
        if _has_index(inspector, "agent_memory", index_name):
            op.drop_index(index_name, table_name="agent_memory")

    op.drop_table("agent_memory")
