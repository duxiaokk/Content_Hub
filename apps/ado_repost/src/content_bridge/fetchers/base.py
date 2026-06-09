from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import TYPE_CHECKING, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import FetchRequest

if TYPE_CHECKING:
    from .incremental import CursorStore
    from .models import FetchBatch


class FetchError(RuntimeError):
    pass


class ParseError(ValueError):
    pass


class SupportsFetch(Protocol):
    source: str
    adapter_name: str

    def fetch(
        self,
        request: FetchRequest | None = None,
        cursor_store: "CursorStore | None" = None,
    ) -> "FetchBatch":
        ...


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    jitter_seconds: float = 0.2

    def next_delay(self, attempt: int) -> float:
        delay = min(self.base_delay_seconds * (2 ** max(attempt - 1, 0)), self.max_delay_seconds)
        return delay + random.uniform(0.0, self.jitter_seconds)


@dataclass(slots=True, frozen=True)
class RequestConfig:
    timeout_seconds: float = 15.0
    user_agent: str = "AdoRepostFetcher/0.1 (+https://example.invalid)"
    extra_headers: Mapping[str, str] = field(default_factory=dict)

    def to_headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent, "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, text/html;q=0.5"}
        headers.update(dict(self.extra_headers))
        return headers


@dataclass(slots=True)
class HttpClient:
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    request_config: RequestConfig = field(default_factory=RequestConfig)

    def get_text(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_policy.attempts + 1):
            try:
                request = Request(url, headers=self.request_config.to_headers(), method="GET")
                with urlopen(request, timeout=self.request_config.timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except (HTTPError, URLError, TimeoutError) as error:
                last_error = error
                if attempt >= self.retry_policy.attempts:
                    break
                time.sleep(self.retry_policy.next_delay(attempt))
        raise FetchError(f"failed to fetch {url}: {last_error}") from last_error


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    try:
        return ensure_utc(parsedate_to_datetime(text))
    except (TypeError, ValueError, IndexError):
        return None


def within_lookback(published_at: datetime | None, request: FetchRequest) -> bool:
    if published_at is None:
        return False
    cutoff = request.now.astimezone(timezone.utc) - timedelta(hours=request.lookback_hours)
    return ensure_utc(published_at) >= cutoff


def strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = unescape(value)
    result: list[str] = []
    inside_tag = False
    for char in text:
        if char == "<":
            inside_tag = True
            continue
        if char == ">":
            inside_tag = False
            continue
        if not inside_tag:
            result.append(char)
    cleaned = " ".join("".join(result).split())
    return cleaned or None


def derive_external_id(url: str, fallback: str) -> str:
    parsed = urlparse(url)
    candidate = parsed.path.rstrip("/").split("/")[-1]
    return candidate or fallback
