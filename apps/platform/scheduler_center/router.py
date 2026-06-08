from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from scheduler_center.auth import verify_internal_token
from scheduler_center.config import scheduler_settings
from scheduler_center.database import SessionLocal, get_db
from scheduler_center.dispatcher import TaskStatus, new_task_id
from scheduler_center.models import SchedulerAgent, SchedulerTask, SchedulerTaskEvent, SchedulerTaskLog
from scheduler_center.redis_queue import _hash_task, redis_submit_queue
from scheduler_center.schemas import (
    AgentItem,
    AgentListResponse,
    AgentRegisterRequest,
    TaskCancelResponse,
    TaskDetailResponse,
    TaskLogItem,
    TaskLogsResponse,
    TaskSubmitRequest,
    TaskSubmitResponse,
    TaskAttemptResponse,
    TaskEventResponse,
    TaskListItem,
    TaskListResponse,
)


router = APIRouter(prefix="/api/internal/scheduler", tags=["Scheduler"])


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _loads_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {"value": obj}
    except Exception:
        return {}


def _loads_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, list) else [obj]
    except Exception:
        return []


def _dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"


def _get_trace_id(request: Request) -> str:
    raw = (request.headers.get("x-trace-id") or "").strip()
    return raw if raw else str(uuid.uuid4())


def _get_idempotency_key(request: Request, payload: TaskSubmitRequest) -> str | None:
    raw = (request.headers.get("x-idempotency-key") or "").strip()
    if raw:
        return raw[:128]
    if payload.idempotency_key:
        return payload.idempotency_key.strip()[:128]
    return None


def _append_event(
    db: Session,
    *,
    task_id: str,
    trace_id: str | None,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    attempt_no: int | None = None,
    message: str | None = None,
) -> None:
    db.add(
        SchedulerTaskEvent(
            task_id=task_id,
            trace_id=trace_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            attempt_no=attempt_no,
            message=message,
        )
    )


def _append_log(
    db: Session,
    *,
    task_id: str,
    trace_id: str | None,
    level: str,
    message: str,
) -> None:
    db.add(SchedulerTaskLog(task_id=task_id, trace_id=trace_id, level=level, message=message))


@router.post("/tasks", response_model=TaskSubmitResponse)
def submit_task(
    request: Request,
    payload: TaskSubmitRequest,
):
    verify_internal_token(request)

    trace_id = _get_trace_id(request)
    idempotency_key = _get_idempotency_key(request, payload)

    if redis_submit_queue.enabled:
        db: Session | None = None
        if idempotency_key:
            try:
                existing_id = redis_submit_queue.try_idempotent_get(
                    idempotency_key=idempotency_key,
                    task_hash=_hash_task(payload.task_type, payload.payload or {}),
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="idempotency key conflict",
                )
            if existing_id:
                existing = redis_submit_queue.get_task(existing_id)
                if existing:
                    created_at = datetime.fromisoformat(str(existing.get("created_at")))
                    return TaskSubmitResponse(
                        id=existing_id,
                        trace_id=str(existing.get("trace_id") or trace_id),
                        status=str(existing.get("status") or TaskStatus.PENDING),
                        created_at=created_at,
                    )
                db = SessionLocal()
                try:
                    row = db.query(SchedulerTask).filter(SchedulerTask.id == existing_id).first()
                    if row:
                        return TaskSubmitResponse(
                            id=row.id,
                            trace_id=row.trace_id or trace_id,
                            status=row.status,
                            created_at=row.created_at,
                        )
                finally:
                    db.close()

        now = _utcnow()
        max_retries = (
            payload.max_retries
            if payload.max_retries is not None
            else scheduler_settings.scheduler_default_max_retries
        )
        retry_delay_seconds = (
            payload.retry_delay_seconds
            if payload.retry_delay_seconds is not None
            else scheduler_settings.scheduler_default_retry_delay_seconds
        )
        task_id = new_task_id()
        redis_submit_queue.enqueue(
            task_id=task_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            task_type=payload.task_type,
            payload=payload.payload or {},
            max_retries=int(max_retries),
            retry_delay_seconds=float(retry_delay_seconds),
        )
        return TaskSubmitResponse(id=task_id, trace_id=trace_id, status=TaskStatus.PENDING, created_at=now)

    db = SessionLocal()
    try:
        task_id = new_task_id()
        now = _utcnow()
        max_retries = (
            payload.max_retries
            if payload.max_retries is not None
            else scheduler_settings.scheduler_default_max_retries
        )
        retry_delay_seconds = (
            payload.retry_delay_seconds
            if payload.retry_delay_seconds is not None
            else scheduler_settings.scheduler_default_retry_delay_seconds
        )

        task = SchedulerTask(
            id=task_id,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            task_type=payload.task_type,
            payload_json=_dumps(payload.payload),
            status=TaskStatus.PENDING,
            cancel_requested=0,
            max_retries=int(max_retries),
            retry_delay_seconds=float(retry_delay_seconds),
            attempt_count=0,
            next_run_at=None,
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        if scheduler_settings.scheduler_submit_write_logs:
            _append_log(db, task_id=task_id, trace_id=trace_id, level="INFO", message="submitted")
        _append_event(
            db,
            task_id=task_id,
            trace_id=trace_id,
            event_type="SUBMITTED",
            from_status=None,
            to_status=TaskStatus.PENDING,
            attempt_no=0,
            message=None,
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if idempotency_key:
                existing = (
                    db.query(SchedulerTask)
                    .filter(SchedulerTask.idempotency_key == idempotency_key)
                    .first()
                )
                if existing:
                    existing_payload = _loads_dict(existing.payload_json)
                    if existing.task_type != payload.task_type or existing_payload != (payload.payload or {}):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="idempotency key conflict",
                        )
                    return TaskSubmitResponse(
                        id=existing.id,
                        trace_id=existing.trace_id or trace_id,
                        status=existing.status,
                        created_at=existing.created_at,
                    )
            raise

        return TaskSubmitResponse(id=task_id, trace_id=trace_id, status=task.status, created_at=task.created_at)
    finally:
        db.close()


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    request: Request,
    task_type: str | None = Query(default=None, min_length=1, max_length=100),
    status_in: list[str] | None = Query(default=None, alias="status"),
    idempotency_key: str | None = Query(default=None, min_length=1, max_length=128),
    trace_id: str | None = Query(default=None, min_length=1, max_length=64),
    cancel_requested: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    query = db.query(SchedulerTask)
    conditions = []
    if task_type:
        conditions.append(SchedulerTask.task_type == task_type)
    if status_in:
        conditions.append(SchedulerTask.status.in_(status_in))
    if idempotency_key:
        conditions.append(SchedulerTask.idempotency_key == idempotency_key)
    if trace_id:
        conditions.append(SchedulerTask.trace_id == trace_id)
    if cancel_requested is not None:
        conditions.append(SchedulerTask.cancel_requested == (1 if cancel_requested else 0))
    if conditions:
        query = query.filter(and_(*conditions))

    total = query.count()
    items = (
        query.order_by(SchedulerTask.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TaskListResponse(
        items=[
            TaskListItem(
                id=t.id,
                idempotency_key=t.idempotency_key,
                trace_id=t.trace_id,
                task_type=t.task_type,
                status=t.status,
                cancel_requested=bool(t.cancel_requested),
                attempt_count=int(t.attempt_count),
                next_run_at=t.next_run_at,
                last_agent=t.last_agent,
                last_error=t.last_error,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in items
        ],
        total=total,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(
    request: Request,
    task_id: str,
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    task = db.query(SchedulerTask).filter(SchedulerTask.id == task_id).first()
    if not task:
        cached = redis_submit_queue.get_task(task_id) if redis_submit_queue.enabled else None
        if not cached:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        created_at = datetime.fromisoformat(str(cached.get("created_at")))
        updated_at = datetime.fromisoformat(str(cached.get("updated_at")))
        return TaskDetailResponse(
            id=str(cached.get("id") or task_id),
            idempotency_key=cached.get("idempotency_key"),
            trace_id=str(cached.get("trace_id") or ""),
            task_type=str(cached.get("task_type") or ""),
            payload=cached.get("payload") if isinstance(cached.get("payload"), dict) else {},
            status=str(cached.get("status") or TaskStatus.PENDING),
            cancel_requested=bool(cached.get("cancel_requested") or False),
            max_retries=int(cached.get("max_retries") or 0),
            retry_delay_seconds=float(cached.get("retry_delay_seconds") or 0),
            attempt_count=int(cached.get("attempt_count") or 0),
            next_run_at=None,
            last_agent=None,
            result=None,
            last_error=None,
            created_at=created_at,
            updated_at=updated_at,
            attempts=[],
            events=[],
        )

    attempts = [
        TaskAttemptResponse(
            id=a.id,
            attempt_no=a.attempt_no,
            agent=a.agent,
            trace_id=a.trace_id,
            request=_loads_dict(a.request_json) if a.request_json else None,
            request_url=a.request_url,
            status=a.status,
            http_status=a.http_status,
            response_text=a.response_text,
            error=a.error,
            retryable=bool(a.retryable),
            started_at=a.started_at,
            finished_at=a.finished_at,
        )
        for a in sorted(task.attempts, key=lambda x: x.attempt_no)
    ]

    events = [
        TaskEventResponse(
            id=e.id,
            trace_id=e.trace_id,
            event_type=e.event_type,
            from_status=e.from_status,
            to_status=e.to_status,
            attempt_no=e.attempt_no,
            message=e.message,
            created_at=e.created_at,
        )
        for e in sorted(task.events, key=lambda x: x.id)
    ]

    return TaskDetailResponse(
        id=task.id,
        idempotency_key=task.idempotency_key,
        trace_id=task.trace_id,
        task_type=task.task_type,
        payload=_loads_dict(task.payload_json),
        status=task.status,
        cancel_requested=bool(task.cancel_requested),
        max_retries=int(task.max_retries),
        retry_delay_seconds=float(task.retry_delay_seconds),
        attempt_count=int(task.attempt_count),
        next_run_at=task.next_run_at,
        last_agent=task.last_agent,
        result=_loads_dict(task.result_json) if task.result_json else None,
        last_error=task.last_error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        attempts=attempts,
        events=events,
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
def cancel_task(
    request: Request,
    task_id: str,
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    task = db.query(SchedulerTask).filter(SchedulerTask.id == task_id).first()
    if not task:
        cached = redis_submit_queue.mark_canceled(task_id) if redis_submit_queue.enabled else None
        if not cached:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        updated_at = datetime.fromisoformat(str(cached.get("updated_at")))
        return TaskCancelResponse(
            id=str(cached.get("id") or task_id),
            trace_id=str(cached.get("trace_id") or _get_trace_id(request)),
            status=str(cached.get("status") or TaskStatus.CANCELED),
            cancel_requested=True,
            updated_at=updated_at,
        )

    if not task.trace_id:
        task.trace_id = _get_trace_id(request)
    trace_id = task.trace_id
    now = _utcnow()
    task.cancel_requested = 1
    if task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        before = task.status
        task.status = TaskStatus.CANCELED if task.status == TaskStatus.PENDING else task.status
        _append_log(db, task_id=task.id, trace_id=trace_id, level="INFO", message="cancel requested")
        _append_event(
            db,
            task_id=task.id,
            trace_id=trace_id,
            event_type="CANCEL_REQUESTED",
            from_status=before,
            to_status=task.status,
            attempt_no=None,
            message=None,
        )
    task.updated_at = now
    db.commit()

    return TaskCancelResponse(
        id=task.id,
        trace_id=trace_id,
        status=task.status,
        cancel_requested=bool(task.cancel_requested),
        updated_at=task.updated_at,
    )


@router.get("/tasks/{task_id}/logs", response_model=TaskLogsResponse)
def get_task_logs(
    request: Request,
    task_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    task = db.query(SchedulerTask).filter(SchedulerTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")

    total = db.query(SchedulerTaskLog).filter(SchedulerTaskLog.task_id == task_id).count()
    items = (
        db.query(SchedulerTaskLog)
        .filter(SchedulerTaskLog.task_id == task_id)
        .order_by(SchedulerTaskLog.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TaskLogsResponse(
        items=[
            TaskLogItem(
                id=i.id,
                trace_id=i.trace_id,
                level=i.level,
                message=i.message,
                created_at=i.created_at,
            )
            for i in items
        ],
        total=total,
    )


def _agent_to_item(agent: SchedulerAgent) -> AgentItem:
    task_types = [str(v) for v in _loads_list(agent.task_types_json)]
    return AgentItem(
        id=agent.id,
        agent_key=agent.agent_key,
        name=agent.name,
        base_url=agent.base_url,
        task_types=task_types,
        health_path=agent.health_path,
        capabilities=_loads_dict(agent.capabilities_json),
        status=int(agent.status),
        last_heartbeat_at=agent.last_heartbeat_at,
        last_health_check_at=agent.last_health_check_at,
        last_health_ok=bool(agent.last_health_ok),
        last_health_error=agent.last_health_error,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.post("/agents/register", response_model=AgentItem)
def register_agent(
    request: Request,
    payload: AgentRegisterRequest,
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    now = _utcnow()
    task_types = [t.strip() for t in payload.task_types if str(t).strip()]
    existing = db.query(SchedulerAgent).filter(SchedulerAgent.agent_key == payload.agent_key).first()
    if existing:
        existing.name = payload.name
        existing.base_url = payload.base_url.rstrip("/")
        existing.task_types_json = _dumps(task_types)
        existing.capabilities_json = _dumps(payload.capabilities or {})
        existing.health_path = payload.health_path
        existing.status = int(payload.status)
        existing.last_heartbeat_at = now
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return _agent_to_item(existing)

    agent = SchedulerAgent(
        agent_key=payload.agent_key,
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        task_types_json=_dumps(task_types),
        capabilities_json=_dumps(payload.capabilities or {}),
        health_path=payload.health_path,
        status=int(payload.status),
        last_heartbeat_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="agent_key conflict")
    db.refresh(agent)
    return _agent_to_item(agent)


@router.get("/agents", response_model=AgentListResponse)
def list_agents(
    request: Request,
    task_type: str | None = Query(default=None, min_length=1, max_length=100),
    status_eq: int | None = Query(default=None, alias="status", ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    verify_internal_token(request)

    query = db.query(SchedulerAgent)
    if status_eq is not None:
        query = query.filter(SchedulerAgent.status == int(status_eq))

    items_all = query.order_by(SchedulerAgent.id.asc()).all()
    if task_type:
        desired = task_type.strip()
        filtered = []
        for agent in items_all:
            task_types = {str(v) for v in _loads_list(agent.task_types_json)}
            if desired in task_types or "*" in task_types:
                filtered.append(agent)
        items_all = filtered

    total = len(items_all)
    page = items_all[offset : offset + limit]
    return AgentListResponse(items=[_agent_to_item(a) for a in page], total=total)

