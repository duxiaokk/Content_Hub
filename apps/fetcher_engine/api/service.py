from __future__ import annotations

import traceback
from typing import Any

from sqlalchemy.orm import Session

from apps.fetcher_engine.api.models import FetchBatchError, FetchBatchRequest, FetchBatchResult, FetchBatchStats
from apps.fetcher_engine.api.registry import get_fetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


class FetchService:
    def __init__(self, db_session: Session, source_repo: Any) -> None:
        self.db_session = db_session
        self.source_repo = source_repo

    async def run_sources(self, request: FetchBatchRequest) -> FetchBatchResult:
        subscriptions = self._load_subscriptions(request.sources)
        result_items: list[dict[str, Any]] = []
        result_errors: list[FetchBatchError] = []
        seen_keys: set[tuple[str, str]] = set()
        total_fetched = 0
        total_inserted = 0
        total_deduped = 0

        for subscription in subscriptions:
            source_type = subscription.source_type
            fetcher_factory = get_fetcher(source_type)
            if fetcher_factory is None:
                result_errors.append(
                    FetchBatchError(
                        source=source_type,
                        error=f"fetcher not registered for source_type={source_type}",
                        traceback=None,
                    )
                )
                continue

            try:
                fetcher = self._build_fetcher(fetcher_factory, subscription)
                source_items = await fetcher.fetch(
                    FetchRequest(
                        source_name=subscription.source_name,
                        lookback_hours=request.lookback_hours,
                        limit=request.limit_per_source,
                        cursor=subscription.last_cursor,
                        options=dict(request.options),
                    )
                )
            except Exception as exc:
                result_errors.append(
                    FetchBatchError(
                        source=source_type,
                        error=str(exc),
                        traceback=traceback.format_exc(),
                    )
                )
                continue

            total_fetched += len(source_items)
            self._update_cursor(subscription, source_items)
            unique_items, deduped_count = self._dedupe_source_items(source_items, seen_keys)
            total_deduped += deduped_count

            for item in unique_items:
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
                )
                result_items.append(self._serialize_content_item(content_item, item.metadata))
                total_inserted += 1

        return FetchBatchResult(
            run_id=request.run_id,
            items=result_items,
            errors=result_errors,
            stats=FetchBatchStats(
                total_fetched=total_fetched,
                total_inserted=total_inserted,
                total_deduped=total_deduped,
            ),
        )

    def _load_subscriptions(self, sources: list[str]) -> list[Any]:
        query = self.db_session.query(self.source_repo.SourceSubscription).filter(
            self.source_repo.SourceSubscription.enabled.is_(True)
        )
        if sources:
            query = query.filter(self.source_repo.SourceSubscription.source_type.in_(sources))
        return list(query.order_by(self.source_repo.SourceSubscription.id.asc()).all())

    def _build_fetcher(self, fetcher_factory: Any, subscription: Any) -> Any:
        kwargs: dict[str, Any] = {}
        if getattr(subscription, "feed_url", None):
            kwargs["feed_url"] = subscription.feed_url
        if getattr(subscription, "source_name", None):
            kwargs["source_name"] = subscription.source_name
        stream_key = getattr(subscription, "account_identifier", None) or f"{subscription.source_type}:{subscription.id}"
        kwargs["stream_key"] = stream_key
        return fetcher_factory(**kwargs)

    def _update_cursor(self, subscription: Any, source_items: list[SourceItem]) -> None:
        if not source_items:
            return
        last_item = source_items[-1]
        cursor_value = None
        published_at = last_item.metadata.get("published_at") if isinstance(last_item.metadata, dict) else None
        if published_at:
            cursor_value = str(published_at)
        elif last_item.source_id:
            cursor_value = last_item.source_id
        if not cursor_value:
            return
        update_cursor = getattr(self.source_repo, "update_cursor", None)
        if callable(update_cursor):
            update_cursor(self.db_session, subscription, cursor_value)
            return
        subscription.last_cursor = cursor_value
        self.db_session.add(subscription)
        self.db_session.commit()

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
