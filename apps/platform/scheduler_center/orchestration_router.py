from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

try:
    from routers.internal_tasks import ContentWorkflowRunRequest, build_content_workflow_payload
except ImportError:  # pragma: no cover - package import fallback
    from apps.platform.routers.internal_tasks import ContentWorkflowRunRequest, build_content_workflow_payload
from scheduler_center.auth import verify_internal_token
from scheduler_center.database import get_db
from scheduler_center.dispatcher import TaskStatus
from scheduler_center.models import SchedulerTask
from scheduler_center.orchestration_schemas import (
    RunListItem,
    RunListResponse,
    RunStatusResponse,
    RunSubmitRequest,
    RunSubmitResponse,
)
from scheduler_center.router import _append_event, _append_log, _dumps, _get_trace_id, _utcnow
from scheduler_center.schemas import TaskSubmitRequest

router = APIRouter(prefix="/api/internal/orchestration", tags=["Orchestration"])

WORKFLOW_TASK_TYPE = "content.workflow.run"


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _to_run_status(task_status: str) -> str:
    mapping = {
        TaskStatus.PENDING: "PENDING",
        TaskStatus.RUNNING: "RUNNING",
        TaskStatus.SUCCEEDED: "SUCCEEDED",
        TaskStatus.FAILED: "FAILED",
        TaskStatus.CANCELED: "CANCELED",
    }
    return mapping.get(task_status, task_status)


def _build_workflow_payload(body: RunSubmitRequest) -> dict[str, Any]:
    context = dict(body.context or {})
    fetcher_name = str(context.get("fetcher_name") or "cnblogs")
    workflow_body = ContentWorkflowRunRequest(
        workflow_name=str(context.get("workflow_name") or body.name or "content.workflow.run"),
        source_name=str(context.get("source_name") or fetcher_name),
        fetcher_name=fetcher_name,
        processor_name=str(context.get("processor_name") or "rewrite"),
        publisher_name=str(context.get("publisher_name") or "blog"),
        lookback_hours=int(context.get("lookback_hours") or 24),
        limit=int(context.get("limit") or 20),
        fetch_options=dict(context.get("fetch_options") or {}),
        process_options=dict(context.get("process_options") or {}),
        publish_options=dict(context.get("publish_options") or {}),
    )
    payload = build_content_workflow_payload(workflow_body)
    payload["intent"] = body.intent
    payload["constraints"] = dict(body.constraints or {})
    return payload


@router.post("/runs", response_model=RunSubmitResponse)
def submit_run(
    request: Request,
    body: RunSubmitRequest,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> RunSubmitResponse:
    trace_id = body.trace_id or _get_trace_id(request)
    run_id = str(uuid.uuid4())
    payload = _build_workflow_payload(body)
    now = _utcnow()
    task = SchedulerTask(
        id=run_id,
        idempotency_key=None,
        trace_id=trace_id,
        task_type=WORKFLOW_TASK_TYPE,
        payload_json=_dumps(payload),
        status=TaskStatus.PENDING,
        cancel_requested=0,
        max_retries=2,
        retry_delay_seconds=3.0,
        attempt_count=0,
        next_run_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(task)
    _append_log(db, task_id=run_id, trace_id=trace_id, level="INFO", message="workflow orchestration submitted")
    _append_event(
        db,
        task_id=run_id,
        trace_id=trace_id,
        event_type="STATUS_CHANGED",
        from_status=None,
        to_status=TaskStatus.PENDING,
        attempt_no=None,
        message="submitted through orchestration adapter",
    )
    db.commit()

    return RunSubmitResponse(
        run_id=run_id,
        trace_id=trace_id,
        status="PENDING",
        total_tasks=3,
        created_at=now,
    )


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> RunStatusResponse:
    task = db.query(SchedulerTask).filter(SchedulerTask.id == run_id, SchedulerTask.task_type == WORKFLOW_TASK_TYPE).first()
    if not task:
        raise HTTPException(status_code=404, detail="Run not found")

    payload = _loads(task.payload_json)
    result = _loads(task.result_json)
    task_statuses = {
        "fetch": _to_run_status(task.status),
        "process": _to_run_status(task.status),
        "publish": _to_run_status(task.status),
    }
    return RunStatusResponse(
        run_id=task.id,
        trace_id=task.trace_id or task.id,
        name=(payload or {}).get("workflow_name") if isinstance(payload, dict) else None,
        status=_to_run_status(task.status),
        total_tasks=3,
        succeeded_tasks=3 if task.status == TaskStatus.SUCCEEDED else 0,
        failed_tasks=1 if task.status == TaskStatus.FAILED else 0,
        skipped_tasks=0,
        task_statuses=task_statuses,
        result=result if isinstance(result, dict) else None,
        last_error=task.last_error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        finished_at=task.updated_at if task.status in {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED} else None,
    )


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> RunListResponse:
    query = db.query(SchedulerTask).filter(SchedulerTask.task_type == WORKFLOW_TASK_TYPE)
    if status:
        query = query.filter(SchedulerTask.status == status)
    total = query.count()
    rows = query.order_by(SchedulerTask.created_at.desc()).offset(offset).limit(limit).all()
    items = []
    for row in rows:
        payload = _loads(row.payload_json)
        items.append(
            RunListItem(
                run_id=row.id,
                trace_id=row.trace_id or row.id,
                name=(payload or {}).get("workflow_name") if isinstance(payload, dict) else None,
                status=_to_run_status(row.status),
                total_tasks=3,
                created_at=row.created_at,
            )
        )
    return RunListResponse(items=items, total=total)


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> dict[str, str]:
    task = db.query(SchedulerTask).filter(SchedulerTask.id == run_id, SchedulerTask.task_type == WORKFLOW_TASK_TYPE).first()
    if not task:
        raise HTTPException(status_code=404, detail="Run not found")
    if task.status not in (TaskStatus.RUNNING, TaskStatus.PENDING):
        raise HTTPException(status_code=400, detail=f"Cannot cancel run in status {task.status}")
    task.cancel_requested = 1
    task.updated_at = _utcnow()
    db.commit()
    return {"run_id": run_id, "status": "cancel_requested"}
