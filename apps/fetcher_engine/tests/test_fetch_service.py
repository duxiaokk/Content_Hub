from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from apps.fetcher_engine.api.models import FetchBatchRequest
from apps.fetcher_engine.api.registry import FETCHER_REGISTRY
from apps.fetcher_engine.api.service import FetchService
from apps.fetcher_engine.connectors.rss.fetcher import RssFetcher
from apps.fetcher_engine.runtime.rss import ParseError, RssFeedAdapter, RssFetchRequest, parse_rss_items
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
    last_cursor_updates: list[tuple[int, str]] = []

    @staticmethod
    def create_content_item(db: Session, **kwargs):
        item = ContentItem(**kwargs)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @classmethod
    def update_cursor(cls, db: Session, subscription: SourceSubscription, cursor_value: str) -> None:
        subscription.last_cursor = cursor_value
        db.add(subscription)
        db.commit()
        cls.last_cursor_updates.append((subscription.id, cursor_value))


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def _reset_repo_state() -> None:
    _RepoNamespace.last_cursor_updates.clear()


def _create_subscription(db: Session, source_type: str, source_name: str, account_identifier: str) -> SourceSubscription:
    subscription = SourceSubscription(
        source_type=source_type,
        source_name=source_name,
        account_identifier=account_identifier,
        feed_url=f"https://example.com/{account_identifier}.xml" if source_type == "rss" else None,
        enabled=True,
        default_tags="python,ai",
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def test_fetch_service_runs_single_source_and_inserts_items():
    _reset_repo_state()
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
    _reset_repo_state()
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
    _reset_repo_state()
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


def test_fetch_service_updates_last_cursor_for_rss_source():
    _reset_repo_state()
    db = _create_session()
    subscription = _create_subscription(db, "rss", "Example Feed", "rss-default")
    FETCHER_REGISTRY["rss"] = lambda **kwargs: _FakeFetcher(  # noqa: ARG005
        items=[
            SourceItem(
                source_type="rss",
                source_id="item-1",
                title="RSS Item",
                source_url="https://example.com/rss-1",
                raw_content="rss-summary",
                metadata={"published_at": "2026-06-12T10:00:00+00:00"},
            )
        ]
    )
    service = FetchService(db, _RepoNamespace)

    result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-4", sources=["rss"])))

    db.refresh(subscription)
    assert result.stats.total_inserted == 1
    assert subscription.last_cursor == "2026-06-12T10:00:00+00:00"
    assert _RepoNamespace.last_cursor_updates == [(subscription.id, "2026-06-12T10:00:00+00:00")]


def test_rss_fetcher_is_registered():
    FETCHER_REGISTRY["rss"] = RssFetcher
    fetcher_factory = FETCHER_REGISTRY.get("rss")

    assert fetcher_factory is RssFetcher


def test_parse_rss_items_raises_parse_error_for_invalid_xml():
    try:
        parse_rss_items("<rss><channel><item></rss>", source="rss", adapter="rss")
    except ParseError as exc:
        assert "invalid rss payload" in str(exc)
    else:
        raise AssertionError("ParseError was not raised")


def test_rss_adapter_applies_lookback_and_limit():
    class _FakeAdapter(RssFeedAdapter):
        def fetch(self, request: RssFetchRequest | None = None, cursor_store=None):  # noqa: ANN001
            return super().fetch(request=request, cursor_store=cursor_store)

    xml_text = """
    <rss>
      <channel>
        <item><title>A</title><link>https://example.com/a</link><guid>a</guid><pubDate>Fri, 12 Jun 2026 10:00:00 GMT</pubDate></item>
        <item><title>B</title><link>https://example.com/b</link><guid>b</guid><pubDate>Fri, 12 Jun 2026 09:00:00 GMT</pubDate></item>
        <item><title>C</title><link>https://example.com/c</link><guid>c</guid><pubDate>Fri, 10 Jun 2020 09:00:00 GMT</pubDate></item>
      </channel>
    </rss>
    """.strip()

    original_urlopen = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"]).urlopen
    runtime_module = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"])

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return xml_text.encode("utf-8")

    runtime_module.urlopen = lambda *args, **kwargs: _Response()  # noqa: ARG005
    try:
        adapter = _FakeAdapter(source="rss", adapter_name="rss", feed_url="https://example.com/feed", stream_key="rss")
        batch = adapter.fetch(RssFetchRequest(lookback_hours=48, limit=2))
    finally:
        runtime_module.urlopen = original_urlopen

    assert len(batch.items) == 2
    assert [item.external_id for item in batch.items] == ["a", "b"]


def test_rss_fetcher_returns_zero_items_for_empty_feed():
    xml_text = """
    <rss>
      <channel>
        <title>Empty Feed</title>
      </channel>
    </rss>
    """.strip()

    original_urlopen = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"]).urlopen
    runtime_module = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"])

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return xml_text.encode("utf-8")

    runtime_module.urlopen = lambda *args, **kwargs: _Response()  # noqa: ARG005
    try:
        fetcher = RssFetcher(
            feed_url="https://example.com/empty-feed",
            source_name="Empty Feed",
            stream_key="rss-empty",
        )
        items = asyncio.run(
            fetcher.fetch(
                request=type(
                    "Request",
                    (),
                    {"source_name": "Empty Feed", "lookback_hours": 24, "limit": 20, "cursor": None, "options": {}},
                )()
            )
        )
    finally:
        runtime_module.urlopen = original_urlopen

    assert items == []


def test_fetch_service_returns_zero_items_for_empty_rss_feed():
    _reset_repo_state()
    db = _create_session()
    subscription = _create_subscription(db, "rss", "Empty Feed", "rss-empty")

    original_urlopen = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"]).urlopen
    runtime_module = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"])
    xml_text = "<rss><channel><title>Empty Feed</title></channel></rss>"

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return xml_text.encode("utf-8")

    runtime_module.urlopen = lambda *args, **kwargs: _Response()  # noqa: ARG005
    try:
        service = FetchService(db, _RepoNamespace)
        result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-empty", sources=["rss"])))
    finally:
        runtime_module.urlopen = original_urlopen

    db.refresh(subscription)
    assert result.items == []
    assert result.errors == []
    assert result.stats.total_fetched == 0
    assert result.stats.total_inserted == 0
    assert subscription.last_cursor is None
    assert _RepoNamespace.last_cursor_updates == []


def test_fetch_service_collects_rss_parse_error_in_errors():
    _reset_repo_state()
    db = _create_session()
    _create_subscription(db, "rss", "Broken Feed", "rss-broken")

    original_urlopen = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"]).urlopen
    runtime_module = __import__("apps.fetcher_engine.runtime.rss", fromlist=["urlopen"])

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self):
            return b"<rss><channel><item></rss>"

    runtime_module.urlopen = lambda *args, **kwargs: _Response()  # noqa: ARG005
    try:
        service = FetchService(db, _RepoNamespace)
        result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-broken", sources=["rss"])))
    finally:
        runtime_module.urlopen = original_urlopen

    assert result.items == []
    assert len(result.errors) == 1
    assert result.errors[0].source == "rss"
    assert "invalid rss payload" in result.errors[0].error
    assert result.stats.total_fetched == 0
