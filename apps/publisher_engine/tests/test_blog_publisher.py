from __future__ import annotations

import os
import sys
from pathlib import Path


def test_blog_publisher_disabled_mode() -> None:
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["ADO_PUBLISH_ENABLED"] = "false"
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from publisher_engine.adapters.blog.publisher import BlogPublisher
    from workflow_engine.registry.contracts import ContentAsset, PublishTarget

    publisher = BlogPublisher()
    result = __import__("asyncio").run(
        publisher.publish(
            ContentAsset(
                content_id=None,
                source_type="cnblogs",
                source_id="1",
                title="Example",
                raw_content="raw",
                processed_content="processed",
                source_url="https://example.com/post/1",
            ),
            PublishTarget(target_name="blog"),
        )
    )

    assert result.status == "disabled"


def test_blog_publisher_publish_draft_maps_to_success(monkeypatch) -> None:
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["ADO_PUBLISH_ENABLED"] = "true"
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from publisher_engine.adapters.blog.publisher import BlogPublisher
    from publisher_engine.runtime.models import PublishRequest
    from workflow_engine.registry.contracts import PublishResult

    async def fake_publish(self, content, target):
        return PublishResult(status="published", target_name=target.target_name, external_id="42")

    monkeypatch.setattr(BlogPublisher, "publish", fake_publish)

    publisher = BlogPublisher()
    result = __import__("asyncio").run(
        publisher.publish_draft(
            PublishRequest(
                content_item_id=1,
                candidate_title="Draft Title",
                candidate_content="Draft Content",
                target_type="blog",
                source_url="https://example.com/post/1",
                tags=["python"],
            )
        )
    )

    assert result.status == "success"
    assert result.external_id == "42"
    assert result.target_type == "blog"


def test_blog_publisher_publish_draft_maps_to_failed(monkeypatch) -> None:
    os.environ["SECRET_KEY"] = "test-secret-key"
    os.environ["ADO_PUBLISH_ENABLED"] = "true"
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from publisher_engine.adapters.blog.publisher import BlogPublisher
    from publisher_engine.runtime.models import PublishRequest
    from workflow_engine.registry.contracts import PublishResult

    async def fake_publish(self, content, target):
        return PublishResult(status="failed", target_name=target.target_name, error_message="network error")

    monkeypatch.setattr(BlogPublisher, "publish", fake_publish)

    publisher = BlogPublisher()
    result = __import__("asyncio").run(
        publisher.publish_draft(
            PublishRequest(
                content_item_id=2,
                candidate_title="Draft Title",
                candidate_content="Draft Content",
                target_type="blog",
            )
        )
    )

    assert result.status == "failed"
    assert result.message == "network error"
