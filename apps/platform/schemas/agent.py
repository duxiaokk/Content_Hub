from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentDraftIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str | None = None
    markdown_content: str = Field(..., min_length=1)
    source_platform: str = Field(..., min_length=1, max_length=64)
    source_link: str = Field(..., min_length=1, max_length=1024)
    source_external_id: str | None = Field(default=None, max_length=255)
    source_dedup_key: str | None = Field(default=None, max_length=255)
    source_published_at: str | None = None
    cover_image_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class AgentDraftUpdateRequest(BaseModel):
    status: Literal["pending_review", "reviewing", "approved", "rejected", "published"] | None = None
    reviewed_by: str | None = Field(default=None, max_length=150)
    markdown_content: str | None = Field(default=None, min_length=1)
    target_type: str | None = Field(default=None, max_length=64)
    target_id: int | None = None


class AgentDraftResponse(BaseModel):
    id: int
    title: str
    status: str
    markdown_path: str
    source_platform: str
    source_link: str
    source_external_id: str | None = None
    source_dedup_key: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
