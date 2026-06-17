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
from models import SourceSubscription  # noqa: F401
from routers.sources import router


def _build_client() -> TestClient:
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
    return TestClient(app)


def test_list_sources_returns_all_items() -> None:
    client = _build_client()
    create_response = client.post(
        "/api/internal/content/sources/",
        json={
            "source_type": "rss",
            "source_name": "Python Blog",
            "account_identifier": "python-blog",
            "feed_url": "https://example.com/feed.xml",
        },
    )
    assert create_response.status_code == 201

    response = client.get("/api/internal/content/sources/")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) == 1
    assert body["data"][0]["source_name"] == "Python Blog"


def test_create_source_creates_new_source() -> None:
    client = _build_client()
    response = client.post(
        "/api/internal/content/sources/",
        json={
            "source_type": "reddit",
            "source_name": "Python Subreddit",
            "account_identifier": "r/python",
            "category": "community",
            "default_tags": "[\"python\"]",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["enabled"] is True
    assert body["data"]["source_type"] == "reddit"


def test_update_source_updates_fields() -> None:
    client = _build_client()
    create_response = client.post(
        "/api/internal/content/sources/",
        json={
            "source_type": "cnblogs",
            "source_name": "Old Name",
            "account_identifier": "cnblogs-user",
        },
    )
    source_id = create_response.json()["data"]["id"]

    response = client.patch(
        f"/api/internal/content/sources/{source_id}",
        json={
            "source_name": "New Name",
            "schedule_expression": "0 9 * * *",
            "default_tags": "[\"ai\",\"python\"]",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["source_name"] == "New Name"
    assert body["data"]["default_tags"] == "[\"ai\",\"python\"]"


def test_enable_and_disable_source_toggle_enabled_flag() -> None:
    client = _build_client()
    create_response = client.post(
        "/api/internal/content/sources/",
        json={
            "source_type": "bilibili",
            "source_name": "B 站",
            "account_identifier": "up-1",
        },
    )
    source_id = create_response.json()["data"]["id"]

    disable_response = client.post(f"/api/internal/content/sources/{source_id}/disable")
    assert disable_response.status_code == 200
    assert disable_response.json()["data"]["enabled"] is False

    enable_response = client.post(f"/api/internal/content/sources/{source_id}/enable")
    assert enable_response.status_code == 200
    assert enable_response.json()["data"]["enabled"] is True


def test_duplicate_source_returns_409() -> None:
    client = _build_client()
    payload = {
        "source_type": "rss",
        "source_name": "Dup Source",
        "account_identifier": "dup-account",
    }
    first_response = client.post("/api/internal/content/sources/", json=payload)
    assert first_response.status_code == 201

    second_response = client.post("/api/internal/content/sources/", json=payload)
    assert second_response.status_code == 409
