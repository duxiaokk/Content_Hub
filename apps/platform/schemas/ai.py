from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class ArticleDraftRequest(BaseModel):
    topic: str
    style: str = "技术文章"
    tags: List[str] = Field(default_factory=list)


class ArticleDraftResponse(BaseModel):
    title: str
    summary: str
    content: str
    draft_id: int | None = None


class OutlineRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200, description="文章主题")
    style: Literal["tutorial", "opinion", "review", "deep_dive"] = Field(
        default="tutorial", description="写作风格"
    )


class PolishRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=8000, description="待润色的原始文本")
    tone: Literal["professional", "casual", "technical"] = Field(
        default="professional", description="语气风格"
    )


class RecommendRequest(BaseModel):
    tech_stack: str | None = Field(
        default=None,
        description="自定义技术栈，不传则使用项目默认值",
    )


class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200, description="文章主题")
    style: Literal["tutorial", "opinion", "review", "deep_dive"] = Field(
        default="tutorial", description="写作风格"
    )


class AgentMarkdownResponse(BaseModel):
    success: bool = True
    data: str = Field(..., description="LLM 返回的 Markdown 内容")
    meta: dict = Field(default_factory=dict, description="额外元信息")
