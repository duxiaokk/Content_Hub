from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AIReplyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    prompt_snapshot: str
    reply_content: str
    reply_summary: str | None
    moderation_result: str
    moderation_reason: str | None
    publish_status: str
    published_comment_id: str | None
    token_input: int
    token_output: int
    model_name: str
    created_at: datetime
    updated_at: datetime


class ReviewQueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reply_id: int
    review_status: str
    reviewer: str | None
    review_comment: str | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReviewActionRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=64)
    review_comment: str | None = Field(default=None, max_length=255)
