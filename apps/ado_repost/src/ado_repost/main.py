from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from ado_repost.fetchers import (
    CursorStore,
    FetchOrchestrator,
    FetchRequest,
    JsonCursorStore,
    MemoryPoolCursorStore,
)
from ado_repost.publishing import BlogPublishingClient, DraftPayload, load_publishing_settings
from ado_repost.schema import DynamicItem

from .config import Settings, load_settings
from .mempool import pool as mempool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("ado_repost.main")

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"
CURSOR_PATH = DATA_DIR / "cursors.json"
RESULT_PATH = DATA_DIR / "run_result.json"
PROCESSED_PATH = DATA_DIR / "processed.json"
ARTICLE_PAYLOADS_PATH = DATA_DIR / "article_payloads.json"


def _unified_post_to_dynamic(post: Any) -> DynamicItem:
    url = str(getattr(post, "url", "") or "")
    title = str(getattr(post, "title", "") or "")
    source = str(getattr(post, "source", "") or "")
    author = ""
    if hasattr(post, "raw") and isinstance(post.raw, dict):
        author = str(post.raw.get("author", "") or "")
    published_at: str | None = None
    if hasattr(post, "published_at") and post.published_at:
        dt = post.published_at
        if isinstance(dt, datetime):
            published_at = dt.astimezone(timezone.utc).isoformat()
        else:
            published_at = str(dt)
    media_urls = [str(a.url) for a in getattr(post, "media", []) or [] if a.url]
    return DynamicItem(
        link=url,
        title=title,
        content=str(getattr(post, "summary", "") or ""),
        source=source,
        author=author,
        published_at=published_at,
        language=None,
        tags=[],
        media_urls=media_urls,
        metadata={"external_id": getattr(post, "external_id", "") or ""},
    )


def _collect_fetch_errors(batches: tuple[Any, ...]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for batch in batches:
        error = batch.metadata.get("error")
        if not error:
            continue
        errors.append(
            {
                "source": str(batch.source),
                "adapter": str(batch.adapter),
                "error": str(error),
            }
        )
    return errors


def _format_published_at_for_title(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown time"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _serialize_processed_items(batch_result: Any) -> list[dict[str, Any]]:
    return [
        {
            "dedup_key": item.dedup_key,
            "source": item.raw.source,
            "title": item.translated_title or item.raw.title,
            "content": item.translated_content or item.raw.content,
            "link": item.raw.link,
            "thumbnail": item.raw.media_urls[0] if item.raw.media_urls else None,
            "published_at": item.raw.published_at,
            "author": item.raw.author,
            "tags": list(item.raw.tags),
            "formatted_message": item.formatted_message,
        }
        for item in batch_result.new_items
    ]


def _build_article_payloads(processed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in processed_items:
        title = str(item.get("title") or "").strip()
        published_at = _format_published_at_for_title(item.get("published_at"))
        article_title = f"{title} | {published_at}" if title else published_at

        content = str(item.get("content") or "").strip()
        link = str(item.get("link") or "").strip()
        article_parts: list[str] = []
        if content:
            article_parts.append(content)
        if link:
            article_parts.append(f"Video Link: {link}")

        payloads.append(
            {
                "source": item.get("source"),
                "source_link": link or None,
                "video_title": title,
                "video_published_at": item.get("published_at"),
                "article_title": article_title,
                "article_content": "\n\n".join(article_parts).strip(),
                "cover_image_url": item.get("thumbnail"),
                "thumbnail": item.get("thumbnail"),
                "dedup_key": item.get("dedup_key"),
            }
        )
    return payloads


def _publish_article_payloads(article_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    publishing_settings = load_publishing_settings()
    if not publishing_settings.enabled:
        return []

    client = BlogPublishingClient(publishing_settings)
    results: list[dict[str, Any]] = []
    for payload in article_payloads:
        draft = DraftPayload(
            title=str(payload.get("article_title") or "").strip(),
            summary=str(payload.get("article_content") or "").strip()[:500],
            markdown_content=str(payload.get("article_content") or "").strip(),
            source_platform=publishing_settings.source_platform,
            source_link=str(payload.get("source_link") or "").strip(),
            source_external_id=str(payload.get("dedup_key") or "").strip() or None,
            source_dedup_key=str(payload.get("dedup_key") or "").strip() or None,
            source_published_at=str(payload.get("video_published_at") or "").strip() or None,
            cover_image_url=payload.get("cover_image_url") or None,
            tags=[],
            raw_payload=payload,
        )
        result = client.publish_draft(draft.to_dict())
        results.append(
            {
                "ok": result.ok,
                "status_code": result.status_code,
                "response_text": result.response_text,
                "source_link": payload.get("source_link"),
            }
        )
    return results


def run(
    config_path: Path | None = None,
    settings: Settings | None = None,
    output_stream: TextIO | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if settings is None:
        settings = load_settings(config_path)

    cursor_store: CursorStore | None = None
    if settings.fetchers.persist_cursors:
        if os.getenv("ADO_REPOST_CURSOR_STORE", "").strip().lower() == "mempool":
            cursor_store = MemoryPoolCursorStore(pool=mempool)
        else:
            cursor_store = JsonCursorStore(file_path=CURSOR_PATH)

    request = FetchRequest(lookback_hours=settings.fetchers.lookback_hours)
    orchestrator = FetchOrchestrator(settings=settings.fetchers)

    logger.info("Starting fetch for all platforms (lookback=%s hours)", request.lookback_hours)
    batches = orchestrator.fetch_all(request=request, cursor_store=cursor_store)
    fetch_errors = _collect_fetch_errors(batches)
    total_new = sum(len(batch.items) for batch in batches)

    for batch in batches:
        error = batch.metadata.get("error")
        if error:
            logger.error("[%s] fetch failed: %s", batch.source, error)
            continue
        logger.info(
            "[%s] total=%s new=%s",
            batch.source,
            batch.metadata.get("total_seen", len(batch.items)),
            len(batch.items),
        )

    if not batches:
        result: dict[str, Any] = {
            "status": "no_items",
            "fetch_error": None,
            "fetch_errors": [],
            "new_items": 0,
            "processed_items": 0,
            "messages": [],
        }
        with PROCESSED_PATH.open("w", encoding="utf-8") as file_handle:
            json.dump([], file_handle, ensure_ascii=False, indent=2)
        with ARTICLE_PAYLOADS_PATH.open("w", encoding="utf-8") as file_handle:
            json.dump([], file_handle, ensure_ascii=False, indent=2)
        _emit(output_stream, result)
        return result

    logger.info("Fetch completed: platforms=%s new_items=%s", len(batches), total_new)

    latest_items: list[DynamicItem] = [
        _unified_post_to_dynamic(post) for batch in batches for post in batch.items
    ]
    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LATEST_PATH.open("w", encoding="utf-8") as file_handle:
        json.dump([item.to_dict() for item in latest_items], file_handle, ensure_ascii=False, indent=2)

    from ado_repost.processors import ContentProcessor

    processor = ContentProcessor()
    batch_result = processor.process_paths(LATEST_PATH, HISTORY_PATH)

    with HISTORY_PATH.open("w", encoding="utf-8") as file_handle:
        json.dump(
            [record.to_dict() for record in batch_result.updated_history],
            file_handle,
            ensure_ascii=False,
            indent=2,
        )

    base_result = {
        "fetch_error": fetch_errors[0]["error"] if fetch_errors else None,
        "fetch_errors": fetch_errors,
    }

    if not batch_result.new_items:
        result = {
            "status": "skipped",
            **base_result,
            "new_items": 0,
            "processed_items": 0,
            "messages": [],
            "items": [],
        }
        with PROCESSED_PATH.open("w", encoding="utf-8") as file_handle:
            json.dump([], file_handle, ensure_ascii=False, indent=2)
        with ARTICLE_PAYLOADS_PATH.open("w", encoding="utf-8") as file_handle:
            json.dump([], file_handle, ensure_ascii=False, indent=2)
        _emit(output_stream, result)
        with RESULT_PATH.open("w", encoding="utf-8") as file_handle:
            json.dump(result, file_handle, ensure_ascii=False, indent=2)
        return result

    result_status = "dry_run" if dry_run else "done"
    if dry_run:
        logger.info("[dry-run] processing completed, pending=%s", len(batch_result.new_items))

    processed_items = _serialize_processed_items(batch_result)
    with PROCESSED_PATH.open("w", encoding="utf-8") as file_handle:
        json.dump(processed_items, file_handle, ensure_ascii=False, indent=2)
    article_payloads = _build_article_payloads(processed_items)
    with ARTICLE_PAYLOADS_PATH.open("w", encoding="utf-8") as file_handle:
        json.dump(article_payloads, file_handle, ensure_ascii=False, indent=2)
    publish_results = _publish_article_payloads(article_payloads)

    result = {
        "status": result_status,
        **base_result,
        "new_items": len(batch_result.new_items),
        "processed_items": len(batch_result.new_items),
        "messages": batch_result.messages,
        "items": processed_items,
        "processed_path": str(PROCESSED_PATH),
        "article_payloads_path": str(ARTICLE_PAYLOADS_PATH),
        "publish_results": publish_results,
    }
    _emit(output_stream, result)
    with RESULT_PATH.open("w", encoding="utf-8") as file_handle:
        json.dump(result, file_handle, ensure_ascii=False, indent=2)
    return result


def _emit(stream: TextIO | None, result: dict[str, Any]) -> None:
    if stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Ado content fetch and processing CLI")
    parser.add_argument("--config", type=Path, default=None, help="Path to YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and process without side effects")
    args = parser.parse_args()
    result = run(config_path=args.config, dry_run=args.dry_run)
    mempool.close()
    return 0 if result["status"] in ("done", "skipped", "no_items", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
