"""mvp batch1 extend

Revision ID: a1b2c3d4e5f7
Revises: f3a1c2d4e5f6
Create Date: 2026-06-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "a1b2c3d4e5f7"
down_revision = "f3a1c2d4e5f6"
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


def _ensure_index(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    inspector = inspect(op.get_bind())
    if not _has_table(inspector, table_name):
        return
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    _ensure_column("content_items", sa.Column("source_account", sa.String(length=255), nullable=True))
    _ensure_column("content_items", sa.Column("language", sa.String(length=16), nullable=False, server_default="zh"))
    _ensure_column("content_items", sa.Column("summary", sa.Text(), nullable=True))
    _ensure_column("content_items", sa.Column("rewritten_title", sa.String(length=512), nullable=True))
    _ensure_column("content_items", sa.Column("rewritten_content", sa.Text(), nullable=True))
    _ensure_column("content_items", sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"))
    _ensure_column("content_items", sa.Column("score", sa.Float(), nullable=False, server_default="0"))
    _ensure_column("content_items", sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"))
    _ensure_column("content_items", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    _ensure_column("content_items", sa.Column("digest_included", sa.Boolean(), nullable=False, server_default=sa.false()))

    _ensure_index("content_items", "ix_content_items_source_account", ["source_account"])
    _ensure_index("content_items", "ix_content_items_language", ["language"])
    _ensure_index("content_items", "ix_content_items_digest_included", ["digest_included"])
    _ensure_index("content_items", "ix_content_items_review_created", ["review_status", "created_at"])

    inspector = inspect(bind)

    if not _has_table(inspector, "source_subscriptions"):
        op.create_table(
            "source_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_type", sa.String(length=64), nullable=False),
            sa.Column("source_name", sa.String(length=128), nullable=False),
            sa.Column("account_identifier", sa.String(length=255), nullable=True),
            sa.Column("feed_url", sa.String(length=1024), nullable=True),
            sa.Column("schedule_expression", sa.String(length=64), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("default_tags", sa.String(length=512), nullable=True),
            sa.Column("last_cursor", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(inspector, "filter_rules"):
        op.create_table(
            "filter_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rule_type", sa.String(length=32), nullable=False),
            sa.Column("rule_value", sa.Text(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(inspector, "rewrite_profiles"):
        op.create_table(
            "rewrite_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=True),
            sa.Column("model", sa.String(length=64), nullable=True),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
            sa.Column("fallback_strategy", sa.String(length=16), nullable=False, server_default="skip"),
            sa.Column("system_prompt", sa.Text(), nullable=True),
            sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="2048"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(inspector, "review_queue"):
        op.create_table(
            "review_queue",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id"), nullable=False),
            sa.Column("candidate_title", sa.String(length=512), nullable=True),
            sa.Column("candidate_content", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("reviewer", sa.String(length=64), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(inspector, "digest_reports"):
        op.create_table(
            "digest_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("content_markdown", sa.Text(), nullable=False),
            sa.Column("included_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("generated_at", sa.DateTime(), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if not _has_table(inspector, "publish_records"):
        op.create_table(
            "publish_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id"), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_name", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("external_url", sa.String(length=1024), nullable=True),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("response_payload", sa.Text(), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    _ensure_index("source_subscriptions", "ix_source_subscriptions_source_type", ["source_type"])
    _ensure_index("source_subscriptions", "ix_source_subscriptions_source_name", ["source_name"])
    _ensure_index("source_subscriptions", "ix_source_subscriptions_enabled", ["enabled"])
    _ensure_index("source_subscriptions", "ix_source_subscriptions_category", ["category"])
    _ensure_index(
        "source_subscriptions",
        "uq_source_subscriptions_type_account",
        ["source_type", "account_identifier"],
        unique=True,
    )

    _ensure_index("filter_rules", "ix_filter_rules_rule_type", ["rule_type"])
    _ensure_index("filter_rules", "ix_filter_rules_priority", ["priority"])
    _ensure_index("filter_rules", "ix_filter_rules_enabled", ["enabled"])

    _ensure_index("rewrite_profiles", "ix_rewrite_profiles_name", ["name"], unique=True)
    _ensure_index("rewrite_profiles", "ix_rewrite_profiles_provider", ["provider"])

    _ensure_index("review_queue", "ix_review_queue_content_item_id", ["content_item_id"])
    _ensure_index("review_queue", "ix_review_queue_status", ["status"])
    _ensure_index("review_queue", "ix_review_queue_reviewer", ["reviewer"])
    _ensure_index("review_queue", "ix_review_queue_reviewed_at", ["reviewed_at"])
    _ensure_index("review_queue", "ix_review_queue_created_at", ["created_at"])
    _ensure_index("review_queue", "ix_review_queue_updated_at", ["updated_at"])
    _ensure_index("review_queue", "ix_review_queue_status_created", ["status", "created_at"])

    _ensure_index("digest_reports", "ix_digest_reports_title", ["title"])
    _ensure_index("digest_reports", "ix_digest_reports_generated_at", ["generated_at"])
    _ensure_index("digest_reports", "ix_digest_reports_run_id", ["run_id"])
    _ensure_index("digest_reports", "ix_digest_reports_created_at", ["created_at"])
    _ensure_index("digest_reports", "ix_digest_reports_updated_at", ["updated_at"])

    _ensure_index("publish_records", "ix_publish_records_content_item_id", ["content_item_id"])
    _ensure_index("publish_records", "ix_publish_records_target_type", ["target_type"])
    _ensure_index("publish_records", "ix_publish_records_target_name", ["target_name"])
    _ensure_index("publish_records", "ix_publish_records_status", ["status"])
    _ensure_index("publish_records", "ix_publish_records_external_id", ["external_id"])
    _ensure_index("publish_records", "ix_publish_records_run_id", ["run_id"])
    _ensure_index("publish_records", "ix_publish_records_published_at", ["published_at"])
    _ensure_index("publish_records", "ix_publish_records_created_at", ["created_at"])
    _ensure_index("publish_records", "ix_publish_records_updated_at", ["updated_at"])
    _ensure_index(
        "publish_records",
        "ix_publish_records_target_status_created",
        ["target_type", "status", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table_name, index_name in [
        ("publish_records", "ix_publish_records_target_status_created"),
        ("publish_records", "ix_publish_records_updated_at"),
        ("publish_records", "ix_publish_records_created_at"),
        ("publish_records", "ix_publish_records_published_at"),
        ("publish_records", "ix_publish_records_run_id"),
        ("publish_records", "ix_publish_records_external_id"),
        ("publish_records", "ix_publish_records_status"),
        ("publish_records", "ix_publish_records_target_name"),
        ("publish_records", "ix_publish_records_target_type"),
        ("publish_records", "ix_publish_records_content_item_id"),
        ("digest_reports", "ix_digest_reports_updated_at"),
        ("digest_reports", "ix_digest_reports_created_at"),
        ("digest_reports", "ix_digest_reports_run_id"),
        ("digest_reports", "ix_digest_reports_generated_at"),
        ("digest_reports", "ix_digest_reports_title"),
        ("review_queue", "ix_review_queue_status_created"),
        ("review_queue", "ix_review_queue_updated_at"),
        ("review_queue", "ix_review_queue_created_at"),
        ("review_queue", "ix_review_queue_reviewed_at"),
        ("review_queue", "ix_review_queue_reviewer"),
        ("review_queue", "ix_review_queue_status"),
        ("review_queue", "ix_review_queue_content_item_id"),
        ("rewrite_profiles", "ix_rewrite_profiles_provider"),
        ("rewrite_profiles", "ix_rewrite_profiles_name"),
        ("filter_rules", "ix_filter_rules_enabled"),
        ("filter_rules", "ix_filter_rules_priority"),
        ("filter_rules", "ix_filter_rules_rule_type"),
        ("source_subscriptions", "uq_source_subscriptions_type_account"),
        ("source_subscriptions", "ix_source_subscriptions_category"),
        ("source_subscriptions", "ix_source_subscriptions_enabled"),
        ("source_subscriptions", "ix_source_subscriptions_source_name"),
        ("source_subscriptions", "ix_source_subscriptions_source_type"),
        ("content_items", "ix_content_items_review_created"),
        ("content_items", "ix_content_items_digest_included"),
        ("content_items", "ix_content_items_language"),
        ("content_items", "ix_content_items_source_account"),
    ]:
        if _has_table(inspector, table_name):
            existing = {index["name"] for index in inspector.get_indexes(table_name)}
            if index_name in existing:
                op.drop_index(index_name, table_name=table_name)

    for table_name in [
        "publish_records",
        "digest_reports",
        "review_queue",
        "rewrite_profiles",
        "filter_rules",
        "source_subscriptions",
    ]:
        if _has_table(inspector, table_name):
            op.drop_table(table_name)

    inspector = inspect(bind)
    if _has_table(inspector, "content_items"):
        existing_columns = {column["name"] for column in inspector.get_columns("content_items")}
        for column_name in [
            "digest_included",
            "reviewed_at",
            "review_status",
            "score",
            "tags_json",
            "rewritten_content",
            "rewritten_title",
            "summary",
            "language",
            "source_account",
        ]:
            if column_name in existing_columns:
                op.drop_column("content_items", column_name)
