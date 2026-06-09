from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        normalized: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                normalized.append(text)
        return normalized
    text = str(value).strip()
    return [text] if text else []


@dataclass(slots=True)
class DynamicItem:
    link: str
    title: str = ""
    content: str = ""
    source: str = ""
    author: str = ""
    published_at: str | None = None
    language: str | None = None
    tags: list[str] = field(default_factory=list)
    media_urls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DynamicItem":
        link = str(payload.get("link") or payload.get("url") or "").strip()
        if not link:
            raise ValueError("动态缺少 link/url 字段，无法参与去重。")

        consumed = {
            "link",
            "url",
            "title",
            "headline",
            "content",
            "text",
            "description",
            "source",
            "platform",
            "author",
            "published_at",
            "publishedAt",
            "date",
            "language",
            "lang",
            "tags",
            "media",
            "media_urls",
            "images",
        }

        return cls(
            link=link,
            title=str(payload.get("title") or payload.get("headline") or "").strip(),
            content=str(
                payload.get("content")
                or payload.get("text")
                or payload.get("description")
                or ""
            ).strip(),
            source=str(payload.get("source") or payload.get("platform") or "").strip(),
            author=str(payload.get("author") or "").strip(),
            published_at=str(
                payload.get("published_at")
                or payload.get("publishedAt")
                or payload.get("date")
                or ""
            ).strip()
            or None,
            language=str(payload.get("language") or payload.get("lang") or "").strip()
            or None,
            tags=_normalize_text_list(payload.get("tags")),
            media_urls=_normalize_text_list(
                payload.get("media_urls")
                or payload.get("media")
                or payload.get("images")
            ),
            metadata={key: value for key, value in payload.items() if key not in consumed},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HistoryRecord:
    dedup_key: str
    link: str
    title: str = ""
    source: str = ""
    published_at: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HistoryRecord":
        dedup_key = str(payload.get("dedup_key") or payload.get("link_md5") or "").strip()
        link = str(payload.get("link") or payload.get("url") or "").strip()
        if not dedup_key and not link:
            raise ValueError("历史记录缺少 dedup_key 与 link，无法识别。")
        return cls(
            dedup_key=dedup_key,
            link=link,
            title=str(payload.get("title") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            published_at=str(payload.get("published_at") or "").strip() or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProcessedItem:
    raw: DynamicItem
    dedup_key: str
    translated_title: str
    translated_content: str
    formatted_message: str


@dataclass(slots=True)
class ProcessBatch:
    latest_items: list[DynamicItem]
    new_items: list[ProcessedItem]
    updated_history: list[HistoryRecord]

    @property
    def messages(self) -> list[str]:
        return [item.formatted_message for item in self.new_items]
