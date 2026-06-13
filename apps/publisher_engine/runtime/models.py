from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DraftPayload:
    title: str
    summary: str | None
    markdown_content: str
    source_platform: str
    source_link: str
    source_external_id: str | None = None
    source_dedup_key: str | None = None
    source_published_at: str | None = None
    cover_image_url: str | None = None
    tags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "markdown_content": self.markdown_content,
            "source_platform": self.source_platform,
            "source_link": self.source_link,
            "source_external_id": self.source_external_id,
            "source_dedup_key": self.source_dedup_key,
            "source_published_at": self.source_published_at,
            "cover_image_url": self.cover_image_url,
            "tags": list(self.tags),
            "raw_payload": dict(self.raw_payload),
        }


@dataclass(slots=True)
class DigestPublishResult:
    title: str
    content_markdown: str
    file_path: str
    included_count: int
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "content_markdown": self.content_markdown,
            "file_path": self.file_path,
            "included_count": self.included_count,
            "generated_at": self.generated_at,
        }
