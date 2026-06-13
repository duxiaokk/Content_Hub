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


@dataclass(slots=True)
class PublishRequest:
    content_item_id: int
    candidate_title: str
    candidate_content: str
    target_type: str
    source_url: str | None = None
    tags: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_item_id": self.content_item_id,
            "candidate_title": self.candidate_title,
            "candidate_content": self.candidate_content,
            "target_type": self.target_type,
            "source_url": self.source_url,
            "tags": list(self.tags),
            "options": dict(self.options),
        }


@dataclass(slots=True)
class PublishResponse:
    content_item_id: int
    target_type: str
    status: str
    external_url: str | None
    external_id: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_item_id": self.content_item_id,
            "target_type": self.target_type,
            "status": self.status,
            "external_url": self.external_url,
            "external_id": self.external_id,
            "message": self.message,
        }
