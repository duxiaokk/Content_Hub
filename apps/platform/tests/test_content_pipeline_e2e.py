from __future__ import annotations

import asyncio
import importlib.util
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

from apps.platform.database import Base, get_db
from apps.platform.models import ContentItem, FetchRun, Post, PublishRecord, ReviewQueue, RewriteProfile
from apps.platform.routers.reviews import router as reviews_router
from apps.platform.security import create_access_token
from apps.workflow_engine.api.service import WorkflowEngineService
import apps.platform.database as platform_database
import apps.workflow_engine.api.service as workflow_service_module
import apps.workflow_engine.runtime.content_repository as content_repository_module


def _load_console_router():
    module_path = REPO_ROOT / "apps" / "platform" / "routers" / "api_v1" / "console.py"
    spec = importlib.util.spec_from_file_location("test_console_router_module_e2e", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


def _build_clients() -> tuple[TestClient, TestClient, sessionmaker]:
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

    review_app = FastAPI()
    review_app.include_router(reviews_router)
    review_app.dependency_overrides[get_db] = override_get_db

    console_app = FastAPI()
    console_app.include_router(_load_console_router())
    console_app.dependency_overrides[get_db] = override_get_db

    return TestClient(review_app), TestClient(console_app), session_factory


def test_content_pipeline_manual_loop_e2e() -> None:
    review_client, console_client, session_factory = _build_clients()

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
        fetch_run = FetchRun(
            source_config_id=1,
            trigger_mode="manual",
            status="success",
        )
        db.add(fetch_run)
        db.commit()
        db.refresh(fetch_run)
        fetch_run_id = int(fetch_run.id)

        db.add(
            ContentItem(
                source_type="rss",
                source_id="e2e-item-1",
                fetch_run_id=fetch_run_id,
                title="E2E Pipeline Item",
                source_url="https://example.com/e2e-item-1",
                language="zh",
                raw_content="Python content for the e2e pipeline",
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

        result = asyncio.run(
                WorkflowEngineService().run_radar_pipeline(
                    {
                        "run_id": "content-pipeline-e2e",
                        "fetch_run_id": fetch_run_id,
                        "limit": 10,
                    }
                )
        )
        assert result["errors"] == []
        assert len(result["review_queue_ids"]) == 1
        review_id = int(result["review_queue_ids"][0])

        approve_response = review_client.post(
            f"/api/internal/content/reviews/{review_id}/approve",
            json={"reviewer": "chief-editor"},
        )
        assert approve_response.status_code == 200
        approve_body = approve_response.json()
        assert approve_body["data"]["status"] == "approved"
        assert approve_body["data"]["next_action"] == "publish_to_post"

        content_item_id = int(approve_body["data"]["content_item_id"])
        publish_response = console_client.post(
            f"/console/content-items/{content_item_id}/publish-to-post",
            headers={"authorization": f"Bearer {create_access_token({'sub': 'tester'})}"},
            json={},
        )
        assert publish_response.status_code == 200
        publish_body = publish_response.json()
        assert publish_body["code"] == 0
        assert publish_body["data"]["publish_status"] == "published"
        assert publish_body["data"]["next_action"] == "open_post_draft"
        assert publish_body["data"]["post_id"] > 0

        verify_db = session_factory()
        item = verify_db.query(ContentItem).filter(ContentItem.id == content_item_id).first()
        review = verify_db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
        post = verify_db.query(Post).filter(Post.id == publish_body["data"]["post_id"]).first()
        record = verify_db.query(PublishRecord).filter(PublishRecord.content_item_id == content_item_id).first()

        assert item is not None
        assert item.publish_status == "published"
        assert item.pipeline_status == "published"
        assert item.review_status == "approved"
        assert review is not None
        assert review.status == "approved"
        assert post is not None
        assert record is not None
        assert record.status == "success"
        verify_db.close()
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session
