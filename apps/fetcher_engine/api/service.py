from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from apps.fetcher_engine.api.models import (
    FetchAlertEvent,
    FetchBatchError,
    FetchBatchRequest,
    FetchBatchResult,
    FetchBatchStats,
    FetchSourceStat,
    FetchValidationIssue,
)
from apps.fetcher_engine.api.retry import RetryOutcome, retry_async
from apps.fetcher_engine.api.validation import validate_source_item
from apps.fetcher_engine.api.registry import get_fetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


logger = logging.getLogger(__name__)


class FetchService:
    def __init__(self, db_session: Session, source_repo: Any) -> None:
        self.db_session = db_session
        self.source_repo = source_repo

    async def run_sources(self, request: FetchBatchRequest) -> FetchBatchResult:
        subscriptions = self._load_subscriptions(request.sources, request.subscription_ids)
        result_items: list[dict[str, Any]] = []
        matched_items: list[dict[str, Any]] = []
        result_errors: list[FetchBatchError] = []
        validation_issues: list[FetchValidationIssue] = []
        alert_events: list[FetchAlertEvent] = []
        source_stats: list[FetchSourceStat] = []
        checkpoints: dict[str, dict[str, Any]] = {}
        seen_keys: set[tuple[str, str]] = set()
        total_fetched = 0
        total_inserted = 0
        total_deduped = 0
        total_validated = 0
        total_invalid = 0
        total_retried = 0
        sources_succeeded = 0
        sources_failed = 0

        for subscription in subscriptions:
            source_type = subscription.source_type
            fetcher_factory = get_fetcher(source_type)
            started_at = perf_counter()
            source_options = self._build_source_options(subscription, request.options)
            previous_cursor = getattr(subscription, "last_cursor", None)
            if fetcher_factory is None:
                result_errors.append(
                    FetchBatchError(
                        source=source_type,
                        error=f"fetcher not registered for source_type={source_type}",
                        traceback=None,
                    )
                )
                sources_failed += 1
                alert_events.append(
                    FetchAlertEvent(
                        source=source_type,
                        alert_type="fetcher_missing",
                        severity="critical",
                        message=f"Fetcher not registered for source_type={source_type}",
                    )
                )
                source_stats.append(
                    FetchSourceStat(
                        source=source_type,
                        status="failure",
                        elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
                        previous_cursor=previous_cursor,
                        resume_cursor=previous_cursor,
                    )
                )
                continue

            retry_outcome = RetryOutcome()
            try:
                fetcher = self._build_fetcher(fetcher_factory, subscription)
                source_items, retry_outcome = await retry_async(
                    lambda: fetcher.fetch(
                        FetchRequest(
                            source_name=getattr(subscription, "name", None)
                            or getattr(subscription, "source_name", None)
                            or "",
                            lookback_hours=request.lookback_hours,
                            limit=request.limit_per_source,
                            cursor=previous_cursor,
                            options=source_options,
                        )
                    ),
                    max_retries=self._to_int(source_options.get("retry_times"), 0),
                    backoff_seconds=self._to_float(source_options.get("retry_backoff_seconds"), 0.0),
                )
            except Exception as exc:
                sources_failed += 1
                total_retried += retry_outcome.retries
                error_traceback = traceback.format_exc()
                result_errors.append(
                    FetchBatchError(
                        source=source_type,
                        error=str(exc),
                        traceback=error_traceback,
                    )
                )
                logger.exception(
                    "Fetch source failed",
                    extra={
                        "run_id": request.run_id,
                        "source_type": source_type,
                        "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                    },
                )
                alert_events.append(
                    FetchAlertEvent(
                        source=source_type,
                        alert_type="source_unavailable",
                        severity="critical",
                        message=str(exc),
                        payload={
                            "retry_count": retry_outcome.retries,
                            "run_id": request.run_id,
                        },
                    )
                )
                source_stats.append(
                    FetchSourceStat(
                        source=source_type,
                        status="failure",
                        retried_count=retry_outcome.retries,
                        elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
                        previous_cursor=previous_cursor,
                        resume_cursor=previous_cursor,
                    )
                )
                continue

            valid_items, source_validation_issues = self._validate_source_items(
                source_type=source_type,
                source_items=source_items,
                lookback_hours=request.lookback_hours,
                validation_rules=self._resolve_validation_rules(source_options),
            )
            validation_issues.extend(source_validation_issues)
            total_validated += len(valid_items)
            total_invalid += len(source_validation_issues)
            total_retried += retry_outcome.retries

            invalid_ratio = len(source_validation_issues) / max(len(source_items), 1)
            if invalid_ratio >= self._to_float(source_options.get("invalid_alert_threshold"), 0.5):
                alert_events.append(
                    FetchAlertEvent(
                        source=source_type,
                        alert_type="invalid_ratio_high",
                        severity="warning",
                        message=f"Invalid ratio too high: {len(source_validation_issues)}/{len(source_items)}",
                        payload={
                            "invalid_count": len(source_validation_issues),
                            "fetched_count": len(source_items),
                        },
                    )
                )

            incremental_items = self._filter_incremental_items(valid_items, previous_cursor)
            total_fetched += len(incremental_items)
            self._update_cursor(subscription, incremental_items)
            unique_items, deduped_count = self._dedupe_source_items(incremental_items, seen_keys)
            total_deduped += deduped_count
            sources_succeeded += 1
            next_cursor = self._build_cursor_value(incremental_items[0]) if incremental_items else previous_cursor
            checkpoints[source_type] = {
                "previous_cursor": previous_cursor,
                "next_cursor": next_cursor,
                "resume_cursor": next_cursor or previous_cursor,
            }

            inserted_for_source = 0
            for item in unique_items:
                matched_items.append(
                    {
                        "source_type": item.source_type,
                        "source_id": item.source_id,
                        "source_url": item.source_url,
                        "title": item.title,
                    }
                )
                if self._content_exists(item.source_type, item.source_id):
                    total_deduped += 1
                    continue
                content_item = self.source_repo.create_content_item(
                    self.db_session,
                    source_type=item.source_type,
                    source_id=item.source_id,
                    source_account=getattr(subscription, "account_identifier", None),
                    source_url=item.source_url,
                    title=item.title,
                    raw_content=item.raw_content,
                    summary=item.raw_content,
                    tags_json=self._serialize_tags(getattr(subscription, "default_tags", None)),
                    language="zh",
                    pipeline_status="fetched",
                    review_status="pending",
                    metadata_json=self._serialize_metadata(item.metadata),
                )
                result_items.append(self._serialize_content_item(content_item, item.metadata))
                total_inserted += 1
                inserted_for_source += 1

            if retry_outcome.retries > 0:
                alert_events.append(
                    FetchAlertEvent(
                        source=source_type,
                        alert_type="network_retry_recovered",
                        severity="info",
                        message=f"Fetch succeeded after {retry_outcome.retries} retries",
                        payload={"retry_count": retry_outcome.retries},
                    )
                )
            if not incremental_items and bool(source_options.get("alert_on_empty", False)):
                alert_events.append(
                    FetchAlertEvent(
                        source=source_type,
                        alert_type="empty_result",
                        severity="warning",
                        message="Fetch completed with zero incremental items",
                    )
                )

            logger.info(
                "Fetch source completed",
                extra={
                    "run_id": request.run_id,
                    "source_type": source_type,
                    "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                    "fetched_count": len(incremental_items),
                    "inserted_count": total_inserted,
                    "invalid_count": len(source_validation_issues),
                    "retry_count": retry_outcome.retries,
                },
            )
            source_stats.append(
                FetchSourceStat(
                    source=source_type,
                    status="success",
                    fetched_count=len(incremental_items),
                    inserted_count=inserted_for_source,
                    deduped_count=deduped_count,
                    invalid_count=len(source_validation_issues),
                    retried_count=retry_outcome.retries,
                    elapsed_ms=round((perf_counter() - started_at) * 1000, 2),
                    previous_cursor=previous_cursor,
                    next_cursor=next_cursor,
                    resume_cursor=next_cursor or previous_cursor,
                )
            )

        return FetchBatchResult(
            run_id=request.run_id,
            items=result_items,
            matched_items=matched_items,
            errors=result_errors,
            validation_issues=validation_issues,
            alerts=alert_events,
            source_stats=source_stats,
            checkpoints=checkpoints,
            stats=FetchBatchStats(
                total_fetched=total_fetched,
                total_inserted=total_inserted,
                total_deduped=total_deduped,
                total_validated=total_validated,
                total_invalid=total_invalid,
                total_retried=total_retried,
                total_alerts=len(alert_events),
                sources_succeeded=sources_succeeded,
                sources_failed=sources_failed,
            ),
        )

    def _load_subscriptions(self, sources: list[str], subscription_ids: list[int] | None = None) -> list[Any]:
        load_subscriptions = getattr(self.source_repo, "load_subscriptions", None)
        if callable(load_subscriptions):
            return list(load_subscriptions(self.db_session, sources=sources, subscription_ids=subscription_ids or []))

        query = self.db_session.query(self.source_repo.SourceSubscription).filter(
            self.source_repo.SourceSubscription.enabled.is_(True)
        )
        if subscription_ids:
            query = query.filter(self.source_repo.SourceSubscription.id.in_(subscription_ids))
        if sources:
            query = query.filter(self.source_repo.SourceSubscription.source_type.in_(sources))
        return list(query.order_by(self.source_repo.SourceSubscription.id.asc()).all())

    def _build_fetcher(self, fetcher_factory: Any, subscription: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if getattr(subscription, "feed_url", None):
            kwargs["feed_url"] = subscription.feed_url
        # 兼容测试中的 source_name 和实际模型中的 name
        source_name = getattr(subscription, "name", None) or getattr(subscription, "source_name", None)
        if source_name:
            kwargs["source_name"] = source_name
        # 从 config 或 config_json 中读取通用参数（如 xiaohongshu 的 urls）
        config = getattr(subscription, "config", None)
        if config is None and hasattr(subscription, "config_json"):
            import json
            try:
                config = json.loads(subscription.config_json)
            except (json.JSONDecodeError, TypeError):
                config = None
        if isinstance(config, dict):
            if "urls" in config:
                kwargs["urls"] = config["urls"]
            for key in ("cookie", "proxy", "timeout", "user_agent"):
                if key in config:
                    kwargs[key] = config[key]
        stream_key = getattr(subscription, "account_identifier", None) or f"{subscription.source_type}:{subscription.id}"
        kwargs["stream_key"] = stream_key
        return fetcher_factory(**kwargs)

    def _build_source_options(self, subscription: Any, request_options: dict[str, Any]) -> dict[str, Any]:
        config = self._resolve_subscription_config(subscription)
        merged = dict(config)
        merged.update(request_options)
        return merged

    def _resolve_subscription_config(self, subscription: Any) -> dict[str, Any]:
        config = getattr(subscription, "config", None)
        if isinstance(config, dict):
            return dict(config)
        raw = getattr(subscription, "config_json", None)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _resolve_validation_rules(self, source_options: dict[str, Any]) -> dict[str, Any]:
        raw = source_options.get("validation_rules")
        if isinstance(raw, dict):
            return raw
        rules: dict[str, Any] = {}
        for key in (
            "require_source_url",
            "require_raw_content",
            "drop_stale",
            "exclude_keywords",
            "invalid_alert_threshold",
        ):
            if key in source_options:
                rules[key] = source_options[key]
        return rules

    def _validate_source_items(
        self,
        *,
        source_type: str,
        source_items: list[SourceItem],
        lookback_hours: int,
        validation_rules: dict[str, Any],
    ) -> tuple[list[SourceItem], list[FetchValidationIssue]]:
        accepted: list[SourceItem] = []
        issues: list[FetchValidationIssue] = []
        for item in source_items:
            result = validate_source_item(
                item,
                lookback_hours=lookback_hours,
                rules=validation_rules,
            )
            if result.accepted:
                accepted.append(item)
                continue
            for reason in result.reasons:
                issues.append(
                    FetchValidationIssue(
                        source=source_type,
                        source_id=item.source_id or None,
                        reason=reason,
                        detail=item.title or item.source_url,
                    )
                )
        return accepted, issues

    def _update_cursor(self, subscription: Any, source_items: list[SourceItem]) -> None:
        if not source_items:
            return
        cursor_value = self._build_cursor_value(source_items[0])
        if not cursor_value:
            return
        update_cursor = getattr(self.source_repo, "update_cursor", None)
        if callable(update_cursor):
            update_cursor(self.db_session, subscription, cursor_value)
            return
        subscription.last_cursor = cursor_value
        self.db_session.add(subscription)
        self.db_session.commit()

    def _build_cursor_value(self, source_item: SourceItem) -> str | None:
        metadata = source_item.metadata if isinstance(source_item.metadata, dict) else {}
        published_at = metadata.get("published_at")
        payload = {
            "external_id": source_item.source_id,
            "published_at": str(published_at) if published_at else None,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        if not payload["external_id"] and not payload["published_at"]:
            return None
        return json.dumps(payload, ensure_ascii=True)

    def _filter_incremental_items(self, source_items: list[SourceItem], raw_cursor: str | None) -> list[SourceItem]:
        cursor = self._parse_cursor(raw_cursor)
        if not cursor:
            return source_items

        cursor_external_id = cursor.get("external_id")
        cursor_published_at = self._parse_timestamp(cursor.get("published_at"))
        filtered_items: list[SourceItem] = []

        for item in source_items:
            if cursor_external_id and item.source_id == cursor_external_id:
                break

            item_published_at = self._parse_timestamp(
                item.metadata.get("published_at") if isinstance(item.metadata, dict) else None
            )
            if cursor_published_at and item_published_at is not None:
                if item_published_at > cursor_published_at:
                    filtered_items.append(item)
                continue

            filtered_items.append(item)

        return filtered_items

    def _parse_cursor(self, raw_cursor: str | None) -> dict[str, str]:
        if not raw_cursor:
            return {}
        try:
            parsed = json.loads(raw_cursor)
        except json.JSONDecodeError:
            parsed_timestamp = self._parse_timestamp(raw_cursor)
            if parsed_timestamp is not None:
                return {"published_at": parsed_timestamp.isoformat()}
            return {"external_id": raw_cursor}

        if not isinstance(parsed, dict):
            return {}
        normalized: dict[str, str] = {}
        for key in ("external_id", "published_at", "fetched_at"):
            value = parsed.get(key)
            if value is None:
                continue
            normalized[key] = str(value)
        return normalized

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _dedupe_source_items(
        self,
        source_items: list[SourceItem],
        seen_keys: set[tuple[str, str]],
    ) -> tuple[list[SourceItem], int]:
        unique_items: list[SourceItem] = []
        deduped_count = 0
        for item in source_items:
            dedup_key = (item.source_type, item.source_id)
            if dedup_key in seen_keys:
                deduped_count += 1
                continue
            seen_keys.add(dedup_key)
            unique_items.append(item)
        return unique_items, deduped_count

    def _content_exists(self, source_type: str, source_id: str) -> bool:
        return (
            self.db_session.query(self.source_repo.ContentItem)
            .filter(self.source_repo.ContentItem.source_type == source_type)
            .filter(self.source_repo.ContentItem.source_id == source_id)
            .first()
            is not None
        )

    def _serialize_content_item(self, content_item: Any, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": content_item.id,
            "source_type": content_item.source_type,
            "source_id": content_item.source_id,
            "title": content_item.title,
            "source_url": content_item.source_url,
            "raw_content": content_item.raw_content,
            "summary": content_item.summary,
            "metadata": metadata,
        }

    def _serialize_tags(self, raw_tags: str | None) -> str:
        if not raw_tags:
            return "[]"
        tags = [tag.strip() for tag in raw_tags.split(",") if tag.strip()]
        return "[" + ", ".join(f'\"{tag}\"' for tag in tags) + "]"

    def _serialize_metadata(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        try:
            return json.dumps(metadata, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return None

    def _to_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _to_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
