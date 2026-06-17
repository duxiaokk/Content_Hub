from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

import models
from core.api_schemas import ApiResponse, paginated, success
from core.permissions import RequireUser
from database import get_db
from schemas.console import (
    PublishToPostRequest,
    ReviewActionRequest,
    SourceConfigCreateRequest,
    SourceConfigUpdateRequest,
    TriggerFetchRequest,
    TriggerProcessFetchRunRequest,
)
from services.console_service import (
    approve_content_item,
    create_source,
    get_content_item_or_404,
    get_source_or_404,
    list_content_items,
    list_fetch_runs,
    list_sources,
    publish_content_to_post,
    reject_content_item,
    trigger_fetch,
    trigger_process_fetch_run,
    update_source,
)

router = APIRouter(prefix="/console", tags=["Console API v1"])


@router.get("/sources", response_model=ApiResponse)
async def console_list_sources(
    _user: RequireUser,
    db: Session = Depends(get_db),
):
    return success(list_sources(db))


@router.post("/sources", response_model=ApiResponse)
async def console_create_source(
    body: SourceConfigCreateRequest,
    _user: RequireUser,
    db: Session = Depends(get_db),
):
    return success(create_source(db, body), "创建成功")


@router.put("/sources/{source_id}", response_model=ApiResponse)
async def console_update_source(
    source_id: int,
    body: SourceConfigUpdateRequest,
    _user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_source_or_404(db, source_id)
    return success(update_source(db, row, body), "更新成功")


@router.post("/sources/{source_id}/run", response_model=ApiResponse)
async def console_trigger_source(
    source_id: int,
    body: TriggerFetchRequest,
    user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_source_or_404(db, source_id)
    return success(trigger_fetch(db, row, body, user), "触发成功")


@router.get("/fetch-runs", response_model=ApiResponse)
async def console_list_fetch_runs(
    _user: RequireUser,
    source_config_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    items = list_fetch_runs(db, source_config_id=source_config_id, status_value=status)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return paginated(items[start:end], total, page, page_size)


@router.post("/fetch-runs/{fetch_run_id}/process", response_model=ApiResponse)
async def console_process_fetch_run(
    fetch_run_id: int,
    body: TriggerProcessFetchRunRequest,
    user: RequireUser,
    db: Session = Depends(get_db),
):
    fetch_run = db.query(models.FetchRun).filter(models.FetchRun.id == fetch_run_id).first()
    if fetch_run is None:
        raise HTTPException(status_code=404, detail="fetch run not found")
    return success(trigger_process_fetch_run(db, fetch_run, body, user), "处理任务已提交")


@router.get("/content-items", response_model=ApiResponse)
async def console_list_content_items(
    _user: RequireUser,
    review_status: str | None = Query(default=None),
    publish_status: str | None = Query(default=None),
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
):
    items = list_content_items(db, review_status=review_status, publish_status=publish_status)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return paginated(items[start:end], total, page, page_size)


@router.get("/content-items/{content_item_id}", response_model=ApiResponse)
async def console_get_content_item(
    content_item_id: int,
    _user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_content_item_or_404(db, content_item_id)
    return success({
        "id": row.id,
        "source_config_id": row.source_config_id,
        "fetch_run_id": row.fetch_run_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "source_url": row.source_url,
        "title": row.title,
        "raw_content": row.raw_content,
        "processed_content": row.processed_content,
        "pipeline_status": row.pipeline_status,
        "review_status": row.review_status,
        "publish_status": row.publish_status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "draft_post_id": row.draft_post_id,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    })


@router.post("/content-items/{content_item_id}/approve", response_model=ApiResponse)
async def console_approve_content(
    content_item_id: int,
    body: ReviewActionRequest,
    user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_content_item_or_404(db, content_item_id)
    return success(approve_content_item(db, row, user, body.reason), "审核通过")


@router.post("/content-items/{content_item_id}/reject", response_model=ApiResponse)
async def console_reject_content(
    content_item_id: int,
    body: ReviewActionRequest,
    user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_content_item_or_404(db, content_item_id)
    return success(reject_content_item(db, row, user, body.reason), "已驳回")


@router.post("/content-items/{content_item_id}/publish-to-post", response_model=ApiResponse)
async def console_publish_content(
    content_item_id: int,
    body: PublishToPostRequest,
    user: RequireUser,
    db: Session = Depends(get_db),
):
    row = get_content_item_or_404(db, content_item_id)
    return success(publish_content_to_post(db, row, user, body), "发布成功")
