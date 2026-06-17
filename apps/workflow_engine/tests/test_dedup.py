from __future__ import annotations

import asyncio

from apps.workflow_engine.pipeline.filter_node import FilterNode
from apps.workflow_engine.registry.contracts import ContentAsset


def test_dedup_keeps_first_item_per_source_type_and_source_id() -> None:
    result = asyncio.run(
        FilterNode().apply(
            [
                ContentAsset(content_id=1, source_type="rss", source_id="same", title="First", raw_content="A"),
                ContentAsset(content_id=2, source_type="rss", source_id="same", title="Second", raw_content="B"),
                ContentAsset(content_id=3, source_type="reddit", source_id="same", title="Third", raw_content="C"),
            ],
            {},
        )
    )

    assert [(item.source_type, item.source_id) for item in result.items] == [("rss", "same"), ("reddit", "same")]


def test_dedup_reports_filtered_stats() -> None:
    result = asyncio.run(
        FilterNode().apply(
            [
                ContentAsset(content_id=1, source_type="rss", source_id="1", title="One", raw_content="A"),
                ContentAsset(content_id=2, source_type="rss", source_id="1", title="One", raw_content="A"),
            ],
            {},
        )
    )

    assert result.stats["input_count"] == 2
    assert result.stats["kept_count"] == 1
    assert result.stats["filtered_count"] == 1
