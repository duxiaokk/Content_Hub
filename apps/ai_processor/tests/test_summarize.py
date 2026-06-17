from __future__ import annotations

import asyncio

import pytest

from apps.ai_processor.processors.summarize.processor import SummarizeProcessor
from apps.workflow_engine.registry.contracts import AIProcessorConfig, ContentAsset, ProcessContext


def _config(provider: str = "local") -> AIProcessorConfig:
    return AIProcessorConfig(
        llm_provider=provider,
        model="mock-model",
        max_tokens_per_call=256,
        timeout_seconds=1,
        fallback_strategy="raw",
        enable_cost_tracking=True,
    )


def _asset(raw_content: str) -> ContentAsset:
    return ContentAsset(
        content_id=1,
        source_type="rss",
        source_id="item-1",
        title="Agent update",
        raw_content=raw_content,
        source_url="https://example.com/item-1",
        metadata={},
    )


def test_summarize_processor_returns_summary() -> None:
    result = asyncio.run(SummarizeProcessor(_config()).process(_asset("Long content about agents"), ProcessContext()))

    assert result.status == "processed"
    assert result.content.metadata["summary"]


def test_summarize_processor_skips_empty_content() -> None:
    result = asyncio.run(SummarizeProcessor(_config()).process(_asset(""), ProcessContext()))

    assert result.status == "skipped"
    assert result.content.metadata["summary"] == ""


def test_summarize_processor_falls_back_when_provider_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    processor = SummarizeProcessor(_config(provider="openai"))

    class _FailingProvider:
        async def chat(self, **kwargs):  # noqa: ANN003
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr("apps.ai_processor.processors.summarize.processor.build_provider", lambda config: _FailingProvider())

    result = asyncio.run(processor.process(_asset("Fallback body"), ProcessContext()))

    assert result.status == "fallback_raw"
    assert result.content.metadata["summary"] == "Fallback body"
