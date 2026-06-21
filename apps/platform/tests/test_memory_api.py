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
from apps.platform.routers.memory import router


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


def test_memory_api_writes_preference() -> None:
    client, _ = _build_client()

    response = client.post(
        "/api/internal/memory/preferences",
        json={
            "scope": "user",
            "scope_key": "user-9",
            "preference_key": "rewrite_style",
            "value": {"tone": "concise", "voice": "technical"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["memory_type"] == "preference"
    assert body["data"]["memory_key"] == "rewrite_style"


def test_memory_api_writes_feedback_and_searches() -> None:
    client, _ = _build_client()

    write_response = client.post(
        "/api/internal/memory/feedback",
        json={
            "scope": "workflow",
            "scope_key": "workflow-search",
            "feedback_key": "fact-check-note",
            "value": {"comment": "need fact check before publish"},
        },
    )
    assert write_response.status_code == 200

    search_response = client.post(
        "/api/internal/memory/search",
        json={
            "keyword": "fact check",
            "scopes": ["workflow"],
            "memory_type": "feedback",
            "limit": 10,
        },
    )

    assert search_response.status_code == 200
    body = search_response.json()
    assert body["code"] == 0
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["memory_key"] == "fact-check-note"
