from __future__ import annotations

from apps.workflow_engine.registry.contracts import FetchRequest, Fetcher, SourceItem


class BaseFetcher(Fetcher):
    name = "base"

    async def fetch(self, request: FetchRequest) -> list[SourceItem]:
        raise NotImplementedError
