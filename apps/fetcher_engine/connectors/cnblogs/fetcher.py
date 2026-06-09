from __future__ import annotations

from fetcher_engine.runtime.base import BaseFetcher
from workflow_engine.registry.contracts import FetchRequest, SourceItem
from workflow_engine.runtime.legacy_paths import ensure_legacy_paths

ensure_legacy_paths()

from ado_repost.fetchers import RssFeedAdapter
from ado_repost.fetchers.models import FetchRequest as LegacyFetchRequest


class CNBlogsFetcher(BaseFetcher):
    name = "cnblogs"

    def __init__(self, feed_url: str | None = None, stream_key: str = "cnblogs:default") -> None:
        self.feed_url = feed_url or "https://feed.cnblogs.com/blog/u/126286/rss"
        self.stream_key = stream_key

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        adapter = RssFeedAdapter(
            source="cnblogs",
            adapter_name="cnblogs_rss",
            feed_url=self.feed_url,
            stream_key=self.stream_key,
        )
        batch = adapter.fetch(
            request=LegacyFetchRequest(lookback_hours=request.lookback_hours),
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
