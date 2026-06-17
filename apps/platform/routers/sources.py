from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from database import get_db
from schemas.source import SourceSubscriptionCreate, SourceSubscriptionOut, SourceSubscriptionUpdate
from services.source_service import SourceConflictError, SourceNotFoundError, SourceService

router = APIRouter(prefix="/api/internal/content/sources", tags=["sources"])


@router.get("/")
def list_sources(
    enabled_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    service = SourceService(db)
    items = [SourceSubscriptionOut.model_validate(item).model_dump(mode="json") for item in service.list_sources(enabled_only)]
    return {"code": 0, "data": items, "message": "ok"}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_source(
    body: SourceSubscriptionCreate,
    db: Session = Depends(get_db),
):
    service = SourceService(db)
    try:
        item = service.create_source(body)
    except SourceConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"code": 0, "data": SourceSubscriptionOut.model_validate(item).model_dump(mode="json"), "message": "ok"}


@router.patch("/{source_id}")
def update_source(
    source_id: int,
    body: SourceSubscriptionUpdate,
    db: Session = Depends(get_db),
):
    service = SourceService(db)
    try:
        item = service.update_source(source_id, body)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"code": 0, "data": SourceSubscriptionOut.model_validate(item).model_dump(mode="json"), "message": "ok"}


@router.post("/{source_id}/enable")
def enable_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    service = SourceService(db)
    try:
        item = service.enable_source(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": SourceSubscriptionOut.model_validate(item).model_dump(mode="json"), "message": "ok"}


@router.post("/{source_id}/disable")
def disable_source(
    source_id: int,
    db: Session = Depends(get_db),
):
    service = SourceService(db)
    try:
        item = service.disable_source(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"code": 0, "data": SourceSubscriptionOut.model_validate(item).model_dump(mode="json"), "message": "ok"}
