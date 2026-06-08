from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentCreate(BaseModel):
    site_id: int
    agent_code: str = Field(min_length=1, max_length=64)
    agent_name: str = Field(min_length=1, max_length=64)
    persona: str = Field(min_length=1)
    tone: str = "friendly"
    model_name: str = Field(min_length=1, max_length=128)
    auto_reply_enabled: bool = True
    auto_article_comment_enabled: bool = True
    moderation_enabled: bool = True
    need_review: bool = False
    status: int = 1


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    agent_code: str
    agent_name: str
    persona: str
    tone: str
    model_name: str
    auto_reply_enabled: int
    auto_article_comment_enabled: int
    moderation_enabled: int
    need_review: int
    status: int
    created_at: datetime
    updated_at: datetime
