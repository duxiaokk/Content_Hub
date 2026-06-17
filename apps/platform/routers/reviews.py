from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from apps.platform.database import get_db
from apps.platform.schemas.review import ReviewApproveRequest, ReviewRejectRequest
from apps.platform.services.review_service import ReviewNotFoundError, ReviewService

router = APIRouter(prefix="/api/internal/content/reviews", tags=["reviews"])


@router.get("/")
def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str = Query("pending", alias="status"),
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    items, total = service.get_pending_reviews(page=page, page_size=page_size, status=status_filter)
    return {
        "code": 0,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "message": "ok",
    }


@router.get("/{review_id}")
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    try:
        item = service.get_review_detail(review_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": item, "message": "ok"}


@router.post("/{review_id}/approve")
def approve_review(
    review_id: int,
    body: ReviewApproveRequest,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    try:
        item = service.approve(review_id, body)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": item, "message": "ok"}


@router.post("/{review_id}/reject")
def reject_review(
    review_id: int,
    body: ReviewRejectRequest,
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    try:
        item = service.reject(review_id, body)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": item, "message": "ok"}


@router.post("/{review_id}/archive")
def archive_review(
    review_id: int,
    reviewer: str = Query("admin", min_length=1),
    db: Session = Depends(get_db),
):
    service = ReviewService(db)
    try:
        item = service.archive(review_id, reviewer)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": item, "message": "ok"}
