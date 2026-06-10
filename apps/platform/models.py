"""
功能摘要：本文件使用对象关系映射（ORM）定义博客系统的核心数据表结构。

初学者指南：
这个文件相当于数据库的"设计图纸"。里面每一个类都对应数据库中的一张表，
比如 Post 类对应文章表、User 类对应用户表。
当你新增功能需要存储新数据时（比如增加标签系统），
通常要在这里新增一个类，然后再执行数据库迁移命令。

主要成员：
- Post: 文章模型，定义标题、内容、点赞数等字段
- User: 用户模型，定义用户名、邮箱、加密密码等字段
- Comment: 评论模型，支持层级回复与软删除状态
- Base: 所有模型的基类，由 SQLAlchemy（数据库工具库）提供
"""
"""
模块名称：models
作用描述：定义博客系统的核心数据模型（文章、用户、评论），用于 SQLAlchemy ORM 映射数据库表结构，支持文章发布/点赞与评论的增删改查。该模块集中维护字段定义、默认值与索引策略，保证查询性能与数据一致性。
输入参数及类型：无（通过 ORM 在运行时由数据库会话调用）
返回值及类型：无（提供 ORM Model 类供业务层引用）
副作用与依赖：依赖 SQLAlchemy 与项目 database.Base；模型变更会影响数据库结构与迁移策略
作者与最后修改日期：Ado_Jk，2026-04-01
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from database import Base


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255))
    content = Column(Text)
    published = Column(Boolean, default=True)
    rating = Column(Integer, nullable=True)
    like_count = Column(Integer, default=0)
    image_path = Column(String(255), nullable=True)
    tech_tag = Column(String(64), nullable=True, index=True)
    module_id = Column(String(64), nullable=True, index=True)
    scenario_type = Column(String(64), nullable=True)
    task_type = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime, nullable=True, index=True)
    deleted_by = Column(String(150), nullable=True, index=True)


class PostLike(Base):
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (Index("uq_post_likes_user_post", "user_id", "post_id", unique=True),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    avatar_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True, index=True)

    content = Column(Text, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    status = Column(String(32), default="active", nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_comments_article_created", "article_id", "created_at"),
        Index("ix_comments_article_parent_created", "article_id", "parent_id", "created_at"),
        Index("ix_comments_user_created", "user_id", "created_at"),
    )


class CommentLike(Base):
    __tablename__ = "comment_likes"

    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (Index("uq_comment_likes_user_comment", "user_id", "comment_id", unique=True),)


class AgentDraft(Base):
    __tablename__ = "agent_drafts"

    id = Column(Integer, primary_key=True, index=True)
    draft_type = Column(String(64), nullable=False, default="youtube_repost", index=True)
    status = Column(String(32), nullable=False, default="pending_review", index=True)
    title = Column(String(255), nullable=False, index=True)
    summary = Column(Text, nullable=True)
    source_platform = Column(String(64), nullable=False, index=True)
    source_link = Column(String(1024), nullable=False, index=True)
    source_external_id = Column(String(255), nullable=True, index=True)
    source_dedup_key = Column(String(255), nullable=True, unique=True, index=True)
    markdown_path = Column(String(512), nullable=False)
    target_type = Column(String(64), nullable=True, index=True)
    target_id = Column(Integer, nullable=True, index=True)
    created_by = Column(String(64), nullable=False, default="ado_repost", index=True)
    reviewed_by = Column(String(150), nullable=True, index=True)
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_agent_drafts_status_created", "status", "created_at"),
        Index("ix_agent_drafts_source_platform_created", "source_platform", "created_at"),
    )


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True, index=True)
    source_config_id = Column(Integer, ForeignKey("source_configs.id"), nullable=True, index=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    source_id = Column(String(255), nullable=False, index=True)
    source_url = Column(String(1024), nullable=True)
    title = Column(String(255), nullable=False, index=True)
    raw_content = Column(Text, nullable=True)
    processed_content = Column(Text, nullable=True)
    publish_target = Column(String(128), nullable=True, index=True)
    publish_status = Column(String(32), nullable=False, default="pending", index=True)
    pipeline_status = Column(String(32), nullable=False, default="fetched", index=True)
    review_status = Column(String(32), nullable=False, default="pending_review", index=True)
    reviewed_by = Column(String(150), nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)
    draft_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("uq_content_items_source", "source_type", "source_id", unique=True),
        Index("ix_content_items_pipeline_created", "pipeline_status", "created_at"),
        Index("ix_content_items_publish_created", "publish_status", "created_at"),
        Index("ix_content_items_review_created", "review_status", "created_at"),
    )


class SourceConfig(Base):
    __tablename__ = "source_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    channels = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    lookback_hours = Column(Integer, nullable=False, default=24)
    item_limit = Column(Integer, nullable=False, default=20)
    dedup_window_hours = Column(Integer, nullable=False, default=24)
    config_json = Column(Text, nullable=True)
    last_cursor = Column(Text, nullable=True)
    last_run_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_source_configs_type_enabled", "source_type", "enabled"),
    )


class FetchRun(Base):
    __tablename__ = "fetch_runs"

    id = Column(Integer, primary_key=True, index=True)
    source_config_id = Column(Integer, ForeignKey("source_configs.id"), nullable=False, index=True)
    trigger_mode = Column(String(32), nullable=False, default="manual", index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    task_id = Column(String(64), nullable=True, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    requested_by = Column(String(150), nullable=True, index=True)
    request_payload = Column(Text, nullable=True)
    fetched_count = Column(Integer, nullable=False, default=0)
    inserted_count = Column(Integer, nullable=False, default=0)
    deduped_count = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_fetch_runs_source_status_created", "source_config_id", "status", "created_at"),
    )


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id = Column(Integer, primary_key=True, index=True)
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=False, index=True)
    decision = Column(String(32), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    operator = Column(String(150), nullable=False, index=True)
    snapshot_title = Column(String(255), nullable=True)
    snapshot_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("ix_review_decisions_content_created", "content_item_id", "created_at"),
    )


class EventLog(Base):
    __tablename__ = "event_logs"

    id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String(80), nullable=False, index=True)
    path = Column(String(255), nullable=True, index=True)
    method = Column(String(12), nullable=True, index=True)
    status_code = Column(Integer, nullable=True, index=True)
    duration_ms = Column(Integer, nullable=True)

    username = Column(String(150), nullable=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    ab_bucket = Column(String(8), nullable=True, index=True)

    properties = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("ix_event_logs_created", "created_at"),
        Index("ix_event_logs_event_created", "event_name", "created_at"),
        Index("ix_event_logs_session_created", "session_id", "created_at"),
    )
