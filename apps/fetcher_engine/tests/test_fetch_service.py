from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from apps.fetcher_engine.api.models import FetchBatchRequest
from apps.fetcher_engine.api.registry import FETCHER_REGISTRY
from apps.fetcher_engine.api.service import FetchService
from apps.workflow_engine.registry.contracts import SourceItem


Base = declarative_base()


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(Integer, primary_key=True)
    source_type = Column(String(64), nullable=False)
    source_id = Column(String(255), nullable=False)
    source_account = Column(String(255), nullable=True)
    source_url = Column(String(1024), nullable=True)
    title = Column(String(255), nullable=False)
    language = Column(String(16), nullable=False, default="zh")
    raw_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    tags_json = Column(Text, nullable=False, default="[]")
    score = Column(Float, nullable=False, default=0)
    publish_status = Column(String(32), nullable=False, default="pending")
    pipeline_status = Column(String(32), nullable=False, default="fetched")
    review_status = Column(String(32), nullable=False, default="pending")
    digest_included = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class SourceSubscription(Base):
    __tablename__ = "source_subscriptions"

    id = Column(Integer, primary_key=True)
    source_type = Column(String(64), nullable=False)
    source_name = Column(String(128), nullable=False)
    account_identifier = Column(String(255), nullable=True)
    feed_url = Column(String(1024), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    default_tags = Column(String(512), nullable=True)
    last_cursor = Column(String(512), nullable=True)


@dataclass
class _FakeFetcher:
    items: list[SourceItem]
    should_fail: bool = False

    async def fetch(self, request):  # noqa: ANN001
        del request
        if self.should_fail:
            raise RuntimeError("fetch failed")
        return list(self.items)


class _RepoNamespace:
    ContentItem = ContentItem
    SourceSubscription = SourceSubscription

    @staticmethod
    def create_content_item(db: Session, **kwargs):
        item = ContentItem(**kwargs)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def _create_subscription(db: Session, source_type: str, source_name: str, account_identifier: str) -> SourceSubscription:
    subscription = SourceSubscription(
        source_type=source_type,
        source_name=source_name,
        account_identifier=account_identifier,
        enabled=True,
        default_tags="python,ai",
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def test_fetch_service_runs_single_source_and_inserts_items():
    db = _create_session()
    _create_subscription(db, "cnblogs", "CNBlogs", "cnblogs-default")
    FETCHER_REGISTRY["cnblogs"] = lambda **kwargs: _FakeFetcher(  # noqa: ARG005
        items=[
            SourceItem(
                source_type="cnblogs",
                source_id="post-1",
                title="First Post",
                source_url="https://example.com/1",
                raw_content="summary-1",
                metadata={"adapter": "test"},
            )
        ]
    )
    service = FetchService(db, _RepoNamespace)

    result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-1", sources=["cnblogs"])))

    assert result.stats.total_fetched == 1
    assert result.stats.total_inserted == 1
    assert result.stats.total_deduped == 0
    assert len(result.items) == 1
    assert db.query(ContentItem).count() == 1


def test_fetch_service_keeps_running_when_one_source_fails():
    db = _create_session()
    _create_subscription(db, "cnblogs", "CNBlogs", "cnblogs-default")
    _create_subscription(db, "bilibili", "Bilibili", "bilibili-default")
    FETCHER_REGISTRY["cnblogs"] = lambda **kwargs: _FakeFetcher(items=[], should_fail=True)  # noqa: ARG005
    FETCHER_REGISTRY["bilibili"] = lambda **kwargs: _FakeFetcher(  # noqa: ARG005
        items=[
            SourceItem(
                source_type="bilibili",
                source_id="video-1",
                title="Video One",
                source_url="https://example.com/video-1",
                raw_content="summary-2",
                metadata={},
            )
        ]
    )
    service = FetchService(db, _RepoNamespace)

    result = asyncio.run(
        service.run_sources(FetchBatchRequest(run_id="run-2", sources=["cnblogs", "bilibili"]))
    )

    assert len(result.errors) == 1
    assert result.errors[0].source == "cnblogs"
    assert result.stats.total_fetched == 1
    assert result.stats.total_inserted == 1
    assert db.query(ContentItem).count() == 1


def test_fetch_service_dedupes_items_before_insert():
    db = _create_session()
    _create_subscription(db, "cnblogs", "CNBlogs", "cnblogs-default")
    existing = ContentItem(
        source_type="cnblogs",
        source_id="post-1",
        title="Existing Post",
        language="zh",
        tags_json="[]",
        score=0,
        publish_status="pending",
        pipeline_status="fetched",
        review_status="pending",
        digest_included=False,
    )
    db.add(existing)
    db.commit()
    FETCHER_REGISTRY["cnblogs"] = lambda **kwargs: _FakeFetcher(  # noqa: ARG005
        items=[
            SourceItem(
                source_type="cnblogs",
                source_id="post-1",
                title="Duplicate Post",
                source_url="https://example.com/1",
                raw_content="dup",
                metadata={},
            ),
            SourceItem(
                source_type="cnblogs",
                source_id="post-1",
                title="Duplicate Post Again",
                source_url="https://example.com/1",
                raw_content="dup",
                metadata={},
            ),
        ]
    )
    service = FetchService(db, _RepoNamespace)

    result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-3", sources=["cnblogs"])))

    assert result.stats.total_fetched == 2
    assert result.stats.total_inserted == 0
    assert result.stats.total_deduped == 2
    assert db.query(ContentItem).count() == 1
