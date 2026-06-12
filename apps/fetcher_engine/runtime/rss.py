from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


CONTENT_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


class ParseError(ValueError):
    pass


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts).strip()


@dataclass(slots=True)
class MediaAsset:
    url: str
    mime_type: str | None = None
    description: str | None = None


@dataclass(slots=True)
class UnifiedPost:
    source: str
    adapter: str
    external_id: str
    title: str
    url: str
    published_at: datetime
    summary: str | None
    media: tuple[MediaAsset, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RssFetchRequest:
    lookback_hours: int = 24
    limit: int = 20


@dataclass(slots=True)
class FetchBatch:
    source: str
    adapter: str
    fetched_at: datetime
    items: tuple[UnifiedPost, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    parser = _HTMLStripper()
    parser.feed(value)
    text = parser.get_text()
    return text or None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def derive_external_id(link: str, fallback: str) -> str:
    clean_link = (link or "").strip()
    if not clean_link:
        return fallback
    parsed = urlparse(clean_link)
    return parsed.path.rstrip("/") or parsed.netloc or fallback


def within_lookback(published_at: datetime, request: RssFetchRequest) -> bool:
    return published_at >= utc_now() - timedelta(hours=max(request.lookback_hours, 0))


def _node_text(node: ET.Element | None, *tags: str) -> str | None:
    if node is None:
        return None
    for tag in tags:
        child = node.find(tag, CONTENT_NAMESPACES)
        if child is not None and child.text:
            return child.text.strip()
    return None


def _iter_media(item: ET.Element) -> tuple[MediaAsset, ...]:
    assets: list[MediaAsset] = []
    for enclosure in item.findall("enclosure"):
        url = enclosure.attrib.get("url")
        if url:
            assets.append(
                MediaAsset(
                    url=url,
                    mime_type=enclosure.attrib.get("type"),
                    description=enclosure.attrib.get("length"),
                )
            )
    for media_node in item.findall("media:content", CONTENT_NAMESPACES):
        url = media_node.attrib.get("url")
        if url:
            assets.append(
                MediaAsset(
                    url=url,
                    mime_type=media_node.attrib.get("type"),
                    description=media_node.attrib.get("medium"),
                )
            )
    unique_assets: list[MediaAsset] = []
    seen: set[str] = set()
    for asset in assets:
        if asset.url in seen:
            continue
        seen.add(asset.url)
        unique_assets.append(asset)
    return tuple(unique_assets)


def parse_rss_items(xml_text: str, source: str, adapter: str) -> list[UnifiedPost]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ParseError(f"invalid rss payload for {source}: {error}") from error

    channel = root.find("channel")
    if channel is None:
        raise ParseError(f"missing channel node for {source}")

    parsed_items: list[UnifiedPost] = []
    for index, item in enumerate(channel.findall("item"), start=1):
        link = _node_text(item, "link") or ""
        title = _node_text(item, "title") or link or f"{source}-{index}"
        guid = _node_text(item, "guid") or derive_external_id(link, fallback=f"{source}-{index}")
        summary = (
            strip_html(_node_text(item, "description"))
            or strip_html(_node_text(item, "content:encoded", "{http://purl.org/rss/1.0/modules/content/}encoded"))
            or None
        )
        published_at = (
            parse_datetime(_node_text(item, "pubDate"))
            or parse_datetime(_node_text(item, "dc:date", "{http://purl.org/dc/elements/1.1/}date"))
            or utc_now()
        )
        parsed_items.append(
            UnifiedPost(
                source=source,
                adapter=adapter,
                external_id=guid,
                title=title,
                url=link,
                published_at=published_at,
                summary=summary,
                media=_iter_media(item),
                raw={
                    "guid": guid,
                    "author": _node_text(item, "author"),
                },
            )
        )
    parsed_items.sort(key=lambda current: (current.published_at, current.external_id), reverse=True)
    return parsed_items


@dataclass(slots=True)
class RssFeedAdapter:
    source: str
    adapter_name: str
    feed_url: str
    stream_key: str
    user_agent: str = "content-hub-fetcher/1.0"

    def fetch(self, request: RssFetchRequest | None = None, cursor_store: object | None = None) -> FetchBatch:
        del cursor_store
        actual_request = request or RssFetchRequest()
        http_request = Request(
            self.feed_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, text/html;q=0.5",
            },
        )
        try:
            with urlopen(http_request, timeout=30) as response:
                xml_text = response.read().decode("utf-8", errors="replace")
        except TimeoutError as error:
            raise RuntimeError(f"rss fetch timeout for {self.feed_url}") from error
        except HTTPError as error:
            raise RuntimeError(f"rss http error for {self.feed_url}: {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"rss network error for {self.feed_url}: {error.reason}") from error

        items = parse_rss_items(xml_text=xml_text, source=self.source, adapter=self.adapter_name)
        filtered_items = [item for item in items if within_lookback(item.published_at, actual_request)]
        if actual_request.limit > 0:
            filtered_items = filtered_items[: actual_request.limit]
        last_item = filtered_items[-1] if filtered_items else None
        return FetchBatch(
            source=self.source,
            adapter=self.adapter_name,
            fetched_at=utc_now(),
            items=tuple(filtered_items),
            metadata={
                "feed_url": self.feed_url,
                "total_seen": len(items),
                "new_items": len(filtered_items),
                "stream_key": self.stream_key,
                "cursor": last_item.published_at.isoformat() if last_item else None,
                "last_external_id": last_item.external_id if last_item else None,
            },
        )
