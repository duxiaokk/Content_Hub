from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.digest import DigestGenerateRequest, DigestReportOut
from services.digest_service import DigestNotFoundError, DigestService

router = APIRouter(prefix="/api/internal/content/digests", tags=["digests"])


@router.get("/")
def list_digests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = DigestService(db)
    items, total = service.list_digests(page=page, page_size=page_size)
    return {
        "code": 0,
        "data": {
            "items": [DigestReportOut.model_validate(item).model_dump(mode="json") for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "message": "ok",
    }


@router.get("/{digest_id}")
def get_digest(
    digest_id: int,
    db: Session = Depends(get_db),
):
    service = DigestService(db)
    try:
        item = service.get_digest(digest_id)
    except DigestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": DigestReportOut.model_validate(item).model_dump(mode="json"), "message": "ok"}


@router.post("/generate")
def generate_digest(
    body: DigestGenerateRequest,
    db: Session = Depends(get_db),
):
    service = DigestService(db)
    item = service.generate_digest(run_id=body.run_id, lookback_hours=body.lookback_hours)
    return {"code": 0, "data": DigestReportOut.model_validate(item).model_dump(mode="json"), "message": "ok"}


@router.get("/{digest_id}/download")
def download_digest_markdown(
    digest_id: int,
    db: Session = Depends(get_db),
):
    service = DigestService(db)
    try:
        digest = service.get_digest(digest_id)
    except DigestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=digest.content_markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="digest_{digest_id}.md"'},
    )
