"""PostgreSQL compatibility migration

迁移目的：
  1. 将 SQLite INTEGER(0/1) 列转为原生 BOOLEAN
  2. 将 naive DATETIME 列转为 TIMESTAMPTZ
  3. 补充 module_id/scenario_type/task_type 字段（合并 add_platform_fields.py）
  4. 添加 CHECK 约束

Revision ID: 0002_pg_compat
Revises: 7b6d2d1f4f10
Create Date: 2026-06-06

说明：本迁移在 SQLite 上为兼容操作（ALTER 受限），在 PostgreSQL 上执行实际类型转换。
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.engine import reflection


revision: str = "0002_pg_compat"
down_revision: str = "7b6d2d1f4f10"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    """检测当前是否为 PostgreSQL 连接。"""
    bind = op.get_bind()
    return bind.engine.url.get_backend_name() == "postgresql"


# =========================================================================
# Upgrade
# =========================================================================


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = _is_postgresql()

    # ---- posts: 添加 module_id, scenario_type, task_type (来自 add_platform_fields.py) ----
    posts_cols = {c["name"] for c in inspector.get_columns("posts")}
    if "module_id" not in posts_cols:
        op.add_column("posts", sa.Column("module_id", sa.String(64), nullable=True))
        op.create_index("ix_posts_module_id", "posts", ["module_id"])
    if "scenario_type" not in posts_cols:
        op.add_column("posts", sa.Column("scenario_type", sa.String(64), nullable=True))
    if "task_type" not in posts_cols:
        op.add_column("posts", sa.Column("task_type", sa.String(128), nullable=True))

    if not is_pg:
        # SQLite: 不做类型转换（SQLite 不区分 BOOLEAN/TIMESTAMPTZ），跳过
        return

    # ---- posts: INTEGER → BOOLEAN ----
    op.execute(
        text(
            "ALTER TABLE posts ALTER COLUMN published TYPE BOOLEAN "
            "USING CASE WHEN published = 0 THEN false ELSE true END"
        )
    )
    op.execute(text("ALTER TABLE posts ALTER COLUMN published SET DEFAULT true"))

    # ---- posts: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("posts", "created_at")
    if "rating" in posts_cols:
        op.execute(text("ALTER TABLE posts ADD CONSTRAINT ck_posts_rating CHECK (rating BETWEEN 1 AND 5)"))

    # ---- users: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("users", "created_at")

    # ---- comments: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("comments", "created_at")
    _datetime_to_timestamptz("comments", "updated_at")

    # ---- post_likes: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("post_likes", "created_at")

    # ---- comment_likes: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("comment_likes", "created_at")

    # ---- agent_drafts: DATETIME → TIMESTAMPTZ ----
    for col in ("created_at", "reviewed_at", "updated_at"):
        if col in {c["name"] for c in inspector.get_columns("agent_drafts")}:
            _datetime_to_timestamptz("agent_drafts", col)

    # ---- event_logs: DATETIME → TIMESTAMPTZ ----
    _datetime_to_timestamptz("event_logs", "created_at")


def _datetime_to_timestamptz(table: str, column: str) -> None:
    """在 PostgreSQL 上将 timestamp 列转为 timestamptz。"""
    op.execute(
        text(
            f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE TIMESTAMPTZ '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )
    )


# =========================================================================
# Downgrade
# =========================================================================


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    is_pg = _is_postgresql()

    if not is_pg:
        return

    # 回滚: TIMESTAMPTZ → TIMESTAMP
    for table, cols in [
        ("event_logs", ["created_at"]),
        ("agent_drafts", ["created_at", "reviewed_at", "updated_at"]),
        ("comment_likes", ["created_at"]),
        ("post_likes", ["created_at"]),
        ("comments", ["created_at", "updated_at"]),
        ("users", ["created_at"]),
        ("posts", ["created_at"]),
    ]:
        for col in cols:
            try:
                op.execute(
                    text(
                        f'ALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE TIMESTAMP '
                        f'USING "{col}" AT TIME ZONE \'UTC\''
                    )
                )
            except Exception:
                pass

    # 回滚: BOOLEAN → INTEGER
    op.execute(
        text(
            "ALTER TABLE posts ALTER COLUMN published TYPE INTEGER "
            "USING CASE WHEN published THEN 1 ELSE 0 END"
        )
    )

    # 移除 CHECK 约束
    try:
        op.execute(text("ALTER TABLE posts DROP CONSTRAINT IF EXISTS ck_posts_rating"))
    except Exception:
        pass
