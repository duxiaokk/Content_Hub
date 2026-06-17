from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


def _utc_from_timestamp(timestamp: float | int | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()


class RedditFetcher(BaseFetcher):
    name = "reddit"
    source_type = "reddit"
    user_agent = "content-hub-fetcher/1.0"

    def __init__(self, subreddit: str = "artificial", sort: str = "hot", limit: int = 25, stream_key: str = "") -> None:
        self.subreddit = self._normalize_subreddit(subreddit or self._subreddit_from_stream(stream_key))
        self.sort = sort or "hot"
        self.limit = limit
        self.stream_key = stream_key or f"reddit:{self.subreddit}"

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        try:
            payload = self._fetch_posts_payload(request_limit=request.limit)
        except RuntimeError:
            return []

        posts = payload.get("data", {}).get("children", [])
        items: list[SourceItem] = []
        max_items = request.limit if request.limit > 0 else self.limit

        for child in posts:
            post_data = child.get("data", {}) if isinstance(child, dict) else {}
            item = self._to_source_item(post_data)
            if item is None:
                continue
            items.append(item)
            if max_items > 0 and len(items) >= max_items:
                break

        return items

    def _build_url(self, request_limit: int) -> str:
        effective_limit = request_limit if request_limit > 0 else self.limit
        query = urlencode({"limit": effective_limit})
        return f"https://www.reddit.com/r/{self.subreddit}/{self.sort}.json?{query}"

    def _fetch_posts_payload(self, request_limit: int) -> dict[str, Any]:
        url = self._build_url(request_limit=request_limit)
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except HTTPError as error:
            if error.code == 404:
                raise RuntimeError("reddit subreddit not found") from error
            raise RuntimeError(f"reddit http error: {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"reddit network error: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("reddit request timeout") from error
        except json.JSONDecodeError as error:
            raise RuntimeError("reddit invalid json payload") from error

    def _to_source_item(self, post_data: dict[str, Any]) -> SourceItem | None:
        post_id = str(post_data.get("name") or "").strip()
        permalink = str(post_data.get("permalink") or "").strip()
        title = str(post_data.get("title") or "").strip()
        if not post_id or not permalink or not title:
            return None

        summary = str(post_data.get("selftext") or "").strip()
        if summary:
            summary = summary[:500]
        else:
            summary = None

        return SourceItem(
            source_type=self.source_type,
            source_id=post_id,
            title=title,
            source_url=f"https://www.reddit.com{permalink}",
            raw_content=summary,
            metadata={
                "published_at": _utc_from_timestamp(post_data.get("created_utc")),
                "subreddit": post_data.get("subreddit") or self.subreddit,
                "author": post_data.get("author"),
                "score": post_data.get("score"),
                "num_comments": post_data.get("num_comments"),
                "ups": post_data.get("ups"),
                "post_url": post_data.get("url"),
                "sort": self.sort,
                "stream_key": self.stream_key,
            },
        )

    def _normalize_subreddit(self, subreddit: str) -> str:
        normalized = subreddit.strip()
        if normalized.startswith("/r/"):
            normalized = normalized[3:]
        elif normalized.startswith("r/"):
            normalized = normalized[2:]
        return normalized.strip("/")

    def _subreddit_from_stream(self, stream_key: str) -> str:
        normalized = stream_key.strip()
        if normalized.startswith("reddit:"):
            return normalized.split(":", 1)[1]
        return normalized or "artificial"
