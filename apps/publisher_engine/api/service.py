from __future__ import annotations

from typing import Any

from apps.publisher_engine.adapters.blog.publisher import BlogPublisher
from apps.publisher_engine.adapters.markdown_export.publisher import MarkdownDigestPublisher
from apps.publisher_engine.runtime.models import PublishRequest


class PublishingService:
    def __init__(self) -> None:
        self._blog_publisher = BlogPublisher()
        self._digest_publisher = MarkdownDigestPublisher()

    async def generate_digest(self, items: list[dict[str, Any]], run_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._digest_publisher.publish(
            items,
            {
                **dict(options or {}),
                "run_id": run_id,
            },
        )

    async def publish_blog_draft(self, request: PublishRequest) -> dict[str, Any]:
        return (await self._blog_publisher.publish_draft(request)).to_dict()
