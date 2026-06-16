from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from services.content_domain_client import ContentDomainClient


@pytest.mark.anyio
async def test_content_domain_client_prepare_review_items(monkeypatch) -> None:
    client = ContentDomainClient()

    class StubWorkflowService:
        async def run_content_radar(self, _payload):
            return {
                "run_id": "run-1",
                "review_items": [{"content_item_id": 1, "title": "demo"}],
                "errors": [],
            }

    monkeypatch.setattr(client, "_get_workflow_service", lambda: StubWorkflowService())

    result = await client.prepare_review_items({"run_id": "run-1"})

    assert result.run_id == "run-1"
    assert result.status == "success"
    assert result.data["review_items"][0]["content_item_id"] == 1
