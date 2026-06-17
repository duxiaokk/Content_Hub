from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


PipelineStage = Literal["fetch", "filter", "process", "review_prepare", "publish", "digest_generate"]
FallbackStrategy = Literal["skip", "raw", "retry"]


@dataclass(slots=True)
class SourceItem:
    source_type: str
    source_id: str
    title: str
    source_url: str | None = None
    raw_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContentAsset:
    content_id: int | None
    source_type: str
    source_id: str
    title: str
    raw_content: str | None = None
    processed_content: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchRequest:
    source_name: str
    lookback_hours: int = 24
    limit: int = 50
    cursor: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessContext:
    run_id: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessResult:
    content: ContentAsset
    status: str = "processed"
    warnings: list[str] = field(default_factory=list)
    cost_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FilterResult:
    items: list[ContentAsset]
    filtered_out: list[dict[str, Any]]
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewItem:
    content_item_id: int
    title: str
    original_url: str
    summary: str | None = None
    rewritten_title: str | None = None
    rewritten_content: str | None = None
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    status: str = "pending"


@dataclass(slots=True)
class DigestResult:
    digest_id: int
    title: str
    items_count: int
    markdown_content: str
    generated_at: str


@dataclass(slots=True)
class PublishTarget:
    target_name: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PublishResult:
    status: str
    target_name: str
    external_id: str | None = None
    url: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AIProcessorConfig:
    llm_provider: str
    model: str
    max_tokens_per_call: int
    timeout_seconds: int
    fallback_strategy: FallbackStrategy
    enable_cost_tracking: bool = True
    default_rewrite_profile: str = "zh_tech_blog"
    rewrite_score_threshold: float = 0.5


class Fetcher(Protocol):
    name: str

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        ...


class Processor(Protocol):
    name: str

    async def process(self, content: ContentAsset, context: ProcessContext) -> ProcessResult:
        ...


class Publisher(Protocol):
    name: str

    async def publish(self, content: ContentAsset, target: PublishTarget) -> PublishResult:
        ...
