from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.platform.services.console_service import build_content_source_id, sync_content_items_from_result


class DummyDB:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.refresh_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def refresh(self, _obj) -> None:  # noqa: ANN001
        self.refresh_calls += 1


def test_sync_content_items_from_result_uses_inline_items(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class StubRepository:
        def upsert_fetched_item(self, item) -> int:  # noqa: ANN001
            calls.append((item.source_type, item.source_id))
            state["created"] = True
            return 1

        def attach_fetch_context(self, **kwargs) -> None:  # noqa: ANN003
            updated_items["attach_fetch_context"] = kwargs

    monkeypatch.setattr("apps.platform.services.console_service.ContentRepository", StubRepository)

    updated_items = {}
    state = {"created": False}

    def fake_get_content_item_by_source(_db, source_type: str, source_id: str):
        if not state["created"]:
            return None
        return SimpleNamespace(
            id=1,
            source_type=source_type,
            source_id=source_id,
            source_url=None,
            title="old",
            raw_content=None,
            processed_content=None,
            publish_status="pending",
            pipeline_status="fetched",
            review_status="pending_review",
            reviewed_by=None,
            reviewed_at=None,
            draft_post_id=None,
            error_message=None,
            source_config_id=None,
            fetch_run_id=None,
        )

    def fake_update_content_item(_db, item, **kwargs):  # noqa: ANN001
        updated_items.update(kwargs)
        return item

    monkeypatch.setattr("apps.platform.services.console_service.get_content_item_by_source", fake_get_content_item_by_source)
    monkeypatch.setattr("apps.platform.services.console_service.update_content_item", fake_update_content_item)

    db = DummyDB()
    inserted = sync_content_items_from_result(
        db,
        fetch_run=SimpleNamespace(id=9),
        source=SimpleNamespace(id=3, source_type="cnblogs"),
        result={
            "items": [
                {
                    "title": "Example",
                    "link": "https://example.com/post",
                    "content": "hello",
                }
            ]
        },
    )

    assert inserted == 1
    assert calls == [("cnblogs", "https://example.com/post")]
    assert updated_items["attach_fetch_context"]["fetch_run_id"] == 9
    assert updated_items["fetch_run_id"] == 9
    assert updated_items["pipeline_status"] == "processed"


def test_build_content_source_id_prefers_dedup_key() -> None:
    assert build_content_source_id({"dedup_key": "abc", "link": "x", "title": "y"}) == "abc"
