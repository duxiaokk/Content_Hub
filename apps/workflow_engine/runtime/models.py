from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text

from workflow_engine.runtime.db import Base


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
    draft_post_id = Column(Integer, nullable=True, index=True)
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
