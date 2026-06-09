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
