from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.fetcher_engine.runtime.base import BaseFetcher
from apps.workflow_engine.registry.contracts import FetchRequest, SourceItem


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TrendingRepository:
    full_name: str
    url: str
    summary: str | None
    language: str | None
    stars: str | None
    forks: str | None


class _TrendingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.repositories: list[TrendingRepository] = []
        self._in_article = False
        self._heading_depth = 0
        self._capture_repo = False
        self._capture_description = False
        self._capture_language = False
        self._capture_star = False
        self._capture_fork = False
        self._current_href: str | None = None
        self._current_full_name_parts: list[str] = []
        self._current_description_parts: list[str] = []
        self._current_language_parts: list[str] = []
        self._current_star_parts: list[str] = []
        self._current_fork_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        class_name = attrs_map.get("class", "") or ""

        if tag == "article" and "Box-row" in class_name:
            self._in_article = True
            self._heading_depth = 0
            self._current_href = None
            self._current_full_name_parts = []
            self._current_description_parts = []
            self._current_language_parts = []
            self._current_star_parts = []
            self._current_fork_parts = []
            return

        if not self._in_article:
            return

        if tag in {"h1", "h2"}:
            self._heading_depth += 1
            return

        if tag == "a" and "/login?return_to=" not in (attrs_map.get("href") or ""):
            href = attrs_map.get("href")
            if self._heading_depth > 0 and href and href.count("/") == 2 and href.startswith("/"):
                self._capture_repo = True
                self._current_href = href
                return

        if tag == "p" and "col-9" in class_name:
            self._capture_description = True
            return

        if tag == "span" and "itemprop" in attrs_map and attrs_map["itemprop"] == "programmingLanguage":
            self._capture_language = True
            return

        if tag == "a":
            href = attrs_map.get("href") or ""
            if self._current_href and href == self._current_href:
                self._capture_star = True
                return
            if self._current_href and href == f"{self._current_href}/forks":
                self._capture_fork = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self._in_article:
            self._in_article = False
            self._heading_depth = 0
            if self._current_href and self._current_full_name_parts:
                full_name = "".join(self._current_full_name_parts).replace(" ", "").strip()
                summary = " ".join(part.strip() for part in self._current_description_parts if part.strip()) or None
                language = " ".join(part.strip() for part in self._current_language_parts if part.strip()) or None
                stars = "".join(part.strip() for part in self._current_star_parts if part.strip()) or None
                forks = "".join(part.strip() for part in self._current_fork_parts if part.strip()) or None
                self.repositories.append(
                    TrendingRepository(
                        full_name=full_name,
                        url=f"https://github.com{self._current_href}",
                        summary=summary,
                        language=language,
                        stars=stars,
                        forks=forks,
                    )
                )
            return

        if tag in {"h1", "h2"} and self._heading_depth > 0:
            self._heading_depth -= 1

        if tag == "a":
            self._capture_repo = False
            self._capture_star = False
            self._capture_fork = False
        elif tag == "p":
            self._capture_description = False
        elif tag == "span":
            self._capture_language = False

    def handle_data(self, data: str) -> None:
        if not self._in_article:
            return
        if self._capture_repo:
            self._current_full_name_parts.append(data)
        elif self._capture_description:
            self._current_description_parts.append(data)
        elif self._capture_language:
            self._current_language_parts.append(data)
        elif self._capture_star:
            self._current_star_parts.append(data)
        elif self._capture_fork:
            self._current_fork_parts.append(data)


class GitHubTrendingFetcher(BaseFetcher):
    name = "github_trending"
    source_type = "github_trending"
    user_agent = "content-hub-fetcher/1.0"

    def __init__(self, language: str = "", since: str = "daily", spoken_language: str = "", stream_key: str = "") -> None:
        self.language = language
        self.since = since
        self.spoken_language = spoken_language
        self.stream_key = stream_key or "github_trending:default"

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        try:
            html_text = self._fetch_trending_page()
        except (RuntimeError, ValueError):
            return []

        repositories = self._parse_trending_repositories(html_text)
        items = repositories[: request.limit] if request.limit > 0 else repositories
        published_at = _utc_now().isoformat()
        return [
            SourceItem(
                source_type=self.source_type,
                source_id=repo.full_name,
                title=repo.full_name,
                source_url=repo.url,
                raw_content=repo.summary,
                metadata={
                    "published_at": published_at,
                    "stars": repo.stars,
                    "language": repo.language,
                    "forks": repo.forks,
                    "since": self.since,
                    "spoken_language": self.spoken_language,
                    "stream_key": self.stream_key,
                },
            )
            for repo in items
        ]

    def _fetch_trending_page(self) -> str:
        query = urlencode(
            {
                key: value
                for key, value in {
                    "since": self.since,
                    "language": self.language,
                    "spoken_language_code": self.spoken_language,
                }.items()
                if value
            }
        )
        url = "https://github.com/trending"
        if query:
            url = f"{url}?{query}"
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as error:
            raise RuntimeError(f"github trending http error: {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"github trending network error: {error.reason}") from error
        except TimeoutError as error:
            raise RuntimeError("github trending request timeout") from error

    def _parse_trending_repositories(self, html_text: str) -> list[TrendingRepository]:
        parser = _TrendingHTMLParser()
        parser.feed(html_text)
        return parser.repositories
