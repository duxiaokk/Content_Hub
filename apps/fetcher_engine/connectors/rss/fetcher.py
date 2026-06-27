from __future__ import annotations

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.fetcher_engine.runtime.rss import RssFeedAdapter, RssFetchRequest
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


class RssFetcher(BaseFetcher):
    name = "rss"
    source_type = "rss"

    def __init__(self, feed_url: str, source_name: str, stream_key: str) -> None:
        self.feed_url = feed_url
        self.source_name = source_name
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        adapter = RssFeedAdapter(
            source=self.source_name,
            adapter_name="rss",
            feed_url=self.feed_url,
            stream_key=self.stream_key,
        )
        batch = await adapter.fetch(
            request=RssFetchRequest(
                lookback_hours=request.lookback_hours,
                limit=request.limit,
            ),
            cursor_store=None,
        )
        return [
            SourceItem(
                source_type=self.source_type,
                source_id=item.external_id,
                title=item.title,
                source_url=item.url,
                raw_content=item.summary,
                metadata={
                    "adapter": item.adapter,
                    "published_at": item.published_at.isoformat(),
                    "media": [asset.url for asset in item.media],
                    "source_name": self.source_name,
                    "feed_url": self.feed_url,
                    **dict(item.raw),
                },
            )
            for item in batch.items
        ]
