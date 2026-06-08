from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReplyTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    agent_id: int
    event_id: str
    source_type: str
    source_id: str
    article_id: str
    comment_id: str | None
    parent_comment_id: str | None
    trigger_reason: str
    task_status: str
    retry_count: int
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
