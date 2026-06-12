from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.fetcher_engine.connectors.bilibili.fetcher import BilibiliFetcher
from apps.fetcher_engine.connectors.cnblogs.fetcher import CNBlogsFetcher
from apps.fetcher_engine.connectors.rss.fetcher import RssFetcher


FetcherFactory = Callable[..., Any]

FETCHER_REGISTRY: dict[str, FetcherFactory] = {}


def register_fetcher(source_type: str, fetcher_factory: FetcherFactory) -> None:
    FETCHER_REGISTRY[source_type] = fetcher_factory


def get_fetcher(source_type: str) -> FetcherFactory | None:
    return FETCHER_REGISTRY.get(source_type)


register_fetcher("cnblogs", CNBlogsFetcher)
register_fetcher("bilibili", BilibiliFetcher)
register_fetcher("rss", RssFetcher)
