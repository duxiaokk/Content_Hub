from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from models import ContentItem, ReviewQueue
from schemas.review import ReviewApproveRequest, ReviewQueueOut, ReviewRejectRequest


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewNotFoundError(ValueError):
    pass


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_pending_reviews(self, page: int, page_size: int, status: str = "pending") -> tuple[list[dict], int]:
        try:
            query = (
                self.db.query(ReviewQueue, ContentItem)
                .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
                .filter(ReviewQueue.status == status)
                .order_by(ReviewQueue.created_at.asc(), ReviewQueue.id.asc())
            )
            total = query.count()
            rows = query.offset((page - 1) * page_size).limit(page_size).all()
        except OperationalError:
            return [], 0
        return [self._serialize_review(review, item) for review, item in rows], total

    def get_review_detail(self, review_id: int) -> dict:
        row = (
            self.db.query(ReviewQueue, ContentItem)
            .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
            .filter(ReviewQueue.id == review_id)
            .first()
        )
        if row is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        review, item = row
        return self._serialize_review(review, item)

    def approve(self, review_id: int, data: ReviewApproveRequest) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        if data.edited_title is not None:
            review.candidate_title = data.edited_title
            item.rewritten_title = data.edited_title
        if data.edited_content is not None:
            review.candidate_content = data.edited_content
            item.rewritten_content = data.edited_content

        review.status = "approved"
        review.reviewer = data.reviewer
        review.reviewed_at = now

        item.review_status = "approved"
        item.reviewed_by = data.reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def reject(self, review_id: int, data: ReviewRejectRequest) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        review.status = "rejected"
        review.reviewer = data.reviewer
        review.review_note = data.note
        review.reviewed_at = now

        item.review_status = "rejected"
        item.reviewed_by = data.reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def archive(self, review_id: int, reviewer: str) -> dict:
        review, item = self._load_review_with_item(review_id)
        now = _utcnow()

        review.status = "archived"
        review.reviewer = reviewer
        review.reviewed_at = now

        item.review_status = "archived"
        item.reviewed_by = reviewer
        item.reviewed_at = now

        self.db.add(review)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(review)
        self.db.refresh(item)
        return self._serialize_review(review, item)

    def _load_review_with_item(self, review_id: int) -> tuple[ReviewQueue, ContentItem]:
        row = (
            self.db.query(ReviewQueue, ContentItem)
            .join(ContentItem, ContentItem.id == ReviewQueue.content_item_id)
            .filter(ReviewQueue.id == review_id)
            .first()
        )
        if row is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        return row

    def _serialize_review(self, review: ReviewQueue, item: ContentItem) -> dict:
        tags: list[str] | None
        try:
            tags = json.loads(item.tags_json or "[]")
        except json.JSONDecodeError:
            tags = []
        payload = ReviewQueueOut(
            id=int(review.id),
            content_item_id=int(review.content_item_id),
            candidate_title=review.candidate_title,
            candidate_content=review.candidate_content,
            status=review.status,
            reviewer=review.reviewer,
            review_note=review.review_note,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            original_title=item.title,
            original_content=item.raw_content,
            summary=item.summary,
            score=float(item.score) if item.score is not None else None,
            tags=tags,
            source_url=item.source_url,
        )
        return payload.model_dump(mode="json")
