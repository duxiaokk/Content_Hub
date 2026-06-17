from __future__ import annotations

import asyncio

import pytest

from apps.ai_processor.processors.rewrite.processor import RewriteProcessor
from apps.workflow_engine.registry.contracts import AIProcessorConfig, ContentAsset, ProcessContext


def _config(fallback_strategy: str) -> AIProcessorConfig:
    return AIProcessorConfig(
        llm_provider="openai",
        model="broken-model",
        max_tokens_per_call=128,
        timeout_seconds=1,
        fallback_strategy=fallback_strategy,
        enable_cost_tracking=True,
        default_rewrite_profile="zh_tech_blog",
        rewrite_score_threshold=0.5,
    )


def _asset(raw_content: str = "Original body") -> ContentAsset:
    return ContentAsset(
        content_id=1,
        source_type="rss",
        source_id="item-1",
        title="Test title",
        raw_content=raw_content,
        source_url="https://example.com/item-1",
        metadata={},
    )


def test_rewrite_processor_returns_fallback_raw() -> None:
    result = asyncio.run(RewriteProcessor(_config("raw")).process(_asset(), ProcessContext()))

    assert result.status == "fallback_raw"
    assert result.content.metadata["rewritten_title"] == "Test title"


def test_rewrite_processor_returns_skipped_when_strategy_is_skip() -> None:
    result = asyncio.run(RewriteProcessor(_config("skip")).process(_asset(), ProcessContext()))

    assert result.status == "skipped"


def test_rewrite_processor_skips_empty_raw_content() -> None:
    result = asyncio.run(RewriteProcessor(_config("raw")).process(_asset(""), ProcessContext()))

    assert result.status == "skipped"
    assert "empty raw content" in result.warnings
