from __future__ import annotations

import os
import sys
import importlib.util
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
from apps.platform.models import ContentItem, FetchRun, SourceConfig
from apps.platform.security import create_access_token


def _load_console_router():
    module_path = REPO_ROOT / "apps" / "platform" / "routers" / "api_v1" / "console.py"
    spec = importlib.util.spec_from_file_location("test_console_router_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module.router


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
    app.include_router(_load_console_router())
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), session_factory


def test_console_process_fetch_run_returns_review_queue_hint(monkeypatch) -> None:
    client, session_factory = _build_client()

    class StubSchedulerClient:
        def submit_task(self, **kwargs):  # noqa: ANN003
            return {"id": "task-radar-1", "trace_id": "trace-radar-1", "status": "pending"}

    monkeypatch.setattr("apps.platform.services.console_service.get_scheduler_client", lambda: StubSchedulerClient())

    db = session_factory()
    source = SourceConfig(
        name="rss-source",
        source_type="rss",
        enabled=True,
        lookback_hours=24,
        item_limit=20,
        dedup_window_hours=24,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    fetch_run = FetchRun(
        source_config_id=source.id,
        trigger_mode="manual",
        status="success",
    )
    db.add(fetch_run)
    db.commit()
    db.refresh(fetch_run)
    fetch_run_id = int(fetch_run.id)
    db.close()

    response = client.post(
        f"/console/fetch-runs/{fetch_run_id}/process",
        headers={"authorization": f"Bearer {create_access_token({'sub': 'tester'})}"},
        json={
            "limit": 8,
            "source_type": "rss",
            "filter_config": {"include_keywords": ["python"]},
            "process_options": {"rewrite_profile": "zh_tech_blog"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["fetch_run_id"] == fetch_run_id
    assert body["data"]["review_status"] == "pending"
    assert body["data"]["review_queue_path"] == "/api/internal/content/reviews/?status=pending"
    assert body["data"]["next_action"] == "open_review_queue"


def test_console_publish_to_post_returns_post_hint() -> None:
    client, session_factory = _build_client()

    db = session_factory()
    item = ContentItem(
        source_type="rss",
        source_id="console-publish-1",
        title="Original Title",
        source_url="https://example.com/console-publish-1",
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

    response = client.post(
        f"/console/content-items/{content_item_id}/publish-to-post",
        headers={"authorization": f"Bearer {create_access_token({'sub': 'tester'})}"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["post_id"] > 0
    assert body["data"]["post_path"] == f"/posts/{body['data']['post_id']}"
    assert body["data"]["publish_status"] == "published"
    assert body["data"]["next_action"] == "open_post_draft"
    assert body["data"]["content_item"]["publish_status"] == "published"
