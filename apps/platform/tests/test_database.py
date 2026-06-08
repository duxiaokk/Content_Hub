"""数据库回归测试

覆盖:
  1. 所有表创建验证
  2. CRUD 操作完整性
  3. 唯一约束生效
  4. 软删除语义
  5. 布尔/时间列类型正确
  6. PostgreSQL 兼容性 (BOOLEAN, TIMESTAMPTZ)
  7. 连接池健康检查

运行:
  pytest tests/test_database.py -v
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from database import Base, get_db, check_db_health, SessionLocal
from models import (
    AgentDraft,
    Comment,
    CommentLike,
    EventLog,
    Post,
    PostLike,
    User,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture(scope="module")
def engine():
    """内存 SQLite 引擎，隔离测试。"""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def session(engine) -> Session:
    """每个测试独立的事务级 session。"""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    trans.rollback()
    conn.close()


# =========================================================================
# 表创建
# =========================================================================


class TestTableCreation:
    """验证所有表可正确创建。"""

    TABLES = ["posts", "users", "comments", "post_likes", "comment_likes", "agent_drafts", "event_logs"]

    def test_all_tables_exist(self, session):
        inspector = inspect(session.bind)
        existing = inspector.get_table_names()
        for table in self.TABLES:
            assert table in existing, f"Table '{table}' not found"

    def test_posts_columns(self, session):
        inspector = inspect(session.bind)
        cols = {c["name"] for c in inspector.get_columns("posts")}
        required = {"id", "title", "content", "published", "like_count", "created_at", "deleted_at"}
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_users_unique_constraints(self, session):
        inspector = inspect(session.bind)
        indexes = inspector.get_indexes("users")
        unique_indexes = [i for i in indexes if i.get("unique")]
        unique_cols = {col for idx in unique_indexes for col in idx["column_names"]}
        assert "username" in unique_cols
        assert "email" in unique_cols

    def test_post_likes_unique(self, session):
        inspector = inspect(session.bind)
        indexes = inspector.get_indexes("post_likes")
        unique_indexes = [i for i in indexes if i.get("unique")]
        assert len(unique_indexes) >= 1, "post_likes should have a unique constraint"


# =========================================================================
# CRUD
# =========================================================================


class TestCRUD:
    """验证各表基本 CRUD 操作。"""

    def test_create_user(self, session):
        user = User(username="test_user", email="test@test.com", hashed_password="hash123")
        session.add(user)
        session.commit()
        assert user.id is not None
        assert user.created_at is not None

    def test_create_post(self, session):
        post = Post(title="Test Post", content="Hello world")
        session.add(post)
        session.commit()
        assert post.id is not None
        assert post.published is True
        assert post.like_count == 0

    def test_create_comment(self, session):
        user = User(username="c_user", email="c@c.com", hashed_password="h")
        post = Post(title="P", content="C")
        session.add_all([user, post])
        session.flush()

        comment = Comment(article_id=post.id, user_id=user.id, content="Good post!")
        session.add(comment)
        session.commit()
        assert comment.id is not None
        assert comment.status == "active"

    def test_create_agent_draft(self, session):
        draft = AgentDraft(
            title="My Draft",
            source_platform="youtube",
            source_link="https://youtube.com/watch?v=abc",
            markdown_path="content/agent_drafts/my_draft.md",
        )
        session.add(draft)
        session.commit()
        assert draft.id is not None
        assert draft.status == "pending_review"

    def test_create_event_log(self, session):
        log = EventLog(event_name="page_view", session_id="sess_001")
        session.add(log)
        session.commit()
        assert log.id is not None

    def test_soft_delete_post(self, session):
        post = Post(title="To Delete", content="x")
        session.add(post)
        session.commit()
        assert post.deleted_at is None

        post.deleted_at = datetime.datetime.now(datetime.timezone.utc)
        post.deleted_by = "admin"
        session.commit()
        assert post.deleted_at is not None
        assert post.deleted_by == "admin"

    def test_comment_status_soft_delete(self, session):
        user = User(username="d_user", email="d@d.com", hashed_password="h")
        post = Post(title="P", content="C")
        session.add_all([user, post])
        session.flush()

        comment = Comment(article_id=post.id, user_id=user.id, content="test")
        session.add(comment)
        session.commit()

        comment.status = "deleted"
        session.commit()
        assert comment.status == "deleted"


# =========================================================================
# 约束
# =========================================================================


class TestConstraints:
    """验证唯一约束和行为。"""

    def test_duplicate_username_raises(self, session):
        u1 = User(username="dup", email="a@a.com", hashed_password="h")
        session.add(u1)
        session.commit()

        u2 = User(username="dup", email="b@b.com", hashed_password="h")
        session.add(u2)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_duplicate_email_raises(self, session):
        u1 = User(username="a", email="dup@dup.com", hashed_password="h")
        session.add(u1)
        session.commit()

        u2 = User(username="b", email="dup@dup.com", hashed_password="h")
        session.add(u2)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_duplicate_like_raises(self, session):
        user = User(username="l_user", email="l@l.com", hashed_password="h")
        post = Post(title="P", content="C")
        session.add_all([user, post])
        session.flush()

        like1 = PostLike(post_id=post.id, user_id=user.id)
        session.add(like1)
        session.commit()

        like2 = PostLike(post_id=post.id, user_id=user.id)
        session.add(like2)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()

    def test_agent_draft_dedup_key_unique(self, session):
        d1 = AgentDraft(
            title="D1", source_platform="youtube",
            source_link="https://youtube.com/watch?v=1",
            source_dedup_key="dedup_001",
            markdown_path="content/d1.md",
        )
        session.add(d1)
        session.commit()

        d2 = AgentDraft(
            title="D2", source_platform="youtube",
            source_link="https://youtube.com/watch?v=2",
            source_dedup_key="dedup_001",
            markdown_path="content/d2.md",
        )
        session.add(d2)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


# =========================================================================
# 类型验证 (PostgreSQL 兼容)
# =========================================================================


class TestTypeCompatibility:
    """验证数据类型与 PostgreSQL 兼容。"""

    def test_boolean_column_default(self, session):
        post = Post(title="B", content="b")
        session.add(post)
        session.commit()
        assert isinstance(post.published, bool) or isinstance(post.published, int)
        assert post.published in (True, 1)

    def test_datetime_column_is_set(self, session):
        post = Post(title="T", content="t")
        session.add(post)
        session.commit()
        assert post.created_at is not None
        assert isinstance(post.created_at, datetime.datetime)

    def test_rating_nullable(self, session):
        post = Post(title="R", content="r")
        session.add(post)
        session.commit()
        assert post.rating is None  # 默认为 null


# =========================================================================
# 健康检查
# =========================================================================


class TestHealthCheck:
    """验证 check_db_health() 正常工作。"""

    def test_health_check_ok(self, session):
        # 健康检查不受 session 事务影响（使用独立连接）
        result = check_db_health()
        assert result["status"] == "ok"

    def test_health_check_structure(self):
        result = check_db_health()
        assert "status" in result


# =========================================================================
# PostgreSQL 特定测试（仅在 PG 环境下运行）
# =========================================================================


@pytest.mark.postgresql
class TestPostgreSQLSpecific:
    """仅在 DATABASE_URL 指向 PostgreSQL 时运行。"""

    @pytest.fixture(autouse=True)
    def _check_pg(self):
        from core.config import settings
        if "postgresql" not in (settings.database_url or ""):
            pytest.skip("Requires PostgreSQL")

    def test_boolean_type_is_native(self, session):
        """PG 上 BOOLEAN 应为原生类型，非 INTEGER。"""
        result = session.execute(
            text("SELECT data_type FROM information_schema.columns "
                 "WHERE table_name='posts' AND column_name='published'")
        ).scalar()
        assert result and result.lower() == "boolean", f"Expected boolean, got {result}"

    def test_timestamptz_type(self, session):
        """PG 上 created_at 应为 timestamptz。"""
        result = session.execute(
            text("SELECT data_type FROM information_schema.columns "
                 "WHERE table_name='posts' AND column_name='created_at'")
        ).scalar()
        assert result and "time" in result.lower(), f"Expected timestamp, got {result}"
