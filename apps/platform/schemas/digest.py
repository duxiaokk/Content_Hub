from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DigestReportOut(BaseModel):
    id: int
    title: str
    content_markdown: str
    included_count: int
    generated_at: datetime | None = None
    run_id: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DigestGenerateRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=720)
    run_id: str | None = None
