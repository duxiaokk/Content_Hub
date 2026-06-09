from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .base import HttpClient, ParseError, derive_external_id, parse_datetime, strip_html, within_lookback
from .incremental import CursorStore, build_cursor, is_new_item
from .models import FetchBatch, FetchCursor, FetchRequest, MediaAsset, UnifiedPost, utc_now

CONTENT_NAMESPACES = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


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
    seen: set[str] = set()
    unique_assets: list[MediaAsset] = []
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
    http_client: HttpClient = field(default_factory=HttpClient)

    def fetch(
        self,
        request: FetchRequest | None = None,
        cursor_store: CursorStore | None = None,
    ) -> FetchBatch:
        actual_request = request or FetchRequest()
        previous_cursor = cursor_store.load(self.stream_key) if cursor_store else None
        xml_text = self.http_client.get_text(self.feed_url)
        items = parse_rss_items(xml_text=xml_text, source=self.source, adapter=self.adapter_name)

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
                "feed_url": self.feed_url,
                "total_seen": len(items),
                "new_items": len(filtered_items),
            },
        )
