from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

import models


def get_agent_draft_by_id(db: Session, draft_id: int) -> models.AgentDraft | None:
    return db.query(models.AgentDraft).filter(models.AgentDraft.id == draft_id).first()


def get_agent_draft_by_source_key(
    db: Session, source_dedup_key: str | None
) -> models.AgentDraft | None:
    if not source_dedup_key:
        return None
    return (
        db.query(models.AgentDraft)
        .filter(models.AgentDraft.source_dedup_key == source_dedup_key)
        .first()
    )


def create_agent_draft(db: Session, **kwargs: Any) -> models.AgentDraft:
    draft = models.AgentDraft(**kwargs)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def update_agent_draft(
    db: Session,
    draft: models.AgentDraft,
    *,
    status: str | None = None,
    reviewed_by: str | None = None,
    markdown_path: str | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    raw_payload: str | None = None,
) -> models.AgentDraft:
    if status is not None:
        draft.status = status
        if status in {"approved", "rejected", "published"}:
            draft.reviewed_at = datetime.now(timezone.utc)
    if reviewed_by is not None:
        draft.reviewed_by = reviewed_by
    if markdown_path is not None:
        draft.markdown_path = markdown_path
    if target_type is not None:
        draft.target_type = target_type
    if target_id is not None:
        draft.target_id = target_id
    if raw_payload is not None:
        draft.raw_payload = raw_payload
    db.commit()
    db.refresh(draft)
    return draft
