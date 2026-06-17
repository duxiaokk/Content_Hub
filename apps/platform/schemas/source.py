from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceSubscriptionCreate(BaseModel):
    source_type: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    account_identifier: str | None = None
    feed_url: str | None = None
    schedule_expression: str | None = None
    category: str | None = None
    default_tags: str | None = None


class SourceSubscriptionUpdate(BaseModel):
    source_name: str | None = Field(default=None, min_length=1)
    feed_url: str | None = None
    schedule_expression: str | None = None
    category: str | None = None
    default_tags: str | None = None


class SourceSubscriptionOut(BaseModel):
    id: int
    source_type: str
    source_name: str
    account_identifier: str | None = None
    feed_url: str | None = None
    enabled: bool
    category: str | None = None
    default_tags: str | None = None
    last_cursor: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
