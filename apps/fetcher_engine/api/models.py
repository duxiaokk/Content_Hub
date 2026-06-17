from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FetchBatchRequest(BaseModel):
    run_id: str
    sources: list[str] = Field(default_factory=list)
    subscription_ids: list[int] = Field(default_factory=list)
    lookback_hours: int = 24
    limit_per_source: int = 20
    options: dict[str, Any] = Field(default_factory=dict)


class FetchBatchError(BaseModel):
    source: str
    error: str
    traceback: str | None = None


class FetchBatchStats(BaseModel):
    total_fetched: int = 0
    total_inserted: int = 0
    total_deduped: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0


class FetchBatchResult(BaseModel):
    run_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    matched_items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[FetchBatchError] = Field(default_factory=list)
    stats: FetchBatchStats = Field(default_factory=FetchBatchStats)
