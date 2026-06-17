from __future__ import annotations

import asyncio

from apps.fetcher_engine.connectors.github_trending.fetcher import GitHubTrendingFetcher


def _request(limit: int = 10):
    return type(
        "Request",
        (),
        {"source_name": "GitHub Trending", "lookback_hours": 24, "limit": limit, "cursor": None, "options": {}},
    )()


def test_github_trending_fetcher_parses_repository_cards() -> None:
    html_text = """
    <article class="Box-row">
      <h2><a href="/openai/openai-python"> openai / openai-python </a></h2>
      <p class="col-9 color-fg-muted my-1 pr-4">Official Python library.</p>
      <div>
        <span itemprop="programmingLanguage">Python</span>
        <a href="/openai/openai-python">12,345</a>
        <a href="/openai/openai-python/forks">1,234</a>
      </div>
    </article>
    """.strip()

    repositories = GitHubTrendingFetcher(language="python")._parse_trending_repositories(html_text)

    assert len(repositories) == 1
    assert repositories[0].full_name == "openai/openai-python"
    assert repositories[0].stars == "12,345"


def test_github_trending_fetcher_returns_source_items() -> None:
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

    items = asyncio.run(fetcher.fetch(_request()))

    assert len(items) == 1
    assert items[0].source_id == "owner/repo"
    assert items[0].metadata["since"] == "weekly"


def test_github_trending_fetcher_returns_empty_on_network_error() -> None:
    fetcher = GitHubTrendingFetcher()
    fetcher._fetch_trending_page = lambda: (_ for _ in ()).throw(RuntimeError("network error"))

    items = asyncio.run(fetcher.fetch(_request(limit=5)))

    assert items == []
