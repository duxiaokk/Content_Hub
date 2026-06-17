from __future__ import annotations

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.fetcher_engine.runtime.rss import RssFeedAdapter, RssFetchRequest
from apps.fetcher_engine.runtime.rss import UnifiedPost
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


class CNBlogsFetcher(BaseFetcher):
    name = "cnblogs"
    source_type = "cnblogs"

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
            request=RssFetchRequest(lookback_hours=request.lookback_hours),
            cursor_store=None,
        )
        return [self._to_source_item(item) for item in batch.items]

    def _to_source_item(self, item: UnifiedPost) -> SourceItem:
        raw = dict(item.raw)
        summary = self._build_summary(item.summary)
        author = self._first_non_empty(raw.get("author"), raw.get("creator"), raw.get("dc_creator"))
        category = self._first_non_empty(raw.get("category"), raw.get("categories"))
        return SourceItem(
            source_type=self.source_type,
            source_id=item.external_id,
            title=item.title,
            source_url=item.url,
            raw_content=summary,
            metadata={
                "adapter": item.adapter,
                "source_account": author,
                "published_at": item.published_at.isoformat(),
                "summary": summary,
                "url": item.url,
                "author": author,
                "category": category,
                "view_count": raw.get("view_count"),
                "media": [asset.url for asset in item.media],
                **raw,
            },
        )

    def _build_summary(self, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized[:300]

    def _first_non_empty(self, *values: object) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
