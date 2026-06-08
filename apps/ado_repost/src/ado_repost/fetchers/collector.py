from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timezone

from ado_repost.config import FetchersSettings

from .base import FetchError, ParseError, ensure_utc
from .base import SupportsFetch
from .incremental import CursorStore
from .instagram import InstagramAdapter
from .models import FetchBatch, FetchCursor, FetchRequest, utc_now
from .x import XAdapter
from .youtube import YouTubeAdapter


@dataclass(slots=True)
class FetchOrchestrator:
    settings: FetchersSettings = field(default_factory=FetchersSettings)
    adapters: tuple[SupportsFetch, ...] = field(
        init=False
    )

    def __post_init__(self) -> None:
        adapters: list[SupportsFetch] = []
        if self.settings.x_enabled:
            adapters.append(XAdapter())
        if self.settings.youtube_enabled:
            adapters.append(
                YouTubeAdapter(
                    api_key=self.settings.youtube_api_key,
                    channel_id=self.settings.youtube_channel_id,
                )
            )
        if self.settings.instagram_enabled:
            adapters.append(InstagramAdapter())
        self.adapters = tuple(adapters)

    def fetch_all(
        self,
        request: FetchRequest | None = None,
        cursor_store: CursorStore | None = None,
    ) -> tuple[FetchBatch, ...]:
        actual_request = request or FetchRequest()
        batches: list[FetchBatch] = []
        for adapter in self.adapters:
            try:
                batches.append(adapter.fetch(request=actual_request, cursor_store=cursor_store))
            except (FetchError, ParseError, TimeoutError, ValueError) as exc:
                batches.append(
                    FetchBatch(
                        source=adapter.source,
                        adapter=adapter.adapter_name,
                        fetched_at=utc_now(),
                        items=(),
                        cursor=FetchCursor(),
                        metadata={
                            "error": str(exc),
                            "failed": True,
                            "new_items": 0,
                            "total_seen": 0,
                            "failed_at": ensure_utc(actual_request.now).astimezone(
                                timezone.utc
                            ).isoformat(),
                        },
                    )
                )
        return tuple(batches)
