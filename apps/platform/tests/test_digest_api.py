from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

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
from models import ContentItem, DigestReport, PublishRecord  # noqa: F401
from routers.digests import router


def _build_client(*, raise_server_exceptions: bool = True) -> tuple[TestClient, sessionmaker]:
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
    return TestClient(app, raise_server_exceptions=raise_server_exceptions), session_factory


def _seed_approved_content(session_factory: sessionmaker) -> None:
    db = session_factory()
    db.add(
        ContentItem(
            source_type="rss",
            source_id="approved-1",
            title="Approved Title",
            source_url="https://example.com/a1",
            language="zh",
            raw_content="Approved raw content",
            summary="Approved summary",
            rewritten_title="Approved Rewrite Title",
            rewritten_content="Approved rewrite content",
            tags_json='["python"]',
            score=4.8,
            publish_status="pending",
            pipeline_status="processed",
            review_status="approved",
            digest_included=False,
        )
    )
    db.commit()
    db.close()


def test_generate_digest_creates_new_digest_report() -> None:
    client, session_factory = _build_client()
    _seed_approved_content(session_factory)

    response = client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24, "run_id": "digest-run-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["run_id"] == "digest-run-1"
    assert body["data"]["included_count"] == 1
    assert "Approved Rewrite Title" in body["data"]["content_markdown"]


def test_generate_digest_marks_content_items_included() -> None:
    client, session_factory = _build_client()
    _seed_approved_content(session_factory)

    client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24})
    db = session_factory()
    item = db.query(ContentItem).filter(ContentItem.source_id == "approved-1").first()
    assert item.digest_included is True
    digest = db.query(DigestReport).first()
    assert digest is not None
    publish_record = db.query(PublishRecord).filter(PublishRecord.target_type == "digest_markdown").first()
    assert publish_record is not None
    assert publish_record.status == "success"
    db.close()


def test_list_digests_returns_generated_reports_in_desc_order() -> None:
    client, session_factory = _build_client()
    _seed_approved_content(session_factory)
    client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24, "run_id": "run-1"})
    client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24, "run_id": "run-2"})

    response = client.get("/api/internal/content/digests/")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 2
    assert body["data"]["items"][0]["id"] >= body["data"]["items"][1]["id"]


def test_get_digest_returns_detail() -> None:
    client, _session_factory = _build_client()
    _seed_approved_content(_session_factory)
    generate_response = client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24})
    digest_id = generate_response.json()["data"]["id"]

    response = client.get(f"/api/internal/content/digests/{digest_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] == digest_id
    assert "content_markdown" in body["data"]


def test_download_digest_returns_markdown_file() -> None:
    client, _session_factory = _build_client()
    _seed_approved_content(_session_factory)
    generate_response = client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24})
    digest_id = generate_response.json()["data"]["id"]

    response = client.get(f"/api/internal/content/digests/{digest_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment; filename=\"digest_" in response.headers["content-disposition"]
    assert "# 技术内容日报 -" in response.text


def test_generate_digest_records_failed_publish(monkeypatch) -> None:
    client, session_factory = _build_client(raise_server_exceptions=False)
    _seed_approved_content(session_factory)

    from services.digest_service import DigestService

    monkeypatch.setattr(
        DigestService,
        "__init__",
        lambda self, db: (
            setattr(self, "db", db),
            setattr(
                self,
                "_publishing_service",
                type("FailingPublisher", (), {"generate_digest": AsyncMock(side_effect=RuntimeError("publish failed"))})(),
            ),
        )[-1],
    )

    response = client.post("/api/internal/content/digests/generate", json={"lookback_hours": 24, "run_id": "digest-fail-1"})
    assert response.status_code == 500

    db = session_factory()
    publish_record = db.query(PublishRecord).filter(PublishRecord.run_id == "digest-fail-1").first()
    assert publish_record is not None
    assert publish_record.status == "failed"
    assert "publish failed" in publish_record.response_payload
    db.close()
