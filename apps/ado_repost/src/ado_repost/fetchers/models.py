from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class MediaAsset:
    url: str
    mime_type: str | None = None
    description: str | None = None


@dataclass(slots=True, frozen=True)
class UnifiedPost:
    source: str
    adapter: str
    external_id: str
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    media: tuple[MediaAsset, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "adapter": self.adapter,
            "external_id": self.external_id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.astimezone(timezone.utc).isoformat(),
            "summary": self.summary,
            "media": [
                {
                    "url": asset.url,
                    "mime_type": asset.mime_type,
                    "description": asset.description,
                }
                for asset in self.media
            ],
            "raw": dict(self.raw),
        }


@dataclass(slots=True, frozen=True)
class FetchCursor:
    latest_published_at: datetime | None = None
    latest_external_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "latest_published_at": (
                self.latest_published_at.astimezone(timezone.utc).isoformat()
                if self.latest_published_at
                else None
            ),
            "latest_external_id": self.latest_external_id,
        }


@dataclass(slots=True, frozen=True)
class FetchBatch:
    source: str
    adapter: str
    fetched_at: datetime
    items: tuple[UnifiedPost, ...]
    cursor: FetchCursor
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "adapter": self.adapter,
            "fetched_at": self.fetched_at.astimezone(timezone.utc).isoformat(),
            "items": [item.to_dict() for item in self.items],
            "cursor": self.cursor.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class FetchRequest:
    now: datetime = field(default_factory=utc_now)
    lookback_hours: int = 24

    @property
    def since(self) -> datetime:
        return (
            self.now.astimezone(timezone.utc) - timedelta(hours=self.lookback_hours)
        ).replace(microsecond=0)
