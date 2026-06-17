from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from apps.fetcher_engine.api.models import FetchBatchRequest
from apps.fetcher_engine.api.registry import FETCHER_REGISTRY
from apps.fetcher_engine.api.service import FetchService
from apps.fetcher_engine.connectors.bilibili.fetcher import BilibiliFetcher
from apps.fetcher_engine.connectors.cnblogs.fetcher import CNBlogsFetcher
from apps.fetcher_engine.connectors.github_trending.fetcher import GitHubTrendingFetcher
from apps.fetcher_engine.connectors.reddit.fetcher import RedditFetcher
from apps.fetcher_engine.connectors.rss.fetcher import RssFetcher
from apps.fetcher_engine.runtime.rss import MediaAsset, ParseError, RssFeedAdapter, RssFetchRequest, UnifiedPost, parse_rss_items
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
    assert result.stats.sources_succeeded == 1
    assert result.stats.sources_failed == 0
    assert len(result.items) == 1
    assert result.matched_items == [
        {
            "source_type": "cnblogs",
            "source_id": "post-1",
            "source_url": "https://example.com/1",
            "title": "First Post",
        }
    ]
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
    assert result.stats.sources_succeeded == 1
    assert result.stats.sources_failed == 1
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
    assert result.matched_items == [
        {
            "source_type": "cnblogs",
            "source_id": "post-1",
            "source_url": "https://example.com/1",
            "title": "Duplicate Post",
        }
    ]
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
    cursor_payload = json.loads(subscription.last_cursor)
    assert cursor_payload["external_id"] == "item-1"
    assert cursor_payload["published_at"] == "2026-06-12T10:00:00+00:00"
    assert "fetched_at" in cursor_payload
    stored_payload = json.loads(_RepoNamespace.last_cursor_updates[0][1])
    assert _RepoNamespace.last_cursor_updates[0][0] == subscription.id
    assert stored_payload["external_id"] == "item-1"
    assert stored_payload["published_at"] == "2026-06-12T10:00:00+00:00"


def test_fetch_service_second_run_skips_items_before_cursor():
    _reset_repo_state()
    db = _create_session()
    subscription = _create_subscription(db, "rss", "Example Feed", "rss-default")
    FETCHER_REGISTRY["rss"] = lambda **kwargs: _FakeFetcher(  # noqa: ARG005
        items=[
            SourceItem(
                source_type="rss",
                source_id="item-2",
                title="RSS Item 2",
                source_url="https://example.com/rss-2",
                raw_content="rss-summary-2",
                metadata={"published_at": "2026-06-12T11:00:00+00:00"},
            ),
            SourceItem(
                source_type="rss",
                source_id="item-1",
                title="RSS Item 1",
                source_url="https://example.com/rss-1",
                raw_content="rss-summary-1",
                metadata={"published_at": "2026-06-12T10:00:00+00:00"},
            ),
        ]
    )
    service = FetchService(db, _RepoNamespace)

    first_result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-cursor-1", sources=["rss"])))
    db.refresh(subscription)
    second_result = asyncio.run(service.run_sources(FetchBatchRequest(run_id="run-cursor-2", sources=["rss"])))

    assert first_result.stats.total_inserted == 2
    assert second_result.stats.total_fetched == 0
    assert second_result.stats.total_inserted == 0
    assert second_result.stats.total_deduped == 0
    assert second_result.stats.sources_succeeded == 1
    assert second_result.stats.sources_failed == 0
    assert db.query(ContentItem).count() == 2
    cursor_payload = json.loads(subscription.last_cursor)
    assert cursor_payload["external_id"] == "item-2"


def test_fetch_service_passes_lookback_when_cursor_is_missing():
    _reset_repo_state()
    db = _create_session()
    _create_subscription(db, "reddit", "Reddit", "artificial")
    captured_request: dict[str, object] = {}

    class _InspectingFetcher:
        async def fetch(self, request):  # noqa: ANN001
            captured_request["lookback_hours"] = request.lookback_hours
            captured_request["cursor"] = request.cursor
            return []

    FETCHER_REGISTRY["reddit"] = lambda **kwargs: _InspectingFetcher()  # noqa: ARG005
    service = FetchService(db, _RepoNamespace)

    result = asyncio.run(
        service.run_sources(FetchBatchRequest(run_id="run-lookback", sources=["reddit"], lookback_hours=72))
    )

    assert result.stats.total_fetched == 0
    assert captured_request == {"lookback_hours": 72, "cursor": None}


def test_fetch_service_uses_repo_load_subscriptions_when_available():
    _reset_repo_state()
    db = _create_session()
    captured = {"called": False}

    class _CustomRepo(_RepoNamespace):
        @staticmethod
        def load_subscriptions(_db: Session, *, sources: list[str], subscription_ids: list[int]):  # noqa: ANN001
            captured["called"] = True
            assert sources == ["reddit"]
            assert subscription_ids == [99]
            return [
                SourceSubscription(
                    id=99,
                    source_type="reddit",
                    source_name="Reddit",
                    account_identifier="python",
                    enabled=True,
                    default_tags="python,ai",
                    last_cursor=None,
                )
            ]

    FETCHER_REGISTRY["reddit"] = lambda **kwargs: _FakeFetcher(items=[])  # noqa: ARG005
    service = FetchService(db, _CustomRepo)

    result = asyncio.run(
        service.run_sources(
            FetchBatchRequest(run_id="run-load-subscriptions", sources=["reddit"], subscription_ids=[99])
        )
    )

    assert captured["called"] is True
    assert result.stats.sources_succeeded == 1


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

    recent_a = datetime.now(timezone.utc)
    recent_b = recent_a - timedelta(hours=1)
    stale = recent_a - timedelta(days=365 * 3)
    xml_text = """
    <rss>
      <channel>
        <item><title>A</title><link>https://example.com/a</link><guid>a</guid><pubDate>{recent_a}</pubDate></item>
        <item><title>B</title><link>https://example.com/b</link><guid>b</guid><pubDate>{recent_b}</pubDate></item>
        <item><title>C</title><link>https://example.com/c</link><guid>c</guid><pubDate>{stale}</pubDate></item>
      </channel>
    </rss>
    """.strip().format(
        recent_a=recent_a.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        recent_b=recent_b.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        stale=stale.strftime("%a, %d %b %Y %H:%M:%S GMT"),
    )

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
    assert result.stats.sources_succeeded == 0
    assert result.stats.sources_failed == 1


def test_github_trending_fetcher_is_registered():
    FETCHER_REGISTRY["github_trending"] = GitHubTrendingFetcher

    assert FETCHER_REGISTRY["github_trending"] is GitHubTrendingFetcher


def test_github_trending_fetcher_parses_repositories():
    html_text = """
    <article class="Box-row">
      <h2>
        <a href="/openai/openai-python">
          openai / openai-python
        </a>
      </h2>
      <p class="col-9 color-fg-muted my-1 pr-4">
        Official Python library for the OpenAI API.
      </p>
      <div>
        <span itemprop="programmingLanguage">Python</span>
        <a href="/openai/openai-python">12,345</a>
        <a href="/openai/openai-python/forks">1,234</a>
      </div>
    </article>
    """.strip()

    fetcher = GitHubTrendingFetcher(language="python", since="daily")
    repositories = fetcher._parse_trending_repositories(html_text)

    assert len(repositories) == 1
    assert repositories[0].full_name == "openai/openai-python"
    assert repositories[0].url == "https://github.com/openai/openai-python"
    assert repositories[0].summary == "Official Python library for the OpenAI API."
    assert repositories[0].language == "Python"
    assert repositories[0].stars == "12,345"
    assert repositories[0].forks == "1,234"


def test_github_trending_fetcher_returns_source_items():
    fetcher = GitHubTrendingFetcher(language="python", since="weekly")
    fetcher._fetch_trending_page = lambda: """
    <article class="Box-row">
      <h2><a href="/owner/repo"> owner / repo </a></h2>
      <p class="col-9 color-fg-muted my-1 pr-4">Trending repository</p>
      <div>
        <span itemprop="programmingLanguage">Python</span>
        <a href="/owner/repo">100</a>
        <a href="/owner/repo/forks">20</a>
      </div>
    </article>
    """.strip()

    items = asyncio.run(
        fetcher.fetch(
            type(
                "Request",
                (),
                {"source_name": "GitHub Trending", "lookback_hours": 24, "limit": 10, "cursor": None, "options": {}},
            )()
        )
    )

    assert len(items) == 1
    assert items[0].source_id == "owner/repo"
    assert items[0].title == "owner/repo"
    assert items[0].source_url == "https://github.com/owner/repo"
    assert items[0].raw_content == "Trending repository"
    assert items[0].metadata["language"] == "Python"
    assert items[0].metadata["stars"] == "100"
    assert items[0].metadata["forks"] == "20"
    assert items[0].metadata["since"] == "weekly"


def test_github_trending_fetcher_returns_empty_list_on_network_error():
    fetcher = GitHubTrendingFetcher()
    fetcher._fetch_trending_page = lambda: (_ for _ in ()).throw(RuntimeError("network error"))

    items = asyncio.run(
        fetcher.fetch(
            type(
                "Request",
                (),
                {"source_name": "GitHub Trending", "lookback_hours": 24, "limit": 10, "cursor": None, "options": {}},
            )()
        )
    )

    assert items == []


def test_reddit_fetcher_is_registered():
    FETCHER_REGISTRY["reddit"] = RedditFetcher

    assert FETCHER_REGISTRY["reddit"] is RedditFetcher


def test_reddit_fetcher_returns_source_items():
    fetcher = RedditFetcher(subreddit="artificial", sort="hot", stream_key="reddit:artificial")
    fetcher._fetch_posts_payload = lambda request_limit: {  # noqa: ARG005
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_abc123",
                        "title": "Interesting research thread",
                        "selftext": "A" * 800,
                        "permalink": "/r/artificial/comments/abc123/interesting_research_thread/",
                        "created_utc": 1710000000,
                        "subreddit": "artificial",
                        "author": "alice",
                        "score": 123,
                        "num_comments": 45,
                        "ups": 120,
                        "url": "https://example.com/research",
                    }
                }
            ]
        }
    }

    items = asyncio.run(
        fetcher.fetch(
            type(
                "Request",
                (),
                {"source_name": "Reddit", "lookback_hours": 24, "limit": 10, "cursor": None, "options": {}},
            )()
        )
    )

    assert len(items) == 1
    assert items[0].source_id == "t3_abc123"
    assert items[0].title == "Interesting research thread"
    assert items[0].source_url == "https://www.reddit.com/r/artificial/comments/abc123/interesting_research_thread/"
    assert items[0].raw_content == "A" * 500
    assert items[0].metadata["subreddit"] == "artificial"
    assert items[0].metadata["author"] == "alice"
    assert items[0].metadata["score"] == 123
    assert items[0].metadata["num_comments"] == 45
    assert items[0].metadata["ups"] == 120


def test_reddit_fetcher_uses_post_id_as_source_id():
    fetcher = RedditFetcher(subreddit="MachineLearning", sort="hot")
    fetcher._fetch_posts_payload = lambda request_limit: {  # noqa: ARG005
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_ml001",
                        "title": "ML post",
                        "selftext": "",
                        "permalink": "/r/MachineLearning/comments/ml001/ml_post/",
                        "created_utc": 1710001000,
                        "subreddit": "MachineLearning",
                        "author": "bob",
                        "score": 50,
                        "num_comments": 8,
                        "ups": 49,
                        "url": "https://example.com/ml-post",
                    }
                }
            ]
        }
    }

    items = asyncio.run(
        fetcher.fetch(
            type(
                "Request",
                (),
                {"source_name": "Reddit", "lookback_hours": 24, "limit": 5, "cursor": None, "options": {}},
            )()
        )
    )

    assert len(items) == 1
    assert items[0].source_id == "t3_ml001"
    assert items[0].metadata["subreddit"] == "MachineLearning"


def test_reddit_fetcher_returns_empty_list_on_404_or_network_error():
    fetcher = RedditFetcher(subreddit="missing")
    fetcher._fetch_posts_payload = lambda request_limit: (_ for _ in ()).throw(RuntimeError("reddit subreddit not found"))  # noqa: ARG005

    items = asyncio.run(
        fetcher.fetch(
            type(
                "Request",
                (),
                {"source_name": "Reddit", "lookback_hours": 24, "limit": 5, "cursor": None, "options": {}},
            )()
        )
    )

    assert items == []


def test_reddit_fetcher_supports_artificial_and_machinelearning_samples():
    artificial_fetcher = RedditFetcher(subreddit="artificial")
    machine_learning_fetcher = RedditFetcher(subreddit="MachineLearning")

    assert artificial_fetcher._build_url(10) == "https://www.reddit.com/r/artificial/hot.json?limit=10"
    assert machine_learning_fetcher._build_url(20) == "https://www.reddit.com/r/MachineLearning/hot.json?limit=20"


def test_cnblogs_fetcher_fills_required_fields():
    fetcher = CNBlogsFetcher(feed_url="https://example.com/cnblogs.xml")
    published_at = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    original_fetch = RssFeedAdapter.fetch

    class _Batch:
        def __init__(self):
            self.items = (
                UnifiedPost(
                    source="cnblogs",
                    adapter="cnblogs_rss",
                    external_id="post-1",
                    title="CNBlogs Post",
                    url="https://www.cnblogs.com/example/p/1.html",
                    published_at=published_at,
                    summary="S" * 400,
                    media=(),
                    raw={
                        "author": "example-author",
                        "category": "Python",
                        "view_count": 321,
                    },
                ),
            )

    RssFeedAdapter.fetch = lambda self, request=None, cursor_store=None: _Batch()  # noqa: ARG005
    try:
        items = asyncio.run(
            fetcher.fetch(
                type(
                    "Request",
                    (),
                    {"source_name": "CNBlogs", "lookback_hours": 24, "limit": 10, "cursor": None, "options": {}},
                )()
            )
        )
    finally:
        RssFeedAdapter.fetch = original_fetch

    assert len(items) == 1
    assert items[0].source_url == "https://www.cnblogs.com/example/p/1.html"
    assert items[0].raw_content == "S" * 300
    assert items[0].metadata["source_account"] == "example-author"
    assert items[0].metadata["published_at"] == published_at.isoformat()
    assert items[0].metadata["summary"] == "S" * 300
    assert items[0].metadata["url"] == "https://www.cnblogs.com/example/p/1.html"
    assert items[0].metadata["author"] == "example-author"
    assert items[0].metadata["category"] == "Python"
    assert items[0].metadata["view_count"] == 321


def test_bilibili_fetcher_fills_required_fields():
    fetcher = BilibiliFetcher(feed_url="https://example.com/bilibili.xml")
    published_at = datetime(2026, 6, 12, 11, 0, tzinfo=timezone.utc)
    original_fetch = RssFeedAdapter.fetch

    class _Batch:
        def __init__(self):
            self.items = (
                UnifiedPost(
                    source="bilibili",
                    adapter="bilibili_rss",
                    external_id="video-1",
                    title="Bilibili Video",
                    url="https://rsshub.app/bilibili/video/BV1xx411c7mD",
                    published_at=published_at,
                    summary="Video intro",
                    media=(MediaAsset(url="https://example.com/cover.jpg"),),
                    raw={
                        "author": "up-master",
                        "play_count": 12345,
                        "danmaku_count": 67,
                        "duration": "12:34",
                        "bvid": "BV1xx411c7mD",
                    },
                ),
            )

    RssFeedAdapter.fetch = lambda self, request=None, cursor_store=None: _Batch()  # noqa: ARG005
    try:
        items = asyncio.run(
            fetcher.fetch(
                type(
                    "Request",
                    (),
                    {"source_name": "Bilibili", "lookback_hours": 24, "limit": 10, "cursor": None, "options": {}},
                )()
            )
        )
    finally:
        RssFeedAdapter.fetch = original_fetch

    assert len(items) == 1
    assert items[0].source_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert items[0].raw_content == "Video intro"
    assert items[0].metadata["source_account"] == "up-master"
    assert items[0].metadata["published_at"] == published_at.isoformat()
    assert items[0].metadata["summary"] == "Video intro"
    assert items[0].metadata["url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert items[0].metadata["author"] == "up-master"
    assert items[0].metadata["play_count"] == 12345
    assert items[0].metadata["danmaku_count"] == 67
    assert items[0].metadata["duration"] == "12:34"
    assert items[0].metadata["cover_url"] == "https://example.com/cover.jpg"
