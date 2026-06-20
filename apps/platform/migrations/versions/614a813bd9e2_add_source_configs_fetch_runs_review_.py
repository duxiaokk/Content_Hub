"""add source_configs, fetch_runs, review_decisions tables

Revision ID: 614a813bd9e2
Revises: a29f40c35240
Create Date: 2026-06-19 17:13:45.760147

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = '614a813bd9e2'
down_revision = 'a29f40c35240'
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    return any(
        idx["name"] == index_name
        for idx in inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    # --- source_configs ---
    if not _has_table("source_configs"):
        op.create_table(
            "source_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("source_type", sa.String(64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("channels", sa.Text(), nullable=True),
            sa.Column("keywords", sa.Text(), nullable=True),
            sa.Column("lookback_hours", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("item_limit", sa.Integer(), nullable=False, server_default="20"),
            sa.Column("dedup_window_hours", sa.Integer(), nullable=False, server_default="24"),
            sa.Column("config_json", sa.Text(), nullable=True),
            sa.Column("last_cursor", sa.Text(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_source_configs_name", "source_configs", ["name"], unique=True)
        op.create_index("ix_source_configs_source_type", "source_configs", ["source_type"])
        op.create_index("ix_source_configs_enabled", "source_configs", ["enabled"])
        op.create_index("ix_source_configs_last_run_at", "source_configs", ["last_run_at"])
        op.create_index("ix_source_configs_created_at", "source_configs", ["created_at"])
        op.create_index("ix_source_configs_updated_at", "source_configs", ["updated_at"])
        op.create_index(
            "ix_source_configs_type_enabled", "source_configs", ["source_type", "enabled"]
        )

    # --- fetch_runs ---
    if not _has_table("fetch_runs"):
        op.create_table(
            "fetch_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_config_id", sa.Integer(), nullable=False),
            sa.Column("trigger_mode", sa.String(32), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("task_id", sa.String(64), nullable=True),
            sa.Column("trace_id", sa.String(64), nullable=True),
            sa.Column("requested_by", sa.String(150), nullable=True),
            sa.Column("request_payload", sa.Text(), nullable=True),
            sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("deduped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_fetch_runs_source_config_id", "fetch_runs", ["source_config_id"])
        op.create_index("ix_fetch_runs_trigger_mode", "fetch_runs", ["trigger_mode"])
        op.create_index("ix_fetch_runs_status", "fetch_runs", ["status"])
        op.create_index("ix_fetch_runs_task_id", "fetch_runs", ["task_id"])
        op.create_index("ix_fetch_runs_trace_id", "fetch_runs", ["trace_id"])
        op.create_index("ix_fetch_runs_requested_by", "fetch_runs", ["requested_by"])
        op.create_index("ix_fetch_runs_started_at", "fetch_runs", ["started_at"])
        op.create_index("ix_fetch_runs_finished_at", "fetch_runs", ["finished_at"])
        op.create_index("ix_fetch_runs_created_at", "fetch_runs", ["created_at"])
        op.create_index(
            "ix_fetch_runs_source_status_created",
            "fetch_runs",
            ["source_config_id", "status", "created_at"],
        )

    # --- review_decisions ---
    if not _has_table("review_decisions"):
        op.create_table(
            "review_decisions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("content_item_id", sa.Integer(), nullable=False),
            sa.Column("decision", sa.String(32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("operator", sa.String(150), nullable=False),
            sa.Column("snapshot_title", sa.String(255), nullable=True),
            sa.Column("snapshot_content", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_review_decisions_content_item_id", "review_decisions", ["content_item_id"])
        op.create_index("ix_review_decisions_decision", "review_decisions", ["decision"])
        op.create_index("ix_review_decisions_operator", "review_decisions", ["operator"])
        op.create_index("ix_review_decisions_created_at", "review_decisions", ["created_at"])
        op.create_index(
            "ix_review_decisions_content_created",
            "review_decisions",
            ["content_item_id", "created_at"],
        )


def downgrade() -> None:
    if _has_table("source_configs"):
        op.drop_table("source_configs")
    if _has_table("fetch_runs"):
        op.drop_table("fetch_runs")
    if _has_table("review_decisions"):
        op.drop_table("review_decisions")
