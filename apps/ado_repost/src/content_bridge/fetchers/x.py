from __future__ import annotations

from dataclasses import dataclass

from .base import HttpClient
from .rss import RssFeedAdapter

X_RSS_URL = "https://rsshub.app/twitter/user/Ado_staff"
X_WEB_URL = "https://x.com/Ado_staff"


@dataclass(slots=True)
class XAdapter(RssFeedAdapter):
    def __init__(self, http_client: HttpClient | None = None) -> None:
        super().__init__(
            source="x",
            adapter_name="rsshub_twitter_user",
            feed_url=X_RSS_URL,
            stream_key="x:ado_staff",
            http_client=http_client or HttpClient(),
        )
