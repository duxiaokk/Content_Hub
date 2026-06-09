from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LinearPipelineFetchRequest(BaseModel):
    source_name: str = Field(default="cnblogs", min_length=1, max_length=64)
    lookback_hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=20, ge=1, le=200)
    cursor: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class LinearPipelineProcessContext(BaseModel):
    run_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class LinearPipelinePublishTarget(BaseModel):
    target_name: str = Field(default="blog", min_length=1, max_length=64)
    options: dict[str, Any] = Field(default_factory=dict)


class LinearPipelineRunRequest(BaseModel):
    fetcher_name: str = Field(default="cnblogs", min_length=1, max_length=64)
    processor_name: str = Field(default="rewrite", min_length=1, max_length=64)
    publisher_name: str = Field(default="blog", min_length=1, max_length=64)
    fetch_request: LinearPipelineFetchRequest = Field(default_factory=LinearPipelineFetchRequest)
    process_context: LinearPipelineProcessContext = Field(default_factory=LinearPipelineProcessContext)
    publish_target: LinearPipelinePublishTarget = Field(default_factory=LinearPipelinePublishTarget)
    trace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)
