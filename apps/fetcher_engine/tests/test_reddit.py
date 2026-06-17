from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.reddit.fetcher import RedditFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "Reddit", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


def test_reddit_fetcher_maps_posts_into_source_items() -> None:
    fetcher = RedditFetcher(subreddit="artificial", sort="hot")
    fetcher._fetch_posts_payload = lambda request_limit: {  # noqa: ARG005
        "data": {
            "children": [
                {
                    "data": {
                        "name": "t3_abc123",
                        "title": "Interesting thread",
                        "selftext": "A" * 800,
                        "permalink": "/r/artificial/comments/abc123/thread/",
                        "created_utc": 1710000000,
                        "subreddit": "artificial",
                        "author": "alice",
                        "score": 123,
                        "num_comments": 45,
                        "ups": 120,
                        "url": "https://example.com/thread",
                    }
                }
            ]
        }
    }

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    assert items[0].source_id == "t3_abc123"
    assert len(items[0].raw_content or "") == 500


def test_reddit_fetcher_skips_invalid_payload_item() -> None:
    fetcher = RedditFetcher(subreddit="artificial")
    fetcher._fetch_posts_payload = lambda request_limit: {  # noqa: ARG005
        "data": {"children": [{"data": {"title": "missing id"}}]}
    }

    items = asyncio.run(fetcher.fetch(_request(limit=5)))

    assert items == []


def test_reddit_fetcher_returns_empty_on_runtime_error() -> None:
    fetcher = RedditFetcher(subreddit="missing")
    fetcher._fetch_posts_payload = lambda request_limit: (_ for _ in ()).throw(RuntimeError("reddit subreddit not found"))  # noqa: ARG005

    items = asyncio.run(fetcher.fetch(_request(limit=5)))

    assert items == []
