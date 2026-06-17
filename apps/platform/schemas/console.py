from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SourceConfigCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    source_type: str = Field(..., min_length=1, max_length=64)
    enabled: bool = True
    channels: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    lookback_hours: int = Field(default=24, ge=1, le=720)
    item_limit: int = Field(default=20, ge=1, le=500)
    dedup_window_hours: int = Field(default=24, ge=1, le=720)
    config: dict[str, Any] = Field(default_factory=dict)


class SourceConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    enabled: bool | None = None
    channels: list[str] | None = None
    keywords: list[str] | None = None
    lookback_hours: int | None = Field(default=None, ge=1, le=720)
    item_limit: int | None = Field(default=None, ge=1, le=500)
    dedup_window_hours: int | None = Field(default=None, ge=1, le=720)
    config: dict[str, Any] | None = None


class TriggerFetchRequest(BaseModel):
    lookback_hours: int | None = Field(default=None, ge=1, le=720)
    item_limit: int | None = Field(default=None, ge=1, le=500)
    dry_run: bool = False


class TriggerProcessFetchRunRequest(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    filter_config: dict[str, Any] = Field(default_factory=dict)
    process_options: dict[str, Any] = Field(default_factory=dict)


class SourceConfigItem(BaseModel):
    id: int
    name: str
    source_type: str
    enabled: bool
    channels: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    lookback_hours: int
    item_limit: int
    dedup_window_hours: int
    config: dict[str, Any] = Field(default_factory=dict)
    last_cursor: dict[str, Any] | str | None = None
    last_run_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class FetchRunItem(BaseModel):
    id: int
    source_config_id: int
    source_name: str
    source_type: str
    trigger_mode: str
    status: str
    task_id: str | None = None
    trace_id: str | None = None
    requested_by: str | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    fetched_count: int
    inserted_count: int
    deduped_count: int
    duration_ms: int | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TriggerFetchResponse(BaseModel):
    fetch_run_id: int
    task_id: str | None = None
    trace_id: str | None = None
    status: str


class ContentItemSummary(BaseModel):
    id: int
    source_config_id: int | None = None
    fetch_run_id: int | None = None
    source_type: str
    source_id: str
    source_url: str | None = None
    title: str
    raw_content: str | None = None
    processed_content: str | None = None
    pipeline_status: str
    review_status: str
    publish_status: str
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    draft_post_id: int | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ReviewActionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class PublishToPostRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)
    tech_tags: str | None = Field(default=None, max_length=255)
