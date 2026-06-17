from __future__ import annotations

import asyncio

from apps.workflow_engine.pipeline.filter_node import FilterNode
from apps.workflow_engine.registry.contracts import ContentAsset


def test_filter_node_applies_include_exclude_rules() -> None:
    node = FilterNode()
    items = [
        ContentAsset(content_id=1, source_type="rss", source_id="a", title="Python news", raw_content="FastAPI"),
        ContentAsset(content_id=2, source_type="rss", source_id="b", title="Blocked news", raw_content="ad content"),
    ]

    result = asyncio.run(
        node.apply(
            items,
            {"include_keywords": ["python"], "exclude_keywords": ["blocked"]},
        )
    )

    assert len(result.items) == 1
    assert result.items[0].source_id == "a"


def test_filter_node_marks_duplicate_items() -> None:
    node = FilterNode()
    items = [
        ContentAsset(content_id=1, source_type="rss", source_id="dup", title="Python news", raw_content="A"),
        ContentAsset(content_id=2, source_type="rss", source_id="dup", title="Python news", raw_content="A"),
    ]

    result = asyncio.run(node.apply(items, {}))

    assert len(result.items) == 1
    assert any(entry["reason"] == "duplicate" for entry in result.filtered_out)


def test_filter_node_filters_when_include_keywords_missing() -> None:
    node = FilterNode()
    items = [
        ContentAsset(content_id=1, source_type="rss", source_id="x", title="Rust news", raw_content="Tokio"),
    ]

    result = asyncio.run(node.apply(items, {"include_keywords": ["python"]}))

    assert result.items == []
    assert result.filtered_out[0]["reason"] == "keyword_not_included"
