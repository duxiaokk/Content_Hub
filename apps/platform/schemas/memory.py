from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryPreferenceWriteRequest(BaseModel):
    scope: str = Field(min_length=1)
    scope_key: str | None = None
    preference_key: str = Field(min_length=1)
    value: dict[str, Any]
    source: str | None = None
    expires_at: datetime | None = None


class MemoryFeedbackWriteRequest(BaseModel):
    scope: str = Field(min_length=1)
    scope_key: str | None = None
    feedback_key: str = Field(min_length=1)
    value: dict[str, Any]
    source: str | None = None
    expires_at: datetime | None = None


class MemorySearchRequest(BaseModel):
    keyword: str = Field(min_length=1)
    scopes: list[str] | None = None
    memory_type: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
