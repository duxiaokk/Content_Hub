"""add missing content_items columns

Revision ID: dc7b5505f37c
Revises: 614a813bd9e2
Create Date: 2026-06-19 20:56:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = 'dc7b5505f37c'
down_revision = '614a813bd9e2'
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    return any(c["name"] == column for c in inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # content_items table
    if "content_items" in inspector.get_table_names():
        for col_name, col_type, fk in [
            ("source_config_id", sa.Integer(), "source_configs.id"),
            ("fetch_run_id", sa.Integer(), "fetch_runs.id"),
            ("reviewed_by", sa.String(150), None),
            ("draft_post_id", sa.Integer(), "posts.id"),
        ]:
            if not _has_column("content_items", col_name):
                with op.batch_alter_table("content_items") as batch_op:
                    batch_op.add_column(sa.Column(col_name, col_type, nullable=True))
                if fk:
                    try:
                        op.create_foreign_key(
                            f"fk_content_items_{col_name}",
                            "content_items", fk.split(".")[0],
                            [col_name], [fk.split(".")[1]],
                        )
                    except Exception:
                        pass


def downgrade() -> None:
    for col_name in ["source_config_id", "fetch_run_id", "reviewed_by", "draft_post_id"]:
        try:
            with op.batch_alter_table("content_items") as batch_op:
                batch_op.drop_column(col_name)
        except Exception:
            pass
