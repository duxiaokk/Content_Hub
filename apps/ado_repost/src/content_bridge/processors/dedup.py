from __future__ import annotations

import hashlib
from typing import Iterable

from content_bridge.schema import DynamicItem, HistoryRecord


def link_md5(link: str) -> str:
    normalized = link.strip()
    if not normalized:
        raise ValueError("link 涓嶈兘涓虹┖锛屾棤娉曠敓鎴?MD5銆?)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


class LinkDeduplicator:
    """鍩轰簬閾炬帴 MD5 鐨勫幓閲嶅櫒锛屽悓鏃跺鐞嗗巻鍙茶褰曚笌鏈鎵规鍐呴噸澶嶃€?""

    def __init__(self, history_records: Iterable[HistoryRecord] | None = None) -> None:
        self._seen_keys: set[str] = set()
        if history_records:
            for record in history_records:
                self.mark_seen(record.link, dedup_key=record.dedup_key or None)

    @property
    def seen_keys(self) -> set[str]:
        return set(self._seen_keys)

    def mark_seen(self, link: str, *, dedup_key: str | None = None) -> str:
        key = dedup_key or link_md5(link)
        self._seen_keys.add(key)
        return key

    def is_duplicate(self, item: DynamicItem) -> bool:
        return link_md5(item.link) in self._seen_keys

    def filter_new_items(self, items: Iterable[DynamicItem]) -> list[DynamicItem]:
        fresh_items: list[DynamicItem] = []
        for item in items:
            key = link_md5(item.link)
            if key in self._seen_keys:
                continue
            self._seen_keys.add(key)
            fresh_items.append(item)
        return fresh_items

    def build_history_records(self, items: Iterable[DynamicItem]) -> list[HistoryRecord]:
        records: list[HistoryRecord] = []
        for item in items:
            records.append(
                HistoryRecord(
                    dedup_key=link_md5(item.link),
                    link=item.link,
                    title=item.title,
                    source=item.source,
                    published_at=item.published_at,
                )
            )
        return records

