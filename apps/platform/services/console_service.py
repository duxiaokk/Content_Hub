from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from apps.platform import models
from apps.platform.core.error_codes import ErrorCode
from apps.platform.crud.crud_content_item import get_content_item_by_source, update_content_item
from apps.platform.crud.crud_post import create_post as crud_create_post
from apps.platform.scheduler_client import get_scheduler_client
from apps.platform.schemas.console import (
    PublishToPostRequest,
    SourceConfigCreateRequest,
    SourceConfigUpdateRequest,
    TriggerFetchRequest,
    TriggerProcessFetchRunRequest,
    TriggerProcessFetchRunResponse,
)
from apps.workflow_engine.registry.contracts import SourceItem
from apps.workflow_engine.runtime.content_repository import ContentRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _from_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def ensure_platform_tables(db: Session) -> None:
    """表结构已在应用启动时通过 lifespan 创建，此处不再重复调用 create_all 以避免并发 I/O 竞争。"""
    pass


def list_sources(db: Session) -> list[dict[str, Any]]:
    try:
        rows = db.query(models.SourceConfig).order_by(models.SourceConfig.updated_at.desc()).all()
    except OperationalError:
        return []
    return [serialize_source(row) for row in rows]


def get_source_or_404(db: Session, source_id: int) -> models.SourceConfig:
    row = db.query(models.SourceConfig).filter(models.SourceConfig.id == source_id).first()
    if not row:
        raise HTTPException(status_code=404, detail={"code": ErrorCode.NOT_FOUND, "message": "数据源不存在"})
    return row


def create_source(db: Session, body: SourceConfigCreateRequest) -> dict[str, Any]:
    existing = db.query(models.SourceConfig).filter(models.SourceConfig.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail={"code": ErrorCode.CONFLICT, "message": "数据源名称已存在"})

    row = models.SourceConfig(
        name=body.name.strip(),
        source_type=body.source_type.strip(),
        enabled=bool(body.enabled),
        channels=_to_json(body.channels),
        keywords=_to_json(body.keywords),
        lookback_hours=int(body.lookback_hours),
        item_limit=int(body.item_limit),
        dedup_window_hours=int(body.dedup_window_hours),
        config_json=_to_json(body.config),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_source(row)


def update_source(db: Session, row: models.SourceConfig, body: SourceConfigUpdateRequest) -> dict[str, Any]:
    if body.name is not None:
        row.name = body.name.strip()
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.channels is not None:
        row.channels = _to_json(body.channels)
    if body.keywords is not None:
        row.keywords = _to_json(body.keywords)
    if body.lookback_hours is not None:
        row.lookback_hours = int(body.lookback_hours)
    if body.item_limit is not None:
        row.item_limit = int(body.item_limit)
    if body.dedup_window_hours is not None:
        row.dedup_window_hours = int(body.dedup_window_hours)
    if body.config is not None:
        row.config_json = _to_json(body.config)
    db.commit()
    db.refresh(row)
    return serialize_source(row)


def trigger_fetch(
    db: Session,
    row: models.SourceConfig,
    body: TriggerFetchRequest,
    requested_by: str,
) -> dict[str, Any]:
    payload = {
        "source_config_id": row.id,
        "source_type": row.source_type,
        "source_name": row.name,
        "channels": _from_json(row.channels, []),
        "keywords": _from_json(row.keywords, []),
        "lookback_hours": int(body.lookback_hours or row.lookback_hours),
        "limit": int(body.item_limit or row.item_limit),
        "dedup_window_hours": int(row.dedup_window_hours),
        "dry_run": bool(body.dry_run),
        "config": _from_json(row.config_json, {}),
    }
    idempotency_key = f"console-fetch:{row.id}:{int(_utcnow().timestamp())}"
    submit = get_scheduler_client().submit_task(
        task_type="content.fetch.batch",
        payload=payload,
        idempotency_key=idempotency_key,
    )

    now = _utcnow()
    fetch_run = models.FetchRun(
        source_config_id=row.id,
        trigger_mode="manual",
        status=str(submit.get("status") or "pending"),
        task_id=submit.get("id"),
        trace_id=submit.get("trace_id"),
        requested_by=requested_by,
        request_payload=_to_json(payload),
        started_at=now,
    )
    row.last_run_at = now
    db.add(fetch_run)
    db.commit()
    db.refresh(fetch_run)
    return {
        "fetch_run_id": fetch_run.id,
        "task_id": fetch_run.task_id,
        "trace_id": fetch_run.trace_id,
        "status": fetch_run.status,
    }


def trigger_process_fetch_run(
    db: Session,
    fetch_run: models.FetchRun,
    body: TriggerProcessFetchRunRequest,
    requested_by: str,
) -> dict[str, Any]:
    payload = {
        "workflow_name": "radar_pipeline",
        "fetch_run_id": int(fetch_run.id),
        "limit": int(body.limit),
        "source_type": body.source_type,
        "filter_config": dict(body.filter_config),
        "process_options": dict(body.process_options),
        "trigger_type": "manual",
        "requested_by": requested_by,
    }
    idempotency_key = f"console-radar-fetch-run:{fetch_run.id}:{int(_utcnow().timestamp())}"
    submit = get_scheduler_client().submit_task(
        task_type="content.pipeline.radar",
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response = TriggerProcessFetchRunResponse(
        fetch_run_id=int(fetch_run.id),
        task_id=submit.get("id"),
        trace_id=submit.get("trace_id"),
        status=str(submit.get("status") or "pending"),
        review_status="pending",
        review_queue_path="/api/internal/content/reviews/?status=pending",
        next_action="open_review_queue",
    )
    return response.model_dump()


def list_fetch_runs(
    db: Session,
    *,
    source_config_id: int | None = None,
    status_value: str | None = None,
) -> list[dict[str, Any]]:
    try:
        query = db.query(models.FetchRun, models.SourceConfig).join(
            models.SourceConfig, models.FetchRun.source_config_id == models.SourceConfig.id
        )
    except OperationalError:
        return []
    if source_config_id is not None:
        query = query.filter(models.FetchRun.source_config_id == source_config_id)
    if status_value:
        query = query.filter(models.FetchRun.status == status_value)
    try:
        rows = query.order_by(models.FetchRun.created_at.desc()).all()
    except OperationalError:
        return []
    items: list[dict[str, Any]] = []
    for fetch_run, source in rows:
        item = serialize_fetch_run(fetch_run, source)
        if fetch_run.task_id:
            item = sync_fetch_run_status(db, fetch_run, source, item)
        items.append(item)
    return items


def list_content_items(
    db: Session,
    *,
    review_status: str | None = None,
    publish_status: str | None = None,
) -> list[dict[str, Any]]:
    try:
        query = db.query(models.ContentItem)
    except OperationalError:
        return []
    if review_status:
        query = query.filter(models.ContentItem.review_status == review_status)
    if publish_status:
        query = query.filter(models.ContentItem.publish_status == publish_status)
    try:
        rows = query.order_by(models.ContentItem.created_at.desc()).all()
    except OperationalError:
        return []
    return [serialize_content_item(row) for row in rows]


def get_content_item_or_404(db: Session, content_item_id: int) -> models.ContentItem:
    row = db.query(models.ContentItem).filter(models.ContentItem.id == content_item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail={"code": ErrorCode.NOT_FOUND, "message": "内容不存在"})
    return row


def approve_content_item(db: Session, row: models.ContentItem, operator: str, reason: str | None) -> dict[str, Any]:
    now = _utcnow()
    row.review_status = "approved"
    row.reviewed_by = operator
    row.reviewed_at = now
    db.add(
        models.ReviewDecision(
            content_item_id=row.id,
            decision="approved",
            reason=reason,
            operator=operator,
            snapshot_title=row.title,
            snapshot_content=row.processed_content or row.raw_content,
        )
    )
    db.commit()
    db.refresh(row)
    return serialize_content_item(row)


def reject_content_item(db: Session, row: models.ContentItem, operator: str, reason: str | None) -> dict[str, Any]:
    now = _utcnow()
    row.review_status = "rejected"
    row.reviewed_by = operator
    row.reviewed_at = now
    row.error_message = reason or row.error_message
    db.add(
        models.ReviewDecision(
            content_item_id=row.id,
            decision="rejected",
            reason=reason,
            operator=operator,
            snapshot_title=row.title,
            snapshot_content=row.processed_content or row.raw_content,
        )
    )
    db.commit()
    db.refresh(row)
    return serialize_content_item(row)


def publish_content_to_post(
    db: Session,
    row: models.ContentItem,
    operator: str,
    body: PublishToPostRequest,
) -> dict[str, Any]:
    title = (body.title or row.title or "").strip()
    content = (body.content or row.processed_content or row.raw_content or "").strip()
    if not title or not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": ErrorCode.VALIDATION_ERROR, "message": "标题和内容不能为空"},
        )

    post = crud_create_post(db, title=title, content=content, tech_tag=body.tech_tags)
    now = _utcnow()
    row.publish_status = "published"
    row.pipeline_status = "published"
    row.review_status = "approved"
    row.reviewed_by = operator
    row.reviewed_at = now
    row.draft_post_id = post.id
    db.add(
        models.ReviewDecision(
            content_item_id=row.id,
            decision="published",
            reason=f"post:{post.id}",
            operator=operator,
            snapshot_title=title,
            snapshot_content=content,
        )
    )
    db.commit()
    db.refresh(row)
    return {"content_item": serialize_content_item(row), "post_id": post.id}


def serialize_source(row: models.SourceConfig) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "source_type": row.source_type,
        "enabled": bool(row.enabled),
        "channels": _from_json(row.channels, []),
        "keywords": _from_json(row.keywords, []),
        "lookback_hours": int(row.lookback_hours or 24),
        "item_limit": int(row.item_limit or 20),
        "dedup_window_hours": int(row.dedup_window_hours or 24),
        "config": _from_json(row.config_json, {}),
        "last_cursor": _from_json(row.last_cursor, None),
        "last_run_at": _iso(row.last_run_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def serialize_fetch_run(fetch_run: models.FetchRun, source: models.SourceConfig) -> dict[str, Any]:
    return {
        "id": fetch_run.id,
        "source_config_id": fetch_run.source_config_id,
        "source_name": source.name,
        "source_type": source.source_type,
        "trigger_mode": fetch_run.trigger_mode,
        "status": fetch_run.status,
        "task_id": fetch_run.task_id,
        "trace_id": fetch_run.trace_id,
        "requested_by": fetch_run.requested_by,
        "request_payload": _from_json(fetch_run.request_payload, {}),
        "fetched_count": int(fetch_run.fetched_count or 0),
        "inserted_count": int(fetch_run.inserted_count or 0),
        "deduped_count": int(fetch_run.deduped_count or 0),
        "duration_ms": fetch_run.duration_ms,
        "error_message": fetch_run.error_message,
        "started_at": _iso(fetch_run.started_at),
        "finished_at": _iso(fetch_run.finished_at),
        "created_at": _iso(fetch_run.created_at),
        "updated_at": _iso(fetch_run.updated_at),
    }


def serialize_content_item(row: models.ContentItem) -> dict[str, Any]:
    return {
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
        "reviewed_at": _iso(row.reviewed_at),
        "draft_post_id": row.draft_post_id,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def sync_fetch_run_status(
    db: Session,
    fetch_run: models.FetchRun,
    source: models.SourceConfig,
    current: dict[str, Any],
) -> dict[str, Any]:
    try:
        detail = get_scheduler_task_detail(fetch_run.task_id or "")
    except Exception:
        return current

    status_value = str(detail.get("status") or fetch_run.status or "pending")
    changed = False
    if fetch_run.status != status_value:
        fetch_run.status = status_value
        changed = True
    result = detail.get("result") or {}
    if isinstance(result, dict):
        fetched = int(result.get("fetched_count") or fetch_run.fetched_count or 0)
        inserted = int(result.get("inserted_count") or fetch_run.inserted_count or 0)
        deduped = int(result.get("deduped_count") or fetch_run.deduped_count or 0)
        duration_ms = result.get("duration_ms")
        if fetch_run.fetched_count != fetched:
            fetch_run.fetched_count = fetched
            changed = True
        if fetch_run.inserted_count != inserted:
            fetch_run.inserted_count = inserted
            changed = True
        if fetch_run.deduped_count != deduped:
            fetch_run.deduped_count = deduped
            changed = True
        if duration_ms is not None and fetch_run.duration_ms != int(duration_ms):
            fetch_run.duration_ms = int(duration_ms)
            changed = True
        if status_value == "success":
            synced = sync_content_items_from_result(db, fetch_run, source, result)
            if synced:
                if fetch_run.inserted_count != synced:
                    fetch_run.inserted_count = synced
                    changed = True
    last_error = detail.get("last_error")
    if last_error and fetch_run.error_message != str(last_error):
        fetch_run.error_message = str(last_error)
        changed = True
    if status_value in {"success", "failure", "cancelled"} and fetch_run.finished_at is None:
        fetch_run.finished_at = _utcnow()
        changed = True
    if changed:
        db.commit()
        db.refresh(fetch_run)
        current = serialize_fetch_run(fetch_run, source)
    return current


def get_scheduler_task_detail(task_id: str) -> dict[str, Any]:
    if not task_id:
        return {}
    client = get_scheduler_client()
    base_url = client.base_url + f"/api/internal/scheduler/tasks/{task_id}"
    headers = {"x-internal-token": client._config.internal_token}
    import httpx

    timeout = httpx.Timeout(float(client._config.timeout_seconds))
    with httpx.Client(timeout=timeout) as http_client:
        response = http_client.get(base_url, headers=headers)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def sync_content_items_from_result(
    db: Session,
    fetch_run: models.FetchRun,
    source: models.SourceConfig,
    result: dict[str, Any],
) -> int:
    result_items = result.get("items") if isinstance(result.get("items"), list) else None
    items: list[dict[str, Any]] = []

    if result_items:
        items = [item for item in result_items if isinstance(item, dict)]

    repository = ContentRepository()
    inserted_count = 0
    for item in items:
        source_id = build_content_source_id(item)
        if not source_id:
            continue
        raw_content = str(item.get("content") or "").strip() or None
        title = str(item.get("title") or "").strip() or source_id
        source_url = str(item.get("link") or "").strip() or None
        existing = get_content_item_by_source(db, source.source_type, source_id)
        if existing:
            update_content_item(
                db,
                existing,
                source_config_id=source.id,
                fetch_run_id=fetch_run.id,
                source_url=source_url,
                title=title,
                raw_content=raw_content,
                processed_content=raw_content,
                pipeline_status="processed",
                review_status="pending_review",
                publish_status="pending",
                error_message=None,
            )
        else:
            inserted_count += 1
            repository.upsert_fetched_item(
                SourceItem(
                    source_type=source.source_type,
                    source_id=source_id,
                    source_url=source_url,
                    title=title,
                    raw_content=raw_content,
                    metadata={},
                )
            )
            repository.attach_fetch_context(
                source_type=source.source_type,
                source_id=source_id,
                source_config_id=source.id,
                fetch_run_id=fetch_run.id,
            )
            existing = get_content_item_by_source(db, source.source_type, source_id)
            if existing is None:
                continue
            update_content_item(
                db,
                existing,
                source_config_id=source.id,
                fetch_run_id=fetch_run.id,
                source_type=source.source_type,
                source_url=source_url,
                title=title,
                raw_content=raw_content,
                processed_content=raw_content,
                publish_status="pending",
                pipeline_status="processed",
                review_status="pending_review",
                error_message=None,
            )
    return inserted_count


def build_content_source_id(item: dict[str, Any]) -> str:
    for key in ("dedup_key", "link", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value[:255]
    return ""
