from __future__ import annotations

from datetime import datetime

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


class ReviewApproveRequest(BaseModel):
    reviewer: str = Field(default="admin", min_length=1)
    edited_title: str | None = None
    edited_content: str | None = None


class ReviewRejectRequest(BaseModel):
    reviewer: str = Field(default="admin", min_length=1)
    note: str = ""
