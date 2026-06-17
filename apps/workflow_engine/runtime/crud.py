from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from apps.workflow_engine.runtime.models import ContentItem


def get_content_item_by_source(db: Session, source_type: str, source_id: str) -> ContentItem | None:
    return (
        db.query(ContentItem)
        .filter(ContentItem.source_type == source_type)
        .filter(ContentItem.source_id == source_id)
        .first()
    )


def list_content_items(
    db: Session,
    *,
    review_status: str | None = None,
    publish_status: str | None = None,
    pipeline_status: str | None = None,
    source_type: str | None = None,
    fetch_run_id: int | None = None,
    limit: int = 100,
) -> list[ContentItem]:
    query = db.query(ContentItem)
    if review_status:
        query = query.filter(ContentItem.review_status == review_status)
    if publish_status:
        query = query.filter(ContentItem.publish_status == publish_status)
    if pipeline_status:
        query = query.filter(ContentItem.pipeline_status == pipeline_status)
    if source_type:
        query = query.filter(ContentItem.source_type == source_type)
    if fetch_run_id is not None:
        query = query.filter(ContentItem.fetch_run_id == fetch_run_id)
    return query.order_by(ContentItem.created_at.desc()).limit(limit).all()


def create_content_item(db: Session, **kwargs: Any) -> ContentItem:
    item = ContentItem(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_content_item(db: Session, item: ContentItem, **kwargs: Any) -> ContentItem:
    for key, value in kwargs.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
