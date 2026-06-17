from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
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

from database import get_db
from apps.platform.database import Base
from models import ContentItem, ReviewQueue  # noqa: F401
from routers.reviews import router


def _build_client() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def _seed_review(session_factory: sessionmaker) -> int:
    db = session_factory()
    item = ContentItem(
        source_type="rss",
        source_id="item-1",
        title="Original Title",
        source_url="https://example.com/item-1",
        language="zh",
        raw_content="Original Content",
        summary="Summary",
        rewritten_title="Rewrite Title",
        rewritten_content="Rewrite Content",
        tags_json='["python","ai"]',
        score=4.2,
        publish_status="pending",
        pipeline_status="processed",
        review_status="pending",
        digest_included=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    review = ReviewQueue(
        content_item_id=item.id,
        candidate_title=item.rewritten_title,
        candidate_content=item.rewritten_content,
        status="pending",
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    review_id = int(review.id)
    db.close()
    return review_id


def test_list_reviews_returns_pending_items() -> None:
    client, session_factory = _build_client()
    _seed_review(session_factory)

    response = client.get("/api/internal/content/reviews/?status=pending")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["original_title"] == "Original Title"


def test_get_review_returns_detail() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.get(f"/api/internal/content/reviews/{review_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["candidate_title"] == "Rewrite Title"
    assert body["data"]["original_content"] == "Original Content"


def test_approve_review_updates_review_and_content_item() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(
        f"/api/internal/content/reviews/{review_id}/approve",
        json={"reviewer": "admin"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "approved"
    assert body["data"]["reviewer"] == "admin"

    db = session_factory()
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    item = db.query(ContentItem).filter(ContentItem.id == review.content_item_id).first()
    assert review.status == "approved"
    assert item.review_status == "approved"
    db.close()


def test_reject_review_persists_note() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(
        f"/api/internal/content/reviews/{review_id}/reject",
        json={"reviewer": "editor", "note": "needs more edits"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "rejected"
    assert body["data"]["review_note"] == "needs more edits"


def test_archive_review_updates_status() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(f"/api/internal/content/reviews/{review_id}/archive?reviewer=archiver")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "archived"
    assert body["data"]["reviewer"] == "archiver"


def test_approve_review_with_edits_persists_edited_content() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(
        f"/api/internal/content/reviews/{review_id}/approve",
        json={
            "reviewer": "chief-editor",
            "edited_title": "Edited Title",
            "edited_content": "Edited Content",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["candidate_title"] == "Edited Title"
    assert body["data"]["candidate_content"] == "Edited Content"

    db = session_factory()
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    item = db.query(ContentItem).filter(ContentItem.id == review.content_item_id).first()
    assert review.candidate_title == "Edited Title"
    assert review.candidate_content == "Edited Content"
    assert item.rewritten_title == "Edited Title"
    assert item.rewritten_content == "Edited Content"
    db.close()
