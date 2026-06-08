"""API v1 — AI 接口

端点:
  POST   /api/v1/ai/outline             — 生成大纲
  POST   /api/v1/ai/outline/stream      — 生成大纲 (SSE)
  POST   /api/v1/ai/polish              — 润色文本
  POST   /api/v1/ai/polish/stream       — 润色 (SSE)
  POST   /api/v1/ai/analyze             — 分析博客
  POST   /api/v1/ai/analyze/stream      — 分析 (SSE)
  POST   /api/v1/ai/recommend           — 推荐主题
  POST   /api/v1/ai/recommend/stream    — 推荐 (SSE)
  POST   /api/v1/ai/draft               — 生成文章
  POST   /api/v1/ai/draft/stream        — 生成文章 (SSE)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.api_schemas import ApiResponse, error, success
from core.error_codes import ErrorCode
from database import get_db
from services.agent_service import BlogAgent

router = APIRouter(prefix="/ai", tags=["AI API v1"])


def get_agent(db=Depends(get_db)) -> BlogAgent:
    return BlogAgent(db=db)


def _build_sse_json(type_: str, data: str | dict | None = None) -> str:
    payload = {"type": type_}
    if data is not None:
        payload["data"] = data
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse_stream(generator, meta: dict | None = None):
    try:
        if meta:
            yield _build_sse_json("meta", meta)
        buffer = ""
        async for chunk in generator:
            buffer += chunk
            if len(buffer) >= 64 or "\n" in buffer:
                yield _build_sse_json("content", buffer)
                buffer = ""
        if buffer:
            yield _build_sse_json("content", buffer)
        yield _build_sse_json("done")
    except Exception as exc:
        yield _build_sse_json("error", str(exc))


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

class OutlineRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="文章主题")
    style: str = Field(default="技术博客", description="写作风格")


class PolishRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待润色文本")
    tone: str = Field(default="专业", description="润色风格")


class RecommendRequest(BaseModel):
    tech_stack: str = Field(default="Python, FastAPI, SQLAlchemy", description="技术栈")


class DraftRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="文章主题")
    style: str = Field(default="技术博客", description="写作风格")


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------

@router.post("/outline", response_model=ApiResponse)
async def generate_outline(req: OutlineRequest, agent: BlogAgent = Depends(get_agent)):
    """生成文章大纲。"""
    try:
        result = await agent.generate_outline(topic=req.topic, style=req.style)
        return success({"data": result.data, "meta": result.meta})
    except Exception:
        return error(ErrorCode.LLM_SERVICE_ERROR, "AI 服务暂时不可用")


@router.post("/outline/stream")
async def generate_outline_stream(req: OutlineRequest, agent: BlogAgent = Depends(get_agent)):
    generator = agent.generate_outline_stream(topic=req.topic, style=req.style)
    return StreamingResponse(
        _sse_stream(generator, meta={"topic": req.topic, "style": req.style}),
        media_type="text/event-stream",
    )


@router.post("/polish", response_model=ApiResponse)
async def polish_text(req: PolishRequest, agent: BlogAgent = Depends(get_agent)):
    """润色文本。"""
    try:
        result = await agent.polish_text(text=req.text, tone=req.tone)
        return success({"data": result.data, "meta": result.meta})
    except Exception:
        return error(ErrorCode.LLM_SERVICE_ERROR, "AI 服务暂时不可用")


@router.post("/polish/stream")
async def polish_text_stream(req: PolishRequest, agent: BlogAgent = Depends(get_agent)):
    generator = agent.polish_text_stream(text=req.text, tone=req.tone)
    return StreamingResponse(_sse_stream(generator, meta={"tone": req.tone}), media_type="text/event-stream")


@router.post("/analyze", response_model=ApiResponse)
async def analyze_blog(agent: BlogAgent = Depends(get_agent)):
    """分析博客整体数据。"""
    try:
        result = await agent.analyze_blog()
        return success({"data": result.data, "meta": result.meta})
    except Exception:
        return error(ErrorCode.LLM_SERVICE_ERROR, "AI 服务暂时不可用")


@router.post("/analyze/stream")
async def analyze_blog_stream(agent: BlogAgent = Depends(get_agent)):
    generator = agent.analyze_blog_stream()
    return StreamingResponse(_sse_stream(generator), media_type="text/event-stream")


@router.post("/recommend", response_model=ApiResponse)
async def recommend_topics(req: RecommendRequest, agent: BlogAgent = Depends(get_agent)):
    """推荐技术文章主题。"""
    try:
        result = await agent.recommend_topics(tech_stack=req.tech_stack)
        return success({"data": result.data, "meta": result.meta})
    except Exception:
        return error(ErrorCode.LLM_SERVICE_ERROR, "AI 服务暂时不可用")


@router.post("/recommend/stream")
async def recommend_topics_stream(req: RecommendRequest, agent: BlogAgent = Depends(get_agent)):
    generator = agent.recommend_topics_stream(tech_stack=req.tech_stack)
    return StreamingResponse(
        _sse_stream(generator, meta={"tech_stack": req.tech_stack}),
        media_type="text/event-stream",
    )


@router.post("/draft", response_model=ApiResponse)
async def generate_draft(req: DraftRequest, agent: BlogAgent = Depends(get_agent)):
    """生成文章初稿。"""
    try:
        result = await agent.generate_draft(topic=req.topic, style=req.style)
        return success({"data": result.data, "meta": result.meta})
    except Exception:
        return error(ErrorCode.LLM_SERVICE_ERROR, "AI 服务暂时不可用")


@router.post("/draft/stream")
async def generate_draft_stream(req: DraftRequest, agent: BlogAgent = Depends(get_agent)):
    generator = agent.generate_draft_stream(topic=req.topic, style=req.style)
    return StreamingResponse(
        _sse_stream(generator, meta={"topic": req.topic, "style": req.style}),
        media_type="text/event-stream",
    )
