from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.workflow_engine.registry.contracts import ContentAsset, PublishResult, SourceItem
from apps.workflow_engine.runtime.crud import (
    create_content_item,
    get_content_item_by_source,
    list_content_items,
    update_content_item,
)
from apps.workflow_engine.runtime.db import SessionLocal


@dataclass(slots=True)
class ContentQuery:
    review_status: str | None = None
    publish_status: str | None = None
    pipeline_status: str | None = None
    source_type: str | None = None
    fetch_run_id: int | None = None
    limit: int = 100


class ContentRepository:
    def upsert_fetched_item(self, item: SourceItem) -> int:
        db = SessionLocal()
        try:
            existing = get_content_item_by_source(db, item.source_type, item.source_id)
            if existing is None:
                created = create_content_item(
                    db,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    source_url=item.source_url,
                    title=item.title,
                    raw_content=item.raw_content,
                    processed_content=None,
                    publish_target=None,
                    publish_status="pending",
                    pipeline_status="fetched",
                    error_message=None,
                )
                return int(created.id)
            updated = update_content_item(
                db,
                existing,
                source_url=item.source_url,
                title=item.title,
                raw_content=item.raw_content,
                pipeline_status="fetched",
                error_message=None,
            )
            return int(updated.id)
        finally:
            db.close()

    def attach_fetch_context(
        self,
        *,
        source_type: str,
        source_id: str,
        source_config_id: int | None,
        fetch_run_id: int | None,
    ) -> None:
        db = SessionLocal()
        try:
            existing = get_content_item_by_source(db, source_type, source_id)
            if existing is None:
                return
            update_content_item(
                db,
                existing,
                source_config_id=source_config_id,
                fetch_run_id=fetch_run_id,
            )
        finally:
            db.close()

    def mark_processed(self, asset: ContentAsset, status: str, error_message: str | None = None) -> None:
        db = SessionLocal()
        try:
            existing = get_content_item_by_source(db, asset.source_type, asset.source_id)
            if existing is None:
                return
            update_content_item(
                db,
                existing,
                processed_content=asset.processed_content,
                pipeline_status=status,
                error_message=error_message,
            )
        finally:
            db.close()

    def mark_published(
        self,
        asset: ContentAsset,
        target_name: str,
        result: PublishResult,
    ) -> None:
        db = SessionLocal()
        try:
            existing = get_content_item_by_source(db, asset.source_type, asset.source_id)
            if existing is None:
                return
            update_content_item(
                db,
                existing,
                publish_target=target_name,
                publish_status=result.status,
                pipeline_status="published" if result.status == "published" else "publish_failed",
                error_message=result.error_message,
            )
        finally:
            db.close()

    def get_by_source(self, source_type: str, source_id: str) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            row = get_content_item_by_source(db, source_type, source_id)
            if row is None:
                return None
            return self.serialize(row)
        finally:
            db.close()

    def list_items(self, query: ContentQuery | None = None) -> list[dict[str, Any]]:
        criteria = query or ContentQuery()
        db = SessionLocal()
        try:
            rows = list_content_items(
                db,
                review_status=criteria.review_status,
                publish_status=criteria.publish_status,
                pipeline_status=criteria.pipeline_status,
                source_type=criteria.source_type,
                fetch_run_id=criteria.fetch_run_id,
                limit=criteria.limit,
            )
            return [self.serialize(row) for row in rows]
        finally:
            db.close()

    @staticmethod
    def serialize(row: Any) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "source_config_id": row.source_config_id,
            "fetch_run_id": row.fetch_run_id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "source_url": row.source_url,
            "title": row.title,
            "raw_content": row.raw_content,
            "processed_content": row.processed_content,
            "publish_target": row.publish_target,
            "publish_status": row.publish_status,
            "pipeline_status": row.pipeline_status,
            "review_status": row.review_status,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "draft_post_id": row.draft_post_id,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
