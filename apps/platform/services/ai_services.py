"""
业务逻辑: 生成文章草稿的占位实现。
后续接入真实 LLM 时, 只需要替换这里的实现即可。
"""

from schemas.ai import ArticleDraftRequest, ArticleDraftResponse


async def generate_article_draft(request: ArticleDraftRequest) -> ArticleDraftResponse:
    return ArticleDraftResponse(
        title=f"{request.topic} — {request.style}",
        summary=f"关于 {request.topic} 的 {request.style} 风格案例摘要。",
        content=f"关于 {request.topic} 的 {request.style} 风格案例内容。",
        draft_id=None,
    )
