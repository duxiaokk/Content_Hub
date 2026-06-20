"""add media metadata columns

Revision ID: b0c1d2e3f4a5
Revises: a29f40c35240
Create Date: 2026-06-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "b0c1d2e3f4a5"
down_revision = "a29f40c35240"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _ensure_column(table_name: str, column: sa.Column) -> None:
    inspector = inspect(op.get_bind())
    if _has_table(inspector, table_name) and not _has_column(inspector, table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _ensure_column("content_items", sa.Column("metadata_json", sa.Text(), nullable=True))
    _ensure_column("posts", sa.Column("media_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table_name, column_name in [
        ("content_items", "metadata_json"),
        ("posts", "media_json"),
    ]:
        if _has_table(inspector, table_name) and _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
