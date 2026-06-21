from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.config import settings
from scheduler_client import get_scheduler_client
from scheduler_center.config import CONTENT_PIPELINE_DAILY_DIGEST, CONTENT_PIPELINE_RADAR
from schemas.pipeline import LinearPipelineRunRequest


router = APIRouter(prefix="/api/internal/tasks", tags=["Internal Tasks"])


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != settings.internal_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _new_trace_id(trace_id: str | None) -> str:
    return (trace_id or "").strip() or str(uuid.uuid4())


def _submit_scheduler_task(
    *,
    task_type: str,
    payload: dict[str, Any],
    trace_id: str,
    idempotency_key: str | None,
) -> dict[str, Any]:
    return get_scheduler_client().submit_task(
        task_type=task_type,
        payload=payload,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )


def build_content_workflow_payload(body: "ContentWorkflowRunRequest") -> dict[str, Any]:
    payload = {
        "workflow_name": body.workflow_name,
        "source_name": body.source_name,
        "fetcher_name": body.fetcher_name,
        "processor_name": body.processor_name,
        "publisher_name": body.publisher_name,
        "lookback_hours": body.lookback_hours,
        "limit": body.limit,
        "fetch_options": body.fetch_options,
        "process_options": body.process_options,
        "publish_options": body.publish_options,
    }
    if body.nodes:
        payload["nodes"] = body.nodes
    return payload


def build_radar_pipeline_payload(body: "RadarPipelineRunRequest") -> dict[str, Any]:
    return {
        "workflow_name": "radar_pipeline",
        "limit": body.limit,
        "source_type": body.source_type,
        "fetch_run_id": body.fetch_run_id,
        "filter_config": body.filter_config,
        "process_options": body.process_options,
        "trigger_type": "manual",
    }


def build_daily_digest_payload(body: "DailyDigestRunRequest") -> dict[str, Any]:
    return {
        "lookback_hours": body.lookback_hours,
        "trigger_type": "manual",
    }


class AdoRepostRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class ContentFetchBatchRequest(BaseModel):
    source_config_id: int = Field(ge=1)
    source_type: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=120)
    channels: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    lookback_hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=20, ge=1, le=200)
    dedup_window_hours: int = Field(default=24, ge=1, le=720)
    dry_run: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class ContentWorkflowRunRequest(BaseModel):
    workflow_name: str = Field(default="content.workflow.run", min_length=1, max_length=128)
    source_name: str = Field(default="cnblogs", min_length=1, max_length=64)
    fetcher_name: str = Field(default="cnblogs", min_length=1, max_length=64)
    processor_name: str = Field(default="rewrite", min_length=1, max_length=64)
    publisher_name: str = Field(default="blog", min_length=1, max_length=64)
    lookback_hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=20, ge=1, le=200)
    fetch_options: dict[str, Any] = Field(default_factory=dict)
    process_options: dict[str, Any] = Field(default_factory=dict)
    publish_options: dict[str, Any] = Field(default_factory=dict)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class RadarPipelineRunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    source_type: str | None = None
    fetch_run_id: int | None = Field(default=None, ge=1)
    filter_config: dict[str, Any] = Field(default_factory=dict)
    process_options: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class DailyDigestRunRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=720)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


class PublishApprovedContentRequest(BaseModel):
    content_item_id: int = Field(ge=1)
    target_type: Literal["blog"] = "blog"
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


@router.post("/ado-repost/run")
def trigger_ado_repost_run(
    request: Request,
    body: AdoRepostRunRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    submit = _submit_scheduler_task(
        task_type="ado_repost.run",
        payload=body.payload or {},
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {"task_id": submit.get("id"), "trace_id": submit.get("trace_id") or trace_id}


@router.post("/content-fetch/batch/run")
def trigger_content_fetch_batch(
    request: Request,
    body: ContentFetchBatchRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = body.model_dump(exclude={"trace_id", "idempotency_key"})
    submit = _submit_scheduler_task(
        task_type="content.fetch.batch",
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": "content.fetch.batch",
    }


@router.post("/content-pipeline/linear/run")
def trigger_linear_content_pipeline(
    request: Request,
    body: LinearPipelineRunRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = {
        "fetcher_name": body.fetcher_name,
        "processor_name": body.processor_name,
        "publisher_name": body.publisher_name,
        "fetch_request": body.fetch_request.model_dump(),
        "process_context": body.process_context.model_dump(),
        "publish_target": body.publish_target.model_dump(),
    }
    submit = _submit_scheduler_task(
        task_type="content.pipeline.linear",
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": "content.pipeline.linear",
    }


@router.post("/content-workflow/run")
def trigger_content_workflow(
    request: Request,
    body: ContentWorkflowRunRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = build_content_workflow_payload(body)
    submit = _submit_scheduler_task(
        task_type="content.workflow.run",
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": "content.workflow.run",
    }


@router.post("/content-pipeline/radar/run")
def trigger_radar_pipeline(
    request: Request,
    body: RadarPipelineRunRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = build_radar_pipeline_payload(body)
    submit = _submit_scheduler_task(
        task_type=CONTENT_PIPELINE_RADAR,
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": CONTENT_PIPELINE_RADAR,
    }


@router.post("/content-pipeline/daily-digest/run")
def trigger_daily_digest_pipeline(
    request: Request,
    body: DailyDigestRunRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = build_daily_digest_payload(body)
    submit = _submit_scheduler_task(
        task_type=CONTENT_PIPELINE_DAILY_DIGEST,
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": CONTENT_PIPELINE_DAILY_DIGEST,
    }


@router.post("/content-publish/approved/run")
def trigger_publish_approved_content(
    request: Request,
    body: PublishApprovedContentRequest,
):
    _verify_internal_token(request)
    trace_id = _new_trace_id(body.trace_id)
    payload = {
        "content_item_id": body.content_item_id,
        "target_type": body.target_type,
    }
    submit = _submit_scheduler_task(
        task_type="content.publish.approved",
        payload=payload,
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {
        "task_id": submit.get("id"),
        "trace_id": submit.get("trace_id") or trace_id,
        "task_type": "content.publish.approved",
    }
