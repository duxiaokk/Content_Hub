from __future__ import annotations

from dataclasses import dataclass

from .base import HttpClient
from .rss import RssFeedAdapter

INSTAGRAM_RSS_URL = "https://rsshub.app/picnob/user/ado_staff_official"
INSTAGRAM_WEB_URL = "https://www.instagram.com/ado_staff_official/"


@dataclass(slots=True)
class InstagramAdapter(RssFeedAdapter):
    def __init__(self, http_client: HttpClient | None = None) -> None:
        RssFeedAdapter.__init__(
            self,
            source="instagram",
            adapter_name="rsshub_picnob_user",
            feed_url=INSTAGRAM_RSS_URL,
            stream_key="instagram:ado_staff_official",
            http_client=http_client or HttpClient(),
        )
