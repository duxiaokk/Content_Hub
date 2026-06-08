from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from core.config import settings
from core.mempool import get_pool
from database import get_db
from scheduler_client import get_scheduler_client
from schemas.agent import AgentDraftIngestRequest, AgentDraftResponse, AgentDraftUpdateRequest
from services.agent_ingest_service import (
    get_agent_draft_detail,
    ingest_agent_draft,
    update_agent_draft_status,
)

router = APIRouter(prefix="/api/internal/agent", tags=["Agent Ingest"])
logger = logging.getLogger(__name__)


def _verify_internal_token(request: Request) -> None:
    token = request.headers.get("x-internal-token")
    if not token or token != settings.internal_agent_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def _to_response(draft) -> AgentDraftResponse:
    return AgentDraftResponse(
        id=draft.id,
        title=draft.title,
        status=draft.status,
        markdown_path=draft.markdown_path,
        source_platform=draft.source_platform,
        source_link=draft.source_link,
        source_external_id=draft.source_external_id,
        source_dedup_key=draft.source_dedup_key,
        reviewed_by=draft.reviewed_by,
        reviewed_at=draft.reviewed_at.isoformat() if draft.reviewed_at else None,
        created_at=draft.created_at.isoformat() if draft.created_at else None,
        updated_at=draft.updated_at.isoformat() if draft.updated_at else None,
    )


@router.post("/drafts", response_model=AgentDraftResponse)
def create_draft(
    request: Request,
    payload: AgentDraftIngestRequest,
    db: Session = Depends(get_db),
):
    _verify_internal_token(request)
    result = ingest_agent_draft(db, payload)
    draft = result["draft"]
    try:
        trace_id = str(uuid.uuid4())
        submit = get_scheduler_client().submit_task(
            task_type="audit.draft",
            payload={
                "draft_id": int(draft.id),
                "title": str(draft.title),
                "markdown_path": str(draft.markdown_path),
                "source_platform": str(draft.source_platform),
                "source_link": str(draft.source_link),
            },
            trace_id=trace_id,
            idempotency_key=f"audit.draft:draft:{int(draft.id)}",
        )
        task_id = str(submit.get("id") or "")
        trace_id2 = str(submit.get("trace_id") or trace_id)
        get_pool().set(
            f"agent_draft:audit:{int(draft.id)}",
            {"task_id": task_id, "trace_id": trace_id2},
            ttl_seconds=86400 * 7,
        )
    except Exception:
        logger.exception("submit audit.draft task failed")
    return _to_response(draft)


@router.get("/drafts/{draft_id}", response_model=AgentDraftResponse)
def read_draft(
    request: Request,
    draft_id: int,
    db: Session = Depends(get_db),
):
    _verify_internal_token(request)
    draft = get_agent_draft_detail(db, draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    return _to_response(draft)


@router.patch("/drafts/{draft_id}", response_model=AgentDraftResponse)
def patch_draft(
    request: Request,
    draft_id: int,
    payload: AgentDraftUpdateRequest,
    db: Session = Depends(get_db),
):
    _verify_internal_token(request)
    draft = update_agent_draft_status(db, draft_id, payload)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    return _to_response(draft)
