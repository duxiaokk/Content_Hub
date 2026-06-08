from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from core.config import settings
from scheduler_client import get_scheduler_client


router = APIRouter(prefix="/api/internal/tasks", tags=["Internal Tasks"])


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != settings.internal_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


class AdoRepostRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)


@router.post("/ado-repost/run")
def trigger_ado_repost_run(
    request: Request,
    body: AdoRepostRunRequest,
):
    _verify_internal_token(request)
    trace_id = (body.trace_id or "").strip() or str(uuid.uuid4())
    submit = get_scheduler_client().submit_task(
        task_type="ado_repost.run",
        payload=body.payload or {},
        trace_id=trace_id,
        idempotency_key=body.idempotency_key,
    )
    return {"task_id": submit.get("id"), "trace_id": submit.get("trace_id") or trace_id}

