from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from apps.platform.database import Base
from apps.platform.models import ContentItem, PublishRecord, ReviewQueue, RewriteProfile, WorkflowRun
from apps.workflow_engine.api.service import WorkflowEngineService
from apps.workflow_engine.pipeline.filter_node import FilterNode
from apps.workflow_engine.registry.contracts import ContentAsset, DigestResult, FilterResult, ReviewItem
from apps.workflow_engine.registry.static_registry import RADAR_PIPELINE_STEPS


def test_contract_imports_work():
    assert FilterResult is not None
    assert ReviewItem is not None
    assert DigestResult is not None


def test_filter_node_applies_include_exclude_and_dedup():
    node = FilterNode()
    items = [
        ContentAsset(content_id=1, source_type="rss", source_id="a", title="Python news", raw_content="FastAPI"),
        ContentAsset(content_id=2, source_type="rss", source_id="a", title="Python news", raw_content="FastAPI"),
        ContentAsset(content_id=3, source_type="rss", source_id="b", title="Rust news", raw_content="Tokio"),
    ]

    result = asyncio.run(
        node.apply(
            items,
            {"include_keywords": ["python"], "exclude_keywords": ["blocked"]},
        )
    )

    assert len(result.items) == 1
    assert result.items[0].source_id == "a"
    assert any(entry["reason"] == "duplicate" for entry in result.filtered_out)


def test_radar_pipeline_steps_registered():
    assert len(RADAR_PIPELINE_STEPS) == 6
    assert [step["name"] for step in RADAR_PIPELINE_STEPS] == [
        "fetch",
        "dedup_filter",
        "summarize",
        "classify_tag",
        "rewrite",
        "review_prepare",
    ]


def test_workflow_service_runs_radar_pipeline():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module
    import apps.workflow_engine.runtime.content_repository as content_repository_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    original_repository_session = content_repository_module.SessionLocal
    platform_database.SessionLocal = factory
    workflow_service_module.SessionLocal = factory
    content_repository_module.SessionLocal = factory
    try:
        db = factory()
        db.add(
            RewriteProfile(
                name="zh_tech_blog",
                provider="local",
                model="mock-model",
                timeout_seconds=30,
                fallback_strategy="raw",
                system_prompt="请改写为中文技术博客。",
                max_tokens=256,
            )
        )
        db.add(
            ContentItem(
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
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        result = asyncio.run(
            service.run_radar_pipeline(
                {
                    "run_id": "radar-1",
                    "source_type": "rss",
                    "limit": 10,
                    "filter_config": {"include_keywords": ["python"]},
                }
            )
        )

        assert result["pipeline"] == "radar_pipeline"
        assert result["errors"] == []
        assert len(result["review_items"]) == 1
        assert result["review_items"][0]["score"] > 0
        assert result["trace_payload"]["total_token_cost"] > 0
        assert [step["name"] for step in result["trace_payload"]["steps"]] == ["fetch", "dedup_filter", "process", "review_prepare"]
        verify_db = factory()
        workflow_run = verify_db.query(WorkflowRun).filter(WorkflowRun.id == result["workflow_run_id"]).first()
        assert workflow_run is not None
        assert workflow_run.status == "success"
        assert workflow_run.items_total == 1
        assert workflow_run.items_succeeded == 1
        assert workflow_run.items_failed == 0
        verify_db.close()
        assert json.loads(result["review_items"][0]["tags"]) if isinstance(result["review_items"][0]["tags"], str) else result["review_items"][0]["tags"]
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session


def test_workflow_service_filters_radar_pipeline_by_fetch_run_id():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module
    import apps.workflow_engine.runtime.content_repository as content_repository_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    original_repository_session = content_repository_module.SessionLocal
    platform_database.SessionLocal = factory
    workflow_service_module.SessionLocal = factory
    content_repository_module.SessionLocal = factory
    try:
        db = factory()
        db.add(
            RewriteProfile(
                name="zh_tech_blog",
                provider="local",
                model="mock-model",
                timeout_seconds=30,
                fallback_strategy="raw",
                system_prompt="test prompt",
                max_tokens=256,
            )
        )
        db.add(
            ContentItem(
                source_type="rss",
                source_id="item-fetch-run-1",
                fetch_run_id=11,
                title="Python Agent update",
                source_url="https://example.com/item-fetch-run-1",
                language="zh",
                raw_content="Python Agent with FastAPI content",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="fetched",
                review_status="pending",
                digest_included=False,
            )
        )
        db.add(
            ContentItem(
                source_type="rss",
                source_id="item-fetch-run-2",
                fetch_run_id=22,
                title="Other update",
                source_url="https://example.com/item-fetch-run-2",
                language="zh",
                raw_content="Other content",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="fetched",
                review_status="pending",
                digest_included=False,
            )
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        result = asyncio.run(
            service.run_radar_pipeline(
                {
                    "run_id": "radar-fetch-run-1",
                    "fetch_run_id": 11,
                    "limit": 10,
                }
            )
        )

        assert result["errors"] == []
        assert len(result["review_items"]) == 1
        assert result["review_items"][0]["original_url"] == "https://example.com/item-fetch-run-1"
        verify_db = factory()
        queues = verify_db.query(ReviewQueue).order_by(ReviewQueue.content_item_id.asc()).all()
        items = verify_db.query(ContentItem).order_by(ContentItem.id.asc()).all()
        assert len(queues) == 1
        assert int(queues[0].content_item_id) == int(items[0].id)
        assert queues[0].status == "pending"
        assert items[0].fetch_run_id == 11
        assert items[0].review_status == "pending"
        assert items[1].fetch_run_id == 22
        assert items[1].review_status == "pending"
        verify_db.close()
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session


def test_workflow_service_creates_review_queue_entries_for_processed_items():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module
    import apps.workflow_engine.runtime.content_repository as content_repository_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    original_repository_session = content_repository_module.SessionLocal
    platform_database.SessionLocal = factory
    workflow_service_module.SessionLocal = factory
    content_repository_module.SessionLocal = factory
    try:
        db = factory()
        db.add(
            RewriteProfile(
                name="zh_tech_blog",
                provider="local",
                model="mock-model",
                timeout_seconds=30,
                fallback_strategy="raw",
                system_prompt="test prompt",
                max_tokens=256,
            )
        )
        db.add(
            ContentItem(
                source_type="rss",
                source_id="item-queue-1",
                fetch_run_id=33,
                title="Queue item",
                source_url="https://example.com/item-queue-1",
                language="zh",
                raw_content="Queue content with Python",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="fetched",
                review_status="pending",
                digest_included=False,
            )
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        result = asyncio.run(
            service.run_radar_pipeline(
                {
                    "run_id": "radar-review-queue",
                    "fetch_run_id": 33,
                    "limit": 10,
                }
            )
        )

        assert result["errors"] == []
        assert len(result["review_items"]) == 1
        assert len(result["review_queue_ids"]) == 1

        verify_db = factory()
        item = verify_db.query(ContentItem).filter(ContentItem.source_id == "item-queue-1").first()
        review = verify_db.query(ReviewQueue).filter(ReviewQueue.content_item_id == item.id).first()
        assert item is not None
        assert item.pipeline_status == "processed"
        assert item.review_status == "pending"
        assert review is not None
        assert review.status == "pending"
        assert review.candidate_title == item.rewritten_title
        assert review.candidate_content == item.rewritten_content
        verify_db.close()
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session


def test_workflow_service_records_failed_trace_when_stop_on_error():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module
    import apps.workflow_engine.runtime.content_repository as content_repository_module
    from apps.ai_processor.api.service import AIProcessingService

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    original_repository_session = content_repository_module.SessionLocal
    original_process = AIProcessingService.process_content_item
    platform_database.SessionLocal = factory
    workflow_service_module.SessionLocal = factory
    content_repository_module.SessionLocal = factory

    async def failing_process(self, content_item_id, context):
        raise RuntimeError("processor exploded")

    AIProcessingService.process_content_item = failing_process
    try:
        db = factory()
        db.add(
            RewriteProfile(
                name="zh_tech_blog",
                provider="local",
                model="mock-model",
                timeout_seconds=30,
                fallback_strategy="raw",
                system_prompt="test prompt",
                max_tokens=256,
            )
        )
        db.add(
            ContentItem(
                source_type="rss",
                source_id="item-2",
                title="Failure item",
                source_url="https://example.com/item-2",
                language="zh",
                raw_content="Failure content",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="fetched",
                review_status="pending",
                digest_included=False,
            )
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        result = asyncio.run(
            service.run_radar_pipeline(
                {
                    "run_id": "radar-fail",
                    "source_type": "rss",
                    "limit": 10,
                    "stop_on_error": True,
                }
            )
        )

        assert len(result["errors"]) == 1
        assert result["trace_payload"]["error_summary"] == "processor exploded"
        verify_db = factory()
        workflow_run = verify_db.query(WorkflowRun).filter(WorkflowRun.id == result["workflow_run_id"]).first()
        assert workflow_run is not None
        assert workflow_run.status == "failed"
        assert workflow_run.items_total == 1
        assert workflow_run.items_succeeded == 0
        assert workflow_run.items_failed == 1
        assert workflow_run.error_summary == "processor exploded"
        verify_db.close()
    finally:
        AIProcessingService.process_content_item = original_process
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
        content_repository_module.SessionLocal = original_repository_session


def test_should_skip_publish_on_success_or_same_run():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import apps.platform.database as platform_database
    import apps.workflow_engine.api.service as workflow_service_module

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    original_platform_session = platform_database.SessionLocal
    original_workflow_session = workflow_service_module.SessionLocal
    platform_database.SessionLocal = factory
    workflow_service_module.SessionLocal = factory
    try:
        db = factory()
        db.add(
            ContentItem(
                source_type="rss",
                source_id="item-3",
                title="Publish item",
                source_url="https://example.com/item-3",
                language="zh",
                raw_content="Publish content",
                tags_json="[]",
                score=0,
                publish_status="pending",
                pipeline_status="processed",
                review_status="pending",
                digest_included=False,
            )
        )
        db.commit()
        item = db.query(ContentItem).filter(ContentItem.source_id == "item-3").first()
        item_id = int(item.id)
        db.add(
            PublishRecord(
                content_item_id=item_id,
                target_type="blog",
                target_name="blog",
                status="success",
                run_id="run-a",
            )
        )
        db.commit()
        db.close()

        service = WorkflowEngineService()
        assert service.should_skip_publish(content_item_id=item_id, target_type="blog") is True
        assert service.should_skip_publish(content_item_id=item_id, target_type="blog", run_id="run-a") is True
        assert service.should_skip_publish(content_item_id=item_id, target_type="wechat", run_id="run-b") is False
    finally:
        platform_database.SessionLocal = original_platform_session
        workflow_service_module.SessionLocal = original_workflow_session
