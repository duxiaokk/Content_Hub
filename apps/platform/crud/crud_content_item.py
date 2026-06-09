from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

import models


def get_content_item_by_source(
    db: Session,
    source_type: str,
    source_id: str,
) -> models.ContentItem | None:
    return (
        db.query(models.ContentItem)
        .filter(models.ContentItem.source_type == source_type)
        .filter(models.ContentItem.source_id == source_id)
        .first()
    )


def create_content_item(db: Session, **kwargs: Any) -> models.ContentItem:
    item = models.ContentItem(**kwargs)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_content_item(
    db: Session,
    item: models.ContentItem,
    **kwargs: Any,
) -> models.ContentItem:
    for key, value in kwargs.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
