"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if not _has_table(inspector, "posts"):
        op.create_table(
            "posts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("published", sa.Boolean(), nullable=True),
            sa.Column("rating", sa.Integer(), nullable=True),
            sa.Column("like_count", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("image_path", sa.String(length=255), nullable=True),
            sa.Column("tech_tag", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_by", sa.String(length=150), nullable=True),
        )
    else:
        if not _has_column(inspector, "posts", "like_count"):
            op.add_column("posts", sa.Column("like_count", sa.Integer(), server_default="0"))
        if not _has_column(inspector, "posts", "deleted_at"):
            op.add_column("posts", sa.Column("deleted_at", sa.DateTime(), nullable=True))
        if not _has_column(inspector, "posts", "deleted_by"):
            op.add_column("posts", sa.Column("deleted_by", sa.String(length=150), nullable=True))
        if not _has_column(inspector, "posts", "tech_tag"):
            op.add_column("posts", sa.Column("tech_tag", sa.String(length=64), nullable=True))

    if not _has_table(inspector, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=150), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("avatar_path", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    else:
        if not _has_column(inspector, "users", "avatar_path"):
            op.add_column("users", sa.Column("avatar_path", sa.String(length=255), nullable=True))

    if not _has_table(inspector, "post_likes"):
        op.create_table(
            "post_likes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    if not _has_table(inspector, "comments"):
        op.create_table(
            "comments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("article_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("comments.id"), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    if not _has_table(inspector, "comment_likes"):
        op.create_table(
            "comment_likes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("comment_id", sa.Integer(), sa.ForeignKey("comments.id"), nullable=False),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    if not _has_table(inspector, "event_logs"):
        op.create_table(
            "event_logs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_name", sa.String(length=80), nullable=False),
            sa.Column("path", sa.String(length=255), nullable=True),
            sa.Column("method", sa.String(length=12), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("username", sa.String(length=150), nullable=True),
            sa.Column("session_id", sa.String(length=64), nullable=False),
            sa.Column("ab_bucket", sa.String(length=8), nullable=True),
            sa.Column("properties", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    inspector = inspect(bind)

    for table_name, index_name, columns, unique in [
        ("posts", "ix_posts_tech_tag", ["tech_tag"], False),
        ("posts", "ix_posts_deleted_at", ["deleted_at"], False),
        ("posts", "ix_posts_deleted_by", ["deleted_by"], False),
        ("users", "ix_users_username", ["username"], True),
        ("users", "ix_users_email", ["email"], True),
        ("post_likes", "uq_post_likes_user_post", ["user_id", "post_id"], True),
        ("comments", "ix_comments_article_created", ["article_id", "created_at"], False),
        ("comments", "ix_comments_article_parent_created", ["article_id", "parent_id", "created_at"], False),
        ("comments", "ix_comments_user_created", ["user_id", "created_at"], False),
        ("comment_likes", "uq_comment_likes_user_comment", ["user_id", "comment_id"], True),
        ("event_logs", "ix_event_logs_created", ["created_at"], False),
        ("event_logs", "ix_event_logs_event_created", ["event_name", "created_at"], False),
        ("event_logs", "ix_event_logs_session_created", ["session_id", "created_at"], False),
    ]:
        if _has_table(inspector, table_name):
            existing = {index["name"] for index in inspector.get_indexes(table_name)}
            if index_name not in existing:
                op.create_index(index_name, table_name, columns, unique=unique)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    for table_name, index_name in [
        ("event_logs", "ix_event_logs_session_created"),
        ("event_logs", "ix_event_logs_event_created"),
        ("event_logs", "ix_event_logs_created"),
        ("comment_likes", "uq_comment_likes_user_comment"),
        ("comments", "ix_comments_user_created"),
        ("comments", "ix_comments_article_parent_created"),
        ("comments", "ix_comments_article_created"),
        ("post_likes", "uq_post_likes_user_post"),
        ("users", "ix_users_email"),
        ("users", "ix_users_username"),
        ("posts", "ix_posts_deleted_by"),
        ("posts", "ix_posts_deleted_at"),
        ("posts", "ix_posts_tech_tag"),
    ]:
        if table_name in inspector.get_table_names():
            existing = {index["name"] for index in inspector.get_indexes(table_name)}
            if index_name in existing:
                op.drop_index(index_name, table_name=table_name)

    for table_name in ["event_logs", "comment_likes", "comments", "post_likes", "users", "posts"]:
        if table_name in inspector.get_table_names():
            op.drop_table(table_name)
