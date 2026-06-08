from __future__ import annotations

import os
import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.config import settings
from core.mempool import get_pool
from database import Base, get_db
from main import app
from models import Post, User
from web_deps import get_optional_user


TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


class _FakeResp:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data
        self.text = ""

    def json(self):
        return self._json_data

    def raise_for_status(self) -> None:
        if 200 <= int(self.status_code) < 300:
            return
        raise RuntimeError(f"http {self.status_code}")


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    import core.mempool as mempool_module

    mempool_module._pool = None
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    mempool_module._pool = None


def test_create_draft_submits_audit_and_writes_shared_memory(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers})
            return _FakeResp(200, {"id": "task-audit-1", "trace_id": headers.get("x-trace-id")})

    import scheduler_client as scheduler_client_module

    sqlite_path = os.path.abspath(f"./.tmp_shared_memory_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SHARED_MEMORY_NAMESPACE", "test_task5")
    monkeypatch.setenv("SHARED_MEMORY_SQLITE_PATH", sqlite_path)
    monkeypatch.setenv("SCHEDULER_CENTER_URL", "http://scheduler.local")
    monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", "scheduler-token")
    monkeypatch.setattr(scheduler_client_module.httpx, "Client", FakeClient)

    resp = client.post(
        "/api/internal/agent/drafts",
        headers={"x-internal-token": settings.internal_agent_token},
        json={
            "title": "t",
            "summary": "s",
            "markdown_content": "# hi",
            "source_platform": "youtube",
            "source_link": "https://example.com",
            "source_external_id": "e1",
            "source_dedup_key": f"dedup-{uuid.uuid4().hex}",
            "tags": [],
            "raw_payload": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    draft_id = int(data["id"])

    assert len(calls) == 1
    assert calls[0]["url"] == "http://scheduler.local/api/internal/scheduler/tasks"
    assert calls[0]["headers"]["x-internal-token"] == "scheduler-token"
    assert calls[0]["json"]["task_type"] == "audit.draft"
    assert calls[0]["json"]["payload"]["draft_id"] == draft_id
    assert calls[0]["json"]["payload"]["title"] == "t"
    assert isinstance(calls[0]["json"]["payload"]["markdown_path"], str)

    stored = get_pool().get(f"agent_draft:audit:{draft_id}", default=None)
    assert stored == {"task_id": "task-audit-1", "trace_id": calls[0]["headers"].get("x-trace-id")}

    try:
        os.remove(sqlite_path)
    except OSError:
        pass


def test_create_comment_async_submits_comment_moderate_and_returns_trace_id(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers})
            return _FakeResp(200, {"id": "task-moderate-1", "trace_id": headers.get("x-trace-id")})

    import scheduler_client as scheduler_client_module

    monkeypatch.setenv("SCHEDULER_CENTER_URL", "http://scheduler.local")
    monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", "scheduler-token")
    monkeypatch.setattr(scheduler_client_module.httpx, "Client", FakeClient)

    def override_optional_user(request: Request):
        return "alice"

    app.dependency_overrides[get_optional_user] = override_optional_user

    db = TestingSessionLocal()
    post = Post(title="p1", tech_tag="t", like_count=0)
    user = User(username="alice", email="alice@example.com", hashed_password="x")
    db.add_all([post, user])
    db.commit()
    db.refresh(post)
    db.close()

    client.cookies.set("csrf_token", "csrf")
    resp = client.post(
        f"/posts/{int(post.id)}/comments",
        headers={"x-csrf-token": "csrf"},
        json={"content": "hello", "parent_id": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "trace_id" in data
    trace_id = data["trace_id"]

    assert len(calls) == 1
    assert calls[0]["json"]["task_type"] == "comment.moderate"
    assert calls[0]["headers"].get("x-trace-id") == trace_id
    assert calls[0]["json"]["payload"]["comment_id"] == int(data["id"])
    assert calls[0]["json"]["payload"]["post_id"] == int(post.id)
    assert calls[0]["json"]["payload"]["username"] == "alice"
    assert calls[0]["json"]["payload"]["content"] == "hello"


def test_internal_route_triggers_ado_repost_run(monkeypatch):
    calls: list[dict] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            calls.append({"url": url, "json": json, "headers": headers})
            return _FakeResp(200, {"id": "task-repost-1", "trace_id": headers.get("x-trace-id")})

    import scheduler_client as scheduler_client_module

    monkeypatch.setenv("SCHEDULER_CENTER_URL", "http://scheduler.local")
    monkeypatch.setenv("SCHEDULER_INTERNAL_TOKEN", "scheduler-token")
    monkeypatch.setattr(scheduler_client_module.httpx, "Client", FakeClient)

    resp = client.post(
        "/api/internal/tasks/ado-repost/run",
        headers={"x-internal-token": settings.internal_agent_token},
        json={"payload": {"dry_run": True}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "task-repost-1"
    assert "trace_id" in data

    assert len(calls) == 1
    assert calls[0]["json"]["task_type"] == "ado_repost.run"
    assert calls[0]["json"]["payload"] == {"dry_run": True}
