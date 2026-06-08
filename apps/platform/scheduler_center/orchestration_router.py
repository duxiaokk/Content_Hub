"""编排 API 路由

  POST /api/internal/orchestration/runs         — 提交编排运行
  GET  /api/internal/orchestration/runs/{id}    — 查询运行状态
  GET  /api/internal/orchestration/runs         — 运行列表
  POST /api/internal/orchestration/runs/{id}/cancel — 取消运行
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from scheduler_center.auth import verify_internal_token
from scheduler_center.database import get_db
from scheduler_center.orchestration_engine import OrchestrationEngine
from scheduler_center.orchestration_models import (
    OrchestrationRun,
    OrchestrationRunLog,
    OrchestrationTask,
    RunStatus,
)
from scheduler_center.orchestration_schemas import (
    AggregatorRequest,
    RunListResponse,
    RunListItem,
    RunStatusResponse,
    RunSubmitRequest,
    RunSubmitResponse,
    TaskResult,
)

router = APIRouter(prefix="/api/internal/orchestration", tags=["Orchestration"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


_engine: OrchestrationEngine | None = None


def get_orchestration_engine() -> OrchestrationEngine:
    global _engine
    if _engine is None:
        _engine = OrchestrationEngine()
    return _engine


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


# =========================================================================
# 提交编排运行
# =========================================================================


@router.post("/runs", response_model=RunSubmitResponse)
def submit_run(
    request: Request,
    body: RunSubmitRequest,
    _token: str = Depends(verify_internal_token),
    engine: OrchestrationEngine = Depends(get_orchestration_engine),
) -> RunSubmitResponse:
    """提交编排运行：规划 → 创建 Run → 开始调度。"""
    trace_id = body.trace_id or str(uuid.uuid4())

    run = engine.create_and_start_run(
        intent=body.intent,
        name=body.name,
        context=body.context,
        constraints=body.constraints,
        trace_id=trace_id,
    )

    plan = _loads(run.plan_json)

    return RunSubmitResponse(
        run_id=run.id,
        trace_id=run.trace_id,
        status=run.status,
        total_tasks=run.total_tasks,
        created_at=run.created_at,
    )


# =========================================================================
# 查询运行状态
# =========================================================================


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> RunStatusResponse:
    """查询运行状态（含所有子任务状态）。"""
    run = db.query(OrchestrationRun).filter(OrchestrationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    orch_tasks = db.query(OrchestrationTask).filter(OrchestrationTask.run_id == run_id).all()
    task_statuses = {ot.task_key: ot.status for ot in orch_tasks}

    result = _loads(run.result_json)

    return RunStatusResponse(
        run_id=run.id,
        trace_id=run.trace_id,
        name=run.name,
        status=run.status,
        total_tasks=run.total_tasks,
        succeeded_tasks=run.succeeded_tasks,
        failed_tasks=run.failed_tasks,
        skipped_tasks=run.skipped_tasks,
        task_statuses=task_statuses,
        result=result if isinstance(result, dict) else None,
        last_error=run.last_error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished_at=run.finished_at,
    )


# =========================================================================
# 运行列表
# =========================================================================


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _token: str = Depends(verify_internal_token),
) -> RunListResponse:
    """查询运行列表（支持按状态过滤）。"""
    query = db.query(OrchestrationRun)
    if status:
        query = query.filter(OrchestrationRun.status == status)
    total = query.count()
    runs = query.order_by(OrchestrationRun.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        RunListItem(
            run_id=r.id,
            trace_id=r.trace_id,
            name=r.name,
            status=r.status,
            total_tasks=r.total_tasks,
            created_at=r.created_at,
        )
        for r in runs
    ]
    return RunListResponse(items=items, total=total)


# =========================================================================
# 取消运行
# =========================================================================


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    db: Session = Depends(get_db),
    engine: OrchestrationEngine = Depends(get_orchestration_engine),
    _token: str = Depends(verify_internal_token),
) -> dict[str, str]:
    """取消运行。"""
    run = db.query(OrchestrationRun).filter(OrchestrationRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in (RunStatus.RUNNING, RunStatus.PENDING):
        raise HTTPException(status_code=400, detail=f"Cannot cancel run in status {run.status}")

    engine.cancel_run(run_id)
    return {"run_id": run_id, "status": "cancel_requested"}
