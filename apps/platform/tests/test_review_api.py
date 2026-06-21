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

from apps.platform.database import Base
from apps.platform.database import get_db
from apps.platform.models import AgentMemory, ContentItem, ReviewQueue  # noqa: F401
from apps.platform.routers.reviews import router


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
    assert body["data"]["publish_status"] == "pending"
    assert body["data"]["publish_path"] == "/console/content-items/1/publish-to-post"
    assert body["data"]["next_action"] == "publish_to_post"

    db = session_factory()
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    item = db.query(ContentItem).filter(ContentItem.id == review.content_item_id).first()
    memory = db.query(AgentMemory).filter(AgentMemory.scope == "review", AgentMemory.scope_key == str(item.id)).first()
    assert review.status == "approved"
    assert item.review_status == "approved"
    assert memory is not None
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

    db = session_factory()
    memory = db.query(AgentMemory).filter(AgentMemory.scope == "review").first()
    assert memory is not None
    assert "needs more edits" in memory.value_json
    db.close()


def test_archive_review_updates_status() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(f"/api/internal/content/reviews/{review_id}/archive?reviewer=archiver")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "archived"
    assert body["data"]["reviewer"] == "archiver"


def test_auto_review_runs_quality_gate_and_keeps_pending_when_no_auto_decision() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    response = client.post(
        f"/api/internal/content/reviews/{review_id}/auto-review",
        json={"reviewer": "quality-gate", "use_tool": True, "auto_approve": False, "auto_reject": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "pending"
    assert body["data"]["quality_gate"]["score"] > 0
    assert body["data"]["quality_gate"]["tool_result"]["success"] is True
    assert body["data"]["review_note"].startswith("quality_gate:")

    db = session_factory()
    memory = db.query(AgentMemory).filter(AgentMemory.scope == "review").first()
    assert memory is not None
    assert "quality_gate" in memory.value_json
    db.close()


def test_auto_review_rejects_low_quality_candidate() -> None:
    client, session_factory = _build_client()
    review_id = _seed_review(session_factory)

    db = session_factory()
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    assert review is not None
    review.candidate_title = ""
    review.candidate_content = ""
    db.add(review)
    db.commit()
    db.close()

    response = client.post(
        f"/api/internal/content/reviews/{review_id}/auto-review",
        json={"reviewer": "quality-gate", "auto_reject": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "rejected"
    assert body["data"]["quality_gate"]["status"] == "failed"


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
    assert body["data"]["publish_path"] == f"/console/content-items/{body['data']['content_item_id']}/publish-to-post"
    assert body["data"]["next_action"] == "publish_to_post"

    db = session_factory()
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    item = db.query(ContentItem).filter(ContentItem.id == review.content_item_id).first()
    assert review.candidate_title == "Edited Title"
    assert review.candidate_content == "Edited Content"
    assert item.rewritten_title == "Edited Title"
    assert item.rewritten_content == "Edited Content"
    db.close()


def test_list_reviews_returns_radar_generated_queue_item() -> None:
    import asyncio

    from apps.platform.models import RewriteProfile
    from apps.workflow_engine.api.service import WorkflowEngineService
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module
    import apps.workflow_engine.runtime.content_repository as content_repository_module

    client, session_factory = _build_client()
    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    original_repository_session = content_repository_module.SessionLocal
    platform_database.SessionLocal = session_factory
    workflow_service_module.SessionLocal = session_factory
    content_repository_module.SessionLocal = session_factory
    try:
        db = session_factory()
        db.add(
            RewriteProfile(
                name="zh_tech_blog",
                provider="local",
                model="mock-model",
                timeout_seconds=30,
                fallback_strategy="raw",
                system_prompt="test prompt",
                max_tokens=256,
            )
        )
        db.add(
            ContentItem(
                source_type="rss",
                source_id="radar-review-item",
                fetch_run_id=88,
                title="Radar Review Item",
                source_url="https://example.com/radar-review-item",
                language="zh",
                raw_content="Python content for radar review queue",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="fetched",
                review_status="pending",
                digest_included=False,
            )
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        result = asyncio.run(
            service.run_radar_pipeline(
                {
                    "run_id": "review-api-radar",
                    "fetch_run_id": 88,
                    "limit": 10,
                        "review_options": {
                            "enable_quality_gate": True,
                            "use_tool": True,
                            "auto_reject": False,
                        },
                }
            )
        )
        assert result["errors"] == []
        assert len(result["quality_gate_results"]) == 1

        response = client.get("/api/internal/content/reviews/?status=pending")
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["original_title"] == "Radar Review Item"
        assert body["data"]["items"][0]["status"] == "pending"
        assert body["data"]["items"][0]["quality_gate"]["tool_result"]["success"] is True

        verify_db = session_factory()
        memory_row = (
            verify_db.query(AgentMemory)
            .filter(
                AgentMemory.scope == "workflow",
                AgentMemory.scope_key == "radar_pipeline",
                AgentMemory.memory_type == "outcome",
                AgentMemory.memory_key == "last_run",
            )
            .first()
        )
        assert memory_row is not None
        verify_db.close()
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session
