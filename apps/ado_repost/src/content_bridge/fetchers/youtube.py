from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode

from .base import FetchError, HttpClient, ParseError, parse_datetime, strip_html, within_lookback
from .incremental import CursorStore, build_cursor, is_new_item
from .models import FetchBatch, FetchRequest, MediaAsset, UnifiedPost, utc_now

YOUTUBE_WEB_URL = "https://www.youtube.com/channel/UCln9P4Qm3-EAY4aiEPmRwEA"
YOUTUBE_API_BASE_URL = "https://www.googleapis.com/youtube/v3"


def _build_api_url(path: str, **params: str | int) -> str:
    return f"{YOUTUBE_API_BASE_URL}/{path}?{urlencode(params)}"


@dataclass(slots=True)
class YouTubeAdapter:
    api_key: str | None = None
    channel_id: str = "UCln9P4Qm3-EAY4aiEPmRwEA"
    http_client: HttpClient = field(default_factory=HttpClient)
    source: str = field(init=False, default="youtube")
    adapter_name: str = field(init=False, default="youtube_data_api_v3")
    stream_key: str = field(init=False)

    def __post_init__(self) -> None:
        self.stream_key = f"youtube:{self.channel_id}"

    def fetch(
        self,
        request: FetchRequest | None = None,
        cursor_store: CursorStore | None = None,
    ) -> FetchBatch:
        if not self.api_key:
            raise FetchError("missing YouTube API key")

        actual_request = request or FetchRequest()
        previous_cursor = cursor_store.load(self.stream_key) if cursor_store else None
        uploads_playlist_id = self._fetch_uploads_playlist_id()
        items = self._fetch_recent_uploads(uploads_playlist_id)

        filtered_items = [
            item
            for item in items
            if within_lookback(item.published_at, actual_request) and is_new_item(item, previous_cursor)
        ]
        next_cursor = build_cursor(items, existing=previous_cursor)

        if cursor_store is not None:
            cursor_store.save(self.stream_key, next_cursor)

        return FetchBatch(
            source=self.source,
            adapter=self.adapter_name,
            fetched_at=utc_now(),
            items=tuple(filtered_items),
            cursor=next_cursor,
            metadata={
                "channel_id": self.channel_id,
                "uploads_playlist_id": uploads_playlist_id,
                "total_seen": len(items),
                "new_items": len(filtered_items),
            },
        )

    def _fetch_uploads_playlist_id(self) -> str:
        url = _build_api_url(
            "channels",
            part="contentDetails",
            id=self.channel_id,
            key=self.api_key or "",
        )
        payload = self._get_json(url)
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ParseError(f"missing channel content details for {self.channel_id}")
        related = items[0].get("contentDetails", {}).get("relatedPlaylists", {})
        uploads = related.get("uploads")
        if not uploads:
            raise ParseError(f"missing uploads playlist for {self.channel_id}")
        return str(uploads)

    def _fetch_recent_uploads(self, playlist_id: str) -> list[UnifiedPost]:
        url = _build_api_url(
            "playlistItems",
            part="snippet,contentDetails",
            playlistId=playlist_id,
            maxResults=50,
            key=self.api_key or "",
        )
        payload = self._get_json(url)
        items = payload.get("items")
        if not isinstance(items, list):
            raise ParseError(f"missing playlist items for {playlist_id}")

        posts: list[UnifiedPost] = []
        for entry in items:
            snippet = entry.get("snippet", {})
            resource = snippet.get("resourceId", {})
            video_id = resource.get("videoId") or entry.get("contentDetails", {}).get("videoId")
            published_text = snippet.get("publishedAt")
            published_at = parse_datetime(str(published_text)) if published_text else utc_now()
            if not video_id:
                continue
            if published_at is None:
                published_at = utc_now()
            title = str(snippet.get("title") or video_id)
            description = strip_html(snippet.get("description"))
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = None
            if isinstance(thumbnails, dict):
                for key in ("maxres", "standard", "high", "medium", "default"):
                    thumb = thumbnails.get(key)
                    if isinstance(thumb, dict) and thumb.get("url"):
                        thumbnail_url = str(thumb["url"])
                        break
            media = (MediaAsset(url=thumbnail_url, mime_type="image/jpeg"),) if thumbnail_url else ()
            posts.append(
                UnifiedPost(
                    source=self.source,
                    adapter=self.adapter_name,
                    external_id=str(video_id),
                    title=title,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    published_at=published_at,
                    summary=description,
                    media=media,
                    raw={
                        "channel_id": self.channel_id,
                        "playlist_id": playlist_id,
                        "video_id": str(video_id),
                    },
                )
            )

        posts.sort(key=lambda current: (current.published_at, current.external_id), reverse=True)
        return posts

    def _get_json(self, url: str) -> dict[str, object]:
        text = self.http_client.get_text(url)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"invalid YouTube API payload: {exc}") from exc
        if not isinstance(payload, dict):
            raise ParseError("unexpected YouTube API payload")
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or "YouTube API request failed"
            raise FetchError(str(message))
        return payload
