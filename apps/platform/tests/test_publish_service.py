from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-secret-key")
REPO_ROOT = Path(__file__).resolve().parents[3]
PLATFORM_DIR = Path(__file__).resolve().parents[1]
for path in (PLATFORM_DIR, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from apps.platform.database import Base
from models import ContentItem, Post, PublishRecord
from services.publish_service import PublishService


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _seed_content_item(factory: sessionmaker) -> int:
    db = factory()
    item = ContentItem(
        source_type="rss",
        source_id="publish-1",
        title="Original Title",
        source_url="https://example.com/publish-1",
        language="zh",
        raw_content="Original Content",
        processed_content="Processed Content",
        rewritten_title="Rewritten Title",
        rewritten_content="Rewritten Content",
        tags_json='["python","fastapi"]',
        score=4.5,
        publish_status="pending",
        pipeline_status="processed",
        review_status="approved",
        digest_included=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    content_item_id = int(item.id)
    db.close()
    return content_item_id


def test_publish_blog_draft_creates_post_and_publish_record() -> None:
    factory = _session_factory()
    content_item_id = _seed_content_item(factory)

    db = factory()
    result = PublishService(db).publish_blog_draft(content_item_id, run_id="blog-run-1")
    assert result["status"] == "success"

    post = db.query(Post).first()
    item = db.query(ContentItem).filter(ContentItem.id == content_item_id).first()
    record = db.query(PublishRecord).filter(PublishRecord.content_item_id == content_item_id).first()

    assert post is not None
    assert post.published is False
    assert post.title == "Rewritten Title"
    assert item.publish_status == "published"
    assert item.pipeline_status == "published"
    assert item.draft_post_id == post.id
    assert record is not None
    assert record.status == "success"
    assert record.target_type == "blog"
    db.close()


def test_publish_blog_draft_skips_when_already_published() -> None:
    factory = _session_factory()
    content_item_id = _seed_content_item(factory)

    db = factory()
    service = PublishService(db)
    first = service.publish_blog_draft(content_item_id, run_id="blog-run-1")
    second = service.publish_blog_draft(content_item_id, run_id="blog-run-2")

    assert first["status"] == "success"
    assert second["status"] == "skipped"

    record_count = db.query(PublishRecord).filter(PublishRecord.content_item_id == content_item_id).count()
    assert record_count == 1
    db.close()


def test_publish_blog_draft_records_failure() -> None:
    factory = _session_factory()
    content_item_id = _seed_content_item(factory)

    db = factory()
    service = PublishService(db)
    original_flush = db.flush
    state = {"failed": False}

    def failing_flush() -> None:
        if not state["failed"]:
            state["failed"] = True
            raise RuntimeError("flush failed")
        return original_flush()

    db.flush = failing_flush  # type: ignore[method-assign]
    try:
        try:
            service.publish_blog_draft(content_item_id, run_id="blog-run-fail")
        except RuntimeError as exc:
            assert str(exc) == "flush failed"
    finally:
        db.flush = original_flush  # type: ignore[method-assign]

    record = db.query(PublishRecord).filter(PublishRecord.run_id == "blog-run-fail").first()
    item = db.query(ContentItem).filter(ContentItem.id == content_item_id).first()
    assert record is not None
    assert record.status == "failed"
    assert "flush failed" in record.response_payload
    assert item.publish_status == "pending"
    assert item.pipeline_status == "processed"
    db.close()
