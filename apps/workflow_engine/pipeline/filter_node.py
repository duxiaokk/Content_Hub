from __future__ import annotations

import os
from typing import Any

from apps.workflow_engine.registry.contracts import ContentAsset, FilterResult


class FilterNode:
    async def apply(self, items: list[ContentAsset], filter_config: dict[str, Any]) -> FilterResult:
        include_keywords = self._normalize_keywords(
            filter_config.get("include_keywords") or os.getenv("CONTENT_HUB_FILTER_KEYWORDS", "")
        )
        exclude_keywords = self._normalize_keywords(
            filter_config.get("exclude_keywords") or os.getenv("CONTENT_HUB_FILTER_EXCLUDE_KEYWORDS", "")
        )

        kept_items: list[ContentAsset] = []
        filtered_out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for item in items:
            dedup_key = (item.source_type, item.source_id)
            haystack = f"{item.title} {item.raw_content or ''}".lower()

            if dedup_key in seen:
                filtered_out.append({"source_id": item.source_id, "reason": "duplicate"})
                continue
            if include_keywords and not any(keyword in haystack for keyword in include_keywords):
                filtered_out.append({"source_id": item.source_id, "reason": "keyword_not_included"})
                continue
            if exclude_keywords and any(keyword in haystack for keyword in exclude_keywords):
                filtered_out.append({"source_id": item.source_id, "reason": "keyword_excluded"})
                continue

            seen.add(dedup_key)
            kept_items.append(item)

        return FilterResult(
            items=kept_items,
            filtered_out=filtered_out,
            stats={
                "input_count": len(items),
                "kept_count": len(kept_items),
                "filtered_count": len(filtered_out),
            },
        )

    def _normalize_keywords(self, raw: str | list[str]) -> list[str]:
        if isinstance(raw, list):
            return [item.strip().lower() for item in raw if isinstance(item, str) and item.strip()]
        if not raw:
            return []
        return [item.strip().lower() for item in str(raw).split(",") if item.strip()]
