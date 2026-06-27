from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from apps.workflow_engine.registry.contracts import SourceItem


@dataclass(slots=True)
class ValidationResult:
    accepted: bool
    reasons: list[str]


def validate_source_item(
    item: SourceItem,
    *,
    lookback_hours: int,
    rules: dict[str, Any] | None = None,
) -> ValidationResult:
    config = rules or {}
    reasons: list[str] = []

    if not str(item.source_id or "").strip():
        reasons.append("missing_source_id")
    if not str(item.title or "").strip():
        reasons.append("missing_title")

    require_source_url = bool(config.get("require_source_url", False))
    source_url = str(item.source_url or "").strip()
    if require_source_url and not source_url:
        reasons.append("missing_source_url")
    if source_url and not _is_valid_http_url(source_url):
        reasons.append("invalid_source_url")

    require_raw_content = bool(config.get("require_raw_content", False))
    raw_content = str(item.raw_content or "").strip()
    if require_raw_content and not raw_content:
        reasons.append("empty_raw_content")

    if item.metadata is not None and not isinstance(item.metadata, dict):
        reasons.append("malformed_metadata")

    if isinstance(item.metadata, dict):
        excluded_keywords = [str(v).strip().lower() for v in config.get("exclude_keywords", []) if str(v).strip()]
        haystacks = [str(item.title or "").lower(), raw_content.lower()]
        if excluded_keywords and any(keyword in haystack for keyword in excluded_keywords for haystack in haystacks):
            reasons.append("excluded_keyword")

        if bool(config.get("drop_stale", False)):
            published_at = _parse_timestamp(item.metadata.get("published_at"))
            if published_at is not None:
                allowed_age = timedelta(hours=max(lookback_hours, 1) * 2)
                if published_at < datetime.now(timezone.utc) - allowed_age:
                    reasons.append("stale_data")

    return ValidationResult(accepted=not reasons, reasons=reasons)


def _is_valid_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
