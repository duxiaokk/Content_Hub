from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .models import FetchCursor, UnifiedPost


class CursorStore(Protocol):
    def load(self, stream: str) -> FetchCursor | None:
        ...

    def save(self, stream: str, cursor: FetchCursor) -> None:
        ...


class KeyValuePool(Protocol):
    def get(self, key: str) -> Any | None:
        ...

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
        persist: bool = True,
    ) -> None:
        ...


@dataclass(slots=True)
class InMemoryCursorStore:
    _state: dict[str, FetchCursor] | None = None

    def __post_init__(self) -> None:
        if self._state is None:
            self._state = {}

    def load(self, stream: str) -> FetchCursor | None:
        return self._state.get(stream)

    def save(self, stream: str, cursor: FetchCursor) -> None:
        self._state[stream] = cursor


@dataclass(slots=True)
class JsonCursorStore:
    file_path: Path

    def load(self, stream: str) -> FetchCursor | None:
        payload = self._read_all()
        record = payload.get(stream)
        if not record:
            return None
        published_at = record.get("latest_published_at")
        return FetchCursor(
            latest_published_at=datetime.fromisoformat(published_at) if published_at else None,
            latest_external_id=record.get("latest_external_id"),
        )

    def save(self, stream: str, cursor: FetchCursor) -> None:
        payload = self._read_all()
        payload[stream] = cursor.to_dict()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_all(self) -> dict[str, dict[str, str | None]]:
        if not self.file_path.exists():
            return {}
        raw = self.file_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}


@dataclass(slots=True)
class MemoryPoolCursorStore:
    pool: KeyValuePool
    key_prefix: str = "cursor:"

    def load(self, stream: str) -> FetchCursor | None:
        payload = self.pool.get(self.key_prefix + stream)
        if not isinstance(payload, dict):
            return None
        published_at = payload.get("latest_published_at")
        return FetchCursor(
            latest_published_at=datetime.fromisoformat(published_at) if published_at else None,
            latest_external_id=payload.get("latest_external_id"),
        )

    def save(self, stream: str, cursor: FetchCursor) -> None:
        self.pool.set(self.key_prefix + stream, cursor.to_dict(), ttl_seconds=None, persist=True)


def is_new_item(item: UnifiedPost, cursor: FetchCursor | None) -> bool:
    if cursor is None:
        return True
    if cursor.latest_published_at and item.published_at > cursor.latest_published_at:
        return True
    if (
        cursor.latest_published_at
        and item.published_at == cursor.latest_published_at
        and cursor.latest_external_id
        and item.external_id != cursor.latest_external_id
    ):
        return True
    return cursor.latest_published_at is None and cursor.latest_external_id != item.external_id


def build_cursor(items: list[UnifiedPost], existing: FetchCursor | None = None) -> FetchCursor:
    if not items:
        return existing or FetchCursor()
    newest = max(items, key=lambda item: (item.published_at, item.external_id))
    return FetchCursor(
        latest_published_at=newest.published_at,
        latest_external_id=newest.external_id,
    )
