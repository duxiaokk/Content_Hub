from __future__ import annotations

from workflow_engine.runtime.legacy_paths import ensure_legacy_paths
from workflow_engine.registry.contracts import ContentAsset, PublishResult, SourceItem

ensure_legacy_paths()

from crud.crud_content_item import create_content_item, get_content_item_by_source, update_content_item
from database import SessionLocal


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
