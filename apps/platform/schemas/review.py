from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReviewQueueOut(BaseModel):
    id: int
    content_item_id: int
    candidate_title: str | None = None
    candidate_content: str | None = None
    status: str
    reviewer: str | None = None
    review_note: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime | None = None
    original_title: str | None = None
    original_content: str | None = None
    summary: str | None = None
    score: float | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    publish_status: str | None = None
    publish_path: str | None = None
    next_action: str | None = None
    quality_gate: dict[str, Any] | None = None


class ReviewApproveRequest(BaseModel):
    reviewer: str = Field(default="admin", min_length=1)
    edited_title: str | None = None
    edited_content: str | None = None


class ReviewRejectRequest(BaseModel):
    reviewer: str = Field(default="admin", min_length=1)
    note: str = ""


class ReviewAutoReviewRequest(BaseModel):
    reviewer: str = Field(default="quality-gate", min_length=1)
    use_tool: bool = False
    auto_approve: bool = False
    auto_reject: bool = True
