from __future__ import annotations

from typing import Any

from apps.publisher_engine.adapters.markdown_export.publisher import MarkdownDigestPublisher


class PublishingService:
    def __init__(self) -> None:
        self._digest_publisher = MarkdownDigestPublisher()

    async def generate_digest(self, items: list[dict[str, Any]], run_id: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._digest_publisher.publish(
            items,
            {
                **dict(options or {}),
                "run_id": run_id,
            },
        )
