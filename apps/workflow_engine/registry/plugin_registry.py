from __future__ import annotations

from dataclasses import dataclass, field

from workflow_engine.registry.contracts import Fetcher, Processor, Publisher


@dataclass(slots=True)
class PluginRegistry:
    fetchers: dict[str, Fetcher] = field(default_factory=dict)
    processors: dict[str, Processor] = field(default_factory=dict)
    publishers: dict[str, Publisher] = field(default_factory=dict)

    def register_fetcher(self, fetcher: Fetcher) -> None:
        self.fetchers[fetcher.name] = fetcher

    def register_processor(self, processor: Processor) -> None:
        self.processors[processor.name] = processor

    def register_publisher(self, publisher: Publisher) -> None:
        self.publishers[publisher.name] = publisher

    def get_fetcher(self, name: str) -> Fetcher:
        return self.fetchers[name]

    def get_processor(self, name: str) -> Processor:
        return self.processors[name]

    def get_publisher(self, name: str) -> Publisher:
        return self.publishers[name]

    def snapshot(self) -> dict[str, list[str]]:
        return {
            "fetchers": sorted(self.fetchers.keys()),
            "processors": sorted(self.processors.keys()),
            "publishers": sorted(self.publishers.keys()),
        }
