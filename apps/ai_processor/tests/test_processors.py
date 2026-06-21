from __future__ import annotations

import asyncio
import json
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("CONTENT_HUB_DEFAULT_REWRITE_PROFILE", "zh_tech_blog")

from apps.ai_processor.api.profiles import load_rewrite_profile
from apps.ai_processor.api.service import AIProcessingService
from apps.ai_processor.processors.classify.processor import ClassifyProcessor
from apps.ai_processor.processors.rewrite import processor as rewrite_processor_module
from apps.ai_processor.processors.rewrite.processor import RewriteProcessor
from apps.ai_processor.processors.summarize.processor import SummarizeProcessor
from apps.ai_processor.processors.tag.processor import TagProcessor
from apps.platform.database import Base
from apps.platform.models import ContentItem, RewriteProfile
from apps.workflow_engine.registry.contracts import AIProcessorConfig, ContentAsset, ProcessContext


def _config() -> AIProcessorConfig:
    return AIProcessorConfig(
        llm_provider="local",
        model="mock-model",
        max_tokens_per_call=256,
        timeout_seconds=30,
        fallback_strategy="raw",
        enable_cost_tracking=True,
        default_rewrite_profile="zh_tech_blog",
        rewrite_score_threshold=0.5,
    )


def _asset(title: str, raw_content: str) -> ContentAsset:
    return ContentAsset(
        content_id=1,
        source_type="rss",
        source_id="item-1",
        title=title,
        raw_content=raw_content,
        source_url="https://example.com/item-1",
        metadata={},
    )


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def test_summarize_processor_returns_summary():
    processor = SummarizeProcessor(_config())

    result = asyncio.run(processor.process(_asset("LLM news", "This is a long raw content about agents."), ProcessContext()))

    assert "summary" in result.content.metadata
    assert result.status == "processed"
    assert result.cost_tokens > 0


def test_classify_processor_returns_category_by_rule():
    processor = ClassifyProcessor(_config())
    asset = _asset("Agent workflow", "About orchestration")
    asset.metadata["summary"] = "LLM and RAG system"

    result = asyncio.run(processor.process(asset, ProcessContext()))

    assert result.content.metadata["category"] == "AI/LLM"


def test_tag_processor_returns_tags_by_rule():
    processor = TagProcessor(_config())
    asset = _asset("Python FastAPI guide", "Build an API with FastAPI")
    asset.metadata["summary"] = "Python FastAPI tutorial"

    result = asyncio.run(processor.process(asset, ProcessContext()))

    assert "Python" in result.content.metadata["tags"]
    assert "FastAPI" in result.content.metadata["tags"]


def test_processors_have_fallback_when_llm_fails():
    config = AIProcessorConfig(
        llm_provider="openai",
        model="broken-model",
        max_tokens_per_call=256,
        timeout_seconds=1,
        fallback_strategy="raw",
        enable_cost_tracking=True,
    )
    processor = SummarizeProcessor(config)

    result = asyncio.run(processor.process(_asset("Test", "Fallback content"), ProcessContext()))

    assert result.status == "fallback_raw"
    assert result.content.metadata["summary"] == "Fallback content"


def test_ai_processing_service_updates_content_item_fields():
    db = _create_session()
    profile = RewriteProfile(
        name="zh_tech_blog",
        provider="local",
        model="mock-model",
        timeout_seconds=30,
        fallback_strategy="raw",
        system_prompt="请改写为中文技术博客。",
        max_tokens=256,
    )
    db.add(profile)
    item = ContentItem(
        source_type="rss",
        source_id="item-1",
        title="Python Agent update",
        source_url="https://example.com/item-1",
        language="zh",
        raw_content="Python Agent with FastAPI and RAG content",
        tags_json="[]",
        score=0,
        publish_status="pending",
        pipeline_status="fetched",
        review_status="pending",
        digest_included=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    service = AIProcessingService(db, _config())
    result = asyncio.run(service.process_content_item(item.id, ProcessContext(run_id="run-ai-1")))

    db.refresh(item)
    assert item.summary
    assert json.loads(item.tags_json)
    assert item.score > 0
    assert item.pipeline_status == "processed"
    assert result.content.metadata["category"] == "AI/LLM"
    assert item.rewritten_title
    assert item.rewritten_content


def test_load_rewrite_profile_uses_default_profile():
    db = _create_session()
    db.add(
        RewriteProfile(
            name="zh_tech_blog",
            provider="local",
            model="mock-model",
            timeout_seconds=30,
            fallback_strategy="raw",
            system_prompt="default profile prompt",
            max_tokens=512,
        )
    )
    db.commit()

    profile = load_rewrite_profile(db, None)

    assert profile.name == "zh_tech_blog"
    assert profile.config.model == "mock-model"
    assert profile.system_prompt == "default profile prompt"


def test_rewrite_processor_fallback_skip_and_raw():
    asset = _asset("Test title", "Original body")

    raw_processor = RewriteProcessor(
        AIProcessorConfig(
            llm_provider="openai",
            model="broken-model",
            max_tokens_per_call=128,
            timeout_seconds=1,
            fallback_strategy="raw",
            enable_cost_tracking=True,
            default_rewrite_profile="zh_tech_blog",
            rewrite_score_threshold=0.5,
        )
    )
    raw_result = asyncio.run(raw_processor.process(asset, ProcessContext()))
    assert raw_result.status == "fallback_raw"
    assert raw_result.content.metadata["rewritten_title"] == "Test title"

    skip_processor = RewriteProcessor(
        AIProcessorConfig(
            llm_provider="openai",
            model="broken-model",
            max_tokens_per_call=128,
            timeout_seconds=1,
            fallback_strategy="skip",
            enable_cost_tracking=True,
            default_rewrite_profile="zh_tech_blog",
            rewrite_score_threshold=0.5,
        )
    )
    skip_result = asyncio.run(skip_processor.process(asset, ProcessContext()))
    assert skip_result.status == "skipped"


def test_ai_processing_service_skips_rewrite_for_low_score():
    db = _create_session()
    item = ContentItem(
        source_type="rss",
        source_id="item-low",
        title="Generic update",
        source_url="https://example.com/item-low",
        language="zh",
        raw_content="Short text",
        tags_json="[]",
        score=0,
        publish_status="pending",
        pipeline_status="fetched",
        review_status="pending",
        digest_included=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    config = AIProcessorConfig(
        llm_provider="local",
        model="mock-model",
        max_tokens_per_call=256,
        timeout_seconds=30,
        fallback_strategy="raw",
        enable_cost_tracking=True,
        default_rewrite_profile="zh_tech_blog",
        rewrite_score_threshold=99.0,
    )
    service = AIProcessingService(db, config)
    result = asyncio.run(service.process_content_item(item.id, ProcessContext(run_id="run-ai-low")))

    db.refresh(item)
    assert item.rewritten_title is None
    assert item.rewritten_content is None
    assert result.content.metadata["rewritten_title"] is None


def test_rewrite_processor_self_critique_retries_once(monkeypatch: pytest.MonkeyPatch):
    class SequencedProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, **_kwargs):  # noqa: ANN003
            self.calls += 1
            responses = [
                "Title: Bad Draft\nContent: Too short",
                "Score: 0.2\nPass: no\nFeedback: 正文过短，需要补充事实和技术细节",
                "Title: 改进后的标题\nContent: 这是一篇补充了事实和技术细节的中文技术博客改写版本，包含更多上下文。",
            ]
            return responses[self.calls - 1]

    provider = SequencedProvider()
    monkeypatch.setattr(rewrite_processor_module, "build_provider", lambda _config: provider)
    processor = RewriteProcessor(_config())

    result = asyncio.run(
        processor.process(
            _asset("Original title", "Original technical content with enough details for rewrite."),
            ProcessContext(run_id="rewrite-1"),
        )
    )

    assert result.status == "processed"
    assert result.content.metadata["rewrite_attempts"] == 2
    assert result.content.title == "改进后的标题"
    assert "中文技术博客改写版本" in result.content.processed_content


def test_rewrite_processor_supports_multiple_self_critique_rounds(monkeypatch: pytest.MonkeyPatch):
    class SequencedProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, **_kwargs):  # noqa: ANN003
            self.calls += 1
            responses = [
                "Title: First Draft\nContent: short",
                "Score: 0.2\nPass: no\nFeedback: 内容太短",
                "Title: Second Draft\nContent: 还是有点短，但开始包含中文技术内容。",
                "Score: 0.5\nPass: no\nFeedback: 细节还不够",
                "Title: 最终标题\nContent: 这是一篇完整的中文技术博客改写，保留了事实、代码块和更多技术背景说明。",
                "Score: 0.9\nPass: yes\nFeedback: 质量通过",
            ]
            return responses[self.calls - 1]

    provider = SequencedProvider()
    monkeypatch.setattr(rewrite_processor_module, "build_provider", lambda _config: provider)
    processor = RewriteProcessor(_config())

    result = asyncio.run(
        processor.process(
            _asset("Original title", "Original technical content with enough details for rewrite."),
            ProcessContext(
                run_id="rewrite-2",
                options={"rewrite_self_critique_rounds": 3, "rewrite_self_critique_threshold": 0.8},
            ),
        )
    )

    assert result.status == "processed"
    assert result.content.metadata["rewrite_attempts"] == 3
    assert len(result.content.metadata["rewrite_critique_history"]) == 3
    assert result.content.title == "最终标题"


def test_rewrite_processor_uses_memory_preferences_in_system_prompt(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}

    class RecordingProvider:
        async def chat(self, **kwargs):  # noqa: ANN003
            captured["system_prompt"] = kwargs["system_prompt"]
            return "Title: 偏好标题\nContent: 这是一篇符合偏好要求的中文技术博客。"

    monkeypatch.setattr(rewrite_processor_module, "build_provider", lambda _config: RecordingProvider())
    processor = RewriteProcessor(_config())

    result = asyncio.run(
        processor.process(
            _asset("Original title", "Original technical content with enough details for rewrite."),
            ProcessContext(
                run_id="rewrite-3",
                options={
                    "enable_self_critique": False,
                    "rewrite_preferences": {"voice": "technical", "tone": "concise", "blocked_tags": ["营销"]},
                },
            ),
        )
    )

    assert result.status == "processed"
    assert "文风偏好：technical" in captured["system_prompt"]
    assert "避免提及标签：营销" in captured["system_prompt"]
