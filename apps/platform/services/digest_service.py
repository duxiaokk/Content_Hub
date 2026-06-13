from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid

from sqlalchemy.orm import Session

from apps.publisher_engine.api.service import PublishingService
from models import ContentItem, DigestReport, PublishRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DigestNotFoundError(ValueError):
    pass


class DigestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._publishing_service = PublishingService()

    def list_digests(self, page: int = 1, page_size: int = 20) -> tuple[list[DigestReport], int]:
        query = self.db.query(DigestReport).order_by(DigestReport.generated_at.desc(), DigestReport.id.desc())
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return items, total

    def get_digest(self, digest_id: int) -> DigestReport:
        digest = self.db.query(DigestReport).filter(DigestReport.id == digest_id).first()
        if digest is None:
            raise DigestNotFoundError(f"digest not found: {digest_id}")
        return digest

    def generate_digest(self, run_id: str | None, lookback_hours: int = 24) -> DigestReport:
        now = _utcnow()
        lookback_start = now - timedelta(hours=lookback_hours)
        items = (
            self.db.query(ContentItem)
            .filter(
                ContentItem.review_status == "approved",
                ContentItem.created_at >= lookback_start,
            )
            .order_by(ContentItem.reviewed_at.desc(), ContentItem.id.asc())
            .all()
        )
        resolved_run_id = run_id or str(uuid.uuid4())
        record_content_item_id = int(items[0].id) if items else None
        payload_items = [
            {
                "title": item.rewritten_title or item.title,
                "url": item.source_url,
                "source_type": item.source_type,
                "source_account": item.source_account,
                "category": "",
                "tags": json.loads(item.tags_json or "[]"),
                "summary": item.summary or item.rewritten_content or item.raw_content or "",
            }
            for item in items
        ]

        try:
            publish_result = __import__("asyncio").run(
                self._publishing_service.generate_digest(payload_items, resolved_run_id)
            )
            digest = DigestReport(
                title=str(publish_result["title"]),
                content_markdown=str(publish_result["content_markdown"]),
                included_count=int(publish_result["included_count"]),
                generated_at=now,
                run_id=resolved_run_id,
            )
            self.db.add(digest)

            for item in items:
                item.digest_included = True
                self.db.add(item)

            if record_content_item_id is not None:
                self.db.add(
                    PublishRecord(
                        content_item_id=record_content_item_id,
                        target_type="digest_markdown",
                        target_name="daily_digest",
                        status="success",
                        run_id=resolved_run_id,
                        response_payload=json.dumps({"file_path": publish_result["file_path"]}, ensure_ascii=False),
                    )
                )
            self.db.commit()
            self.db.refresh(digest)
            return digest
        except Exception as exc:
            self.db.rollback()
            if record_content_item_id is not None:
                self.db.add(
                    PublishRecord(
                        content_item_id=record_content_item_id,
                        target_type="digest_markdown",
                        target_name="daily_digest",
                        status="failed",
                        run_id=resolved_run_id,
                        response_payload=json.dumps({"error": str(exc)}, ensure_ascii=False),
                    )
                )
                self.db.commit()
            raise
