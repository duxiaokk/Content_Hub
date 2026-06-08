from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from schemas.ai import (
    AgentMarkdownResponse,
    ArticleDraftRequest,
    ArticleDraftResponse,
    DraftRequest,
    OutlineRequest,
    PolishRequest,
    RecommendRequest,
)
from services.agent_service import BlogAgent
from services.ai_services import generate_article_draft

router = APIRouter(prefix="/ai", tags=["AI"])


def get_agent(db: Session = Depends(get_db)) -> BlogAgent:
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


@router.post("/articles/draft", response_model=ArticleDraftResponse)
async def create_article_draft(request: ArticleDraftRequest):
    return await generate_article_draft(request)


@router.post("/outline", response_model=AgentMarkdownResponse)
async def generate_outline(
    req: OutlineRequest,
    agent: BlogAgent = Depends(get_agent),
) -> AgentMarkdownResponse:
    result = await agent.generate_outline(topic=req.topic, style=req.style)
    return AgentMarkdownResponse(data=result, meta={"topic": req.topic, "style": req.style})


@router.post("/outline/stream")
async def generate_outline_stream(
    req: OutlineRequest,
    agent: BlogAgent = Depends(get_agent),
):
    generator = agent.generate_outline_stream(topic=req.topic, style=req.style)
    return StreamingResponse(
        _sse_stream(generator, meta={"topic": req.topic, "style": req.style}),
        media_type="text/event-stream",
    )


@router.post("/polish", response_model=AgentMarkdownResponse)
async def polish_text(
    req: PolishRequest,
    agent: BlogAgent = Depends(get_agent),
) -> AgentMarkdownResponse:
    result = await agent.polish_text(text=req.text, tone=req.tone)
    return AgentMarkdownResponse(data=result, meta={"tone": req.tone})


@router.post("/polish/stream")
async def polish_text_stream(
    req: PolishRequest,
    agent: BlogAgent = Depends(get_agent),
):
    generator = agent.polish_text_stream(text=req.text, tone=req.tone)
    return StreamingResponse(
        _sse_stream(generator, meta={"tone": req.tone}),
        media_type="text/event-stream",
    )


@router.post("/analyze", response_model=AgentMarkdownResponse)
async def analyze_blog(
    agent: BlogAgent = Depends(get_agent),
) -> AgentMarkdownResponse:
    result = await agent.analyze_blog()
    return AgentMarkdownResponse(data=result)


@router.post("/analyze/stream")
async def analyze_blog_stream(
    agent: BlogAgent = Depends(get_agent),
):
    generator = agent.analyze_blog_stream()
    return StreamingResponse(
        _sse_stream(generator),
        media_type="text/event-stream",
    )


@router.post("/recommend", response_model=AgentMarkdownResponse)
async def recommend_topics(
    req: RecommendRequest,
    agent: BlogAgent = Depends(get_agent),
) -> AgentMarkdownResponse:
    result = await agent.recommend_topics(tech_stack=req.tech_stack)
    return AgentMarkdownResponse(data=result, meta={"tech_stack": req.tech_stack})


@router.post("/recommend/stream")
async def recommend_topics_stream(
    req: RecommendRequest,
    agent: BlogAgent = Depends(get_agent),
):
    generator = agent.recommend_topics_stream(tech_stack=req.tech_stack)
    return StreamingResponse(
        _sse_stream(generator, meta={"tech_stack": req.tech_stack}),
        media_type="text/event-stream",
    )


@router.post("/draft", response_model=AgentMarkdownResponse)
async def generate_draft(
    req: DraftRequest,
    agent: BlogAgent = Depends(get_agent),
) -> AgentMarkdownResponse:
    result = await agent.generate_draft(topic=req.topic, style=req.style)
    return AgentMarkdownResponse(data=result, meta={"topic": req.topic, "style": req.style})


@router.post("/draft/stream")
async def generate_draft_stream(
    req: DraftRequest,
    agent: BlogAgent = Depends(get_agent),
):
    generator = agent.generate_draft_stream(topic=req.topic, style=req.style)
    return StreamingResponse(
        _sse_stream(generator, meta={"topic": req.topic, "style": req.style}),
        media_type="text/event-stream",
    )
