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

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text

from apps.platform.database import Base


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
    source_account = Column(String(255), nullable=True, index=True)
    source_url = Column(String(1024), nullable=True)
    title = Column(String(255), nullable=False, index=True)
    language = Column(String(16), nullable=False, default="zh", index=True)
    raw_content = Column(Text, nullable=True)
    processed_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    rewritten_title = Column(String(512), nullable=True)
    rewritten_content = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    score = Column(Float, nullable=False, default=0)
    publish_target = Column(String(128), nullable=True, index=True)
    publish_status = Column(String(32), nullable=False, default="pending", index=True)
    pipeline_status = Column(String(32), nullable=False, default="fetched", index=True)
    review_status = Column(String(32), nullable=False, default="pending", index=True)
    reviewed_by = Column(String(150), nullable=True, index=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)
    digest_included = Column(Boolean, nullable=False, default=False, index=True)
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


class SourceSubscription(Base):
    __tablename__ = "source_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    source_name = Column(String(128), nullable=False, index=True)
    account_identifier = Column(String(255), nullable=True)
    feed_url = Column(String(1024), nullable=True)
    schedule_expression = Column(String(64), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    category = Column(String(64), nullable=True, index=True)
    default_tags = Column(String(512), nullable=True)
    last_cursor = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("uq_source_subscriptions_type_account", "source_type", "account_identifier", unique=True),
    )


class FilterRule(Base):
    __tablename__ = "filter_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String(32), nullable=False, index=True)
    rule_value = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False, default=0, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )


class RewriteProfile(Base):
    __tablename__ = "rewrite_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False, unique=True, index=True)
    provider = Column(String(32), nullable=True, index=True)
    model = Column(String(64), nullable=True)
    timeout_seconds = Column(Integer, nullable=False, default=60)
    fallback_strategy = Column(String(16), nullable=False, default="skip")
    system_prompt = Column(Text, nullable=True)
    max_tokens = Column(Integer, nullable=False, default=2048)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )


class ReviewQueue(Base):
    __tablename__ = "review_queue"

    id = Column(Integer, primary_key=True, index=True)
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=False, index=True)
    candidate_title = Column(String(512), nullable=True)
    candidate_content = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    reviewer = Column(String(64), nullable=True, index=True)
    review_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_review_queue_status_created", "status", "created_at"),
    )


class DigestReport(Base):
    __tablename__ = "digest_reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    content_markdown = Column(Text, nullable=False)
    included_count = Column(Integer, nullable=False, default=0)
    generated_at = Column(DateTime, nullable=True, index=True)
    run_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id = Column(Integer, primary_key=True, index=True)
    content_item_id = Column(Integer, ForeignKey("content_items.id"), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, index=True)
    target_name = Column(String(128), nullable=True, index=True)
    status = Column(String(32), nullable=False, index=True)
    external_url = Column(String(1024), nullable=True)
    external_id = Column(String(255), nullable=True, index=True)
    response_payload = Column(Text, nullable=True)
    run_id = Column(String(64), nullable=True, index=True)
    published_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_publish_records_target_status_created", "target_type", "status", "created_at"),
        Index("uq_publish_records_run_content_target", "run_id", "content_item_id", "target_type", unique=True),
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_run"

    id = Column(Integer, primary_key=True, index=True)
    workflow_name = Column(String(64), nullable=False, index=True, comment="Workflow name.")
    trigger_type = Column(String(32), nullable=False, default="manual", index=True, comment="Run trigger type.")
    status = Column(String(32), nullable=False, default="running", index=True, comment="Run status.")
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    items_total = Column(Integer, nullable=False, default=0, comment="Total input items.")
    items_succeeded = Column(Integer, nullable=False, default=0, comment="Successfully processed items.")
    items_failed = Column(Integer, nullable=False, default=0, comment="Failed items.")
    error_summary = Column(Text, nullable=True, comment="Run error summary.")
    trace_payload = Column(JSON, nullable=True, comment="Structured workflow trace payload.")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )

    __table_args__ = (
        Index("ix_workflow_run_name_status_created", "workflow_name", "status", "created_at"),
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
