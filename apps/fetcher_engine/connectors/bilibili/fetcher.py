from __future__ import annotations

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.fetcher_engine.runtime.rss import RssFeedAdapter, RssFetchRequest
from apps.fetcher_engine.runtime.rss import UnifiedPost
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


class BilibiliFetcher(BaseFetcher):
    name = "bilibili"
    source_type = "bilibili"

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
        return [self._to_source_item(item) for item in batch.items]

    def _to_source_item(self, item: UnifiedPost) -> SourceItem:
        raw = dict(item.raw)
        summary = self._build_summary(item.summary)
        author = self._first_non_empty(raw.get("author"), raw.get("up_name"), raw.get("uploader"))
        source_url = self._build_video_url(item.url, raw)
        cover_url = self._first_non_empty(raw.get("cover_url"), raw.get("cover"), *(asset.url for asset in item.media))
        return SourceItem(
            source_type=self.source_type,
            source_id=item.external_id,
            title=item.title,
            source_url=source_url,
            raw_content=summary,
            metadata={
                "adapter": item.adapter,
                "source_account": author,
                "published_at": item.published_at.isoformat(),
                "summary": summary,
                "url": source_url,
                "author": author,
                "play_count": raw.get("play_count"),
                "danmaku_count": raw.get("danmaku_count"),
                "duration": raw.get("duration"),
                "cover_url": cover_url,
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

    def _build_video_url(self, original_url: str, raw: dict[str, object]) -> str:
        bvid = self._first_non_empty(raw.get("bvid"), raw.get("video_id"))
        if bvid:
            return f"https://www.bilibili.com/video/{bvid}"
        return original_url

    def _first_non_empty(self, *values: object) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
