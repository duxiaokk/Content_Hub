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


class FetchValidationIssue(BaseModel):
    source: str
    source_id: str | None = None
    reason: str
    detail: str | None = None


class FetchAlertEvent(BaseModel):
    source: str
    alert_type: str
    severity: str = "warning"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class FetchSourceStat(BaseModel):
    source: str
    status: str = "success"
    fetched_count: int = 0
    inserted_count: int = 0
    deduped_count: int = 0
    invalid_count: int = 0
    retried_count: int = 0
    elapsed_ms: float = 0
    previous_cursor: str | None = None
    next_cursor: str | None = None
    resume_cursor: str | None = None


class FetchBatchStats(BaseModel):
    total_fetched: int = 0
    total_inserted: int = 0
    total_deduped: int = 0
    total_validated: int = 0
    total_invalid: int = 0
    total_retried: int = 0
    total_alerts: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0


class FetchBatchResult(BaseModel):
    run_id: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    matched_items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[FetchBatchError] = Field(default_factory=list)
    validation_issues: list[FetchValidationIssue] = Field(default_factory=list)
    alerts: list[FetchAlertEvent] = Field(default_factory=list)
    source_stats: list[FetchSourceStat] = Field(default_factory=list)
    checkpoints: dict[str, dict[str, Any]] = Field(default_factory=dict)
    stats: FetchBatchStats = Field(default_factory=FetchBatchStats)
