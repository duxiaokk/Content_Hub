from __future__ import annotations

import os
import tempfile
import uuid

from fastapi.testclient import TestClient


def test_audit_agent_run_writes_shared_memory(monkeypatch):
    sqlite_path = os.path.abspath(f"./.tmp_shared_memory_{uuid.uuid4().hex}.db")
    monkeypatch.setenv("SHARED_MEMORY_NAMESPACE", "test_audit_agent")
    monkeypatch.setenv("SHARED_MEMORY_SQLITE_PATH", sqlite_path)
    monkeypatch.setenv("AUDIT_AGENT_INTERNAL_TOKEN", "audit-token")
    monkeypatch.setenv("MOCK_LLM", "true")

    from audit_agent import app
    from core.mempool import get_pool

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write("# hello\n\ncontent")
        md_path = f.name

    client = TestClient(app)
    resp = client.post(
        "/api/internal/agent/run",
        headers={"x-internal-token": "audit-token"},
        json={
            "task_id": "t1",
            "trace_id": "trace-1",
            "attempt_no": 1,
            "task_type": "audit.draft",
            "payload": {"draft_id": 1, "markdown_path": md_path},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True

    stored = get_pool().get("audit:draft:1", default=None)
    assert isinstance(stored, dict)
    assert stored["draft_id"] == 1
    assert stored["task_id"] == "t1"

    try:
        os.remove(md_path)
    except OSError:
        pass
    try:
        os.remove(sqlite_path)
    except OSError:
        pass

