from __future__ import annotations

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.fetcher_engine.runtime.rss import RssFeedAdapter, RssFetchRequest
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


class BilibiliFetcher(BaseFetcher):
    name = "bilibili"

    def __init__(self, feed_url: str | None = None, stream_key: str = "bilibili:default") -> None:
        self.feed_url = feed_url or "https://rsshub.app/bilibili/user/video/2267573"
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        adapter = RssFeedAdapter(
            source="bilibili",
            adapter_name="bilibili_rss",
            feed_url=self.feed_url,
            stream_key=self.stream_key,
        )
        batch = adapter.fetch(
            request=RssFetchRequest(lookback_hours=request.lookback_hours),
            cursor_store=None,
        )
        return [
            SourceItem(
                source_type=item.source,
                source_id=item.external_id,
                title=item.title,
                source_url=item.url,
                raw_content=item.summary,
                metadata={
                    "adapter": item.adapter,
                    "published_at": item.published_at.isoformat(),
                    "media": [asset.url for asset in item.media],
                    **dict(item.raw),
                },
            )
            for item in batch.items
        ]
