from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from apps.platform.database import get_db
from apps.platform.schemas.memory import MemoryFeedbackWriteRequest, MemoryPreferenceWriteRequest, MemorySearchRequest
from apps.platform.services.agent_memory_service import AgentMemoryService

router = APIRouter(prefix="/api/internal/memory", tags=["memory"])


@router.post("/preferences")
def write_preference(
    body: MemoryPreferenceWriteRequest,
    db: Session = Depends(get_db),
):
    row = AgentMemoryService(db).record_preference(
        scope=body.scope,
        scope_key=body.scope_key,
        preference_key=body.preference_key,
        value=body.value,
        source=body.source or "manual_preference_api",
        expires_at=body.expires_at,
    )
    return {
        "code": 0,
        "data": {
            "id": int(row.id),
            "scope": row.scope,
            "scope_key": row.scope_key,
            "memory_type": row.memory_type,
            "memory_key": row.memory_key,
        },
        "message": "ok",
    }


@router.post("/feedback")
def write_feedback(
    body: MemoryFeedbackWriteRequest,
    db: Session = Depends(get_db),
):
    row = AgentMemoryService(db).record_manual_feedback(
        scope=body.scope,
        scope_key=body.scope_key,
        feedback_key=body.feedback_key,
        value=body.value,
        source=body.source or "manual_feedback_api",
        expires_at=body.expires_at,
    )
    return {
        "code": 0,
        "data": {
            "id": int(row.id),
            "scope": row.scope,
            "scope_key": row.scope_key,
            "memory_type": row.memory_type,
            "memory_key": row.memory_key,
        },
        "message": "ok",
    }


@router.post("/search")
def search_memory(
    body: MemorySearchRequest,
    db: Session = Depends(get_db),
):
    items = AgentMemoryService(db).search_memories(
        keyword=body.keyword,
        scopes=body.scopes,
        memory_type=body.memory_type,
        limit=body.limit,
    )
    return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}
