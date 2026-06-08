from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.models.review_queue import ReviewQueue
from app.schemas.review import ReviewActionRequest, ReviewQueueRead
from app.services.review_service import approve_review, reject_review

router = APIRouter()


@router.get("", response_model=list[ReviewQueueRead])
def list_reviews(
    review_status: str | None = None,
    db: Session = Depends(get_db_session),
) -> list[ReviewQueue]:
    query = db.query(ReviewQueue).order_by(ReviewQueue.id.desc())
    if review_status is not None:
        query = query.filter(ReviewQueue.review_status == review_status)
    return query.limit(100).all()


@router.post("/{review_id}/approve", response_model=ReviewQueueRead)
def approve_review_item(
    review_id: int,
    payload: ReviewActionRequest,
    db: Session = Depends(get_db_session),
) -> ReviewQueue:
    return approve_review(db, review_id, payload)


@router.post("/{review_id}/reject", response_model=ReviewQueueRead)
def reject_review_item(
    review_id: int,
    payload: ReviewActionRequest,
    db: Session = Depends(get_db_session),
) -> ReviewQueue:
    return reject_review(db, review_id, payload)
