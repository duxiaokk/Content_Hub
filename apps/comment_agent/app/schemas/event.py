from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


EventType = Literal[
    "article.published",
    "article.updated",
    "comment.created",
    "comment.deleted",
    "comment.approved",
]


class SitePayload(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    url: HttpUrl


class ArticlePayload(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=128)
    url: HttpUrl
    tags: list[str] = Field(default_factory=list)
    published_at: datetime | None = None


class CommentPayload(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=128)
    parent_id: str | None = Field(default=None, max_length=128)
    created_at: datetime | None = None


class EventRequest(BaseModel):
    event: EventType
    timestamp: datetime
    signature: str = Field(min_length=1)
    site: SitePayload
    article: ArticlePayload | None = None
    comment: CommentPayload | None = None


class EventAcceptData(BaseModel):
    event_id: str
    task_id: int | None = None
    status: str
