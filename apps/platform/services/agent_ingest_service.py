from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from core.config import BASE_DIR
from crud.crud_agent import (
    create_agent_draft,
    get_agent_draft_by_id,
    get_agent_draft_by_source_key,
    update_agent_draft,
)
from schemas.agent import AgentDraftIngestRequest, AgentDraftUpdateRequest

AGENT_DRAFT_DIR = BASE_DIR / "content" / "agent_drafts"
AGENT_DRAFT_DIR.mkdir(parents=True, exist_ok=True)


def _slugify_filename(text: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe[:80] or "draft"


def _build_markdown_path(title: str, source_dedup_key: str | None) -> Path:
    base = source_dedup_key or title
    return AGENT_DRAFT_DIR / f"{_slugify_filename(base)}.md"


def ingest_agent_draft(db: Session, request: AgentDraftIngestRequest) -> dict[str, Any]:
    existing = get_agent_draft_by_source_key(db, request.source_dedup_key)
    markdown_path = _build_markdown_path(request.title, request.source_dedup_key)
    markdown_path.write_text(request.markdown_content, encoding="utf-8")

    payload_json = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    if existing:
        draft = update_agent_draft(
            db,
            existing,
            status="pending_review",
            markdown_path=str(markdown_path),
            raw_payload=payload_json,
        )
    else:
        draft = create_agent_draft(
            db,
            draft_type="youtube_repost",
            status="pending_review",
            title=request.title,
            summary=request.summary,
            source_platform=request.source_platform,
            source_link=request.source_link,
            source_external_id=request.source_external_id,
            source_dedup_key=request.source_dedup_key,
            markdown_path=str(markdown_path),
            created_by="ado_repost",
            raw_payload=payload_json,
        )

    return {"draft": draft, "markdown_path": str(markdown_path)}


def get_agent_draft_detail(db: Session, draft_id: int):
    return get_agent_draft_by_id(db, draft_id)


def update_agent_draft_status(
    db: Session, draft_id: int, request: AgentDraftUpdateRequest
):
    draft = get_agent_draft_by_id(db, draft_id)
    if not draft:
        return None

    markdown_path = None
    if request.markdown_content is not None:
        path = Path(draft.markdown_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.markdown_content, encoding="utf-8")
        markdown_path = str(path)

    return update_agent_draft(
        db,
        draft,
        status=request.status,
        reviewed_by=request.reviewed_by,
        markdown_path=markdown_path,
        target_type=request.target_type,
        target_id=request.target_id,
    )
